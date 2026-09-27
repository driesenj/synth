#include <Arduino.h>
#include <math.h>

#include "auxout.h"
#include "clock.h"
#include "config.h"
#include "looper.h"
#include "settings.h"

namespace aux {

static uint8_t  written = 0;
static uint8_t  modWheel = 0;
static uint8_t  sineTable[256];

// Period bookkeeping: which period we are in, so a new one is noticed.
static uint32_t periodIndex = 0xFFFFFFFF;
static uint32_t periodStartMs = 0;
static uint8_t  randomLevel = 0;

// Clock pulses: which pulse slot was last fired.
static uint32_t pulseIndex = 0xFFFFFFFF;
static uint32_t pulseStartMs = 0;

// The envelope.
static uint32_t envTriggerMs = 0;
static bool     envOn = false;

static void write(uint8_t code)
{
    if (code == written)
        return;
    dacWrite(PIN_AUX, code);
    written = code;
}

void begin()
{
    for (int i = 0; i < 256; ++i)
        sineTable[i] = (uint8_t)lroundf(127.5f + 127.5f * sinf((float)i / 256.0f * 2.0f * (float)M_PI));
    written = 1;   // so the first write lands
    write(0);
}

void trigger()
{
    envTriggerMs = millis();
    envOn = true;
}

void setModWheel(uint8_t value) { modWheel = value & 0x7F; }
uint8_t level() { return written; }

// Where we are in the period: 0-65535 across it, and the period's index so a
// new one can be told from the last.
static void phase(uint16_t &frac, uint32_t &index)
{
    const uint8_t rate = settings::current.auxRate;
    if (rate == AUX_PER_LOOP && looper::anyRunning())
    {
        // The active loop's pass; the other loop's if the active one is not
        // running.
        uint8_t ch = looper::active();
        if (looper::state(ch) != looper::PLAYING && looper::state(ch) != looper::OVERDUB)
            ch ^= 1;
        const uint32_t len = looper::lengthTicks(ch);
        const uint32_t pos = looper::positionTicks(ch);
        frac = len ? (uint16_t)((uint64_t)pos * 65536 / len) : 0;
        index = looper::passStart(ch);   // moves once per pass, at the wrap
        return;
    }
    const uint32_t period = rate == AUX_PER_BEAT ? TICKS_PER_BEAT : (uint32_t)TICKS_PER_BEAT * BEATS_PER_BAR;
    const uint32_t t = clk::ticksSinceOrigin();
    index = t / period;
    frac = (uint16_t)((uint64_t)(t % period) * 65536 / period);
}

void service()
{
    const uint32_t now = millis();
    const uint8_t wave = settings::current.auxWave;

    uint16_t frac;
    uint32_t index;
    phase(frac, index);
    const bool newPeriod = index != periodIndex;
    if (newPeriod)
    {
        periodIndex = index;
        periodStartMs = now;
        randomLevel = (uint8_t)(esp_random() & 0xFF);
    }
    const uint8_t p = (uint8_t)(frac >> 8);   // 0-255 across the period

    uint8_t out = 0;
    switch (wave)
    {
    case AUX_SAW_UP:   out = p; break;
    case AUX_SAW_DOWN: out = (uint8_t)(255 - p); break;
    case AUX_TRI:      out = p < 128 ? (uint8_t)(p * 2) : (uint8_t)((255 - p) * 2); break;
    case AUX_SINE:     out = sineTable[p]; break;
    case AUX_SQUARE:   out = p < 128 ? 255 : 0; break;
    case AUX_RANDOM:   out = randomLevel; break;

    case AUX_CLOCK:
    {
        // One pulse a beat, or one per 16th at the beat rate.
        const uint32_t step = settings::current.auxRate == AUX_PER_BEAT ? TICKS_PER_BEAT / 4 : TICKS_PER_BEAT;
        const uint32_t slot = clk::ticksSinceOrigin() / step;
        if (slot != pulseIndex)
        {
            pulseIndex = slot;
            pulseStartMs = now;
        }
        out = now - pulseStartMs < AUX_PULSE_MS ? 255 : 0;
        break;
    }
    case AUX_RESET:
        out = now - periodStartMs < AUX_PULSE_MS ? 255 : 0;
        break;

    case AUX_ENV:
    {
        if (!envOn)
            break;
        // Exponential decay: full scale falling to a few codes in about
        // three time constants.
        const float x = (float)(now - envTriggerMs) / (float)AUX_ENV_MS;
        const float v = 255.0f * expf(-3.0f * x);
        if (v < 1.0f)
            envOn = false;
        else
            out = (uint8_t)v;
        break;
    }
    case AUX_MODWHEEL: out = (uint8_t)(modWheel * 2); break;
    case AUX_OFF:
    default:           out = 0; break;
    }
    write(out);
}

}  // namespace aux
