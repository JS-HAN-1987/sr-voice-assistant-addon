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

// Helper to set motor angle (Safe Range: -50 to 50)
void set_servo_level(esphome::servo::Servo *servo, float angle) {
  if (servo == nullptr)
    return;
  if (angle > 50.0f)
    angle = 50.0f;
  if (angle < -50.0f)
    angle = -50.0f;

  // Angle 0deg = 0.075 (Center), +/- 50deg range
  // 0.10f factor
  float level = 0.075f + (angle / 180.0f) * 0.10f;
  servo->make_call().set_level(level).perform();
}

// Global Helper
// Note: id(my_servo_1) returns a pointer or reference depending on context in
// lambda vs raw C++. In external header included in YAML, we usually access
// global variables declared by ESPHome. However, direct `id()` usage inside a
// header file might be tricky if not inside a lambda context. But since this is
// included and used inside lambda or effectively in main scope, `id(name)`
// usually resolves to `name`. If `id(my_servo_1)` gives
// `esphome::servo::Servo`, we need address `&`. The error says: cannot convert
// `esphome::servo::Servo` to `esphome::servo::Servo*`. So `id(my_servo_1)` is
// the OBJECT (Reference-like). We need `&id(my_servo_1)`. But wait, standard
// `id()` macro returns a reference. Let's change `set_servo_level` to take
// `esphome::servo::Servo &` instead of pointer for cleaner C++.

void set_servo_level_ref(esphome::servo::Servo &servo, float angle) {
  if (angle > 50.0f)
    angle = 50.0f;
  if (angle < -50.0f)
    angle = -50.0f;
  float level = 0.075f + (angle / 180.0f) * 0.10f;
  servo.make_call().set_level(level).perform();
}

void set_motors(float m1, float m2, float m3, float m4) {
  // Pass by reference
  set_servo_level_ref(*id(my_servo_1), m1);
  set_servo_level_ref(*id(my_servo_2), m2);
  set_servo_level_ref(*id(my_servo_3), m3);
  set_servo_level_ref(*id(my_servo_4), m4);
}

class UDPListener : public Component {
  int sock = -1;

public:
  void setup() override {
    // Disambiguate global socket function using ::
    sock = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
      ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
      return;
    }

    struct sockaddr_in dest_addr;
    dest_addr.sin_addr.s_addr = htonl(INADDR_ANY);
    dest_addr.sin_family = AF_INET;
    dest_addr.sin_port = htons(UDP_PORT);

    if (::bind(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) < 0) {
      ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
      close(sock);
      sock = -1;
      return;
    }

    // Set non-blocking
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

    ssize_t len = ::recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, 0,
                             (struct sockaddr *)&source_addr, &socklen);

    if (len > 0) {
      rx_buffer[len] = 0;
      std::string msg(rx_buffer);

      // Manual parsing without exceptions
      // Format: m1,m2,m3,m4
      auto parts = split(msg, ',');
      if (parts.size() >= 4) {
        // Use strtof instead of stof to avoid exceptions
        char *end;
        float m1 = strtof(parts[0].c_str(), &end);
        float m2 = strtof(parts[1].c_str(), &end);
        float m3 = strtof(parts[2].c_str(), &end);
        float m4 = strtof(parts[3].c_str(), &end);

        set_motors(m1, m2, m3, m4);
      }
    }
  }
};
