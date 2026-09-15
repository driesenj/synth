#include <Arduino.h>
#include <Wire.h>
#include <stdarg.h>
#include <string.h>

#include "config.h"
#include "inject.h"
#include "keybed.h"
#include "mcp23017.h"
#include "mcp4725.h"

#include "driver/periph_ctrl.h"   // periph_module_reset, the diagnosis ladder's last rung

// ============================================================================
//  Meowsic MIDI - I2C board bring-up self test.
//
//  Built as its own environment:  pio run -e selftest -t upload
//
//  Shares mcp23017.cpp and mcp4725.cpp with the real firmware, so a pass here
//  means the production drivers talk to the chips - not merely that something
//  ACKed.
//
//  Runs with the I2C board on its four-wire cable and nothing else powered:
//  no blob, no 12 V. USB alone runs the ESP32, the MCP23017 and both MCP4725s
//  (README, "Power notes that matter to firmware"), so this is a bench test
//  with the toy unplugged. The keybed and button board may be plugged in;
//  check 6 only asks that nothing is being pressed.
//
//  Serial monitor at 115200, single-letter commands:
//    r  re-run the full sequence
//    m  live matrix monitor - press a key, or short a strobe pin to a return
//       pin; each lit cell is named from position_map.cpp
//    p  pin-pair monitor - the same, assuming nothing about which port or bit
//       a wire is on: the two chip pins a key joins are named. This is how
//       COLS_ON_PORT_A, COL_BIT and ROW_BIT are read off a new board
//    d  dump the configuration registers once
//    s  bus stress test at 100 kHz and 400 kHz, all three devices
//    l  toggle the bus clock every other check runs at, 400 <-> 100 kHz,
//       and re-run: passing at 100 and dying at 400 is signal integrity
//       (pull-ups, cable, an SCL joint), not the chip
//    v  step both DACs through five levels, for a meter on CV1 / CV2
//    o  octave test: each DAC alternates two codes 12 semitones apart, to
//       calibrate CV_CODES_PER_SEMITONE / CV2_CODES_PER_SEMITONE
//    e  program both DACs' EEPROM to 0, so CV is 0 V from power-up
//
//  Which physical port is strobes and which is returns follows
//  COLS_ON_PORT_A in config.h; the banner prints the active mapping.
//
//  Mapping sweep - fills in position_map.cpp without probing the keybed. The
//  shipped table is measured and hand-annotated (names, the +12 rebase, the
//  button board's seven); only re-run this if a matrix wire has moved:
//    n  record piano keys, lowest first, as ascending notes
//    c  record buttons as ascending CCs
//    w  write out the finished position_map.cpp
//    z  discard the recording and start over
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

static const char *bin8(uint8_t v)
{
    static char s[9];
    for (int i = 0; i < 8; ++i)
        s[i] = (v & (0x80u >> i)) ? '1' : '0';
    s[8] = 0;
    return s;
}

// Clock every check other than the stress test runs at. 'l' toggles it.
static uint32_t busHz = I2C_HZ;

// ---------------------------------------------------------------------------
//  1. Bus idle levels, before I2C is brought up.
//
//  Only a LOW reading is conclusive: something is holding the line down - a
//  short to ground, or a slave left mid-byte by a corrupted transaction, which
//  holds SDA until it sees more clocks. That state survives an ESP32 reset,
//  so the previous run's failure would poison this one; the standard cure is
//  applied here - nine SCL pulses with SDA released, then a STOP.
//
//  HIGH does not prove the 2.2k pull-ups are present or the right value; that
//  is what the 400 kHz stress test in step 5 is for.
//
//  Wire.end() first: pinMode() on the bus pins detaches the I2C peripheral's
//  output from them, and Wire.begin() on an already-started bus is a no-op on
//  this core, so without the end() every re-run after the first would talk to
//  nothing.
// ---------------------------------------------------------------------------
static bool busRecover()
{
    pinMode(PIN_SDA, INPUT);
    pinMode(PIN_SCL, OUTPUT_OPEN_DRAIN);
    digitalWrite(PIN_SCL, HIGH);
    delayMicroseconds(5);

    for (uint8_t i = 0; i < 9 && !digitalRead(PIN_SDA); ++i)
    {
        digitalWrite(PIN_SCL, LOW);
        delayMicroseconds(5);
        digitalWrite(PIN_SCL, HIGH);
        delayMicroseconds(5);
    }

    // START then STOP, so whatever was listening sees a clean end of frame.
    pinMode(PIN_SDA, OUTPUT_OPEN_DRAIN);
    digitalWrite(PIN_SDA, LOW);
    delayMicroseconds(5);
    digitalWrite(PIN_SDA, HIGH);
    delayMicroseconds(5);

    pinMode(PIN_SDA, INPUT);
    pinMode(PIN_SCL, INPUT);
    delayMicroseconds(50);
    return digitalRead(PIN_SDA) && digitalRead(PIN_SCL);
}

static void testBusIdle()
{
    Wire.end();
    pinMode(PIN_SDA, INPUT); // no internal pull-up - we want the bus own level
    pinMode(PIN_SCL, INPUT);
    delayMicroseconds(50);

    const bool sda = digitalRead(PIN_SDA);
    const bool scl = digitalRead(PIN_SCL);

    p("[1] bus idle    SDA(gpio%d)=%s  SCL(gpio%d)=%s   t=%lu ms",
      PIN_SDA, sda ? "HIGH" : "LOW", PIN_SCL, scl ? "HIGH" : "LOW", (unsigned long)millis());

    if (!scl)
    {
        p("    FAIL  SCL held low. Nothing but the master drives SCL, so this is");
        p("          a short to GND or a wrong link, not a stuck device.");
    }
    else if (!sda)
    {
        p("    SDA held low: a slave is stuck mid-byte. Clocking it out...");
        if (busRecover())
        {
            p("    ok    released. The last run ended in a corrupted transaction that");
            p("          left a slave holding the bus - check 5, and 'l' for 100 kHz,");
            p("          say whether that is pull-ups / cable / an SCL joint.");
        }
        else
        {
            p("    FAIL  still low after nine clocks: a short to GND, or a device");
            p("          with no supply clamping the line. Power-cycle and meter it.");
        }
    }
    else
        p("    ok    both lines released");
}

// A quick ACK probe, so the checks that need the expander can skip cleanly
// when it has dropped off the bus instead of marching through timeouts.
static bool mcpAnswers()
{
    Wire.beginTransmission(MCP_ADDR);
    return Wire.endTransmission() == 0;
}

// ---------------------------------------------------------------------------
//  2. Address sweep. Three devices are expected: the expander at 0x20 and the
//     DACs at 0x60 / 0x61. A chip answering elsewhere has its address pins
//     wrong - A0-A2 on the MCP23017, the ADDR jumper on a breakout. Two
//     breakouts at one address both ACK and their reads collide, so that
//     fault looks like "0x60 present, 0x61 absent".
// ---------------------------------------------------------------------------
static bool haveMcp, haveDac1, haveDac2;

