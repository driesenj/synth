#include <Arduino.h>
#include <stdarg.h>

#include "arp.h"
#include "auxout.h"
#include "clock.h"
#include "config.h"
#include "controls.h"
#include "cv.h"
#include "inject.h"
#include "keybed.h"
#include "led.h"
#include "looper.h"
#include "mcp23017.h"
#include "midi_in.h"
#include "midi_out.h"
#include "router.h"
#include "settings.h"

// ============================================================================
//  Meowsic MIDI - stages 1 to 3 of docs/firmware.md: the panel, CV/gate,
//  the router, MIDI in, the clock, the looper and the arpeggiator. Keys go
//  through the router - a tap into the toy, a note on MIDI out, CV/gate on
//  the channel the switch selects, transposed by the pots - and so do notes
//  arriving on MIDI channel 1, the arp's steps and the loop's playback;
//  MIDI channel 2 drives the other CV/gate pair. The buttons have their new
//  meanings (firmware.md section 2): voices and catface as before, record /
//  play / STOP as the looper's transport, ♪ as tap tempo, the rhythm
//  buttons as settings, every setting also reachable over CC and kept in
//  NVS. AUX draws one of eleven shapes on the clock. Panic is a long press
//  of STOP.
// ============================================================================

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
//  Text-mode diagnostics (USB_MIDI 0): every change of state is logged as it
//  happens - a setting, the pots, the switch, a gate, a DAC code - and 's'
//  on the monitor dumps all of it. This is what the acceptance run in
//  docs/tests.md reads.
// ---------------------------------------------------------------------------

#if !USB_MIDI
static const char *const GATE_NAMES[]      = {"legato", "retrigger"};
static const char *const GLIDE_NAMES[]     = {"off", "short", "long"};
static const char *const AUX_WAVE_NAMES[]  = {"saw up", "saw down", "triangle", "sine", "square",
                                              "random", "clock", "reset", "envelope", "mod wheel", "off"};
static const char *const AUX_RATE_NAMES[]  = {"per loop", "per bar", "per beat"};
static const char *const ARP_ORDER_NAMES[] = {"up", "down", "up-down", "as played"};
static const char *const ARP_DIV_NAMES[]   = {"16ths", "8ths", "quarters"};

static const char *const LOOP_NAMES[]      = {"empty", "armed", "recording", "playing", "overdub", "stopped"};
static const char *const CLOCK_NAMES[]     = {"internal", "midi", "jack"};

static const char *onOff(bool b) { return b ? "on" : "off"; }
static float cvVolts(int32_t code) { return code < 0 ? 0.0f : code * 3.3f / 4096.0f * 1.5f; }

// Log the fields of b that differ from a, or all of them.
static void logSettings(const Settings &a, const Settings &b, bool all)
{
    if (all || a.quantLoop != b.quantLoop)   log("  quantise loop  %s", onOff(b.quantLoop));
    if (all || a.quantPitch != b.quantPitch) log("  quantise pitch %s", onOff(b.quantPitch));
    if (all || a.gateMode != b.gateMode)     log("  gate mode      %s", GATE_NAMES[b.gateMode]);
    if (all || a.glide != b.glide)           log("  glide          %s", GLIDE_NAMES[b.glide]);
    if (all || a.auxWave != b.auxWave)       log("  aux waveform   %u %s", b.auxWave, AUX_WAVE_NAMES[b.auxWave]);
    if (all || a.auxRate != b.auxRate)       log("  aux rate       %s", AUX_RATE_NAMES[b.auxRate]);
    if (all || a.arpOn != b.arpOn)           log("  arp            %s", onOff(b.arpOn));
    if (all || a.arpOrder != b.arpOrder)     log("  arp order      %s", ARP_ORDER_NAMES[b.arpOrder]);
    if (all || a.arpDiv != b.arpDiv)         log("  arp rate       %s", ARP_DIV_NAMES[b.arpDiv]);
    if (all || a.toyNotes != b.toyNotes)     log("  toy notes      %s", onOff(b.toyNotes));
    if (all || a.bpm != b.bpm)               log("  tempo          %u", b.bpm);
}

static void logChannel(uint8_t ch)
{
    uint8_t note;
    const bool held = cv::sounding(ch, note);
    const int32_t code = cv::written(ch);
    if (held)
        log("  CV %c  gate %-4s note %3u  code %4ld  %.3f V", 'A' + ch,
            cv::gate(ch) ? "high" : "low", note, (long)code, cvVolts(code));
    else
        log("  CV %c  gate %-4s          code %4ld  %.3f V", 'A' + ch,
            cv::gate(ch) ? "high" : "low", (long)code, cvVolts(code));
}

static void logLoop(uint8_t ch)
{
    log("  loop %c%c %-9s %.2f beats  %u events  layer %u", 'A' + ch,
        ch == looper::active() ? '*' : ' ', LOOP_NAMES[looper::state(ch)],
        (float)looper::lengthTicks(ch) / (float)TICKS_PER_BEAT, looper::eventCount(ch), looper::layer(ch));
}

