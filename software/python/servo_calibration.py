"""
Servo calibration script for the robotic hand.

This script sends manual pulse commands to the Arduino so each servo can be
calibrated after the tendons are installed. Open and closed pulse values are
saved to servo_calibration.json and can be copied into the vision controller.
"""

import json
import time
from pathlib import Path

import serial

# Connection settings
# Run ls /dev/cu.* in your terminal to find the correct port
# Ensure BAUD_RATE matches the baud rate in your Arduino code
PORT = "/dev/cu.usbmodem3101"
BAUD_RATE = 115200

NUM_SERVOS = 6
FALLBACK_PULSE = 1500
CALIBRATION_FILE = Path("servo_calibration.json")

SERVO_NAMES = {
    0: "thumb_rotation",
    1: "thumb_curl",
    2: "index",
    3: "middle",
    4: "ring",
    5: "pinky",
}


def send_command(arduino: serial.Serial, command: str) -> None:
    command = command.strip()
    arduino.write((command + "\n").encode("utf-8"))
    time.sleep(0.05)

    while arduino.in_waiting:
        response = arduino.readline().decode("utf-8", errors="replace").strip()
        if response:
            print(f"Arduino: {response}")


def move_servo(arduino: serial.Serial, channel: int, pulse: int) -> int:
    send_command(arduino, f"{channel} {pulse}")
    return pulse


def make_default_calibration_entry(channel: int) -> dict:
    return {
        "channel": channel,
        "open_pulse": None,
        "closed_pulse": None,
        "notes": "",
    }


def load_calibration() -> dict:
    if CALIBRATION_FILE.exists():
        with CALIBRATION_FILE.open("r") as file:
            calibration = json.load(file)
    else:
        calibration = {}

    for channel, servo_name in SERVO_NAMES.items():
        if servo_name not in calibration:
            calibration[servo_name] = make_default_calibration_entry(channel)

        calibration[servo_name]["channel"] = channel
        calibration[servo_name].setdefault("open_pulse", None)
        calibration[servo_name].setdefault("closed_pulse", None)
        calibration[servo_name].setdefault("notes", "")

    return calibration


def save_calibration(calibration: dict) -> None:
    with CALIBRATION_FILE.open("w") as file:
        json.dump(calibration, file, indent=2)

    print(f"Saved calibration to {CALIBRATION_FILE}")


def get_open_pulse(calibration: dict, channel: int) -> int:
    servo_name = SERVO_NAMES[channel]
    open_pulse = calibration[servo_name].get("open_pulse")

    if open_pulse is None:
        return FALLBACK_PULSE
    return int(open_pulse)


def move_all_to_open_positions(
    arduino: serial.Serial,
    calibration: dict,
    current_pulses: dict[int, int],
) -> None:
    print("Moving servos to saved open pulse.")

    for channel, servo_name in SERVO_NAMES.items():
        pulse = get_open_pulse(calibration, channel)
        print(f"{servo_name}: channel {channel} -> {pulse}")
        current_pulses[channel] = move_servo(arduino, channel, pulse)
        time.sleep(0.25)


def print_help() -> None:
    print()
    print("Commands:")
    print("  +              increase current servo by current step")
    print("  -              decrease current servo by current step")
    print("  ++             increase current servo by 50")
    print("  --             decrease current servo by 50")
    print("  p 1500         move current servo to exact pulse")
    print("  step 10        change step size")
    print("  ch 5           switch to channel 5 without moving it")
    print("  open           save current pulse as open")
    print("  closed         save current pulse as closed")
    print("  start          move current servo to saved open pulse")
    print("  allstart       move all servos to saved open pulses")
    print("  show           show calibration table")
    print("  save           save calibration file")
    print("  help           show this menu")
    print("  q              save and quit")
    print()


def show_calibration(calibration: dict) -> None:
    print()
    print("Current calibration:")
    print("-" * 70)
    print(f"{'Name':<18} {'Channel':<8} {'Open':<10} {'Closed':<10}")
    print("-" * 70)

    for servo_name in SERVO_NAMES.values():
        data = calibration[servo_name]
        print(
            f"{servo_name:<18} "
            f"{data['channel']:<8} "
            f"{str(data['open_pulse']):<10} "
            f"{str(data['closed_pulse']):<10}"
        )

    print("-" * 70)
    print()


