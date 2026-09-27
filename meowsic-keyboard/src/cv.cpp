#include <Arduino.h>
#include <math.h>

#include "config.h"
#include "cv.h"
#include "mcp4725.h"
#include "settings.h"

namespace cv {

struct Channel
{
    uint8_t addr;
    int     gatePin;
    float   codesPerSemi;

    // Held notes in press order, with per-note flags: released while sustain
    // was down (it keeps sounding until the pedal comes up), and whether the
    // pots' offset applies.
    uint8_t notes[CV_STACK_LEN];
    uint8_t flags[CV_STACK_LEN];
    uint8_t n;
    bool    sustain;

    float   offset, bend;   // semitones
    float   target;         // DAC code the current note asks for
    float   code;           // where the slew is; equals target with glide off
    int32_t written;        // last code on the wire, -1 = never
    bool    gateHigh;
    uint32_t retrigEnd;     // gate is held low until this millis(); 0 = not retriggering
};

static constexpr uint8_t F_SUSTAINED = 1;   // released under the pedal
static constexpr uint8_t F_OFFSET    = 2;   // takes the pots

static Channel ch[N_CH] = {
    {DAC_ADDR,  PIN_GATE,  CV_CODES_PER_SEMITONE,  {}, {}, 0, false, 0, 0, 0, 0, -1, false, 0},
    {DAC2_ADDR, PIN_GATE2, CV2_CODES_PER_SEMITONE, {}, {}, 0, false, 0, 0, 0, 0, -1, false, 0},
};

static uint32_t lastServiceMs;

static inline uint8_t top(const Channel &c) { return c.notes[c.n - 1]; }
static inline bool topTakesOffset(const Channel &c) { return c.flags[c.n - 1] & F_OFFSET; }

static float codeOf(const Channel &c, uint8_t note, bool withOffset)
{
    const float semis = (float)note - (float)CV_ZERO_NOTE + (withOffset ? c.offset : 0.0f) + c.bend;
    float code = semis * c.codesPerSemi;
    if (code < 0.0f) code = 0.0f;
    if (code > 4095.0f) code = 4095.0f;
    return code;
}

static void setGate(Channel &c, bool high)
{
    c.gateHigh = high;
    digitalWrite(c.gatePin, high ? HIGH : LOW);
}

// Point the pitch at the top of the stack. With glide off the slew is
// skipped and the DAC gets the new code on the next service(). With glide
// on the pitch always slides from wherever it last was, across gaps too -
// portamento the SH-101 way, not legato-only.
static void retarget(Channel &c)
{
    if (c.n == 0)
        return;
    c.target = codeOf(c, top(c), topTakesOffset(c));
    if (GLIDE_MS[settings::current.glide] == 0)
        c.code = c.target;
}

// Remove index i, keeping press order.
static void removeAt(Channel &c, uint8_t i)
{
    for (uint8_t k = i; k + 1 < c.n; ++k)
    {
        c.notes[k] = c.notes[k + 1];
        c.flags[k] = c.flags[k + 1];
    }
    --c.n;
}

static int find(const Channel &c, uint8_t note)
{
    for (uint8_t i = 0; i < c.n; ++i)
        if (c.notes[i] == note)
            return i;
    return -1;
}

// After notes left the stack: pitch follows the new top, or the gate drops.
static void afterRelease(Channel &c, uint8_t oldTop)
{
    if (c.n == 0)
    {
        setGate(c, false);
        c.retrigEnd = 0;
        return;
    }
    if (top(c) != oldTop)
        retarget(c);
}

void begin()
{
    for (auto &c : ch)
    {
        pinMode(c.gatePin, OUTPUT);
        digitalWrite(c.gatePin, LOW);
        c.n = 0;
        c.sustain = false;
        c.offset = c.bend = 0.0f;
        c.target = c.code = 0.0f;
        c.gateHigh = false;
        c.retrigEnd = 0;
        c.written = dac::write(c.addr, 0) ? 0 : -1;
    }
    lastServiceMs = millis();
}

void noteOn(uint8_t chan, uint8_t note, bool withOffset)
{
    if (chan >= N_CH || note > 127)
        return;
    Channel &c = ch[chan];

    // A note already in the stack moves to the top; a full stack forgets
    // its oldest entry.
    const int i = find(c, note);
    if (i >= 0)
        removeAt(c, (uint8_t)i);
    else if (c.n == CV_STACK_LEN)
        removeAt(c, 0);
    c.notes[c.n] = note;
    c.flags[c.n] = withOffset ? F_OFFSET : 0;
    ++c.n;
    retarget(c);

    if (!c.gateHigh)
    {
        setGate(c, true);
        c.retrigEnd = 0;
    }
    else if (settings::current.gateMode == GATE_RETRIG && c.retrigEnd == 0)
    {
        // A new note on a held one: dip the gate so an envelope restarts.
        // Legato leaves it high.
        setGate(c, false);
        c.retrigEnd = millis() + GATE_RETRIG_MS;
    }
}

void noteOff(uint8_t chan, uint8_t note)
{
    if (chan >= N_CH)
        return;
    Channel &c = ch[chan];
    const int i = find(c, note);
    if (i < 0)
        return;

    if (c.sustain)
    {
        c.flags[i] |= F_SUSTAINED;   // released, but the pedal holds it
        return;
    }
    const uint8_t oldTop = top(c);
    removeAt(c, (uint8_t)i);
    afterRelease(c, oldTop);
}

void allOff(uint8_t chan)
{
    if (chan >= N_CH)
        return;
    Channel &c = ch[chan];
    c.n = 0;
    c.sustain = false;   // a pedal left down would hold the next notes for ever
    setGate(c, false);
    c.retrigEnd = 0;
}

void setOffset(uint8_t chan, float semis)
{
    if (chan >= N_CH)
        return;
    ch[chan].offset = semis;
    retarget(ch[chan]);
}

void setBend(uint8_t chan, float semis)
{
    if (chan >= N_CH)
        return;
    ch[chan].bend = semis;
    retarget(ch[chan]);
}

void setSustain(uint8_t chan, bool on)
{
    if (chan >= N_CH)
        return;
    Channel &c = ch[chan];
    c.sustain = on;
    if (on || c.n == 0)
        return;

    // Pedal up: everything released under it goes now.
    const uint8_t oldTop = top(c);
    for (uint8_t i = 0; i < c.n;)
    {
        if (c.flags[i] & F_SUSTAINED)
            removeAt(c, i);
        else
            ++i;
    }
    afterRelease(c, oldTop);
}

bool gate(uint8_t chan) { return chan < N_CH && ch[chan].gateHigh; }

bool sounding(uint8_t chan, uint8_t &note)
{
    if (chan >= N_CH || ch[chan].n == 0)
        return false;
    note = top(ch[chan]);
    return true;
}

int32_t written(uint8_t chan) { return chan < N_CH ? ch[chan].written : -1; }

void service()
{
    const uint32_t now = millis();
    const uint32_t dt = now - lastServiceMs;
    lastServiceMs = now;

    for (auto &c : ch)
    {
        if (c.retrigEnd != 0 && (int32_t)(now - c.retrigEnd) >= 0)
        {
            setGate(c, true);
            c.retrigEnd = 0;
        }

        if (c.code != c.target)
        {
            // First-order slew: the pitch closes the gap by dt / glide each
            // service, so a step settles in a few glide times.
            const uint16_t glideMs = GLIDE_MS[settings::current.glide];
            if (glideMs == 0 || dt >= glideMs)
                c.code = c.target;
            else
                c.code += (c.target - c.code) * ((float)dt / (float)glideMs);
            if (fabsf(c.target - c.code) < 0.5f)
                c.code = c.target;
        }

        // Written once per change, success or not: a DAC that NACKs is not
        // retried every 3 ms, and a bus that drops is caught by the scan's
        // fail counter, whose recovery calls resync().
        const int32_t want = (int32_t)lroundf(c.code);
        if (want != c.written)
        {
            dac::write(c.addr, (uint16_t)want);
            c.written = want;
        }
    }
}

void resync()
{
    for (auto &c : ch)
        c.written = -1;
}

}  // namespace cv