static void testAddressScan()
{
    Wire.begin(PIN_SDA, PIN_SCL, busHz);
    Wire.setTimeOut(20);

    uint8_t found = 0;
    haveMcp = haveDac1 = haveDac2 = false;

    p("[2] address scan (0x03-0x77) at %lu kHz   t=%lu ms", (unsigned long)(busHz / 1000), (unsigned long)millis());
    for (uint8_t a = 0x03; a <= 0x77; ++a)
    {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() != 0)
            continue;

        ++found;
        const char *who = "";
        if (a == MCP_ADDR)       { haveMcp = true;  who = "  <- MCP23017"; }
        else if (a == DAC_ADDR)  { haveDac1 = true; who = "  <- MCP4725, CV1"; }
        else if (a == DAC2_ADDR) { haveDac2 = true; who = "  <- MCP4725, CV2"; }
        p("    device at 0x%02X%s", a, who);
    }

    if (found == 0)
    {
        p("    FAIL  nothing on the bus. Check 3V3 and GND at the board, SDA/SCL");
        p("          not swapped, and RESET (chip pin 18) pulled to 3.3 V through 10k.");
        return;
    }
    if (!haveMcp)
    {
        p("    FAIL  no MCP23017 at 0x%02X. If something answers at 0x21-0x27, A0-A2", MCP_ADDR);
        p("          (pins 15-17) are not all grounded - the offset is their value.");
    }
    if (!haveDac1)
    {
        p("    FAIL  no MCP4725 at 0x%02X: breakout #1 has no VCC (the 10 ohm), or its", DAC_ADDR);
        p("          ADDR jumper is closed and it sits on top of #2 at 0x%02X.", DAC2_ADDR);
    }
    if (!haveDac2)
    {
        p("    FAIL  no MCP4725 at 0x%02X: breakout #2's ADDR jumper is open (it then", DAC2_ADDR);
        p("          sits on top of #1 at 0x%02X), or it has no VCC.", DAC_ADDR);
    }
    if (haveMcp && haveDac1 && haveDac2)
        p("    ok    %u devices: expander and both DACs", found);
}

// ---------------------------------------------------------------------------
//  3. Apply the production register set and read every one back.
//
//  This is the read path's first real workout: an address ACK only exercises
//  writes. ROW_GPPU and ROW_IPOL are the two registers whose target value
//  differs from the power-on default, so they are the ones that expose a chip
//  that keeps resetting underneath us.
// ---------------------------------------------------------------------------
struct RegCheck
{
    uint8_t reg;
    uint8_t want;
    uint8_t por; // power-on default
    const char *name;
};

static const RegCheck REGS[] = {
    {REG_IOCON, 0x00, 0x00, "IOCON    "},
    {REG_COL_IODIR, 0xFF, 0xFF, "COL_IODIR"},
    {REG_COL_OLAT, 0x00, 0x00, "COL_OLAT "},
    {REG_COL_GPPU, 0x00, 0x00, "COL_GPPU "},
    {REG_ROW_IODIR, 0xFF, 0xFF, "ROW_IODIR"},
    {REG_ROW_GPPU, 0xFF, 0x00, "ROW_GPPU "},
    {REG_ROW_IPOL, 0xFF, 0x00, "ROW_IPOL "},
    {REG_GPINTENA, 0x00, 0x00, "GPINTENA "},
    {REG_GPINTENB, 0x00, 0x00, "GPINTENB "},
};
static constexpr uint8_t N_REGS = sizeof(REGS) / sizeof(REGS[0]);

static bool droppedOff;   // set by dumpRegs: answered, then went silent

static bool dumpRegs(bool verbose)
{
    uint8_t bad = 0, atPor = 0, readOk = 0, readFail = 0;
    droppedOff = false;

    for (uint8_t i = 0; i < N_REGS; ++i)
    {
        uint8_t got = 0;
        if (!mcp::readReg(REGS[i].reg, got))
        {
            p("    %s @0x%02X  READ FAILED   t=%lu ms", REGS[i].name, REGS[i].reg,
              (unsigned long)millis());
            ++bad;
            ++readFail;
            continue;
        }
        ++readOk;

        const bool ok = (got == REGS[i].want);
        if (!ok)
        {
            ++bad;
            if (got == REGS[i].por)
                ++atPor;
        }
        if (verbose || !ok)
            p("    %s @0x%02X  want %s  got %s  %s",
              REGS[i].name, REGS[i].reg, bin8(REGS[i].want), bin8(got),
              ok ? "" : "<- MISMATCH");
    }

    if (bad && atPor)
    {
        p("    FAIL  %u register(s) read back at their power-on default.", atPor);
        p("          The chip is resetting under us: RESET (pin 18) floating,");
        p("          or VDD dipping. This is the classic MCP23017 failure, and");
        p("          the one that only shows up once the wiring moves.");
    }
    if (readOk && readFail)
    {
        droppedOff = true;
        p("    FAIL  the chip answered %u read(s), then stopped answering at all.", readOk);
    }
    return bad == 0;
}

// ---------------------------------------------------------------------------
//  Why did it stop? Each rung below separates one explanation from the rest
//  and prints what it found; read them top to bottom. Write-only probes are
//  used wherever possible because a read that hits a stuck controller costs a
//  full second (the driver's fallback when the hardware raises no interrupt
//  at all - error 263 after ~1000 ms is that, not a slave timeout).
// ---------------------------------------------------------------------------
static bool ack(uint8_t addr)
{
    Wire.beginTransmission(addr);
    return Wire.endTransmission() == 0;
}

// n probes, 10 ms apart; how many answered.
static uint8_t flicker(uint8_t addr, uint8_t n)
{
    uint8_t hits = 0;
    for (uint8_t i = 0; i < n; ++i)
    {
        if (ack(addr)) ++hits;
        delay(10);
    }
    return hits;
}

