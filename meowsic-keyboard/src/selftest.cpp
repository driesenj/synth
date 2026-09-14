#include <Arduino.h>
#include <Wire.h>
#include <stdarg.h>
#include <string.h>

#include "config.h"
#include "inject.h"
#include "keybed.h"
#include "mcp23017.h"

// ============================================================================
//  Meowsic MIDI - MCP23017 bring-up self test.
//
//  Built as its own environment:  pio run -e selftest -t upload
//
//  Shares mcp23017.cpp with the real firmware, so a pass here means the
//  production driver talks to the chip - not merely that something ACKed.
//
//  Runs with only the expander wired: no keybed, no blob, no 12 V. USB alone
//  powers the ESP32 and the MCP23017 (README, "Power notes that matter to
//  firmware"), so this is a bench test with the toy unplugged.
//
//  Serial monitor at 115200, single-letter commands:
//    r  re-run the full sequence
//    m  live matrix monitor - short a strobe pin to a return pin
//
//  Which physical port is strobes and which is returns follows
//  COLS_ON_PORT_A in config.h; the banner prints the active mapping.
//    d  dump the configuration registers once
//    s  bus stress test at 100 kHz and 400 kHz
//
//  Mapping sweep - fills in position_map.cpp without probing the keybed:
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

// ---------------------------------------------------------------------------
//  1. Bus idle levels, before I2C is brought up.
//
//  Only a LOW reading is conclusive: something is holding the line down - a
//  short to ground, or a device stuck mid-transaction. HIGH does not prove the
//  2.2k pull-ups are present or the right value; that is what the 400 kHz
//  stress test in step 5 is for.
// ---------------------------------------------------------------------------
static void testBusIdle()
{
    pinMode(PIN_SDA, INPUT); // no internal pull-up - we want the bus own level
    pinMode(PIN_SCL, INPUT);
    delayMicroseconds(50);

    const bool sda = digitalRead(PIN_SDA);
    const bool scl = digitalRead(PIN_SCL);

    p("[1] bus idle    SDA(gpio%d)=%s  SCL(gpio%d)=%s",
      PIN_SDA, sda ? "HIGH" : "LOW", PIN_SCL, scl ? "HIGH" : "LOW");

    if (!sda || !scl)
        p("    FAIL  a line is stuck low: short to GND, or a wedged device");
    else
        p("    ok    both lines released");
}

