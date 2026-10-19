// MR60BHA2 -> USB bridge for the XIAO ESP32C6 in the Seeed MR60BHA2 kit.
//
// The kit ships with ESPHome firmware, which only exposes heart rate, breathing,
// distance and a target count. This sketch replaces it with a transparent pipe:
// every byte the radar sends on its UART goes straight out the XIAO's USB port,
// where the Raspberry Pi decodes it (including the x/y target positions).
//
// Arduino IDE settings:
//   Board:            XIAO_ESP32C6 (esp32 by Espressif, 3.x)
//   USB CDC On Boot:  Enabled   <-- required, or nothing shows up on USB
//
// Based on the passthrough example in Seeed's MIT-licensed Seeed-mmWave-library.

#include <Arduino.h>
#include <HardwareSerial.h>

static const uint32_t RADAR_BAUD = 115200;

// UART0 on its default pins is wired to the radar on the kit's carrier board.
HardwareSerial radar(0);

static uint8_t buf[256];

void setup() {
  Serial.begin(115200);  // USB CDC; the baud rate is ignored over USB
  radar.setRxBufferSize(4096);
  radar.begin(RADAR_BAUD);
}

void loop() {
  size_t n = radar.available();
  if (n > 0) {
    n = radar.readBytes(buf, min(n, sizeof(buf)));
    Serial.write(buf, n);
  }

  // Pass anything from the Pi back to the radar (for future configuration commands).
  n = Serial.available();
  if (n > 0) {
    n = Serial.readBytes(buf, min(n, sizeof(buf)));
    radar.write(buf, n);
  }
}