static void diagnoseDropout()
{
    p("          lines, peripheral attached and idle:  SDA=%s  SCL=%s",
      digitalRead(PIN_SDA) ? "HIGH" : "LOW", digitalRead(PIN_SCL) ? "HIGH" : "LOW");

    // A. is it flickering or gone?
    uint8_t hits = flicker(MCP_ADDR, 5);
    p("          A  expander answers %u of 5 probes, 10 ms apart", hits);
    if (hits == 5)
    {
        p("             ...so it is back already. A transient - one corrupted");
        p("             transaction. Check 5 and 'l' will show it as 400 kHz-only.");
        return;
    }

    // B. the rest of the bus, without reads that can stall
    const bool w1 = haveDac1 && ack(DAC_ADDR), w2 = haveDac2 && ack(DAC2_ADDR);
    p("          B  DAC write probes: cv1 %s, cv2 %s", w1 ? "ACK" : "no", w2 ? "ACK" : "no");
    if (w1)
    {
        dac::State st;
        const uint32_t t0 = millis();
        const bool ok = dac::read(DAC_ADDR, st);
        const uint32_t dt = millis() - t0;
        p("             cv1 read: %s in %lu ms%s", ok ? "ok" : "FAILED", (unsigned long)dt,
          (!ok && dt > 500) ? " - the controller stalled, not the slave" : "");
    }

    // C. did its address move?
    for (uint8_t a = 0x20; a <= 0x27; ++a)
    {
        if (a == MCP_ADDR) continue;
        if (ack(a))
        {
            p("          C  the expander answers at 0x%02X: A0-A2 (legs 15-17) are not", a);
            p("             held at GND. Ground them at the legs.");
            return;
        }
    }
    p("          C  not at 0x21-0x27 either");

    // D. does traffic to other addresses bring it back? (that is what 'r' does
    //    before it reaches 0x20, and it worked once)
    for (uint8_t a = 0x08; a < 0x20; ++a) ack(a);
    hits = flicker(MCP_ADDR, 5);
    p("          D  after 24 probes to other addresses: answers %u of 5", hits);
    if (hits)
    {
        p("             traffic resynchronised it: its I2C engine had lost the");
        p("             thread. A glitch on SCL/SDA mid-transaction does that -");
        p("             signal integrity, not power. 'l' should pass.");
        return;
    }

    // E. clock speed
    Wire.setClock(100000);
    delay(2);
    hits = flicker(MCP_ADDR, 5);
    Wire.setClock(busHz);
    p("          E  at 100 kHz: answers %u of 5", hits);
    if (hits)
    {
        p("             it hears the slower clock: the 400 kHz edges are what it");
        p("             cannot follow. Pull-ups, cable, the strip next to SCL.");
        return;
    }

    // F. time: how long until it answers by itself?
    p("          F  probing once a second, up to 60 s...");
    for (uint8_t sec = 1; sec <= 60; ++sec)
    {
        delay(1000);
        if (ack(MCP_ADDR))
        {
            p("             back after %u s of near-idle. That is a slow recovery -", sec);
            p("             something is charging back up. Meter leg 9 to leg 10 on");
            p("             the expander right after a failure, not later.");
            return;
        }
    }
    p("             still silent after 60 s");

    // G. the master
    Wire.end();
    pinMode(PIN_SDA, INPUT);
    pinMode(PIN_SCL, INPUT);
    delayMicroseconds(50);
    p("          G  lines with the peripheral detached:  SDA=%s  SCL=%s",
      digitalRead(PIN_SDA) ? "HIGH" : "LOW", digitalRead(PIN_SCL) ? "HIGH" : "LOW");
    busRecover();
    periph_module_reset(PERIPH_I2C0_MODULE);
    Wire.begin(PIN_SDA, PIN_SCL, busHz);
    Wire.setTimeOut(20);
    hits = flicker(MCP_ADDR, 5);
    p("             after bus recovery + controller reset: answers %u of 5", hits);
    if (hits)
        p("             the ESP32 side was stuck, not the board.");
    else
        p("             nothing brings it back short of a reset. Scope time.");
}

static void testRegisters()
{
    p("[3] register write / read-back   t=%lu ms", (unsigned long)millis());

    if (!mcp::begin())
    {
        p("    FAIL  mcp::begin() - no ACK, or a config write was not accepted");
        if (haveMcp)
        {
            p("          it answered the scan %lu ms ago and not now", (unsigned long)millis());
            diagnoseDropout();
        }
        return;
    }
    Wire.setClock(busHz);   // mcp::begin() set the production 400 kHz
    if (dumpRegs(true))
        p("    ok    all %u registers hold the configured value", N_REGS);
    else if (droppedOff)
        diagnoseDropout();
}

// ---------------------------------------------------------------------------
//  4. Dedicated retention probe.
//
//  The return port's output latch is the one writable register the firmware
//  never uses - those pins are inputs, so it drives nothing. Walking a pattern
//  through it tests whether the chip retains state at all, with no
//  interference from the keybed configuration.
// ---------------------------------------------------------------------------
static void testRetention()
{
    static const uint8_t PATTERN[] = {0xFF, 0xA5, 0x5A, 0x00};
    uint8_t bad = 0;

    p("[4] state retention (walking pattern through port " ROW_PORT_NAME " OLAT)   t=%lu ms", (unsigned long)millis());

    if (!mcpAnswers())
    {
        p("    skipped - the expander is not answering, see check 3");
        return;
    }

    for (uint8_t i = 0; i < sizeof(PATTERN); ++i)
    {
        if (!mcp::writeReg(REG_ROW_OLAT, PATTERN[i]))
        {
            p("    write %s FAILED", bin8(PATTERN[i]));
            ++bad;
            continue;
        }
        delay(1);

        uint8_t got = 0;
        if (!mcp::readReg(REG_ROW_OLAT, got) || got != PATTERN[i])
        {
            p("    wrote %s  read %s  <- MISMATCH", bin8(PATTERN[i]), bin8(got));
            ++bad;
        }
    }

    if (bad)
        p("    FAIL  the chip is not holding what it is told. RESET or VDD.");
    else
        p("    ok    all 4 patterns survived");
}

// ---------------------------------------------------------------------------
//  5. Sustained transaction test at both speeds.
//
//  An address ACK passes with no external pull-ups at all, on the ESP32 ~45k
//  internals. What that cannot survive is 400 kHz: rise time gets too long and
//  reads start corrupting. Running 100 kHz first makes the result diagnostic
//  rather than just pass/fail - clean at 100 k but dirty at 400 k is a pull-up
//  problem specifically, dirty at both is wiring or power.
// ---------------------------------------------------------------------------
struct Fails
{
    uint16_t mcp, dac1, dac2;
    uint16_t total() const { return mcp + dac1 + dac2; }
};

// A device that fails GIVE_UP reads in a row is gone, not marginal, and every
// further attempt would cost the 20 ms timeout - 2000 of them is most of a
// minute of apparent hang. Stop asking it, count the rest as failed, and
// remember how far it got: a device that dies after some hundreds of good
// reads at one speed is the signature of marginal signal integrity.
static constexpr uint16_t GIVE_UP = 3;

struct Probe
{
    bool     ask;
    uint16_t fails, run, diedAt;   // run = consecutive fails; diedAt = good reads before death
};

static void tally(Probe &d, bool ok, uint16_t i, uint16_t n)
{
    if (!d.ask)
        return;
    if (ok)
    {
        d.run = 0;
        return;
    }
    ++d.fails;
    if (++d.run == GIVE_UP)
    {
        d.ask = false;
        d.diedAt = i + 1 - GIVE_UP;
        d.fails = n;
    }
}

static uint16_t diedMcp, diedDac1, diedDac2;   // 0 = did not die

