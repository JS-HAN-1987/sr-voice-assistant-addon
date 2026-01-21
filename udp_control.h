#pragma once

#include "esphome.h"
#include <WiFiUdp.h>
#include <vector>
#include <string>
#include <sstream>

static const char *TAG = "udp_control";

WiFiUDP udp;
const int UDP_PORT = 5005;

// Servo Objects (IDs from YAML)
// They must be declared in YAML with these IDs: my_servo_1, my_servo_2, my_servo_3, my_servo_4

// Helper to split string
std::vector<std::string> split(const std::string &s, char delimiter) {
    std::vector<std::string> tokens;
    std::string token;
    std::istringstream tokenStream(s);
    while (std::getline(tokenStream, token, delimiter)) {
        tokens.push_back(token);
    }
    return tokens;
}

// Helper to set motor angle
// Angle: -50 to 50 degrees
// Servo PWM: 2.5% (0.5ms) to 12.5% (2.5ms)
// Center (0 deg) = 7.5%
// Range = +/- 50 deg -> +/- 2.5% duty
// Duty = 0.075 + (Angle / 50.0) * 0.025  <-- CHECK MG996R spec in YAML
// YAML Says: min 2.5%, idle 7.5%, max 12.5%.
// That means 7.5% is center. 2.5% is -MaxRange, 12.5% is +MaxRange.
// If typical servo is 180 deg total, +/- 90.
// But we only want to move SAFE range.
// Blossom code uses -50 to 50.
// Formula: Level = 0.075 + (Angle / 90.0) * 0.025 ??
// Let's assume 0.025 to 0.125 covers full 0-180 (or 270?).
// MG996R is 180 deg servo usually.
// 0.5ms = 0deg, 1.5ms = 90deg, 2.5ms = 180deg.
// Center (1.5ms) = 7.5% (of 20ms).
// Angle 0 (in our logic) = 90 (real servo).
// Angle +50 (our) = 140 (real).
// Angle -50 (our) = 40 (real).
// 90 deg = 0.075.
// 1 deg = (0.125 - 0.025) / 180 = 0.000555...
// Level = 0.075 + (Angle * 0.0005555)
// Let's check: 50 deg * 0.000555 = 0.0277. 0.075 + 0.0277 = 0.1027 (approx 10%)
// -50 deg * ... = -0.027. 0.075 - 0.027 = 0.048 (approx 5%)
// Safe range 0.025 ~ 0.125. OK.

void set_servo_level(esphome::servo::Servo *servo, float angle) {
    if (servo == nullptr) return;
    
    // Clamp angle -50 to 50 for safety (Blossom Limit)
    if (angle > 50.0f) angle = 50.0f;
    if (angle < -50.0f) angle = -50.0f;

    // Calculate Duty Cycle
    // 0 deg = 0.075
    // 1 deg change = 0.0005555 (assuming 180deg range for 2.5-12.5%)
    float level = 0.075f + (angle / 180.0f) * 0.10f; 
    // Wait, (0.125 - 0.025) = 0.10 range.
    
    servo->make_call().set_level(level).perform();
}

// Global Helper for Lambda
void set_motors(float m1, float m2, float m3, float m4) {
    set_servo_level(id(my_servo_1), m1);
    set_servo_level(id(my_servo_2), m2);
    set_servo_level(id(my_servo_3), m3);
    set_servo_level(id(my_servo_4), m4);
}

class UDPListener : public Component {
public:
    void setup() override {
        udp.begin(UDP_PORT);
        ESP_LOGI(TAG, "UDP Server started on port %d", UDP_PORT);
    }

    void loop() override {
        int packetSize = udp.parsePacket();
        if (packetSize) {
            char packetBuffer[255];
            int len = udp.read(packetBuffer, 255);
            if (len > 0) {
                packetBuffer[len] = 0;
            }
            
            std::string msg(packetBuffer);
            //ESP_LOGD(TAG, "Received UDP: %s", msg.c_str());
            
            // Expected format: m1,m2,m3,m4
            auto parts = split(msg, ',');
            if (parts.size() >= 4) {
                try {
                    float m1 = std::stof(parts[0]);
                    float m2 = std::stof(parts[1]);
                    float m3 = std::stof(parts[2]);
                    float m4 = std::stof(parts[3]);
                    
                    set_motors(m1, m2, m3, m4);
                    
                } catch (...) {
                    ESP_LOGW(TAG, "Error parsing motor values");
                }
            }
        }
    }
};
