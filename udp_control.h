#pragma once

#include "esphome.h"
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <vector>

static const char *TAG = "udp_control";
const int UDP_PORT = 5005;

std::vector<std::string> split(const std::string &s, char delimiter) {
  std::vector<std::string> tokens;
  std::string token;
  std::istringstream tokenStream(s);
  while (std::getline(tokenStream, token, delimiter)) {
    tokens.push_back(token);
  }
  return tokens;
}

// Fixed function: Use Servo::write with correct -1 to 1 range
void set_servo_level(esphome::servo::Servo *servo, float angle) {
  if (servo == nullptr)
    return;
  // Clamp angle to safe range (-50 to 50 degrees)
  if (angle > 50.0f)
    angle = 50.0f;
  if (angle < -50.0f)
    angle = -50.0f;

  // ESPHome servo->write() expects -1.0 to 1.0
  // Where: -1.0 = min_level, 0.0 = idle_level, 1.0 = max_level
  // Assuming ±90 degrees maps to ±1.0
  float level = angle / 90.0f;

  ESP_LOGD("servo_ctrl", "Angle: %.1f -> Level: %.3f", angle, level);
  servo->write(level);
}

void set_motors(float m1, float m2, float m3, float m4) {
  // id(my_servo_1) returns `esphome::servo::Servo *` usually in this context?
  // Wait, let's verify. The previous error said:
  // "no match for 'operator*' (operand type is 'esphome::servo::Servo')"
  // This means id(my_servo_1) IS ALREADY A REFERENCE (or object), NOT a pointer
  // in that context? But `set_servo_level(esphome::servo::Servo *servo)`
  // expects a pointer. If id() returns reference `Servo&`, then we should pass
  // `&id(...)`.

  // Let's try passing address of id().
  set_servo_level(&id(my_servo_1), m1);
  set_servo_level(&id(my_servo_2), m2);
  set_servo_level(&id(my_servo_3), m3);
  set_servo_level(&id(my_servo_4), m4);
}

class UDPListener : public Component {
  int sock = -1;

public:
  void setup() override {
    sock = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
      ESP_LOGE(TAG, "Socket Error: %d", errno);
      return;
    }

    struct sockaddr_in dest_addr;
    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(UDP_PORT);

    if (::bind(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) < 0) {
      ESP_LOGE(TAG, "Bind Error: %d", errno);
      close(sock);
      sock = -1;
      return;
    }

    int flags = fcntl(sock, F_GETFL, 0);
    fcntl(sock, F_SETFL, flags | O_NONBLOCK);
    ESP_LOGI(TAG, "UDP Server started on port %d", UDP_PORT);
  }

  void loop() override {
    if (sock < 0)
      return;
    char rx_buffer[128];
    struct sockaddr_in source_addr;
    socklen_t socklen = sizeof(source_addr);
    int len = ::recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, 0,
                         (struct sockaddr *)&source_addr, &socklen);
    if (len > 0) {
      rx_buffer[len] = 0;
      std::string msg(rx_buffer);
      ESP_LOGD(TAG, "Received UDP: %s", msg.c_str()); // Debug Log

      std::vector<std::string> parts;
      std::string token;
      std::istringstream tokenStream(msg);
      while (std::getline(tokenStream, token, ','))
        parts.push_back(token);

      if (parts.size() >= 4) {
        char *end;
        float m1 = strtof(parts[0].c_str(), &end);
        float m2 = strtof(parts[1].c_str(), &end);
        float m3 = strtof(parts[2].c_str(), &end);
        float m4 = strtof(parts[3].c_str(), &end);
        ESP_LOGI(TAG, "Moving Motors: %.2f, %.2f, %.2f, %.2f", m1, m2, m3, m4);
        set_motors(m1, m2, m3, m4);
      } else {
        ESP_LOGW(TAG, "Invalid UDP format: %s", msg.c_str());
      }
    }
  }
};