// One MCP23017 register read and one 5-byte read from each DAC per pass, so
// every device - and the whole cable - is under the same clock.
static Fails hammer(uint32_t hz, uint16_t n)
{
    Wire.setClock(hz);
    delay(2);

    Probe m = {true, 0, 0, 0}, d1 = {haveDac1, 0, 0, 0}, d2 = {haveDac2, 0, 0, 0};
    for (uint16_t i = 0; i < n; ++i)
    {
        uint8_t v;
        dac::State st;
        if (m.ask)  tally(m,  mcp::readReg(REG_ROW_GPIO, v), i, n);
        if (d1.ask) tally(d1, dac::read(DAC_ADDR, st), i, n);
        if (d2.ask) tally(d2, dac::read(DAC2_ADDR, st), i, n);
    }
    diedMcp = m.ask ? 0 : m.diedAt + 1;
    diedDac1 = d1.ask ? 0 : d1.diedAt + 1;
    diedDac2 = d2.ask ? 0 : d2.diedAt + 1;
    return Fails{m.fails, d1.fails, d2.fails};
}

static void failCell(char (&out)[12], bool present, uint16_t fails, uint16_t n)
{
    if (!present)        snprintf(out, sizeof(out), "  n/a");
    else if (fails == n) snprintf(out, sizeof(out), " dead");
    else                 snprintf(out, sizeof(out), "%5u", (unsigned)fails);
}

static void failLine(const char *speed, const Fails &f, uint16_t n)
{
    char m[12], d1[12], d2[12];
    failCell(m, true, f.mcp, n);
    failCell(d1, haveDac1, f.dac1, n);
    failCell(d2, haveDac2, f.dac2, n);
    p("    %s  mcp %s   cv1 %s   cv2 %s  failed", speed, m, d1, d2);
    if (diedMcp)  p("             mcp stopped answering after %u good reads", diedMcp - 1);
    if (diedDac1) p("             cv1 stopped answering after %u good reads", diedDac1 - 1);
    if (diedDac2) p("             cv2 stopped answering after %u good reads", diedDac2 - 1);
}

static void testBusQuality()
{
    static constexpr uint16_t N = 2000;
    char fastLabel[12];
    snprintf(fastLabel, sizeof(fastLabel), "%3lu kHz", (unsigned long)(I2C_HZ / 1000));

    p("[5] bus stress, %u reads per device at each speed   t=%lu ms", N, (unsigned long)millis());

    const Fails slow = hammer(100000, N);
    failLine("100 kHz", slow, N);
    const Fails fast = hammer(I2C_HZ, N);
    failLine(fastLabel, fast, N);

    if (slow.total() == 0 && fast.total() == 0)
        p("    ok    clean at both speeds");
    else if (slow.total() == 0)
    {
        p("    FAIL  clean at 100 kHz, dirty at %lu kHz. That is the signature",
          (unsigned long)(I2C_HZ / 1000));
        p("          of missing or too-weak pull-ups - the bus needs its one 2.2k");
        p("          pair to 3.3 V, on the I2C board. A long or bundled bus cable");
        p("          does it too. One device dirty with the others clean is that");
        p("          device's own joint: its SDA/SCL links, or VCC through the 10 ohm.");
    }
    else
    {
        p("    FAIL  errors even at 100 kHz. Wiring, power, or RESET. A device");
        p("          marked dead stopped answering and stays silent until the bus");
        p("          is clocked out: 'r' does that in check 1.");
    }

    Wire.setClock(busHz);
}

// ---------------------------------------------------------------------------
//  6. Column strobe, and the frame timing the scanner assumes.
//
//  Asserts each column the way keybed::scan() does - by writing IODIRA, never
//  GPIOA - reads IODIRA back to prove the write landed, and checks that the
//  returns are all open. With no keybed attached every row is held high by its
//  100k internal pull-up, and IPOLB inverts that, so GPIOB must read all
//  zeros. Any bit set here is a column shorted to a return.
// ---------------------------------------------------------------------------
static void timeFrame();

static void testStrobe()
{
    uint8_t bad = 0;

    p("[6] column strobe, nothing pressed - every row must read 0   t=%lu ms", (unsigned long)millis());

    if (!mcpAnswers())
    {
        p("    skipped - the expander is not answering, see check 3");
        return;
    }

    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        const uint8_t want = mcp::colStrobe(c);

        if (!mcp::writeReg(REG_COL_IODIR, want))
        {
            p("    col %u  COL_IODIR write FAILED", c);
            ++bad;
            continue;
        }

        uint8_t back = 0, rows = 0;
        if (!mcp::readReg(REG_COL_IODIR, back) || back != want)
        {
            p("    col %u  COL_IODIR want %s got %s  <- MISMATCH",
              c, bin8(want), bin8(back));
            ++bad;
        }
        if (!mcp::readReg(REG_ROW_GPIO, rows))
        {
            p("    col %u  ROW_GPIO read FAILED", c);
            ++bad;
            continue;
        }
        if (mcp::packRows(rows))
        {
            p("    col %u  GP" ROW_PORT_NAME "=%s  <- closed with nothing pressed:",
              c, bin8(rows));
            p("           GP" COL_PORT_NAME "%u is shorted to a return line, or a key is held",
              COL_BIT[c]);
            ++bad;
        }
    }

    mcp::writeReg(REG_COL_IODIR, 0xFF); // release

    if (!bad)
        p("    ok    all 8 columns strobe, all returns open");

    timeFrame();
}

// ---------------------------------------------------------------------------
//  Frame timing, split by transaction type.
//
//  A frame that overruns its period is not automatically a bug - it matters
//  *why*. Bus time is arithmetic: at 400 kHz a register write is 27 bit-times
//  (~68 us) and a repeated-start read is 36 (~90 us), so eight of each is
//  ~1.26 ms. That is where the README's "~1.4 ms" comes from, and it counts
//  only the wire. The Arduino Wire driver adds a semaphore, a command-link
//  allocation and an i2c_master_cmd_begin per transaction on top.
//
//  Timing the two separately says which one you are actually paying for, so
//  the fix is chosen rather than guessed.
// ---------------------------------------------------------------------------
static void timeFrame()
{
    static constexpr uint16_t N_T = 200;

    // Bus time only, from the bit counts above.
    static constexpr uint32_t WRITE_BITS = 27;
    static constexpr uint32_t READ_BITS = 36;
    const uint32_t wireW = WRITE_BITS * 1000000UL / busHz;
    const uint32_t wireR = READ_BITS * 1000000UL / busHz;

    uint32_t t0 = micros();
    for (uint16_t i = 0; i < N_T; ++i)
        mcp::writeReg(REG_COL_IODIR, 0xFF);
    const uint32_t gotW = (micros() - t0) / N_T;

    uint8_t tmp;
    t0 = micros();
    for (uint16_t i = 0; i < N_T; ++i)
        mcp::readReg(REG_ROW_GPIO, tmp);
    const uint32_t gotR = (micros() - t0) / N_T;

    const uint32_t frame = N_COLS * (gotW + gotR);
    const uint32_t wire = N_COLS * (wireW + wireR);

    p("    write  %3lu us   (%lu us on the wire, %lu us driver overhead)",
      (unsigned long)gotW, (unsigned long)wireW, (unsigned long)(gotW - wireW));
    p("    read   %3lu us   (%lu us on the wire, %lu us driver overhead)",
      (unsigned long)gotR, (unsigned long)wireR, (unsigned long)(gotR - wireR));
    p("    frame  %lu us = 8 x (write + read)   bus time alone would be %lu us",
      (unsigned long)frame, (unsigned long)wire);

    if (frame <= SCAN_PERIOD_MS * 1000)
    {
        p("    ok    fits the %u ms period", (unsigned)SCAN_PERIOD_MS);
        return;
    }

    // The scan loop is  delay(dt >= SCAN_PERIOD_MS ? 1 : SCAN_PERIOD_MS - dt),
    // so it already yields at least 1 ms however long the frame ran. Nothing
    // here can starve the idle task or trip the task watchdog - the constant
    // is simply describing a period the bus cannot deliver.
    const uint32_t want = (frame + 999) / 1000;          // honest floor
    const uint32_t actual = 1000000UL / (frame + 1000);  // frame + the 1 ms yield

    p("    WARN  frame does not fit SCAN_PERIOD_MS = %u, so the real rate is",
      (unsigned)SCAN_PERIOD_MS);
    p("          ~%lu Hz, not %lu Hz.", (unsigned long)actual,
      (unsigned long)(1000 / SCAN_PERIOD_MS));
    if (gotW > wireW * 2 || gotR > wireR * 2)
        p("          Most of it is Wire driver overhead, not the bus, so a");
    p("          faster I2C clock would not buy much.");
    p("");
    p("          This is a labelling problem, not a fault. The loop's delay()");
    p("          already yields 1 ms whatever the frame cost, so the watchdog");
    p("          is fed either way, and ~%lu Hz is still several times the",
      (unsigned long)actual);
    p("          blob's own poll rate. Setting SCAN_PERIOD_MS = %lu changes no",
      (unsigned long)want);
    p("          timing at all - it just stops the constant lying. Raising it");
    p("          further only makes the scan slower.");
}

