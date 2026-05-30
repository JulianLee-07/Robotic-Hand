# Wiring

## Arduino to PCA9685

 Arduino Uno | PCA9685 |            Purpose 
-------------|---------|-------------------------------
     5V      |   VCC   | Logic power for PCA9685 
    GND      |   GND   | Shared ground 
     A4      |   SDA   | I2C data 
     A5      |   SCL   | I2C clock 
    GND      |   OE    | Keeps PCA9685 outputs enabled 

## External Servo Power

 Power Supply |       PCA9685 
--------------|---------------------
     +5V      | V+ screw terminal 
   GND / -    | GND screw terminal 

## Servo Connections

Each servo plugs into one PCA9685 channel.

    Servo Wire     |    PCA9685 Row 
-------------------|----------------------
  Orange / Yellow  |         PWM 
        Red        |         V+ 
   Brown / Black   |         GND 

## Servo Channel Map

 PCA9685 Channel |       Servo       
-----------------|--------------------
        0        | Thumb rotation 
        1        | Thumb curl 
        2        | Index 
        3        | Middle 
        4        | Ring 
        5        | Pinky 
