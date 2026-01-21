#pragma once

#include "esphome.h"

// Servo Control Helper Functions for Blossom Robot
// Used by: YAML lambda (ear_wiggle), API action (set_motors)

// Set servo to specific angle (-50 to 50 degrees safe range)
void set_servo_level(esphome::servo::Servo *servo, float angle) {
  if (servo == nullptr)
    return;
  // Clamp angle to safe range
  if (angle > 50.0f)
    angle = 50.0f;
  if (angle < -50.0f)
    angle = -50.0f;

  // ESPHome servo->write() expects -1.0 to 1.0
  // Mapping: ±90 degrees -> ±1.0
  float level = angle / 90.0f;

  ESP_LOGD("servo_ctrl", "Angle: %.1f -> Level: %.3f", angle, level);
  servo->write(level);
}

// Set all 4 motors at once (m1,m2,m3 = head, m4 = ear)
void set_motors(float m1, float m2, float m3, float m4) {
  set_servo_level(&id(my_servo_1), m1);
  set_servo_level(&id(my_servo_2), m2);
  set_servo_level(&id(my_servo_3), m3);
  set_servo_level(&id(my_servo_4), m4);
}