// ---------------------------------------------------------------------------
//  7. The two MCP4725s. Read the whole state back - DAC register, power-down
//     mode, EEPROM - then push four patterns through the fast-mode write the
//     firmware will use per note, reading each back. The EEPROM is what the
//     output sits at from power-up until the firmware writes the DAC; it
//     should hold 0 so CV starts at 0 V ('e' does that).
// ---------------------------------------------------------------------------
static float jackVolts(uint16_t code)
{
    return code * 3.3f / 4096.0f * 1.5f;    // breakout x1.5 at the TL074
}

static bool testOneDac(const char *name, uint8_t addr)
{
    dac::State s;
    if (!dac::read(addr, s))
    {
        p("    %s 0x%02X  read FAILED", name, addr);
        return false;
    }
    p("    %s 0x%02X  dac %4u (pd %u)   eeprom %4u (pd %u)   %s",
      name, addr, s.code, s.pd, s.eepromCode, s.eepromPd,
      s.ready ? "ready" : "BUSY");

    static const uint16_t PATTERN[] = {0x000, 0xA5A, 0x5A5, 0xFFF};
    uint8_t bad = 0;
    for (uint8_t i = 0; i < sizeof(PATTERN) / sizeof(PATTERN[0]); ++i)
    {
        const uint16_t code = PATTERN[i];
        dac::State back = {};
        if (!dac::write(addr, code) || !dac::read(addr, back) ||
            back.code != code || back.pd != 0)
        {
            p("          wrote %4u  read %4u (pd %u)  <- MISMATCH",
              code, back.code, back.pd);
            ++bad;
        }
    }
    dac::write(addr, 0);

    if (s.eepromPd != 0)
        p("          note: EEPROM says power-down - output is pulled to GND from");
    else if (s.eepromCode != 0)
        p("          note: EEPROM is %u - the jack sits at %.2f V from", s.eepromCode,
          jackVolts(s.eepromCode));
    if (s.eepromPd != 0 || s.eepromCode != 0)
        p("          power-up until the firmware writes the DAC. 'e' programs it to 0.");

    return bad == 0;
}

static void testDacs()
{
    p("[7] MCP4725 DACs: state, then fast-mode write and read-back   t=%lu ms", (unsigned long)millis());

    if (!haveDac1 && !haveDac2)
    {
        p("    skipped - neither DAC answered the address scan");
        return;
    }

    bool ok = true;
    if (haveDac1) ok &= testOneDac("cv1", DAC_ADDR);
    if (haveDac2) ok &= testOneDac("cv2", DAC2_ADDR);

    if (ok)
        p("    ok    %s what it is told, outputs left at 0",
          (haveDac1 && haveDac2) ? "both DACs hold" : "the DAC present holds");
    else
        p("    FAIL  a DAC is not retaining writes: VCC through the 10 ohm, or its bus joints");
}

// ---------------------------------------------------------------------------
//  Meter modes, for the analogue side. Both DACs get equivalent codes so CV1
//  (TL074 pin 1) and CV2 (pin 14) can be compared on one meter. Volts are
//  nominal: 3.3 V / 4096 per code at the breakout, x1.5 at the jack; the
//  DevKit's regulator and the 1% resistors move them a little, which is what
//  the octave mode calibrates out.
// ---------------------------------------------------------------------------
enum DacMode : uint8_t { DAC_OFF, DAC_STEPS, DAC_OCTAVE };

static DacMode dacMode = DAC_OFF;
static uint8_t dacStep;
static uint32_t dacNext;

static bool monitorOn = false;
static void sweepStop();
static void pairsStop();

static void dacSet(uint16_t c1, uint16_t c2)
{
    if (haveDac1) dac::write(DAC_ADDR, c1);
    if (haveDac2) dac::write(DAC2_ADDR, c2);
}

static void dacStop()
{
    if (dacMode == DAC_OFF)
        return;
    dacMode = DAC_OFF;
    dacSet(0, 0);
    p("DACs back to 0");
}

static void dacBegin(DacMode m)
{
    if (!haveDac1 && !haveDac2)
    {
        p("no DAC answered the address scan - run r first");
        return;
    }
    monitorOn = false;
    sweepStop();
    pairsStop();
    dacMode = m;
    dacStep = 0;
    dacNext = millis();

    p("");
    if (m == DAC_STEPS)
    {
        p("DAC steps, 3 s each: meter CV1 (TL074 pin 1) and CV2 (pin 14).");
        p("Any key stops.");
    }
    else
    {
        p("Octave test, 4 s each: each DAC alternates two codes 12 semitones");
        p("apart. The jack must move by exactly 1.000 V. Adjust");
        p("CV_CODES_PER_SEMITONE (now %.2f) and CV2_CODES_PER_SEMITONE (%.2f)",
          CV_CODES_PER_SEMITONE, CV2_CODES_PER_SEMITONE);
        p("in config.h until it does; larger if the step is short. Any key stops.");
    }
}