static void logClock()
{
    log("  clock %-8s %.1f bpm", CLOCK_NAMES[clk::source()], clk::bpm());
}

static void logAux()
{
    const uint8_t v = aux::level();
    log("  aux   %3u  %.2f V", v, v * 3.3f / 255.0f * PANEL_LOGIC_GAIN);
}

static void dumpState()
{
    log("state:");
    logSettings(settings::current, settings::current, true);
    log("  keys -> CV %c   base %+.2f   tune %+.2f", 'A' + router::keysChannel(),
        controls::basePitch(), controls::tune());
    logChannel(0);
    logChannel(1);
    logClock();
    logLoop(0);
    logLoop(1);
    logAux();
}

static void watch()
{
    static bool primed = false;
    static Settings last;
    static float lastBase, lastTune;
    static uint8_t lastCh;
    static bool lastGate[cv::N_CH];
    static int32_t lastCode[cv::N_CH];
    static uint32_t lastPotLog, lastCodeLog[cv::N_CH];
    static looper::State lastLoop[looper::N_LOOPS];
    static uint8_t lastLayer[looper::N_LOOPS];
    static clk::Source lastSrc;
    static float lastBpm;

    const uint32_t now = millis();
    const Settings &s = settings::current;
    const float base = controls::basePitch(), tune = controls::tune();
    const uint8_t ch = router::keysChannel();

    if (!primed)
    {
        last = s;
        lastBase = base;
        lastTune = tune;
        lastCh = ch;
        for (uint8_t c = 0; c < cv::N_CH; ++c)
        {
            lastGate[c] = cv::gate(c);
            lastCode[c] = cv::written(c);
            lastCodeLog[c] = 0;
        }
        lastPotLog = 0;
        for (uint8_t l = 0; l < looper::N_LOOPS; ++l)
        {
            lastLoop[l] = looper::state(l);
            lastLayer[l] = looper::layer(l);
        }
        lastSrc = clk::source();
        lastBpm = clk::bpm();
        primed = true;
        return;
    }

    logSettings(last, s, false);
    last = s;

    for (uint8_t l = 0; l < looper::N_LOOPS; ++l)
    {
        if (looper::state(l) != lastLoop[l] || looper::layer(l) != lastLayer[l])
        {
            lastLoop[l] = looper::state(l);
            lastLayer[l] = looper::layer(l);
            logLoop(l);
        }
    }
    if (clk::source() != lastSrc || fabsf(clk::bpm() - lastBpm) > 0.5f)
    {
        lastSrc = clk::source();
        lastBpm = clk::bpm();
        logClock();
    }

    // The pots, at most ten times a second while they move.
    if ((fabsf(base - lastBase) > 0.005f || fabsf(tune - lastTune) > 0.005f) && now - lastPotLog >= 100)
    {
        log("pots: base %+.2f  tune %+.2f", base, tune);
        lastBase = base;
        lastTune = tune;
        lastPotLog = now;
    }

    if (ch != lastCh)
    {
        log("keys -> CV %c, loop %c", 'A' + ch, 'A' + ch);
        lastCh = ch;
    }

    for (uint8_t c = 0; c < cv::N_CH; ++c)
    {
        const bool g = cv::gate(c);
        const int32_t code = cv::written(c);
        // A gate edge is always logged; a code change at most ten times a
        // second, since a glide changes it every frame.
        if (g != lastGate[c] || (code != lastCode[c] && now - lastCodeLog[c] >= 100))
        {
            logChannel(c);
            lastGate[c] = g;
            lastCode[c] = code;
            lastCodeLog[c] = now;
        }
    }
}
#endif

// ---------------------------------------------------------------------------

// Everything sounding stops; the keybed's held state is left alone, so keys
// still down release normally later (their note-offs find nothing to do) and
// the STOP button that triggered this is not seen as pressed again.
static void panic()
{
    looper::stopAll(); // or the loops play the notes straight back in
    arp::allOff();
    router::panic();   // note-offs for everything sounding, both gates low
    inject::flush();   // drop queued taps, open the switch
    led::flash(255, 255, 255, 300);
    log("PANIC - all notes off");
}

// A dropped bus: the scan state may be garbage, so forget it too and bring
// the expander and the DACs back.
static void recover()
{
    panic();
    keybed::reset();
    log("I2C recovery");
    mcp::begin();
    cv::resync(); // the DACs share the bus; write them again
}