def parse_channel_command(user_input: str) -> int | None:
    try:
        return int(user_input.split()[1])
    except (IndexError, ValueError):
        print("Use: ch 5")
        return None


def parse_step_command(user_input: str) -> int | None:
    try:
        step = int(user_input.split()[1])
    except (IndexError, ValueError):
        print("Use: step 10")
        return None

    if step <= 0:
        print("Step must be positive.")
        return None

    return step


def parse_pulse_command(user_input: str) -> int | None:
    try:
        return int(user_input.split()[1])
    except (IndexError, ValueError):
        print("Use: p 1500")
        return None


def main() -> None:
    calibration = load_calibration()
    current_pulses = {
        channel: get_open_pulse(calibration, channel)
        for channel in range(NUM_SERVOS)
    }

    current_channel = 0
    step = 10

    print("Opening Arduino serial connection...")
    print(f"Port: {PORT}")

    try:
        with serial.Serial(PORT, BAUD_RATE, timeout=1) as arduino:
            time.sleep(2)

            print("Connected.")
            print("Use small steps while tendons are attached.")
            print("Keep the external servo power plug within reach.")
            print()

            move_all_to_open_positions(arduino, calibration, current_pulses)
            print_help()

            while True:
                current_name = SERVO_NAMES[current_channel]
                current_pulse = current_pulses[current_channel]

                user_input = input(
                    f"[{current_name} | channel {current_channel} | "
                    f"pulse {current_pulse} | step {step}] > "
                ).strip().lower()

                if not user_input:
                    continue

                if user_input == "q":
                    save_calibration(calibration)
                    print("Quitting.")
                    break

                if user_input == "help":
                    print_help()
                    continue

                if user_input == "show":
                    show_calibration(calibration)
                    continue

                if user_input == "save":
                    save_calibration(calibration)
                    continue

                if user_input == "allstart":
                    move_all_to_open_positions(arduino, calibration, current_pulses)
                    continue

                if user_input == "start":
                    start_pulse = get_open_pulse(calibration, current_channel)
                    current_pulses[current_channel] = move_servo(
                        arduino,
                        current_channel,
                        start_pulse,
                    )
                    continue

                if user_input == "+":
                    current_pulses[current_channel] = move_servo(
                        arduino,
                        current_channel,
                        current_pulse + step,
                    )
                    continue

                if user_input == "-":
                    current_pulses[current_channel] = move_servo(
                        arduino,
                        current_channel,
                        current_pulse - step,
                    )
                    continue

                if user_input == "++":
                    current_pulses[current_channel] = move_servo(
                        arduino,
                        current_channel,
                        current_pulse + 50,
                    )
                    continue

                if user_input == "--":
                    current_pulses[current_channel] = move_servo(
                        arduino,
                        current_channel,
                        current_pulse - 50,
                    )
                    continue

                if user_input == "open":
                    calibration[current_name]["open_pulse"] = current_pulse
                    print(f"Saved open pulse for {current_name}: {current_pulse}")
                    continue

                if user_input == "closed":
                    calibration[current_name]["closed_pulse"] = current_pulse
                    print(f"Saved closed pulse for {current_name}: {current_pulse}")
                    continue

                if user_input.startswith("ch "):
                    new_channel = parse_channel_command(user_input)

                    if new_channel is None:
                        continue

                    if new_channel < 0 or new_channel >= NUM_SERVOS:
                        print(f"Channel must be between 0 and {NUM_SERVOS - 1}.")
                        continue

                    current_channel = new_channel
                    current_name = SERVO_NAMES[current_channel]
                    print(f"Switched to {current_name}. No movement sent.")
                    continue

                if user_input.startswith("step "):
                    new_step = parse_step_command(user_input)

                    if new_step is not None:
                        step = new_step
                        print(f"Step size set to {step}")

                    continue

                if user_input.startswith("p "):
                    target_pulse = parse_pulse_command(user_input)

                    if target_pulse is not None:
                        current_pulses[current_channel] = move_servo(
                            arduino,
                            current_channel,
                            target_pulse,
                        )

                    continue

                print("Unknown command. Type help.")

    except KeyboardInterrupt:
        save_calibration(calibration)
        print("\nStopped by user. Calibration saved.")


if __name__ == "__main__":
    main()