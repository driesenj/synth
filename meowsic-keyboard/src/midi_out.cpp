#include <Arduino.h>

#include "config.h"
#include "midi_out.h"

namespace midi {

// No running status. It saves a third of the bytes but complicates every
// future sender (looper, MIDI thru, arpeggiator) with shared state, and at
// 31250 baud a full 3-byte message is 960 us - not a bottleneck here.
static void send3(uint8_t status, uint8_t d1, uint8_t d2) {
    const uint8_t buf[3] = { status, (uint8_t)(d1 & 0x7F), (uint8_t)(d2 & 0x7F) };
    Serial2.write(buf, 3);
#if USB_MIDI
    Serial.write(buf, 3);
#endif
}

void begin() {
    Serial.begin(USB_BAUD);
    Serial2.begin(31250, SERIAL_8N1, PIN_MIDI_RX, PIN_MIDI_TX);
}

void noteOn(uint8_t ch, uint8_t note, uint8_t vel) {
    send3((uint8_t)(0x90 | (ch & 0x0F)), note, vel);
}

// Note-on with velocity 0 rather than 0x80: universally understood, and it
// keeps the door open for running status later.
void noteOff(uint8_t ch, uint8_t note) {
    send3((uint8_t)(0x90 | (ch & 0x0F)), note, 0);
}

void cc(uint8_t ch, uint8_t num, uint8_t val) {
    send3((uint8_t)(0xB0 | (ch & 0x0F)), num, val);
}

void allSoundOff(uint8_t ch) {
    cc(ch, 120, 0);
    cc(ch, 123, 0);
}

}  // namespace midi
