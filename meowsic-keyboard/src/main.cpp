#include <Arduino.h>
#include <stdarg.h>

#include "config.h"
#include "inject.h"
#include "keybed.h"
#include "mcp23017.h"
#include "midi_out.h"

// ============================================================================
//  Meowsic MIDI - build order step 4: keybed -> MCP23017 -> MIDI out.
//  The toy is silent in this stage. Injection, MIDI in and the looper are not
//  implemented yet; the only thing done for them here is parking the mux INH
//  line high so the cat does not meow on reset.
// ============================================================================

// What each position is currently sounding, so note-off always matches the
// note-on even if TRANSPOSE changes while a key is down.
static uint8_t sounding[N_POS];
static constexpr uint8_t NOT_SOUNDING = 0xFF;

static uint8_t i2cFails = 0;

// ---------------------------------------------------------------------------

static void log(const char *fmt, ...)
{
#if !USB_MIDI
    char buf[96];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    Serial.println(buf);
#else
    (void)fmt; // UART0 is a MIDI port in this build, keep it clean
#endif
}

// ---------------------------------------------------------------------------

static void panic()
{
    for (uint8_t p = 0; p < N_POS; ++p)
    {
        if (sounding[p] != NOT_SOUNDING)
        {
            midi::noteOff(NOTE_CHANNEL, sounding[p]);
            sounding[p] = NOT_SOUNDING;
        }
    }
    midi::allSoundOff(NOTE_CHANNEL);
    if (CTRL_CHANNEL != NOTE_CHANNEL)
        midi::allSoundOff(CTRL_CHANNEL);

    inject::open(); // release any injected key
    keybed::reset();
    log("PANIC - all notes off");
}

static void pollPanic()
{
    static bool lastLevel = true; // pulled up, so idle is high
    static uint32_t lastMs = 0;

    const bool level = digitalRead(PIN_PANIC);
    if (level == lastLevel)
        return;
    if (millis() - lastMs < 50)
        return; // crude debounce, it is one button

    lastMs = millis();
    lastLevel = level;
    if (!level)
        panic(); // act on press
}

// ---------------------------------------------------------------------------

static void handle(const KeyEvent &e)
{
    const PosMap &m = POSITION_MAP[e.pos];

    log("%s pos=%2u  col=%u row=%u  kind=%u data=%u",
        e.down ? "DOWN" : "UP  ", e.pos, e.pos / N_ROWS, e.pos % N_ROWS,
        (unsigned)m.kind, m.data);

    switch (m.kind)
    {
    case K_NOTE:
    {
        if (e.down)
        {
            if (sounding[e.pos] != NOT_SOUNDING)
                break; // already on
            const int n = (int)m.data + TRANSPOSE;
            if (n < 0 || n > 127)
                break;
            sounding[e.pos] = (uint8_t)n;
            midi::noteOn(NOTE_CHANNEL, (uint8_t)n, NOTE_VELOCITY);
        }
        else
        {
            if (sounding[e.pos] == NOT_SOUNDING)
                break;
            midi::noteOff(NOTE_CHANNEL, sounding[e.pos]);
            sounding[e.pos] = NOT_SOUNDING;
        }
        break;
    }
    case K_CC:
        midi::cc(CTRL_CHANNEL, m.data, e.down ? 127 : 0);
        break;

    case K_NONE:
    default:
        break;
    }
}

// ---------------------------------------------------------------------------

void setup()
{
    inject::begin(); // INH high before anything else

    // GPIO34 is input-only with no internal pull-up. The 10k to 3.3 V is
    // mandatory or this floats and fires randomly.
    pinMode(PIN_PANIC, INPUT);

    for (uint8_t p = 0; p < N_POS; ++p)
        sounding[p] = NOT_SOUNDING;

    midi::begin();
    delay(50);
    log("Meowsic MIDI - keybed scan stage");

    while (!keybed::begin())
    {
        // Almost always RESET (pin 18) floating, or a missing 2.2k pull-up.
        log("MCP23017 not responding at 0x%02X", MCP_ADDR);
        delay(500);
    }
    log("MCP23017 up. Frame period %u ms.", (unsigned)SCAN_PERIOD_MS);
}

void loop()
{
    const uint32_t t0 = millis();

    if (keybed::scan())
    {
        i2cFails = 0;
    }
    else if (++i2cFails >= I2C_FAIL_LIMIT)
    {
        // Do not let a dropped bus leave notes hanging.
        panic();
        log("I2C recovery");
        mcp::begin();
        i2cFails = 0;
    }

    KeyEvent e;
    while (keybed::nextEvent(e))
        handle(e);

    pollPanic();

    // delay() yields to the idle task, which keeps the task watchdog happy.
    // Never less than 1 ms.
    const uint32_t dt = millis() - t0;
    delay(dt >= SCAN_PERIOD_MS ? 1 : SCAN_PERIOD_MS - dt);
}
