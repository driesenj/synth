#include <Arduino.h>
#include <Wire.h>
#include <stdarg.h>

#include "config.h"
#include "inject.h"
#include "keybed.h"
#include "mcp23017.h"
#include "mcp4725.h"

// ============================================================================
//  Meowsic MIDI - panel test: every function from the outside.
//
//  Built as its own environment:  pio run -e systest -t upload
//
//  For the finished instrument: every board cabled, the jacks, pots, CV
//  select switch, DIN sockets and the record-button LED on the panel. The
//  synth's +-12 V and 5 V on, the toy on, USB for the monitor. Everything is
//  checked where a user would meet it - at a jack with a meter or a patch
//  cable, at a socket with a MIDI cable, at a knob by turning it - on the
//  production drivers, so a pass here is the firmware's own paths working.
//
//  What you need: a meter, two 3.5 mm patch cables, a MIDI cable. A VCO, a
//  clock source and a MIDI keyboard or DAW make three of the checks nicer but
//  none of them necessary - each of those has a self-contained loopback.
//
//  Boot, and r, runs the automatic part:
//    0  the rails, for the meter
//    1  I2C: expander and both DACs answer, the scan setup takes, EEPROMs 0
//    2  keybed: eight frames, nothing held (or what is)
//    3  inputs at rest: switch position, clock in and MIDI RX idle high, pots
//    4  LED: red, green, blue, then all three
//  Then single-letter commands. Outputs, for a meter at the jack tip:
//    c  CV: both DACs to the next of 0, 25, 50, 75, 100 % per press
//    v  octave: both CVs alternate 0 and 12 semitones every 4 s - the 1 V/oct
//       calibration of CV_CODES_PER_SEMITONE / CV2_CODES_PER_SEMITONE
//    1  toggle gate 1        2  toggle gate 2        a  AUX to the next level
//    g  sequence: an octave in semitones on CV1 with gate 1 pulsing, then the
//       same on CV2 / gate 2, AUX ramping over each - for a VCO or a scope
//  Inputs:
//    s  CV select: flip the switch within 10 s, the level must change
//    p  pots: turn each end to end; the range seen is tracked and judged
//    k  clock loopback: patch the gate 1 jack to the clock-in jack; gate 1 is
//       toggled ten times and GPIO35 must follow it, inverted
//    x  external clock: count pulses at the clock-in jack for 5 s (or patch
//       gate 1 in while g runs, for 4 Hz)
//    b  keybed: press every key and button; each is named, and stopping the
//       check lists the ones not seen
//  MIDI:
//    m  loopback: a MIDI cable from the out socket to the in socket; twelve
//       bytes out on UART2 must come back through the opto
//    o  beacon: a note every 500 ms out of the DIN socket, for a synth or DAW
//    n  monitor: whatever arrives at the in socket, decoded, for 20 s
//  Sound:
//    j  a five-note run through the injector: the toy plays it, and the
//       audio jack carries it
//  i  live inputs, printed on change    l  LED again    r  re-run    ?  this
//  Any other key stops whatever is running.
// ============================================================================

