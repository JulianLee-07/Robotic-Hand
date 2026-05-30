"""
This file contains the computer vision controller for the robotic hand

It tracks a human hand with MediaPipe, estimates finger openness from joint
angles, maps those scores to calibrated servo pulse values, and sends
commands to an Arduino over serial
"""

import math
import time
from typing import Optional

import cv2
import mediapipe as mp
import serial

# Connection settings
# Run ls /dev/cu.* in your terminal to find the correct port
# Ensure BAUD_RATE matches the baud rate in your Arduino code
PORT = "/dev/cu.usbmodem3101"
BAUD_RATE = 115200
CAMERA_INDEX = 1

# Servo config
# Ensure channels match your wiring in PCA9685 and Arduino code
# Use servo_calibration.py to find the correct open/closed pulse values for your hand
SERVO_CONFIG = {
    "thumb_rotation": {
        "channel": 0,
        "open_pulse": 500,
        "closed_pulse": 1050,
    },
    "thumb_curl": {
        "channel": 1,
        "open_pulse": 2000,
        "closed_pulse": 650,
    },
    "index": {
        "channel": 2,
        "open_pulse": 770,
        "closed_pulse": 1970,
    },
    "middle": {
        "channel": 3,
        "open_pulse": 1090,
        "closed_pulse": 2460,
    },
    "ring": {
        "channel": 4,
        "open_pulse": 770,
        "closed_pulse": 1970,
    },
    "pinky": {
        "channel": 5,
        "open_pulse": 900,
        "closed_pulse": 2150,
    },
}

# Vision settings
FINGER_CLOSED_ANGLE = 65.0
FINGER_OPEN_ANGLE = 175.0

THUMB_CLOSED_ANGLE = 80.0
THUMB_OPEN_ANGLE = 175.0

SMOOTHING = 0.45
MAX_PULSE_CHANGE_PER_UPDATE = 80
SEND_INTERVAL_SECONDS = 0.03

THUMB_OBSERVED_CLOSED_SCORE = 0.4
THUMB_OBSERVED_OPEN_SCORE = 1.00

# Landmarks
FINGER_MCP = {
    "index": 5,
    "middle": 9,
    "ring": 13,
    "pinky": 17,
}

FINGER_PIP = {
    "index": 6,
    "middle": 10,
    "ring": 14,
    "pinky": 18,
}

FINGER_TIP = {
    "index": 8,
    "middle": 12,
    "ring": 16,
    "pinky": 20,
}

THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def map_range(
    value: float,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
) -> float:
    value = clamp(value, in_min, in_max)
    ratio = (value - in_min) / (in_max - in_min)
    return out_min + ratio * (out_max - out_min)


def landmark_to_tuple(landmark) -> tuple[float, float, float]:
    return landmark.x, landmark.y, landmark.z


def vector_from_to(a, b) -> tuple[float, float, float]:
    return b[0] - a[0], b[1] - a[1], b[2] - a[2]


def vector_magnitude(v) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def angle_between_vectors(v1, v2) -> float:
    mag1 = vector_magnitude(v1)
    mag2 = vector_magnitude(v2)

    if mag1 == 0 or mag2 == 0:
        return 0.0

    dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    cosine = clamp(dot / (mag1 * mag2), -1.0, 1.0)

    return math.degrees(math.acos(cosine))


def joint_angle(a, b, c) -> float:
    """
    Returns angle ABC in degrees.
    b is the middle joint.
    """
    ba = vector_from_to(b, a)
    bc = vector_from_to(b, c)
    return angle_between_vectors(ba, bc)


def score_to_pulse(servo_name: str, open_score: float) -> int:
    """
    open_score:
      1.0 = fully open
      0.0 = fully closed
    """
    config = SERVO_CONFIG[servo_name]

    open_pulse = config["open_pulse"]
    closed_pulse = config["closed_pulse"]

    pulse = closed_pulse + (open_pulse - closed_pulse) * open_score
    return int(round(pulse))


def limit_pulse_change(previous: Optional[int], desired: int) -> int:
    if previous is None:
        return desired

    difference = desired - previous

    if abs(difference) <= MAX_PULSE_CHANGE_PER_UPDATE:
        return desired

    if difference > 0:
        return previous + MAX_PULSE_CHANGE_PER_UPDATE

    return previous - MAX_PULSE_CHANGE_PER_UPDATE


def send_servo_command(arduino, channel: int, pulse: int) -> None:
    command = f"{channel} {pulse}\n"
    arduino.write(command.encode("utf-8"))


def get_finger_open_scores(hand_landmarks) -> dict[str, float]:
    landmarks = hand_landmarks.landmark
    scores = {}

    for finger in ["index", "middle", "ring", "pinky"]:
        mcp = landmark_to_tuple(landmarks[FINGER_MCP[finger]])
        pip = landmark_to_tuple(landmarks[FINGER_PIP[finger]])
        tip = landmark_to_tuple(landmarks[FINGER_TIP[finger]])

        angle = joint_angle(mcp, pip, tip)

        # Closed finger = lower angle
        # Open finger = higher angle
        open_score = map_range(
            angle,
            FINGER_CLOSED_ANGLE,
            FINGER_OPEN_ANGLE,
            0.0,
            1.0,
        )

        scores[finger] = open_score

    return scores