// ---------------------------------------------------------------------------
//  2. Address sweep. Catches a chip that is present but at the wrong address,
//     which means A0-A2 are not actually grounded.
// ---------------------------------------------------------------------------
static void testAddressScan()
{
    Wire.begin(PIN_SDA, PIN_SCL, I2C_HZ);
    Wire.setTimeOut(20);

    uint8_t found = 0;
    bool atExpected = false;

    p("[2] address scan (0x03-0x77)");
    for (uint8_t a = 0x03; a <= 0x77; ++a)
    {
        Wire.beginTransmission(a);
        if (Wire.endTransmission() != 0)
            continue;

        ++found;
        if (a == MCP_ADDR)
            atExpected = true;
        p("    device at 0x%02X%s", a, a == MCP_ADDR ? "  <- expected" : "");
    }

    if (found == 0)
    {
        p("    FAIL  nothing on the bus. Check VDD, GND, SDA/SCL not swapped,");
        p("          and RESET (chip pin 18) pulled to 3.3 V through 10k.");
    }
    else if (!atExpected)
    {
        p("    FAIL  chip answers, but not at 0x%02X. A0-A2 (pins 15-17) are", MCP_ADDR);
        p("          not all grounded - the offset from 0x20 is their value.");
    }
    else
    {
        p("    ok    %u device(s), including 0x%02X", found, MCP_ADDR);
    }
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

static bool dumpRegs(bool verbose)
{
    uint8_t bad = 0, atPor = 0;

    for (uint8_t i = 0; i < N_REGS; ++i)
    {
        uint8_t got = 0;
        if (!mcp::readReg(REGS[i].reg, got))
        {
            p("    %s @0x%02X  READ FAILED", REGS[i].name, REGS[i].reg);
            ++bad;
            continue;
        }

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
    return bad == 0;
}

static void testRegisters()
{
    p("[3] register write / read-back");

    if (!mcp::begin())
    {
        p("    FAIL  mcp::begin() - no ACK, or a config write was not accepted");
        return;
    }
    if (dumpRegs(true))
        p("    ok    all %u registers hold the configured value", N_REGS);
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

    p("[4] state retention (walking pattern through port " ROW_PORT_NAME " OLAT)");

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
static uint16_t hammer(uint32_t hz, uint16_t n)
{
    Wire.setClock(hz);
    delay(2);

    uint16_t fails = 0;
    for (uint16_t i = 0; i < n; ++i)
    {
        uint8_t v;
        if (!mcp::readReg(REG_ROW_GPIO, v))
            ++fails;
    }
    return fails;
}

static void testBusQuality()
{
    static constexpr uint16_t N = 2000;

    p("[5] bus stress, %u reads at each speed", N);

    const uint16_t slow = hammer(100000, N);
    const uint16_t fast = hammer(I2C_HZ, N);

    p("    100 kHz  %4u / %u failed", slow, N);
    p("    %3lu kHz  %4u / %u failed", (unsigned long)(I2C_HZ / 1000), fast, N);

    if (slow == 0 && fast == 0)
        p("    ok    clean at both speeds");
    else if (slow == 0)
    {
        p("    FAIL  clean at 100 kHz, dirty at %lu kHz. That is the signature",
          (unsigned long)(I2C_HZ / 1000));
        p("          of missing or too-weak pull-ups - this firmware needs 2.2k");
        p("          to 3.3 V on both lines. Long unshielded runs do it too.");
    }
    else
    {
        p("    FAIL  errors even at 100 kHz. Wiring, power, or RESET.");
    }

    Wire.setClock(I2C_HZ);
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

    p("[6] column strobe, keybed detached - every row must read 0");

    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        const uint8_t want = (uint8_t)~(1u << c);

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
        if (rows & 0x3F)
        {
            p("    col %u  GP" ROW_PORT_NAME "=%s  <- closed with nothing wired:",
              c, bin8(rows));
            p("           GP" COL_PORT_NAME "%u is shorted to a return line", c);
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
    const uint32_t wireW = WRITE_BITS * 1000000UL / I2C_HZ;
    const uint32_t wireR = READ_BITS * 1000000UL / I2C_HZ;

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
//  Live monitor. The point of this mode is that it needs no keybed: a jumper
//  from GP<strobe port><col> to GP<return port><row> is electrically a key
//  press, and exactly one cell should light. Raw view - no debounce, no ghost
//  rejection - so contact bounce and shorts stay visible.
// ---------------------------------------------------------------------------
static bool monitorOn = false;

static void monitorTick()
{
    static uint8_t shown[N_COLS];
    static bool first = true;
    static uint32_t fails = 0;

    uint8_t now[N_COLS];

    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        uint8_t rows;
        if (!mcp::writeReg(REG_COL_IODIR, (uint8_t)~(1u << c)) ||
            !mcp::readReg(REG_ROW_GPIO, rows))
        {
            ++fails;
            return; // a partial frame is worse than no frame
        }
        now[c] = rows & 0x3F;
    }
    mcp::writeReg(REG_COL_IODIR, 0xFF);

    if (!first && memcmp(now, shown, sizeof(now)) == 0)
        return;
    first = false;
    memcpy(shown, now, sizeof(now));

    p("");
    p("        r0 r1 r2 r3 r4 r5      i2c errors: %lu", (unsigned long)fails);
    for (uint8_t c = 0; c < N_COLS; ++c)
    {
        char line[72];
        int n = snprintf(line, sizeof(line), "    c%u  ", c);
        for (uint8_t r = 0; r < N_ROWS; ++r)
            n += snprintf(line + n, sizeof(line) - n, " %c ",
                          (now[c] & (1u << r)) ? 'X' : '.');

        for (uint8_t r = 0; r < N_ROWS; ++r)
            if (now[c] & (1u << r))
                n += snprintf(line + n, sizeof(line) - n, "  pos=%u", POS(c, r));

        Serial.println(line);
    }
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
    p("=== MCP23017 self test =========================================");
    p("    %u strobes on port " COL_PORT_NAME "0-%u, %u returns on port "
      ROW_PORT_NAME "0-%u   (COLS_ON_PORT_A = %d)",
      N_COLS, N_COLS - 1, N_ROWS, N_ROWS - 1, COLS_ON_PORT_A);
    testBusIdle();
    testAddressScan();
    testRegisters();
    testRetention();
    testBusQuality();
    testStrobe();
    p("================================================================");
    p("r re-run   m live monitor   d register dump   s bus stress");
    p("sweep:  n notes   c CCs   w write position_map.cpp   z clear");
}

void setup()
{
    // Park the muxes exactly as the real firmware does. They are unpowered on
    // USB alone, but if the 12 V happens to be up this is what stops the cat
    // meowing through the whole test.
    inject::begin();

    // GPIO34 is deliberately left alone here. The panic button is not part of
    // the expander, and if its 10k pull-up is not fitted yet the pin floats and
    // would only add noise to the log.

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
            runAll();
            break;
        case 'm':
            sweep = SWEEP_NONE;
            monitorOn = !monitorOn;
            p(monitorOn ? "monitor on - jumper GP" COL_PORT_NAME "<col> to GP"
                      ROW_PORT_NAME "<row>, any key stops"
                    : "monitor off");
            break;
        case 'd':
            monitorOn = false;
            sweep = SWEEP_NONE;
            p("register dump");
            dumpRegs(true);
            break;
        case 's':
            monitorOn = false;
            sweep = SWEEP_NONE;
            testBusQuality();
            break;

        case 'n':
            sweepBegin(SWEEP_NOTE);
            break;
        case 'c':
            sweepBegin(SWEEP_CC);
            break;
        case 'w':
            monitorOn = false;
            sweepWrite();
            break;
        case 'z':
            monitorOn = false;
            sweepReset();
            break;
        default:
            if (monitorOn)
            {
                monitorOn = false;
                p("monitor off");
            }
            if (sweep != SWEEP_NONE)
            {
                sweep = SWEEP_NONE;
                p("sweep stopped - w writes the table, z clears it");
            }
            break;
        }
    }

    if (monitorOn)
        monitorTick();
    else if (sweep != SWEEP_NONE)
        sweepTick();

    delay(SCAN_PERIOD_MS);
}
