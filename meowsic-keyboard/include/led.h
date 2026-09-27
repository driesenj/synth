#pragma once
#include <stdint.h>

// The RGB LED in the record button, three PWM legs (PIN_LED_* in config.h).
// Two layers: a base colour that stays until changed - the looper's state -
// and a blink overlay on top of it for the settings' blink codes and the
// tap-tempo flash, after which the base colour comes back by itself.
// Colours are 0-255 per channel before the balance in LED_LEVEL_*.
namespace led {

void begin();

// Base colour.
void set(uint8_t r, uint8_t g, uint8_t b);
void off();

// Overlay: n pulses of a colour, then back to the base. A new blink replaces
// one still running.
void blink(uint8_t r, uint8_t g, uint8_t b, uint8_t n, uint16_t onMs = 80, uint16_t offMs = 120);

// One pulse.
void flash(uint8_t r, uint8_t g, uint8_t b, uint16_t ms);

void service();

}  // namespace led
