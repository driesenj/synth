#include <Arduino.h>
#include <math.h>

#include "clock.h"
#include "config.h"
#include "midi_out.h"
#include "settings.h"

namespace clk {

static Source   src = SRC_INTERNAL;
static uint32_t curTick = 0;       // what tick() returns; never goes backwards
static uint32_t originTick = 0;    // beat 1

// Internal clock: ticks accumulated from micros().
static float    internalBpm = 120.0f;
static float    tickUs = 5208.3f;  // 60e6 / bpm / TICKS_PER_BEAT
static uint32_t lastUs = 0;
static float    accUs = 0.0f;

// External clock, either kind: the tick the last pulse stood for, when it
// came, the smoothed interval, and how many ticks one pulse is worth.
static uint32_t extBase = 0;
static uint32_t extPulseUs = 0;
static float    extIntervalUs = 0.0f;
static uint16_t ticksPerPulse = 4;
static float    extBpm = 120.0f;
static uint32_t extLastMs = 0;     // millis() of the last pulse, for the timeout

// The jack, from its interrupt.
static volatile uint32_t jackPulses = 0;
static volatile uint32_t jackPulseUs = 0;
static uint32_t jackSeen = 0;

// Tap tempo.
static uint32_t tapLastUs = 0;
static uint32_t tapIntervals[4];
static uint8_t  tapN = 0;          // intervals collected in this series
static bool     everTapped = false;

// Beat bookkeeping for the LED.
static uint32_t beatIndex = 0xFFFFFFFF;
static uint32_t beatStartMs = 0;

// MIDI clock out.
static uint32_t nextOutTick = 0;

static void IRAM_ATTR onJackEdge()
{
    jackPulseUs = micros();
    ++jackPulses;
}

static void setInternalTempo(float bpm)
{
    if (bpm < BPM_MIN) bpm = BPM_MIN;
    if (bpm > BPM_MAX) bpm = BPM_MAX;
    internalBpm = bpm;
    tickUs = 60000000.0f / bpm / (float)TICKS_PER_BEAT;
}

void begin()
{
    pinMode(PIN_CLOCK_IN, INPUT);   // its 10k pull-up is on the board
    attachInterrupt(digitalPinToInterrupt(PIN_CLOCK_IN), onJackEdge, FALLING);

    setInternalTempo((float)settings::current.bpm);
    src = SRC_INTERNAL;
    curTick = originTick = 0;
    lastUs = micros();
    accUs = 0.0f;
    nextOutTick = 0;
    jackSeen = jackPulses;
}

// ---- The engine -------------------------------------------------------------

static void advanceInternal(uint32_t nowUs)
{
    accUs += (float)(nowUs - lastUs);
    lastUs = nowUs;
    while (accUs >= tickUs)
    {
        accUs -= tickUs;
        ++curTick;
    }
}

// Where the external clock says we are: its last pulse plus however far
// into the next one we are, never past the tick before the next pulse.
static void advanceExternal(uint32_t nowUs)
{
    uint32_t frac = 0;
    if (extIntervalUs > 0.0f)
    {
        frac = (uint32_t)((float)(nowUs - extPulseUs) * (float)ticksPerPulse / extIntervalUs);
        if (frac > (uint32_t)ticksPerPulse - 1)
            frac = ticksPerPulse - 1;
    }
    const uint32_t t = extBase + frac;
    if ((int32_t)(t - curTick) > 0)
        curTick = t;
}

// A pulse from either external source.
static uint32_t candidateUs[3];   // per source: the previous pulse, while not yet master

static void externalPulse(Source which, uint16_t tpp, uint32_t atUs)
{
    const uint32_t nowMs = millis();
    if (src != which)
    {
        // Takeover needs two pulses at a plausible tempo, so a stray edge at
        // the jack or one clock byte cannot grab the clock. The count then
        // continues from wherever it is, at the tempo those two pulses say.
        const float pulsesPerBeat = (float)TICKS_PER_BEAT / (float)tpp;
        const float minUs = 60000000.0f / (float)BPM_MAX / pulsesPerBeat;
        const float maxUs = 60000000.0f / (float)BPM_MIN / pulsesPerBeat;
        const uint32_t prev = candidateUs[which];
        const float gap = (float)(atUs - prev);
        candidateUs[which] = atUs;
        if (prev == 0 || gap < minUs || gap > maxUs)
            return;
        src = which;
        ticksPerPulse = tpp;
        extBase = curTick;
        extIntervalUs = gap;
        extBpm = 60000000.0f / (gap * pulsesPerBeat);
    }
    else
    {
        const float measured = (float)(atUs - extPulseUs);
        // A pulse more than four times late is a restart, not a tempo.
        if (measured > 0.0f && measured < extIntervalUs * 4.0f)
            extIntervalUs += (measured - extIntervalUs) * 0.25f;
        extBase += tpp;
        if ((int32_t)(extBase - curTick) < 0)
            extBase = curTick;   // the interpolation had already got there
        extBpm = 60000000.0f / (extIntervalUs * ((float)TICKS_PER_BEAT / (float)tpp));
    }
    extPulseUs = atUs;
    extLastMs = nowMs;
    if ((int32_t)(extBase - curTick) > 0)
        curTick = extBase;
}

void midiTick()
{
    externalPulse(SRC_MIDI, TICKS_PER_BEAT / 24, micros());
}

static void serviceJack()
{
    const uint32_t pulses = jackPulses;
    if (pulses == jackSeen)
        return;
    const uint32_t atUs = jackPulseUs;
    const uint32_t n = pulses - jackSeen;
    jackSeen = pulses;

    // MIDI clock outranks the jack while it is alive.
    if (src == SRC_MIDI && millis() - extLastMs < CLOCK_EXT_TIMEOUT_MS)
        return;

    // Pulses never come faster than the loop, so n is 1; if it ever is not,
    // the extra ones simply advance the count.
    for (uint32_t i = 0; i < n; ++i)
        externalPulse(SRC_JACK, TICKS_PER_BEAT / CLOCK_PPQN, atUs);
}

static void serviceBeat()
{
    const uint32_t b = (curTick - originTick) / TICKS_PER_BEAT;
    if (b != beatIndex)
    {
        beatIndex = b;
        beatStartMs = millis();
    }
}

static void serviceClockOut()
{
#if MIDI_CLOCK_OUT
    if (src == SRC_MIDI)
    {
        nextOutTick = curTick;   // re-armed for whenever we are master again
        return;
    }
    // A jump in the count - a takeover, a phase reset - must not turn into
    // a burst of clocks.
    if ((int32_t)(curTick - nextOutTick) > (int32_t)TICKS_PER_BEAT)
        nextOutTick = curTick;
    while ((int32_t)(curTick - nextOutTick) >= 0)
    {
        midi::realtime(0xF8);
        nextOutTick += TICKS_PER_BEAT / 24;
    }
#endif
}

void service()
{
    const uint32_t nowUs = micros();

    serviceJack();

    if (src != SRC_INTERNAL && millis() - extLastMs >= CLOCK_EXT_TIMEOUT_MS)
    {
        // The external source stopped: carry on from here at its tempo.
        src = SRC_INTERNAL;
        setInternalTempo(extBpm);
        lastUs = nowUs;
        accUs = 0.0f;
    }

    if (src == SRC_INTERNAL)
        advanceInternal(nowUs);
    else
        advanceExternal(nowUs);

    serviceBeat();
    serviceClockOut();
}

// ---- Queries ----------------------------------------------------------------

uint32_t tick() { return curTick; }
Source source() { return src; }
float bpm() { return src == SRC_INTERNAL ? internalBpm : extBpm; }
uint32_t origin() { return originTick; }
uint32_t ticksSinceOrigin() { return curTick - originTick; }

uint32_t nextBeatTick()
{
    const uint32_t r = (curTick - originTick) % TICKS_PER_BEAT;
    return r == 0 ? curTick : curTick + (TICKS_PER_BEAT - r);
}

uint32_t beatAgeMs() { return millis() - beatStartMs; }
uint8_t beatInBar() { return (uint8_t)(beatIndex % BEATS_PER_BAR); }

void resetPhase()
{
    originTick = curTick;
    if (src == SRC_INTERNAL)
    {
        // The next tick is exactly one tick from now.
        lastUs = micros();
        accUs = 0.0f;
    }
    nextOutTick = curTick;   // a clock goes out on the new beat 1
    beatIndex = 0xFFFFFFFF;  // so the LED sees beat 1 begin
}

// ---- Tap tempo --------------------------------------------------------------

bool tap()
{
    const uint32_t now = micros();
    if (tapN > 0 || tapLastUs != 0)
    {
        const uint32_t since = now - tapLastUs;
        if (since < TAP_MIN_MS * 1000UL)
            return false;                 // bounce
        if (since > TAP_MAX_MS * 1000UL)
            tapN = 0;                     // too long ago: a new series starts
        else
        {
            tapIntervals[tapN % 4] = since;
            ++tapN;
        }
    }
    tapLastUs = now;

    if (tapN < 2)
        return false;   // three taps make two intervals

    const uint8_t used = tapN < 4 ? tapN : 4;
    float sum = 0.0f;
    for (uint8_t i = 0; i < used; ++i)
        sum += (float)tapIntervals[i];
    float bpm = 60000000.0f / (sum / (float)used);
    if (bpm < BPM_MIN) bpm = BPM_MIN;
    if (bpm > BPM_MAX) bpm = BPM_MAX;

    settings::current.bpm = (uint16_t)lroundf(bpm);
    settings::changed();
    everTapped = true;
    if (src == SRC_INTERNAL)
    {
        setInternalTempo(bpm);
        resetPhase();   // this tap is beat 1
    }
    else
        internalBpm = bpm;   // for when the external source goes away
    return true;
}

bool tapped() { return everTapped; }

// ---- Transport out ----------------------------------------------------------

void sendStart()
{
#if MIDI_CLOCK_OUT
    if (src != SRC_MIDI)
        midi::realtime(0xFA);
#endif
}

void sendStop()
{
#if MIDI_CLOCK_OUT
    if (src != SRC_MIDI)
        midi::realtime(0xFC);
#endif
}

}  // namespace clk
