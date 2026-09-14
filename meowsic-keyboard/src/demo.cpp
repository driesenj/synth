#include <Arduino.h>
#include <stdarg.h>

#include "config.h"
#include "inject.h"

// ============================================================================
//  Meowsic MIDI - injection demo: loops a tune through the toy's own voices.
//
//  Built as its own environment:  pio run -e demo -t upload
//
//  Needs the ESP32, the two muxes and the blob powered; no I2C, the expander
//  and the DAC can stay unplugged. Runs on the production injector
//  (inject.cpp) and the measured tables in config.h, so if this plays in tune
//  the stage-5 hardware is done.
//
//  The tune is Korobeiniki (traditional, 1861), A minor - the melody from a
//  certain falling-blocks game. One pass per voice: meow, piano, meow, organ,
//  meow, banjo, meow, bells. Starts by itself two seconds after boot.
//
//  Serial monitor at 115200, no Enter needed:
//    space  play / pause        s  stop and rewind       x  release the key now
//    + / -  tempo +-10 BPM      m  meow only, toggle     n  next voice now
//    1-5    piano bells meow organ banjo, from the next note
//    c      catface             t  the toy's STOP        ?  banner
//
//  Timing is nominal: each step is scheduled from the previous one's end, so
//  the loop stays in time however long the log takes. Button taps are
//  blocking and shift the schedule by their own length instead of making the
//  next notes rush.
// ============================================================================

static void p(const char *fmt, ...)
{
    char buf[128];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    Serial.println(buf);
}

// ---- the tune ---------------------------------------------------------------
// note = MIDI number as in position_map.cpp, 0 = rest; len in sixteenths.
struct Step {
    uint8_t note;
    uint8_t len;
};

static const Step TUNE[] = {
    // A section, 4/4
    {76, 4}, {71, 2}, {72, 2}, {74, 4}, {72, 2}, {71, 2},
    {69, 4}, {69, 2}, {72, 2}, {76, 4}, {74, 2}, {72, 2},
    {71, 6}, {72, 2}, {74, 4}, {76, 4},
    {72, 4}, {69, 4}, {69, 4}, {0, 4},
    {0, 2},  {74, 4}, {77, 2}, {81, 4}, {79, 2}, {77, 2},
    {76, 6}, {72, 2}, {76, 4}, {74, 2}, {72, 2},
    {71, 4}, {71, 2}, {72, 2}, {74, 4}, {76, 4},
    {72, 4}, {69, 4}, {69, 4}, {0, 4},
    // B section
    {76, 8}, {72, 8},
    {74, 8}, {71, 8},
    {72, 8}, {69, 8},
    {68, 8}, {71, 8},
    {76, 8}, {72, 8},
    {74, 8}, {71, 8},
    {72, 4}, {76, 4}, {81, 8},
    {80, 8}, {0, 8},
};
static constexpr uint16_t TUNE_LEN = sizeof(TUNE) / sizeof(TUNE[0]);

static const uint8_t PASS_VOICE[] = {CC_MEOW, CC_PIANO, CC_MEOW, CC_ORGAN,
                                     CC_MEOW, CC_BANJO, CC_MEOW, CC_BELLS};
static constexpr uint8_t N_PASS_VOICES = sizeof(PASS_VOICE) / sizeof(PASS_VOICE[0]);

static const uint8_t KEY_VOICE[5] = {CC_PIANO, CC_BELLS, CC_MEOW, CC_ORGAN, CC_BANJO};

// ---- map lookups ------------------------------------------------------------
static uint8_t posOfNote[128];
static uint8_t posOfCC[CC_LAST - CC_PIANO + 1];

static void indexMap()
{
    memset(posOfNote, 0xFF, sizeof(posOfNote));
    memset(posOfCC, 0xFF, sizeof(posOfCC));
    for (uint8_t pos = 0; pos < N_POS; ++pos)
    {
        const PosMap &m = POSITION_MAP[pos];
        if (m.kind == K_NOTE && m.data < 128)
            posOfNote[m.data] = pos;
        else if (m.kind == K_CC && m.data >= CC_PIANO && m.data <= CC_LAST)
            posOfCC[m.data - CC_PIANO] = pos;
    }
}

static const char *NOTE_NAMES[12] = {"C", "C#", "D", "D#", "E", "F",
                                     "F#", "G", "G#", "A", "A#", "B"};

// ---- transport --------------------------------------------------------------
static uint16_t bpm = 150;
static constexpr uint32_t GAP_MS      = 40; // release before the next step, so repeats retrigger
static constexpr uint32_t MIN_HOLD_MS = 30; // the blob's poll is 10-20 ms
static constexpr uint32_t TAP_MS      = 60; // a button press, plus the same again to settle

static bool     playing   = false;
static uint16_t idx       = 0;
static uint8_t  phase     = 0;     // 0 start step, 1 holding, 2 released
static uint32_t stepStart = 0;     // nominal
static uint32_t tNext     = 0;
static uint8_t  pass      = 0;
static bool     passStart = true;
static bool     meowOnly  = false;
static uint8_t  voiceIdx  = 0;     // into PASS_VOICE
static uint8_t  pendingCC = 0xFF;  // a button to tap between steps
static bool     warnedMissing = false;