static void dacTick()
{
    if ((int32_t)(millis() - dacNext) < 0)
        return;

    if (dacMode == DAC_STEPS)
    {
        static const uint16_t LEVEL[] = {0, 1024, 2048, 3072, 4095};
        const uint16_t code = LEVEL[dacStep];
        dacSet(code, code);
        p("  code %4u   breakout %.3f V   jack %.3f V",
          code, code * 3.3f / 4096.0f, jackVolts(code));
        dacStep = (dacStep + 1) % (sizeof(LEVEL) / sizeof(LEVEL[0]));
        dacNext = millis() + 3000;
    }
    else
    {
        static constexpr uint16_t BASE = 1000;
        const uint16_t up1 = BASE + (uint16_t)(12.0f * CV_CODES_PER_SEMITONE + 0.5f);
        const uint16_t up2 = BASE + (uint16_t)(12.0f * CV2_CODES_PER_SEMITONE + 0.5f);
        const bool high = dacStep & 1;
        const uint16_t c1 = high ? up1 : BASE;
        const uint16_t c2 = high ? up2 : BASE;
        dacSet(c1, c2);
        p("  %s   cv1 code %4u -> %.3f V   cv2 code %4u -> %.3f V   (nominal, at the jack)",
          high ? "high" : "low ", c1, jackVolts(c1), c2, jackVolts(c2));
        dacStep ^= 1;
        dacNext = millis() + 4000;
    }
}

static void dacProgramEeprom()
{
    monitorOn = false;
    sweepStop();
    pairsStop();
    dacStop();

    if (!haveDac1 && !haveDac2)
    {
        p("no DAC answered the address scan - run r first");
        return;
    }
    p("programming EEPROM to 0, normal mode (one write each, ~50 ms)");
    if (haveDac1)
        p("  cv1 0x%02X  %s", DAC_ADDR, dac::writeEeprom(DAC_ADDR, 0) ? "ok" : "FAILED");
    if (haveDac2)
        p("  cv2 0x%02X  %s", DAC2_ADDR, dac::writeEeprom(DAC2_ADDR, 0) ? "ok" : "FAILED");
}

// ---------------------------------------------------------------------------
//  Live monitor. Needs no keybed: a jumper from GP<strobe port><col> to
//  GP<return port><row> is electrically a key press, and exactly one cell
//  should light. With the keybed and button board plugged in, each lit cell
//  is named from position_map.cpp - that is the acceptance test for the
//  button board's seven joints. Raw view - no debounce, no ghost rejection -
//  so contact bounce and shorts stay visible.
// ---------------------------------------------------------------------------
static const char *NOTE_NAMES[12] = {"C", "C#", "D", "D#", "E", "F",
                                     "F#", "G", "G#", "A", "A#", "B"};

static void posLabel(uint8_t pos, char *out, size_t n)
{
    const PosMap &m = POSITION_MAP[pos];
    if (m.kind == K_NOTE)
        snprintf(out, n, "note %u %s%d", m.data, NOTE_NAMES[m.data % 12],
                 (int)(m.data / 12) - 1);
    else if (m.kind == K_CC)
        snprintf(out, n, "cc%u %s", m.data, ccName(m.data));
    else
        snprintf(out, n, "unmapped");
}

static void monitorTick()
{
    static uint8_t shown[N_COLS];
    static bool shownSel;
    static bool first = true;
    static uint32_t fails = 0;

    uint8_t now[N_COLS];
    const bool selB = digitalRead(PIN_CV_SELECT) == LOW;

    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        uint8_t rows;
        if (!mcp::writeReg(REG_COL_IODIR, mcp::colStrobe(c)) ||
            !mcp::readReg(REG_ROW_GPIO, rows))
        {
            ++fails;
            return; // a partial frame is worse than no frame
        }
        now[c] = mcp::packRows(rows);
    }
    mcp::writeReg(REG_COL_IODIR, 0xFF);

    if (!first && memcmp(now, shown, sizeof(now)) == 0 && selB == shownSel)
        return;
    first = false;
    memcpy(shown, now, sizeof(now));
    shownSel = selB;

    p("");
    p("        r0 r1 r2 r3 r4 r5      i2c errors: %lu   cv select: %s",
      (unsigned long)fails, selB ? "B (low)" : "A (high)");
    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        char line[128], label[32];
        int n = snprintf(line, sizeof(line), "    c%u  ", c);
        for (uint8_t r = 0; r < N_ROWS; ++r)
            n += snprintf(line + n, sizeof(line) - n, " %c ",
                          (now[c] & (1u << r)) ? 'X' : '.');

        for (uint8_t r = 0; r < N_ROWS; ++r)
            if (now[c] & (1u << r))
            {
                posLabel(POS(c, r), label, sizeof(label));
                n += snprintf(line + n, sizeof(line) - n, "  pos=%u %s  [GP"
                              COL_PORT_NAME "%u x GP" ROW_PORT_NAME "%u]",
                              POS(c, r), label, COL_BIT[c], ROW_BIT[r]);
            }

        Serial.println(line);
    }
}

// ---------------------------------------------------------------------------
//  Pin-pair monitor. The live monitor above trusts COLS_ON_PORT_A, COL_BIT
//  and ROW_BIT: a wire on a bit the tables do not list, or on the wrong port
//  altogether, never lights a cell - it is silent rather than wrong, and the
//  first I2C board had eight such keys. This mode assumes nothing about the
//  wiring. Each of the 16 pins is driven low in turn and the other 15 read,
//  so a key press or a jumper shows as the two chip pins it joins, plus what
//  the tables make of that pair. Both ports get the returns' pull-ups and
//  inversion while it runs; mcp::configure() restores the scan setup after.
//
//  Pin index 0-7 is GPA0-7, 8-15 is GPB0-7.
// ---------------------------------------------------------------------------
static bool pairsOn = false;

static constexpr uint8_t STROBE_PIN0 = COLS_ON_PORT_A ? 0 : 8;

static inline char pinPort(uint8_t i) { return i < 8 ? 'A' : 'B'; }

static int colOfBit(uint8_t bit)
{
    for (uint8_t c = 0; c < N_COLS; ++c)
        if (COL_BIT[c] == bit)
            return c;
    return -1;
}

static int rowOfBit(uint8_t bit)
{
    for (uint8_t r = 0; r < N_ROWS; ++r)
        if (ROW_BIT[r] == bit)
            return r;
    return -1;
}

static bool pairsSetup()
{
    // The returns' setup on both ports: input, pulled up, inverted, latch 0
    // so a pin switched to output drives low. Latches before directions, as
    // in mcp::configure().
    bool ok = mcp::writeReg(REG_OLATA, 0x00);
    ok &= mcp::writeReg(REG_OLATB, 0x00);
    ok &= mcp::writeReg(REG_IODIRA, 0xFF);
    ok &= mcp::writeReg(REG_IODIRB, 0xFF);
    ok &= mcp::writeReg(REG_GPPUA, 0xFF);
    ok &= mcp::writeReg(REG_GPPUB, 0xFF);
    ok &= mcp::writeReg(REG_IPOLA, 0xFF);
    ok &= mcp::writeReg(REG_IPOLB, 0xFF);
    return ok;
}