static void p(const char *fmt, ...)
{
    char buf[200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    Serial.println(buf);
}

static const char *NOTE_NAMES[12] = {"C", "C#", "D", "D#", "E", "F",
                                     "F#", "G", "G#", "A", "A#", "B"};

static void noteName(uint8_t note, char *out, size_t n)
{
    snprintf(out, n, "%s%d", NOTE_NAMES[note % 12], (int)(note / 12) - 1);
}

static void posLabel(uint8_t pos, char *out, size_t n)
{
    const PosMap &m = POSITION_MAP[pos];
    char nm[8];
    if (m.kind == K_NOTE)
    {
        noteName(m.data, nm, sizeof(nm));
        snprintf(out, n, "note %u %s", m.data, nm);
    }
    else if (m.kind == K_CC)
        snprintf(out, n, "cc%u %s", m.data, ccName(m.data));
    else
        snprintf(out, n, "unmapped");
}

static uint8_t posOfNote(uint8_t note)
{
    for (uint8_t pos = 0; pos < N_POS; ++pos)
        if (POSITION_MAP[pos].kind == K_NOTE && POSITION_MAP[pos].data == note)
            return pos;
    return 0xFF;
}

static uint8_t lowestNote()
{
    for (int n = 0; n < 128; ++n)
        if (posOfNote((uint8_t)n) != 0xFF)
            return (uint8_t)n;
    return 0xFF;
}

// ---- what the meter should see ---------------------------------------------
static float cvVolts(uint16_t code) { return code * 3.3f / 4096.0f * 1.5f; }
static float gateVolts(bool high) { return high ? 3.3f * PANEL_LOGIC_GAIN : 0.0f; }
static float auxVolts(uint8_t code) { return code * 3.3f / 255.0f * PANEL_LOGIC_GAIN; }
static uint16_t semitoneCode(uint8_t ch, uint8_t semis)
{
    const float per = ch ? CV2_CODES_PER_SEMITONE : CV_CODES_PER_SEMITONE;
    return (uint16_t)(semis * per + 0.5f);
}

// ---- state ------------------------------------------------------------------
static bool haveMcp, haveDac1, haveDac2;
static bool gate1, gate2;
static uint8_t cvStep = 0, auxStep = 0;

static const uint16_t CV_CODES[]  = {0, 1024, 2048, 3072, 4095};
static const uint8_t  AUX_CODES[] = {0, 64, 128, 192, 255};

// Running modes. Independent, so a beacon can feed the monitor through a
// cable and the sequence can feed the clock counter; any unknown key ends
// them all.
static bool inputsOn, seqOn, octOn, beaconOn, keybedOn, potsOn, midiInOn;
static uint32_t midiInEnd;

static bool ack(uint8_t addr)
{
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

static void writeCv(uint8_t ch, uint16_t code)
{
    if (ch == 0 && haveDac1) dac::write(DAC_ADDR, code);
    if (ch == 1 && haveDac2) dac::write(DAC2_ADDR, code);
}

static void setGate(uint8_t ch, bool high)
{
    (ch ? gate2 : gate1) = high;
    digitalWrite(ch ? PIN_GATE2 : PIN_GATE, high ? HIGH : LOW);
}

static void stopAll(bool say)
{
    const bool was = inputsOn || seqOn || octOn || beaconOn || keybedOn || potsOn || midiInOn;
    inputsOn = seqOn = octOn = beaconOn = keybedOn = potsOn = midiInOn = false;
    inject::flush();
    if (was && say)
        p("stopped");
}

// ---------------------------------------------------------------------------
//  Automatic part
// ---------------------------------------------------------------------------
static void checkRails()
{
    p("[0] rails - meter these first, the rest assumes them:");
    p("    +12 V  TL074 pin 4, TL072 pin 8      -12 V  TL074 pin 11, TL072 pin 4");
    p("    5 V    4051 pin 16 (both), the toy's battery contacts");
    p("    3V3    I2C board rail, MCP23017 pin 9");
}

static void checkI2c()
{
    p("[1] I2C board");
    haveMcp = keybed::begin(); // mcp::begin(): ACK, then the scan register setup
    p("    MCP23017 0x%02X   %s", MCP_ADDR,
      haveMcp ? "answers, scan setup written" : "NO ACK  <- selftest, checks 1-3");

    struct
    {
        uint8_t addr;
        bool &have;
        const char *name;
    } dacs[] = {{DAC_ADDR, haveDac1, "CV1"}, {DAC2_ADDR, haveDac2, "CV2"}};
    for (auto &d : dacs)
    {
        d.have = ack(d.addr);
        if (!d.have)
        {
            p("    MCP4725 0x%02X   NO ACK  <- %s DAC: VCC through its 10 ohm, ADDR jumper", d.addr, d.name);
            continue;
        }
        dac::State s;
        if (!dac::read(d.addr, s))
        {
            p("    MCP4725 0x%02X   ACKs but the read failed  <- selftest check 7", d.addr);
            continue;
        }
        dac::write(d.addr, 0);
        p("    MCP4725 0x%02X   %s DAC answers, EEPROM %u%s", d.addr, d.name, s.eepromCode,
          s.eepromCode == 0 ? " (0 V at power-up)" : "  <- not 0: CV jumps at power-up, run selftest e");
    }
}

static void checkKeybed()
{
    p("[2] keybed");
    if (!haveMcp)
    {
        p("    skipped, no expander");
        return;
    }
    bool ok = true;
    for (uint8_t i = 0; i < 8 && ok; ++i)
    {
        ok = keybed::scan();
        delay(SCAN_PERIOD_MS);
    }
    KeyEvent e;
    while (keybed::nextEvent(e))
        ; // drain: held() is the state we want
    if (!ok)
    {
        p("    scan FAILED mid-frame  <- I2C error, selftest check 5");
        return;
    }
    uint8_t held = 0;
    for (uint8_t pos = 0; pos < N_POS; ++pos)
        if (keybed::held(pos))
        {
            char label[32];
            posLabel(pos, label, sizeof(label));
            p("    held: pos %2u col %u row %u  %s", pos, pos / N_ROWS, pos % N_ROWS, label);
            ++held;
        }
    if (!held)
        p("    8 frames, nothing held - the scan runs");
    else
        p("    %u held - fine if you are pressing them; otherwise a stuck contact or a short", held);
}

static void checkInputs()
{
    p("[3] inputs at rest");
    const bool sel = digitalRead(PIN_CV_SELECT);
    const bool clk = digitalRead(PIN_CLOCK_IN);
    const bool rx  = digitalRead(PIN_MIDI_RX);
    p("    cv select gpio%d  %s   channel %s - flip it and run s to see it move", PIN_CV_SELECT,
      sel ? "high" : "low ", sel ? "A (open)" : "B (closed)");
    p("    clock in  gpio%d  %s   %s", PIN_CLOCK_IN, clk ? "high" : "LOW ",
      clk ? "ok - BC549 off, 10k pull-up" : "<- must be high with nothing at the jack: pull-up missing,"
                                             " or the transistor on (base 100k to GND? C/E swapped? jack tip shorted?)");
    p("    MIDI RX   gpio%d  %s   %s", PIN_MIDI_RX, rx ? "high" : "LOW ",
      rx ? "ok - opto off, 1k pull-up" : "<- must be high when nothing sends: 1k to 3V3 missing, or the opto"
                                          " conducting - a base resistor on pin 5 (collector) instead of pin 4 does that");
    const int a = analogRead(PIN_POT_BASE), b = analogRead(PIN_POT_TUNE);
    p("    base pitch gpio%d = %4d (%.2f V)   tune gpio%d = %4d (%.2f V)   - p sweeps them",
      PIN_POT_BASE, a, a * 3.3f / 4095.0f, PIN_POT_TUNE, b, b * 3.3f / 4095.0f);
}

static void ledCycle()
{
    p("[4] LED in the record button: red, green, blue, then all three, half a second each");
    const int pins[] = {PIN_LED_RED, PIN_LED_GREEN, PIN_LED_BLUE};
    for (int pin : pins)
    {
        digitalWrite(pin, HIGH);
        delay(500);
        digitalWrite(pin, LOW);
    }
    for (int pin : pins)
        digitalWrite(pin, HIGH);
    delay(500);
    for (int pin : pins)
        digitalWrite(pin, LOW);
}

static void help()
{
    p("out:  c CV step   v octave   1 / 2 gates   a AUX step   g sequence (VCO)");
    p("in:   s switch   p pots   k clock loopback   x count clock   b keybed");
    p("MIDI: m loopback   o beacon out   n monitor in        sound: j run");
    p("i live inputs   l LED   r re-run   ? this   - any other key stops");
}

static void runAll()
{
    stopAll(false);
    p("");
    p("=== panel test =====================================================");
    p("    rails on, toy on. Meter at the jack tips, GND at any jack sleeve");
    checkRails();
    checkI2c();
    checkKeybed();
    checkInputs();
    ledCycle();
    p("====================================================================");
    help();
}

// ---------------------------------------------------------------------------
//  Outputs
// ---------------------------------------------------------------------------
static void cvStepNext()
{
    if (!haveDac1 && !haveDac2)
    {
        p("no DAC answered - run r");
        return;
    }
    octOn = seqOn = false;
    cvStep = (uint8_t)((cvStep + 1) % 5);
    const uint16_t code = CV_CODES[cvStep];
    writeCv(0, code);
    writeCv(1, code);
    p("CV step %u/4  code %4u  ->  %.2f V at the CV1 and CV2 jacks%s", cvStep, code, cvVolts(code),
      cvStep == 0 ? "  (a few mV over 0 is the op-amp's offset)" : "");
}

static void auxStepNext()
{
    seqOn = false;
    auxStep = (uint8_t)((auxStep + 1) % 5);
    const uint8_t code = AUX_CODES[auxStep];
    dacWrite(PIN_AUX, code);
    p("AUX code %3u  ->  %.2f V at the AUX jack, nominal - the ESP32's DAC is within ~0.15 V of it",
      code, auxVolts(code));
}

static void gateToggle(uint8_t ch)
{
    seqOn = false;
    const bool high = !(ch ? gate2 : gate1);
    setGate(ch, high);
    p("gate %u %s  ->  %.1f V at the gate %u jack", ch + 1, high ? "HIGH" : "low ", gateVolts(high), ch + 1);
}

// Both CVs alternate 0 and 12 semitones. Meter one jack: adjust that
// channel's CV_CODES_PER_SEMITONE until the two readings differ by 1.000 V.
static void octaveTick()
{
    static uint32_t next;
    static bool high;
    const uint32_t now = millis();
    if ((int32_t)(now - next) < 0)
        return;
    next = now + 4000;
    high = !high;
    const uint16_t c1 = high ? semitoneCode(0, 12) : 0, c2 = high ? semitoneCode(1, 12) : 0;
    writeCv(0, c1);
    writeCv(1, c2);
    p("  %s   CV1 code %4u -> %.3f V   CV2 code %4u -> %.3f V   (nominal at the jacks)",
      high ? "octave up" : "base     ", c1, cvVolts(c1), c2, cvVolts(c2));
}

// An octave in semitones, 250 ms a step, gate high for the first half of
// each; channel A for one octave, then channel B, and round again. AUX ramps
// 0 -> full over each octave, the loop-phase shape the firmware will give it.
static void sequenceTick()
{
    static uint32_t next;
    static uint8_t ch, step;
    static bool gateUp;
    const uint32_t now = millis();
    if ((int32_t)(now - next) < 0)
        return;

    if (!gateUp)
    {
        if (step == 0)
            p("  channel %c: CV%u climbs an octave in semitones, gate %u pulses, AUX ramps",
              ch ? 'B' : 'A', ch + 1, ch + 1);
        writeCv(ch, semitoneCode(ch, step));
        dacWrite(PIN_AUX, (uint8_t)(step * 255 / 12));
        setGate(ch, true);
        gateUp = true;
        next = now + 125;
        return;
    }

    setGate(ch, false);
    gateUp = false;
    next = now + 125;
    if (++step > 12)
    {
        step = 0;
        writeCv(ch, 0);
        ch ^= 1;
    }
}

// ---------------------------------------------------------------------------
//  Inputs
// ---------------------------------------------------------------------------
static void switchCheck()
{
    const bool start = digitalRead(PIN_CV_SELECT);
    p("CV select: now %s - flip the switch within 10 s", start ? "A (high, open)" : "B (low, closed)");
    const uint32_t t0 = millis();
    while (millis() - t0 < 10000)
    {
        if (digitalRead(PIN_CV_SELECT) != start)
        {
            delay(50); // settle, a slide switch bounces
            const bool now = digitalRead(PIN_CV_SELECT);
            if (now != start)
            {
                p("    ok    %s -> %s", start ? "A" : "B", now ? "A (high)" : "B (low)");
                return;
            }
        }
        delay(5);
    }
    p("    FAIL  no change in 10 s: the switch is not across J4's two pins, or its cable is open."
      " Stuck low is J4 shorted");
}

static void potsTick()
{
    static int minA, maxA, minB, maxB;
    static uint32_t lastPrint;
    static bool first = true;
    if (first)
    {
        minA = maxA = analogRead(PIN_POT_BASE);
        minB = maxB = analogRead(PIN_POT_TUNE);
        first = false;
    }
    const int a = analogRead(PIN_POT_BASE), b = analogRead(PIN_POT_TUNE);
    bool grew = false;
    if (a < minA) { minA = a; grew = true; }
    if (a > maxA) { maxA = a; grew = true; }
    if (b < minB) { minB = b; grew = true; }
    if (b > maxB) { maxB = b; grew = true; }
    if (grew && millis() - lastPrint > 150)
    {
        lastPrint = millis();
        p("    base pitch %4d  seen %4d..%4d      tune %4d  seen %4d..%4d", a, minA, maxA, b, minB, maxB);
    }
    if (!potsOn) // stopping: the verdict
    {
        first = true;
        struct
        {
            const char *name;
            int lo, hi;
        } pots[] = {{"base pitch", minA, maxA}, {"tune", minB, maxB}};
        for (auto &pt : pots)
        {
            if (pt.lo < 60 && pt.hi > 4030)
                p("    %-10s ok    %d..%d, the whole travel", pt.name, pt.lo, pt.hi);
            else if (pt.hi - pt.lo < 150)
                p("    %-10s FAIL  stuck at %d..%d: the middle lug is not on pin 1 (the ADC), or an outer lug is open."
                  " A brownout at one end of the travel is the middle lug on a rail", pt.name, pt.lo, pt.hi);
            else
                p("    %-10s FAIL  %d..%d, not the whole travel: the end that does not reach its rail"
                  " is open (%s)", pt.name, pt.lo, pt.hi, pt.lo >= 60 ? "GND end" : "3V3 end");
        }
    }
}

static void clockLoopback()
{
    p("clock loopback - patch cable from the gate 1 jack to the clock-in jack");
    const bool wasSeq = seqOn;
    seqOn = false;
    uint8_t good = 0, lowSeen = 0, highSeen = 0;
    for (uint8_t i = 0; i < 10; ++i)
    {
        digitalWrite(PIN_GATE, HIGH);
        delay(20);
        const bool lowWhenHigh = digitalRead(PIN_CLOCK_IN) == LOW;
        digitalWrite(PIN_GATE, LOW);
        delay(20);
        const bool highWhenLow = digitalRead(PIN_CLOCK_IN) == HIGH;
        lowSeen += lowWhenHigh;
        highSeen += highWhenLow;
        good += lowWhenHigh && highWhenLow;
    }
    digitalWrite(PIN_GATE, gate1 ? HIGH : LOW);
    seqOn = wasSeq;

    if (good == 10)
        p("    ok    GPIO%d followed gate 1 inverted, 10 of 10 - gate 1 jack, the cable and the clock-in jack all work",
          PIN_CLOCK_IN);
    else if (lowSeen == 0)
        p("    FAIL  GPIO%d never went low: no 4.5 V at the gate 1 jack (meter it with 1), the cable, or"
          " the clock jack's tip / the BC549 base network (10k from the tip, 100k to GND)", PIN_CLOCK_IN);
    else if (highSeen == 0)
        p("    FAIL  GPIO%d never came back high: collector held low - transistor in backwards,"
          " or its 10k pull-up to 3V3 missing", PIN_CLOCK_IN);
    else
        p("    FAIL  %u of 10 - intermittent: the cable, or a joint", good);
}

static volatile uint32_t clockEdges;
static void IRAM_ATTR onClockEdge() { ++clockEdges; }

static void countClock()
{
    p("counting falling edges at the clock-in jack for 5 s (a rising edge at the jack is a falling one here)");
    clockEdges = 0;
    attachInterrupt(digitalPinToInterrupt(PIN_CLOCK_IN), onClockEdge, FALLING);
    const uint32_t t0 = millis();
    while (millis() - t0 < 5000)
    {
        if (seqOn)
            sequenceTick(); // so a patch cable from gate 1 keeps pulsing
        delay(1);
    }
    detachInterrupt(digitalPinToInterrupt(PIN_CLOCK_IN));
    const uint32_t n = clockEdges;
    if (n == 0)
        p("    none. Nothing plugged in, or the source's pulses never reach 2 V at the tip");
    else
        p("    %lu pulses = %.2f Hz = %.0f BPM at one pulse per beat, %.0f at 24 PPQN",
          (unsigned long)n, n / 5.0f, n * 12.0f, n * 12.0f / 24.0f);
}

static bool seen[N_POS];

static void keybedTick()
{
    if (!keybed::scan())
        return;
    KeyEvent e;
    while (keybed::nextEvent(e))
    {
        char label[32];
        posLabel(e.pos, label, sizeof(label));
        if (e.down)
            seen[e.pos] = true;
        p("    %s pos %2u  %s", e.down ? "DOWN" : "up  ", e.pos, label);
    }
}

static void keybedSummary()
{
    uint8_t mapped = 0, hit = 0;
    char line[200];
    int n = 0;
    for (uint8_t pos = 0; pos < N_POS; ++pos)
    {
        if (POSITION_MAP[pos].kind == K_NONE)
            continue;
        ++mapped;
        if (seen[pos])
        {
            ++hit;
            continue;
        }
        char label[32];
        posLabel(pos, label, sizeof(label));
        if (n < (int)sizeof(line) - 40)
            n += snprintf(line + n, sizeof(line) - n, "%s%s", n ? ", " : "", label);
    }
    if (hit == mapped)
        p("    every one of the %u mapped positions was pressed", mapped);
    else
        p("    %u of %u pressed. Not seen: %s", hit, mapped, line);
}

static void inputsTick()
{
    static bool first = true;
    static bool sel, clk, rx;
    static int a, b;

    const bool s = digitalRead(PIN_CV_SELECT), c = digitalRead(PIN_CLOCK_IN), r = digitalRead(PIN_MIDI_RX);
    const int ra = analogRead(PIN_POT_BASE), rb = analogRead(PIN_POT_TUNE);

    if (!first && s == sel && c == clk && r == rx && abs(ra - a) < 40 && abs(rb - b) < 40)
        return;
    first = false;
    sel = s;
    clk = c;
    rx = r;
    a = ra;
    b = rb;
    p("    cv select %s   clock in %s   MIDI RX %s   base pitch %4d (%.2f V)   tune %4d (%.2f V)",
      s ? "A (high)" : "B (low) ", c ? "high" : "LOW ", r ? "high" : "LOW ",
      a, a * 3.3f / 4095.0f, b, b * 3.3f / 4095.0f);
}

// ---------------------------------------------------------------------------
//  MIDI
// ---------------------------------------------------------------------------
// A phototransistor that takes longer than a bit (32 us) to turn off is
// still holding RX low when the bit after a 0 is sampled, so every first 1
// after a 0 arrives as 0 - the LSB included, since the start bit is a 0.
// What a sent byte becomes under that fault, to recognise it exactly.
static uint8_t slowTurnOff(uint8_t sent)
{
    uint8_t got = 0;
    bool prev = false; // the start bit
    for (uint8_t i = 0; i < 8; ++i)
    {
        const bool bit = (sent >> i) & 1;
        if (bit && prev)
            got |= (uint8_t)(1u << i);
        prev = bit;
    }
    return got;
}

static void midiLoopback()
{
    p("MIDI loopback - a MIDI cable from the out socket to the in socket");
    beaconOn = midiInOn = false;
    while (Serial2.available())
        Serial2.read();

    static const uint8_t pattern[] = {0x90, 0x3C, 0x64, 0x80, 0x3C, 0x00,
                                      0xF8, 0x55, 0xAA, 0x0F, 0xF0, 0xFF};
    const size_t n = sizeof(pattern);
    Serial2.write(pattern, n);
    Serial2.flush();

    uint8_t back[sizeof(pattern)];
    size_t got = 0;
    const uint32_t t0 = millis();
    while (got < n && millis() - t0 < 100)
        if (Serial2.available())
            back[got++] = (uint8_t)Serial2.read();

    size_t wrong = 0;
    for (size_t i = 0; i < got; ++i)
        wrong += back[i] != pattern[i];

    if (got == n && wrong == 0)
    {
        p("    ok    %u bytes out of the DIN socket, the same %u back in through the opto",
          (unsigned)n, (unsigned)n);
        return;
    }
    if (got == 0)
    {
        p("    FAIL  nothing back. The cable, DIN pins 4 and 5 swapped at one socket (silent, swap back),"
          " the 3V3 leg's resistor, the 1N4148 backwards, or the opto's emitter to GND");
        return;
    }
    char hex[3 * sizeof(pattern) + 1];
    int k = 0;
    for (size_t i = 0; i < got; ++i)
        k += snprintf(hex + k, sizeof(hex) - k, "%02X ", back[i]);
    p("    FAIL  %u of %u bytes, %u wrong: %s", (unsigned)got, (unsigned)n, (unsigned)wrong, hex);

    bool slow = got == n;
    for (size_t i = 0; i < got && slow; ++i)
        slow = back[i] == slowTurnOff(pattern[i]);
    if (slow)
    {
        p("          every first 1 after a 0 came back as 0: the opto turns off later than one bit (32 us)");
        p("          but sooner than two. Deep saturation, not the pull-up. Fit 220k from 4N35 pin 6 (base)");
        p("          to pin 4 (emitter); if it still fails, an H11L1 in its place (pinout differs, section 7)");
    }
    else
        p("          missing bytes: the RX pull-up is not 1k, or a joint");
}

static void beaconTick()
{
    static uint32_t next;
    static bool on;
    const uint32_t now = millis();
    if ((int32_t)(now - next) < 0)
        return;
    on = !on;
    const uint8_t msg[3] = {(uint8_t)((on ? 0x90 : 0x80) | NOTE_CHANNEL), 60, (uint8_t)(on ? 100 : 0)};
    Serial2.write(msg, 3);
    next = now + 250;
}

static void midiInTick()
{
    static uint8_t status, need, have, data[2];
    static uint32_t clocks, sensing, lastReport;

    while (Serial2.available())
    {
        const uint8_t b = (uint8_t)Serial2.read();
        if (b >= 0xF8)
        {
            if (b == 0xF8) ++clocks;
            else if (b == 0xFE) ++sensing;
            else p("    %s", b == 0xFA ? "start" : b == 0xFB ? "continue" : b == 0xFC ? "stop" : "realtime");
            continue;
        }
        if (b & 0x80)
        {
            status = b;
            have = 0;
            const uint8_t hi = b & 0xF0;
            need = (hi == 0xC0 || hi == 0xD0) ? 1 : (hi < 0xF0 || b == 0xF2) ? 2 : (b == 0xF1 || b == 0xF3) ? 1 : 0;
            if (b == 0xF0)
                p("    sysex ...");
            else if (b == 0xF7)
                p("    ... end of sysex");
            else if (need == 0)
                p("    status %02X", b);
            continue;
        }
        if (!status)
        {
            p("    data %02X with no status", b);
            continue;
        }
        if (status == 0xF0 || need == 0)
            continue; // sysex payload, or a data byte after a message that takes none
        data[have++] = b;
        if (have < need)
            continue;
        have = 0; // running status: the next data bytes reuse this status
        const uint8_t ch = (status & 0x0F) + 1, hi = status & 0xF0;
        char nm[8];
        noteName(data[0], nm, sizeof(nm));
        if (hi == 0x90 && data[1])
            p("    ch %2u  note on   %3u %-4s vel %u", ch, data[0], nm, data[1]);
        else if (hi == 0x80 || hi == 0x90)
            p("    ch %2u  note off  %3u %s", ch, data[0], nm);
        else if (hi == 0xB0)
            p("    ch %2u  cc %u = %u", ch, data[0], data[1]);
        else if (hi == 0xE0)
            p("    ch %2u  bend %d", ch, (int)((data[1] << 7) | data[0]) - 8192);
        else
            p("    ch %2u  %02X %02X %02X", ch, status, data[0], need > 1 ? data[1] : 0);
    }

    const uint32_t now = millis();
    if ((clocks || sensing) && now - lastReport > 2000)
    {
        lastReport = now;
        p("    ... %lu clock ticks, %lu active sensing", (unsigned long)clocks, (unsigned long)sensing);
    }
    if ((int32_t)(now - midiInEnd) >= 0)
    {
        midiInOn = false;
        p("MIDI in monitor done");
        clocks = sensing = 0;
    }
}

// ---------------------------------------------------------------------------
//  Sound
// ---------------------------------------------------------------------------
static void playRun()
{
    const uint8_t base = lowestNote();
    if (base == 0xFF)
    {
        p("no key in position_map.cpp");
        return;
    }
    const uint8_t offsets[] = {0, 2, 4, 5, 7};
    uint8_t queued = 0;
    for (uint8_t o : offsets)
    {
        const uint8_t pos = posOfNote((uint8_t)(base + o));
        if (pos == 0xFF)
            continue;
        inject::queueTap(pos, INJECT_NOTE_HOLD_MS, 150);
        ++queued;
    }
    char nm[8];
    noteName(base, nm, sizeof(nm));
    p("%u notes from %s through the muxes - the toy plays them, and the audio jack carries them"
      " (level pot up)", queued, nm);
}

// ---------------------------------------------------------------------------

void setup()
{
    inject::begin(); // INH high before anything else: the toy is on

    const int outs[] = {PIN_GATE, PIN_GATE2, PIN_LED_RED, PIN_LED_GREEN, PIN_LED_BLUE};
    for (int pin : outs)
    {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
    dacWrite(PIN_AUX, 0);

    const int ins[] = {PIN_CV_SELECT, PIN_CLOCK_IN, PIN_POT_BASE, PIN_POT_TUNE};
    for (int pin : ins)
        pinMode(pin, INPUT); // input-only pins, no internal pull-ups to enable

    Serial.begin(USB_BAUD);
    Serial2.begin(31250, SERIAL_8N1, PIN_MIDI_RX, PIN_MIDI_TX); // as midi::begin() does
    delay(300); // let the host reopen the port after the reset
    runAll();
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
        case ' ':
            break;
        case 'r':
            runAll();
            break;
        case '?':
            help();
            break;

        case 'c':
            cvStepNext();
            break;
        case 'v':
            seqOn = false;
            octOn = !octOn;
            if (octOn)
            {
                p("octave: both CVs alternate 0 and 12 semitones every 4 s. Meter a CV jack; adjust that");
                p("channel's CV_CODES_PER_SEMITONE until the two readings differ by 1.000 V. Any key stops");
            }
            else
            {
                writeCv(0, 0);
                writeCv(1, 0);
                p("octave off, CVs at 0");
            }
            break;
        case '1':
            gateToggle(0);
            break;
        case '2':
            gateToggle(1);
            break;
        case 'a':
            auxStepNext();
            break;
        case 'g':
            octOn = false;
            seqOn = !seqOn;
            if (seqOn)
                p("sequence: CV1 + gate 1 for an octave, then CV2 + gate 2, AUX ramping. Patch a VCO. Any key stops");
            else
            {
                setGate(0, false);
                setGate(1, false);
                writeCv(0, 0);
                writeCv(1, 0);
                dacWrite(PIN_AUX, 0);
                p("sequence off");
            }
            break;

        case 's':
            switchCheck();
            break;
        case 'p':
            potsOn = !potsOn;
            if (potsOn)
                p("pots: turn base pitch and tune each end to end, slowly. Any key stops and judges");
            else
                potsTick(); // prints the verdict
            break;
        case 'k':
            clockLoopback();
            break;
        case 'x':
            countClock();
            break;
        case 'b':
            keybedOn = !keybedOn;
            if (keybedOn)
            {
                memset(seen, 0, sizeof(seen));
                keybed::reset();
                p("keybed: press every key and button; each is named. Any key here stops and lists the ones missed");
            }
            else
                keybedSummary();
            break;

        case 'm':
            midiLoopback();
            break;
        case 'o':
            beaconOn = !beaconOn;
            p(beaconOn ? "beacon: C4 on channel %u, on 250 ms / off 250 ms, out of the DIN socket. Any key stops"
                       : "beacon off",
              NOTE_CHANNEL + 1);
            if (!beaconOn)
            {
                const uint8_t off[3] = {(uint8_t)(0x80 | NOTE_CHANNEL), 60, 0};
                Serial2.write(off, 3);
            }
            break;
        case 'n':
            midiInOn = true;
            midiInEnd = millis() + 20000;
            while (Serial2.available())
                Serial2.read();
            p("MIDI in: play something into the in socket; 20 s, decoded. Clock and active sensing are counted");
            break;

        case 'j':
            playRun();
            break;
        case 'i':
            inputsOn = !inputsOn;
            p(inputsOn ? "live inputs - printed on change; any other key stops" : "live inputs off");
            break;
        case 'l':
            ledCycle();
            break;

        default:
            if (keybedOn)
            {
                keybedOn = false;
                keybedSummary();
            }
            if (potsOn)
            {
                potsOn = false;
                potsTick();
            }
            stopAll(true);
            break;
        }
    }

    if (seqOn)     sequenceTick();
    if (octOn)     octaveTick();
    if (beaconOn)  beaconTick();
    if (keybedOn)  keybedTick();
    if (potsOn)    potsTick();
    if (midiInOn)  midiInTick();
    if (inputsOn)  inputsTick();
    inject::service();
    delay(SCAN_PERIOD_MS);
}