def get_thumb_open_score(hand_landmarks) -> float:
    landmarks = hand_landmarks.landmark

    thumb_cmc = landmark_to_tuple(landmarks[THUMB_CMC])
    thumb_mcp = landmark_to_tuple(landmarks[THUMB_MCP])
    thumb_ip = landmark_to_tuple(landmarks[THUMB_IP])
    thumb_tip = landmark_to_tuple(landmarks[THUMB_TIP])

    thumb_mcp_angle = joint_angle(thumb_cmc, thumb_mcp, thumb_ip)
    thumb_ip_angle = joint_angle(thumb_mcp, thumb_ip, thumb_tip)

    average_thumb_angle = (thumb_mcp_angle + thumb_ip_angle) / 2.0

    thumb_open_score = map_range(
        average_thumb_angle,
        THUMB_CLOSED_ANGLE,
        THUMB_OPEN_ANGLE,
        0.0,
        1.0,
    )

    return thumb_open_score


def draw_text(frame, text: str, y: int) -> None:
    cv2.putText(
        frame,
        text,
        (20, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (255, 255, 255),
        2,
    )


def draw_scores(frame, scores: dict[str, float]) -> None:
    y = 40

    draw_text(frame, "Open score: 0.00 = closed, 1.00 = open", y)
    y += 35

    for name in ["thumb", "index", "middle", "ring", "pinky"]:
        score = scores.get(name, 0.0)
        text = f"{name}: {score:.2f}"
        draw_text(frame, text, y)
        y += 35


def open_all_servos(arduino) -> None:
    for config in SERVO_CONFIG.values():
        send_servo_command(arduino, config["channel"], config["open_pulse"])


def calibrate_thumb_score(raw_thumb_score: float) -> float:
    """
    Remaps the thumb score from the camera's actual observed range
    into the full 0.00–1.00 servo control range.

    Example:
      raw score 0.30 -> calibrated score 0.00
      raw score 1.00 -> calibrated score 1.00
    """
    return map_range(
        raw_thumb_score,
        THUMB_OBSERVED_CLOSED_SCORE,
        THUMB_OBSERVED_OPEN_SCORE,
        0.0,
        1.0,
    )


def main() -> None:
    arduino = None
    camera = None

    try:
        print("Opening Arduino serial connection...")
        arduino = serial.Serial(PORT, BAUD_RATE, timeout=1)
        time.sleep(2)

        print("Opening camera...")
        camera = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_AVFOUNDATION)

        if not camera.isOpened():
            raise RuntimeError(
                f"Could not open webcam at index {CAMERA_INDEX}. "
                "Try changing CAMERA_INDEX to 0, 1, or 2."
            )

        time.sleep(1)

        for _ in range(10):
            success, _ = camera.read()
            if success:
                break
            time.sleep(0.1)

        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils

        smoothed_scores = {
            "thumb": 0.5,
            "index": 0.5,
            "middle": 0.5,
            "ring": 0.5,
            "pinky": 0.5,
        }

        last_sent_pulses = {}
        last_send_time = 0

        with mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        ) as hands:
            print("Vision servo control started.")
            print("Press q to quit.")
            print("Press c to open all servos.")

            while True:
                success, frame = camera.read()
                if not success:
                    print("Failed to read frame.")
                    break

                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                results = hands.process(rgb_frame)

                if results.multi_hand_landmarks:
                    hand_landmarks = results.multi_hand_landmarks[0]

                    finger_scores = get_finger_open_scores(hand_landmarks)
                    thumb_score = get_thumb_open_score(hand_landmarks)
                    thumb_score = calibrate_thumb_score(thumb_score)

                    raw_scores = {
                        "thumb": thumb_score,
                        **finger_scores,
                    }

                    for name, raw_score in raw_scores.items():
                        smoothed_scores[name] = (
                            SMOOTHING * smoothed_scores[name]
                            + (1.0 - SMOOTHING) * raw_score
                        )

                    desired_pulses = {
                        "thumb_rotation": score_to_pulse(
                            "thumb_rotation",
                            smoothed_scores["thumb"],
                        ),
                        "thumb_curl": score_to_pulse(
                            "thumb_curl",
                            smoothed_scores["thumb"],
                        ),
                        "index": score_to_pulse("index", smoothed_scores["index"]),
                        "middle": score_to_pulse("middle", smoothed_scores["middle"]),
                        "ring": score_to_pulse("ring", smoothed_scores["ring"]),
                        "pinky": score_to_pulse("pinky", smoothed_scores["pinky"]),
                    }

                    now = time.time()

                    if now - last_send_time > SEND_INTERVAL_SECONDS:
                        for servo_name, desired_pulse in desired_pulses.items():
                            previous_pulse = last_sent_pulses.get(servo_name)
                            limited_pulse = limit_pulse_change(
                                previous_pulse,
                                desired_pulse,
                            )

                            channel = SERVO_CONFIG[servo_name]["channel"]
                            send_servo_command(arduino, channel, limited_pulse)

                            last_sent_pulses[servo_name] = limited_pulse

                        last_send_time = now

                    mp_drawing.draw_landmarks(
                        frame,
                        hand_landmarks,
                        mp_hands.HAND_CONNECTIONS,
                    )

                    draw_scores(frame, smoothed_scores)

                else:
                    draw_text(frame, "No hand detected", 40)

                cv2.imshow("Vision Servo Control", frame)

                key = cv2.waitKey(1) & 0xFF

                if key == ord("q"):
                    break

                if key == ord("c"):
                    print("Opening all servos.")
                    open_all_servos(arduino)
                    last_sent_pulses.clear()

    except KeyboardInterrupt:
        print("\nStopped by user.")

    finally:
        print("Closing.")

        if camera is not None:
            camera.release()

        cv2.destroyAllWindows()

        if arduino is not None and arduino.is_open:
            arduino.close()


if __name__ == "__main__":
    main()