static void pairsStop()
{
    if (!pairsOn)
        return;
    pairsOn = false;
    // configure() never touches the strobe port's IPOL, so undo that one here
    // or the register dump would show it inverted from now on.
    mcp::writeReg(COLS_ON_PORT_A ? REG_IPOLA : REG_IPOLB, 0x00);
    mcp::configure();
    p("pin pairs off");
}

// What config.h makes of pins a and b being joined. On return a is the pin
// on the strobe port when exactly one of them is, so the caller prints the
// pair the way the live monitor does, strobe first.
static void pairLabel(uint8_t &a, uint8_t &b, char *out, size_t n)
{
    const bool aStrobe = (a < 8) == (STROBE_PIN0 == 0);
    const bool bStrobe = (b < 8) == (STROBE_PIN0 == 0);

    if (aStrobe == bStrobe)
    {
        snprintf(out, n, "both on the %s port: a wire on the wrong side of the"
                         " chip, or COLS_ON_PORT_A is wrong",
                 aStrobe ? "strobe" : "return");
        return;
    }
    if (!aStrobe)
    {
        const uint8_t t = a;
        a = b;
        b = t;
    }

    const int c = colOfBit(a & 7);
    const int r = rowOfBit(b & 7);
    if (c < 0 && r < 0)
        snprintf(out, n, "GP%c%u is in no COL_BIT entry, GP%c%u in no ROW_BIT entry",
                 pinPort(a), a & 7, pinPort(b), b & 7);
    else if (c < 0)
        snprintf(out, n, "GP%c%u is in no COL_BIT entry", pinPort(a), a & 7);
    else if (r < 0)
        snprintf(out, n, "GP%c%u is in no ROW_BIT entry", pinPort(b), b & 7);
    else
    {
        char label[32];
        posLabel(POS(c, r), label, sizeof(label));
        snprintf(out, n, "col %d row %d  pos=%u %s", c, r, POS(c, r), label);
    }
}

static void pairsTick()
{
    static uint16_t shown[16];
    static bool first = true;
    static uint32_t fails = 0;

    uint16_t now[16]; // now[i] bit j: pin j read closed while pin i was low
    for (uint8_t i = 0; i < 16; ++i)
    {
        const uint8_t iodir = (i < 8) ? REG_IODIRA : REG_IODIRB;
        uint8_t a = 0, b = 0;
        const bool ok = mcp::writeReg(iodir, (uint8_t)~(1u << (i & 7))) &&
                        mcp::readReg(REG_GPIOA, a) &&
                        mcp::readReg(REG_GPIOB, b);
        mcp::writeReg(iodir, 0xFF); // release before the next pin, always
        if (!ok)
        {
            ++fails;
            return; // a partial frame is worse than no frame
        }
        // The driven pin reads as closed to itself; drop that bit.
        now[i] = (uint16_t)((a | (b << 8)) & ~(1u << i));
    }

    // Seen from either end counts: a contact closing reads from one end a
    // frame before the other, and a pair that only ever reads one way is a
    // marginal contact, still worth naming. Symmetrise before comparing so
    // that a pair is printed once, not once per end.
    for (uint8_t i = 0; i < 16; ++i)
        for (uint8_t j = i + 1; j < 16; ++j)
            if (((now[i] >> j) | (now[j] >> i)) & 1)
            {
                now[i] |= (uint16_t)(1u << j);
                now[j] |= (uint16_t)(1u << i);
            }

    if (!first && memcmp(now, shown, sizeof(now)) == 0)
        return;
    first = false;
    memcpy(shown, now, sizeof(now));

    p("");
    p("    pin pairs closed      i2c errors: %lu", (unsigned long)fails);
    bool any = false;
    for (uint8_t i = 0; i < 16; ++i)
        for (uint8_t j = i + 1; j < 16; ++j)
        {
            if (!((now[i] >> j) & 1))
                continue;
            any = true;
            uint8_t s = i, t = j;
            char label[96];
            pairLabel(s, t, label, sizeof(label));
            p("    GP%c%u x GP%c%u   %s", pinPort(s), s & 7, pinPort(t), t & 7, label);
        }
    if (!any)
        p("    none");
}


// ---------------------------------------------------------------------------
//  Mapping sweep.
//
//  The shipped position_map.cpp is a placeholder: it guesses that the 28 piano
//  keys land on positions 0..27 in pitch order, which the design document
//  itself calls "almost certainly wrong". The real table has to come off the
//  hardware.
//
//  Doing that by hand means transcribing 48 col/row pairs out of a scrolling
//  log without losing your place. This records them instead - press the keys
//  in order, and it emits the finished file.
//
//  It uses keybed::scan() rather than the raw monitor above, so the presses
//  are debounced and ghost-filtered exactly as the firmware will see them.
// ---------------------------------------------------------------------------
enum SweepMode : uint8_t { SWEEP_NONE, SWEEP_NOTE, SWEEP_CC };

static SweepMode sweep = SWEEP_NONE;
static uint8_t sweepCount;  // assigned so far in this run
static uint8_t sweepBase;

static PosKind mapKind[N_POS];
static uint8_t mapData[N_POS];

static void sweepBegin(SweepMode mode)
{
    sweep = mode;
    sweepCount = 0;
    sweepBase = (mode == SWEEP_NOTE) ? SWEEP_BASE_NOTE : SWEEP_BASE_CC;

    keybed::begin();
    monitorOn = false;
    pairsStop();

    if (mode == SWEEP_NOTE)
    {
        p("");
        p("Recording NOTES from %u. Press the piano keys one at a time,",
          SWEEP_BASE_NOTE);
        p("lowest pitch first. Any other command key stops.");
        p("Chromatic is assumed - if this keybed skips accidentals, fix the");
        p("data column afterwards; the col/row half is what is hard to get.");
    }
    else
    {
        p("");
        p("Recording CCs from %u. Press the toe buttons, nose, face, transport", SWEEP_BASE_CC);
        p("and the rest, one at a time. Any other command key stops.");
    }
}

static void sweepTick()
{
    if (!keybed::scan())
        return;

    KeyEvent e;
    while (keybed::nextEvent(e))
    {
        if (!e.down)
            continue; // releases carry no new information here

        if (mapKind[e.pos] != K_NONE)
        {
            p("  pos %2u already recorded as %s %u - ignored",
              e.pos, mapKind[e.pos] == K_NOTE ? "note" : "cc", mapData[e.pos]);
            continue;
        }

        const uint8_t value = (uint8_t)(sweepBase + sweepCount);
        if (value > 127)
        {
            p("  ran past 127 - stopping");
            sweep = SWEEP_NONE;
            return;
        }

        mapKind[e.pos] = (sweep == SWEEP_NOTE) ? K_NOTE : K_CC;
        mapData[e.pos] = value;
        ++sweepCount;

        p("  %2u: pos %2u (col %u row %u) -> %s %u",
          sweepCount, e.pos, e.pos / N_ROWS, e.pos % N_ROWS,
          sweep == SWEEP_NOTE ? "note" : "cc", value);
    }
}

static void sweepStop()
{
    sweep = SWEEP_NONE;
}

