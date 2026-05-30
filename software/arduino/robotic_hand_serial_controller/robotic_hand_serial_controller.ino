#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

const int NUM_SERVOS = 6;

// Safe initial pulse limits.
// Later, when the hand is assembled, we will tune these per finger.
const int MIN_PULSE = 500;
const int MID_PULSE = 1500;
const int MAX_PULSE = 2500;

void moveServo(int channel, int pulse) {
  if (channel < 0 || channel >= NUM_SERVOS) {
    Serial.println("ERROR: invalid channel");
    return;
  }

  pulse = constrain(pulse, MIN_PULSE, MAX_PULSE);

  pwm.writeMicroseconds(channel, pulse);

  Serial.print("OK: channel ");
  Serial.print(channel);
  Serial.print(" -> ");
  Serial.println(pulse);
}

void centerAll() {
  for (int ch = 0; ch < NUM_SERVOS; ch++) {
    moveServo(ch, MID_PULSE);
    delay(150);
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("Starting robotic hand serial servo controller...");

  pwm.begin();
  pwm.setPWMFreq(50);
  delay(10);

  Serial.println("Ready.");
  Serial.println("Send commands like:");
  Serial.println("0 1500");
  Serial.println("1 1700");
  Serial.println("all 1500");
}

void loop() {
  if (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line.length() == 0) {
      return;
    }

    if (line.startsWith("all")) {
      int spaceIndex = line.indexOf(' ');
      if (spaceIndex == -1) {
        Serial.println("ERROR: use all 1500");
        return;
      }

      int pulse = line.substring(spaceIndex + 1).toInt();

      for (int ch = 0; ch < NUM_SERVOS; ch++) {
        moveServo(ch, pulse);
        delay(100);
      }

      return;
    }

    int spaceIndex = line.indexOf(' ');
    if (spaceIndex == -1) {
      Serial.println("ERROR: use channel pulse, example: 0 1500");
      return;
    }

    int channel = line.substring(0, spaceIndex).toInt();
    int pulse = line.substring(spaceIndex + 1).toInt();

    moveServo(channel, pulse);
  }
}