static uint32_t tickMs() { return 60000UL / bpm / 4; }

// Blocking button press. Returns how long it took, so the caller can shift the
// schedule rather than let the next notes catch up in a rush.
static uint32_t tapButton(uint8_t cc)
{
    const uint8_t pos = posOfCC[cc - CC_PIANO];
    if (pos == 0xFF)
    {
        p("  %s: not in the map", ccName(cc));
        return 0;
    }
    const uint32_t t0 = millis();
    inject::tap(pos, TAP_MS);
    delay(TAP_MS);
    p("  [%s]", ccName(cc));
    return millis() - t0;
}

static void rewind()
{
    inject::open();
    playing   = false;
    idx       = 0;
    phase     = 0;
    pass      = 0;
    voiceIdx  = 0;
    passStart = true;
}

static void start()
{
    // A running rhythm or demo song would talk over us.
    tapButton(CC_STOP);
    tNext   = millis();
    playing = true;
    p("playing at %u BPM", bpm);
}

static void tick()
{
    const uint32_t now = millis();
    if (!playing || (int32_t)(now - tNext) < 0)
        return;

    switch (phase)
    {
    case 0:
    {
        if (idx == 0 && passStart)
        {
            passStart = false;
            const uint8_t voice = meowOnly ? CC_MEOW : PASS_VOICE[voiceIdx % N_PASS_VOICES];
            p("pass %u: %s", pass + 1, ccName(voice));
            tNext += tapButton(voice);
        }
        const Step &st  = TUNE[idx];
        const uint32_t len = st.len * tickMs();
        stepStart = tNext;

        if (st.note == 0)
        {
            tNext = stepStart + len;
            phase = 2;
            break;
        }
        const uint8_t pos = posOfNote[st.note];
        if (pos == 0xFF)
        {
            if (!warnedMissing)
            {
                warnedMissing = true;
                p("  note %u is not on this keybed - played as a rest", st.note);
            }
            tNext = stepStart + len;
            phase = 2;
            break;
        }
        uint32_t hold = len > GAP_MS + MIN_HOLD_MS ? len - GAP_MS : MIN_HOLD_MS;
        inject::press(pos);
        p("  %-3s%d", NOTE_NAMES[st.note % 12], (int)st.note / 12 - 1);
        tNext = stepStart + hold;
        phase = 1;
        break;
    }

    case 1:
        inject::open();
        tNext = stepStart + TUNE[idx].len * tickMs();
        phase = 2;
        break;

    case 2:
        if (pendingCC != 0xFF)
        {
            const uint8_t cc = pendingCC;
            pendingCC = 0xFF;
            tNext += tapButton(cc);
        }
        if (++idx >= TUNE_LEN)
        {
            idx = 0;
            ++pass;
            ++voiceIdx;
            passStart = true;
        }
        phase = 0;
        break;
    }
}

// ---------------------------------------------------------------------------

static void banner()
{
    p("");
    p("=== Meowsic injection demo ======================================");
    p("    Korobeiniki, %u steps, one pass per voice, meow every other pass", TUNE_LEN);
    p("    %u BPM   %s", bpm, meowOnly ? "meow only" : "rotating voices");
    p("");
    p("space play/pause   s stop   x release   +/- tempo   m meow only   n next voice");
    p("1-5 piano bells meow organ banjo   c catface   t toy STOP   ? this");
    p("================================================================");
}

void setup()
{
    inject::begin();
    indexMap();

    Serial.begin(USB_BAUD);
    delay(300); // let the host reopen the port after the reset
    banner();

    delay(1700);
    start();
}

void loop()
{
    if (Serial.available())
    {
        const int ch = Serial.read();
        switch (ch)
        {
        case '\r':
        case '\n':
            break;

        case ' ':
            if (playing)
            {
                inject::open();
                playing = false;
                p("paused");
            }
            else
                start();
            break;
        case 's':
            rewind();
            p("stopped");
            break;
        case 'x':
            inject::open();
            break;

        case '+':
            if (bpm < 240) bpm += 10;
            p("%u BPM", bpm);
            break;
        case '-':
            if (bpm > 60) bpm -= 10;
            p("%u BPM", bpm);
            break;

        case 'm':
            meowOnly = !meowOnly;
            p(meowOnly ? "meow only" : "rotating voices");
            if (meowOnly)
                pendingCC = CC_MEOW;
            break;
        case 'n':
            ++voiceIdx;
            pendingCC = PASS_VOICE[voiceIdx % N_PASS_VOICES];
            break;
        case '1': case '2': case '3': case '4': case '5':
            pendingCC = KEY_VOICE[ch - '1'];
            break;
        case 'c':
            pendingCC = CC_CATFACE;
            break;
        case 't':
            pendingCC = CC_STOP;
            break;
        case '?':
            banner();
            break;
        default:
            break;
        }
    }

    if (!playing && pendingCC != 0xFF)
    {
        const uint8_t cc = pendingCC;
        pendingCC = 0xFF;
        tapButton(cc);
    }

    tick();
    delay(1);
}
