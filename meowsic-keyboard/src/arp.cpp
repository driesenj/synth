#include <Arduino.h>

#include "arp.h"
#include "clock.h"
#include "config.h"
#include "router.h"
#include "settings.h"

namespace arp {

static constexpr uint8_t NONE = 0xFF;

// Held notes in press order.
static uint8_t held[ARP_HELD_MAX];
static uint8_t n = 0;

static bool     wasOn = false;
static uint8_t  sounding = NONE;   // the step note currently on
static uint32_t lastStepIdx = 0xFFFFFFFF;
static uint32_t stepCounter = 0;   // steps played since the pattern (re)started
static uint32_t offTick = 0;       // when the sounding note ends

static const uint16_t DIV_TICKS[ARP_DIV_N] = {
    TICKS_PER_BEAT / 4, TICKS_PER_BEAT / 2, TICKS_PER_BEAT};   // 16ths, 8ths, quarters

static int find(uint8_t note)
{
    for (uint8_t i = 0; i < n; ++i)
        if (held[i] == note)
            return i;
    return -1;
}

static void removeAt(uint8_t i)
{
    for (uint8_t k = i; k + 1 < n; ++k)
        held[k] = held[k + 1];
    --n;
}

void begin()
{
    n = 0;
    wasOn = false;
    sounding = NONE;
    lastStepIdx = 0xFFFFFFFF;
    stepCounter = 0;
}

void noteOn(uint8_t note)
{
    const int i = find(note);
    if (i >= 0)
        removeAt((uint8_t)i);
    else if (n == ARP_HELD_MAX)
        removeAt(0);
    const bool wasEmpty = (n == 0);
    held[n++] = note;
    if (wasEmpty)
        stepCounter = 0;   // a fresh chord starts its pattern from the top
}

void noteOff(uint8_t note)
{
    const int i = find(note);
    if (i >= 0)
        removeAt((uint8_t)i);
}

static void stopSounding()
{
    if (sounding == NONE)
        return;
    router::noteOff(sounding, router::SRC_ARP);
    sounding = NONE;
}

void allOff() { stopSounding(); }

// The k-th note of the pattern for the current order.
static uint8_t pick(uint32_t k)
{
    uint8_t sorted[ARP_HELD_MAX];
    for (uint8_t i = 0; i < n; ++i)
        sorted[i] = held[i];
    for (uint8_t i = 1; i < n; ++i)   // insertion sort, n <= 16
    {
        const uint8_t v = sorted[i];
        uint8_t j = i;
        while (j > 0 && sorted[j - 1] > v)
        {
            sorted[j] = sorted[j - 1];
            --j;
        }
        sorted[j] = v;
    }

    switch (settings::current.arpOrder)
    {
    case ARP_DOWN:
        return sorted[n - 1 - (k % n)];
    case ARP_UPDOWN:
    {
        if (n < 3)
            return sorted[k % n];   // one or two notes: up-down is just up
        const uint32_t len = 2u * n - 2u;   // up, then down without repeating the ends
        const uint32_t p = k % len;
        return p < n ? sorted[p] : sorted[len - p];
    }
    case ARP_PLAYED:
        return held[k % n];
    case ARP_UP:
    default:
        return sorted[k % n];
    }
}

void service()
{
    const bool on = settings::current.arpOn;
    if (on != wasOn)
    {
        wasOn = on;
        if (on)
        {
            // Whatever the keys were sounding directly stops; the arp takes
            // over on the next grid step.
            router::releaseKeysPath();
            stepCounter = 0;
            lastStepIdx = 0xFFFFFFFF;
        }
        else
            stopSounding();
        // Keys held when the arp goes off stay silent until re-pressed.
    }
    if (!on)
        return;

    const uint16_t div = DIV_TICKS[settings::current.arpDiv];
    const uint32_t t = clk::ticksSinceOrigin();

    if (sounding != NONE && (int32_t)(t - offTick) >= 0)
        stopSounding();

    const uint32_t idx = t / div;
    if (idx == lastStepIdx)
        return;
    lastStepIdx = idx;

    stopSounding();
    if (n == 0)
        return;
    sounding = pick(stepCounter++);
    router::noteOn(sounding, router::SRC_ARP);
    offTick = idx * div + (uint32_t)div * ARP_GATE_PERCENT / 100;
}

}  // namespace arp