static void handleCommand(controls::Cmd c)
{
    switch (c)
    {
    case controls::CMD_PANIC:     panic(); break;
    case controls::CMD_TAP_TEMPO:
        if (clk::tap())
            log("tap: %u bpm", settings::current.bpm);
        break;
    case controls::CMD_STOP:      looper::stop(); break;
    case controls::CMD_RECORD:    looper::record(); break;
    case controls::CMD_UNDO:      looper::undo(); break;
    case controls::CMD_PLAY:      looper::play(); break;
    case controls::CMD_CLEAR:     looper::clear(); break;
    }
}

// ---------------------------------------------------------------------------
//  The LED (docs/firmware.md 3.7): the looper's state as the base colour,
//  the beat as a pulse on top of it. Settings blinks and the tap flash are
//  led's own overlay and come through unchanged.
// ---------------------------------------------------------------------------

static void updateLed()
{
    static uint8_t lastR = 1, lastG = 1, lastB = 1;

    // A pulse that starts on each beat and fades over 120 ms, stronger on
    // beat 1.
    const uint32_t age = clk::beatAgeMs();
    float pulse = age < 120 ? (120.0f - (float)age) / 120.0f : 0.0f;
    if (clk::beatInBar() != 0)
        pulse *= 0.5f;

    uint8_t r = 0, g = 0, b = 0;
    switch (looper::state())
    {
    case looper::EMPTY:
        if (clk::tapped() || clk::source() != clk::SRC_INTERNAL)
            r = g = b = (uint8_t)(40.0f * pulse);   // a dim tick once there is a tempo
        break;
    case looper::ARMED:
        r = ((millis() / 250) & 1) ? 255 : 0;
        break;
    case looper::RECORDING:
        r = 255;
        break;
    case looper::PLAYING:
        g = (uint8_t)(60.0f + 195.0f * pulse);
        break;
    case looper::OVERDUB:
        r = 200;
        g = (uint8_t)(50.0f + 120.0f * pulse);
        break;
    case looper::STOPPED:
        g = 25;
        break;
    }
    if (r != lastR || g != lastG || b != lastB)
    {
        led::set(r, g, b);
        lastR = r;
        lastG = g;
        lastB = b;
    }
}

static void handle(const KeyEvent &e)
{
    const PosMap &m = POSITION_MAP[e.pos];

    log("%s pos=%2u  col=%u row=%u  kind=%u data=%u",
        e.down ? "DOWN" : "UP  ", e.pos, e.pos / N_ROWS, e.pos % N_ROWS,
        (unsigned)m.kind, m.data);

    switch (m.kind)
    {
    case K_NOTE:
        if (e.down)
            router::noteOn(m.data);
        else
            router::noteOff(m.data);
        break;

    case K_CC:
        controls::onButton(m.data, e.down);
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
    led::begin();
    settings::begin();

    midi::begin();
    delay(50);
    log("Meowsic MIDI - the full firmware (docs/firmware.md)");

    while (!keybed::begin())
    {
        // Almost always RESET (pin 18) floating, or a missing 2.2k pull-up.
        log("MCP23017 not responding at 0x%02X", MCP_ADDR);
        delay(500);
    }
    log("MCP23017 up. Frame period %u ms.", (unsigned)SCAN_PERIOD_MS);

    // Wire is up now, so the DACs can be parked; then the router, then the
    // panel, which tells the router where the switch and the pots sit.
    cv::begin();
    router::begin();
    controls::begin();
    midi_in::begin();
    clk::begin();
    looper::begin();
    arp::begin();
    aux::begin();
#if !USB_MIDI
    dumpState();
    log("monitor: s = state, x = panic");
#endif
}

#if !USB_MIDI
static void pollMonitor()
{
    while (Serial.available())
    {
        switch (Serial.read())
        {
        case 's': dumpState(); break;
        case 'x': panic(); break;
        default: break;
        }
    }
}
#endif

void loop()
{
    const uint32_t t0 = millis();

    if (keybed::scan())
    {
        i2cFails = 0;
    }
    else if (++i2cFails >= I2C_FAIL_LIMIT)
    {
        recover(); // do not let a dropped bus leave notes hanging
        i2cFails = 0;
    }

    clk::service();    // the tick everything below reads

    KeyEvent e;
    while (keybed::nextEvent(e))
        handle(e);
    midi_in::service();  // both sockets, into the router and cv

    controls::service(); // long presses, pots, switch
    controls::Cmd c;
    while (controls::nextCommand(c))
        handleCommand(c);

    looper::service();   // playback, and the pass wrapping
    arp::service();      // a step on its grid
    cv::service();       // glide, retrigger, DAC writes
    aux::service();      // the shape, on the clock
    inject::service();   // plays the tap queue out, one switch closure at a time
    updateLed();
    led::service();
    settings::service();
#if !USB_MIDI
    watch();
    pollMonitor();
#endif

    // delay() yields to the idle task, which keeps the task watchdog happy.
    // Never less than 1 ms.
    const uint32_t dt = millis() - t0;
    delay(dt >= SCAN_PERIOD_MS ? 1 : SCAN_PERIOD_MS - dt);
}
