#include <Arduino.h>

#include "config.h"
#include "led.h"

namespace led {

// LEDC channels 0-2; the Arduino core 2.x API pairs a channel with a pin.
static constexpr uint8_t CH_RED = 0, CH_GREEN = 1, CH_BLUE = 2;

static uint8_t baseR, baseG, baseB;

// Overlay state.
static bool     overlay = false;
static uint8_t  ovR, ovG, ovB;
static uint8_t  pulsesLeft;     // pulses still to start, not counting the current one
static bool     ovOn;           // in the on half of a pulse
static uint16_t onMs, offMs;
static uint32_t phaseEnd;

static void write(uint8_t r, uint8_t g, uint8_t b)
{
    ledcWrite(CH_RED,   (uint32_t)r * LED_LEVEL_RED   / 255);
    ledcWrite(CH_GREEN, (uint32_t)g * LED_LEVEL_GREEN / 255);
    ledcWrite(CH_BLUE,  (uint32_t)b * LED_LEVEL_BLUE  / 255);
}

static void showBase() { write(baseR, baseG, baseB); }

void begin()
{
    const struct { uint8_t ch; int pin; } legs[] = {
        {CH_RED, PIN_LED_RED}, {CH_GREEN, PIN_LED_GREEN}, {CH_BLUE, PIN_LED_BLUE}};
    for (auto &l : legs)
    {
        ledcSetup(l.ch, LED_PWM_HZ, 8);
        ledcAttachPin(l.pin, l.ch);
    }
    baseR = baseG = baseB = 0;
    overlay = false;
    showBase();
}

void set(uint8_t r, uint8_t g, uint8_t b)
{
    baseR = r;
    baseG = g;
    baseB = b;
    if (!overlay)
        showBase();
}

void off() { set(0, 0, 0); }

void blink(uint8_t r, uint8_t g, uint8_t b, uint8_t n, uint16_t on, uint16_t off)
{
    if (n == 0)
        return;
    ovR = r;
    ovG = g;
    ovB = b;
    onMs = on;
    offMs = off;
    pulsesLeft = (uint8_t)(n - 1);
    ovOn = true;
    overlay = true;
    phaseEnd = millis() + onMs;
    write(ovR, ovG, ovB);
}

void flash(uint8_t r, uint8_t g, uint8_t b, uint16_t ms)
{
    blink(r, g, b, 1, ms, 0);
}

void service()
{
    if (!overlay)
        return;
    const uint32_t now = millis();
    if ((int32_t)(now - phaseEnd) < 0)
        return;

    if (ovOn)
    {
        // End of a pulse. The gap shows the base colour, so a blink reads as
        // a count even when the base is lit.
        ovOn = false;
        if (pulsesLeft == 0 && offMs == 0)
        {
            overlay = false;
            showBase();
            return;
        }
        showBase();
        phaseEnd = now + offMs;
        return;
    }

    if (pulsesLeft == 0)
    {
        overlay = false;
        showBase();
        return;
    }
    --pulsesLeft;
    ovOn = true;
    phaseEnd = now + onMs;
    write(ovR, ovG, ovB);
}

}  // namespace led