static void sweepReset()
{
    for (uint8_t i = 0; i < N_POS; ++i)
    {
        mapKind[i] = K_NONE;
        mapData[i] = 0;
    }
    sweep = SWEEP_NONE;
    sweepCount = 0;
    p("recording cleared");
}

static void sweepWrite()
{
    uint8_t notes = 0, ccs = 0;
    for (uint8_t i = 0; i < N_POS; ++i)
    {
        if (mapKind[i] == K_NOTE) ++notes;
        else if (mapKind[i] == K_CC) ++ccs;
    }

    sweep = SWEEP_NONE;

    p("");
    p("%u notes, %u CCs, %u positions still unassigned.",
      notes, ccs, (unsigned)(N_POS - notes - ccs));
    p("Copy everything between the markers into src/position_map.cpp.");
    p("");
    p("// ---- BEGIN position_map.cpp ----");
    p("#include \"config.h\"");
    p("");
    p("// Generated by the selftest mapping sweep.");
    p("// Index = col * %u + row.", N_ROWS);
    p("");
    p("const PosMap POSITION_MAP[N_POS] = {");

    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        char line[128];
        int n = snprintf(line, sizeof(line), "    ");
        for (uint8_t r = 0; r < N_ROWS; ++r)
        {
            const uint8_t i = POS(c, r);
            const char *k = (mapKind[i] == K_NOTE) ? "K_NOTE"
                          : (mapKind[i] == K_CC)   ? "K_CC  "
                                                   : "K_NONE";
            n += snprintf(line + n, sizeof(line) - n, "{ %s, %3u }, ", k, mapData[i]);
        }
        snprintf(line + n, sizeof(line) - n, " // col %u", c);
        Serial.println(line);
    }

    p("};");
    p("// ---- END position_map.cpp ----");
}

// ---------------------------------------------------------------------------

static void runAll()
{
    p("");
    char colBits[2 * N_COLS + 1], rowBits[2 * N_ROWS + 1];
    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        colBits[2 * c] = (char)('0' + (COL_BIT[c] & 7));
        colBits[2 * c + 1] = ' ';
    }
    colBits[2 * N_COLS] = 0;
    for (uint8_t r = 0; r < N_ROWS; ++r)
    {
        rowBits[2 * r] = (char)('0' + (ROW_BIT[r] & 7));
        rowBits[2 * r + 1] = ' ';
    }
    rowBits[2 * N_ROWS] = 0;
    p("=== I2C board self test ========================================");
    p("    columns 0-%u strobe GP" COL_PORT_NAME " bits %s  rows 0-%u return on GP"
      ROW_PORT_NAME " bits %s (COLS_ON_PORT_A = %d)",
      N_COLS - 1, colBits, N_ROWS - 1, rowBits, COLS_ON_PORT_A);
    p("    expander 0x%02X, DACs 0x%02X / 0x%02X, bus %lu kHz, cv select gpio%d = %s",
      MCP_ADDR, DAC_ADDR, DAC2_ADDR, (unsigned long)(busHz / 1000), PIN_CV_SELECT,
      digitalRead(PIN_CV_SELECT) ? "A (high)" : "B (low)");
    testBusIdle();
    testAddressScan();
    testRegisters();
    testRetention();
    testBusQuality();
    testStrobe();
    testDacs();
    p("================================================================");
    p("r re-run   m live monitor   p pin pairs   d register dump   s bus stress");
    p("l re-run with every check at %lu kHz instead",
      (unsigned long)((busHz == I2C_HZ ? 100000 : I2C_HZ) / 1000));
    p("DACs:   v meter steps   o octave calibration   e program EEPROM to 0");
    p("sweep, only if a matrix wire moved:  n notes   c CCs   w write   z clear");
}

void setup()
{
    // Park the muxes exactly as the real firmware does. They are unpowered on
    // USB alone, but if the 12 V happens to be up this is what stops the cat
    // meowing through the whole test.
    inject::begin();

    // The CV select switch. Input-only pin; the 10k on the ESP32 board holds
    // it high, so the level is meaningful and the monitor shows it live.
    pinMode(PIN_CV_SELECT, INPUT);

    Serial.begin(USB_BAUD);
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
        // A monitor that sends a line ending would otherwise hit the default
        // case and switch the live view straight back off.
        case '\r':
        case '\n':
        case ' ':
            break;

        case 'r':
            monitorOn = false;
            sweep = SWEEP_NONE;
            pairsStop();
            dacStop();
            runAll();
            break;
        case 'l':
            monitorOn = false;
            sweep = SWEEP_NONE;
            pairsStop();
            dacStop();
            busHz = (busHz == I2C_HZ) ? 100000 : I2C_HZ;
            runAll();
            break;
        case 'v':
            dacBegin(DAC_STEPS);
            break;
        case 'o':
            dacBegin(DAC_OCTAVE);
            break;
        case 'e':
            dacProgramEeprom();
            break;
        case 'm':
            sweep = SWEEP_NONE;
            pairsStop();
            dacStop();
            monitorOn = !monitorOn;
            p(monitorOn ? "monitor on - press keys, or jumper a strobe pin to a return"
                          " pin; the physical pair is printed. Any key stops"
                        : "monitor off");
            break;
        case 'p':
            monitorOn = false;
            sweep = SWEEP_NONE;
            dacStop();
            if (pairsOn)
                pairsStop();
            else if (pairsSetup())
            {
                pairsOn = true;
                p("pin pairs on - no port roles or bit tables assumed. Press a key:");
                p("the two chip pins it joins are named, with what COL_BIT / ROW_BIT");
                p("make of them. Any key stops");
            }
            else
                p("expander not answering - run r first");
            break;
        case 'd':
            monitorOn = false;
            sweep = SWEEP_NONE;
            pairsStop();
            dacStop();
            p("register dump");
            dumpRegs(true);
            break;
        case 's':
            monitorOn = false;
            sweep = SWEEP_NONE;
            pairsStop();
            dacStop();
            testBusQuality();
            break;

        case 'n':
            dacStop();
            sweepBegin(SWEEP_NOTE);
            break;
        case 'c':
            dacStop();
            sweepBegin(SWEEP_CC);
            break;
        case 'w':
            monitorOn = false;
            pairsStop();
            dacStop();
            sweepWrite();
            break;
        case 'z':
            monitorOn = false;
            pairsStop();
            dacStop();
            sweepReset();
            break;
        default:
            if (monitorOn)
            {
                monitorOn = false;
                p("monitor off");
            }
            pairsStop();
            if (sweep != SWEEP_NONE)
            {
                sweep = SWEEP_NONE;
                p("sweep stopped - w writes the table, z clears it");
            }
            dacStop();
            break;
        }
    }

    if (monitorOn)
        monitorTick();
    else if (pairsOn)
        pairsTick();
    else if (sweep != SWEEP_NONE)
        sweepTick();
    else if (dacMode != DAC_OFF)
        dacTick();

    delay(SCAN_PERIOD_MS);
}
