#include <Arduino.h>
#include <stdarg.h>

#include "config.h"
#include "inject.h"

// ============================================================================
//  Meowsic MIDI - 74HCT4051 injection bring-up self test.
//
//  Built as its own environment:  pio run -e muxtest -t upload
//
//  Needs only the ESP32 and the two muxes. No I2C: the MCP23017 and the DAC
//  can stay unplugged. The muxes do want their 5 V - USB alone does not
//  provide it, by design - so either the power board is up, or for the bench
//  jumper VIN to both VCC pins for the duration. Their ground must be the
//  ESP32's ground; a floating one reads ~1.7 V on every select and passes
//  nothing.
//
//  Two kinds of coordinate, and the log always says which:
//    raw      a mux channel pair: mux A channel a joined to mux B channel b.
//             That is Y<a> of the column chip to Y<b> of the row chip, and
//             whichever blob lines those pins were wired to.
//    keybed   a (col,row) of position_map.cpp, i.e. what the expander sees.
//             MUX_COL_OF / MUX_ROW_OF in config.h translate keybed to raw.
//  The digit/letter commands are raw - that is what the mapping walk needs.
//  The sweeps are keybed, through the tables, so once the tables are right
//  the scale sweep plays a scale.
//
//  Two ways to read a result:
//    meter  blob unpowered, muxes powered, ohms between the two Y pins named
//           in the log: ~100-300 ohm when connected, open otherwise.
//    ears   blob powered: a connected pair plays whatever key those two blob
//           lines make; k should play an ascending scale.
//
//  Serial monitor at 115200, single-letter commands, no Enter needed:
//    0-7   raw: select mux A channel        selects take effect at once;
//    a-h   raw: select mux B channel 0-7    INH is raised while they move
//    o     INH low: the selected pair stays connected until x
//    x     INH high: everything open
//    p     one 50 ms press of the selected pair
//    t     print the keybed map as a grid of note names
//    s     sweep every keybed position in position order, 250 ms each
//    k     sweep the piano keys in ascending note order - the scale test
//    v     sweep the panel buttons: press each, then play the lowest key
//    i     INH gating check: every channel cycled with INH high - must be silent
//    z     stop a sweep
//    ?     banner
//
//  On this board mux B's six row lines sit on Y1, Y2, Y4, Y5, Y6, Y7; Y0 and
//  Y3 are tied to ground, so raw a and d connect a column to nothing.
// ============================================================================

static void p(const char *fmt, ...)
{
    char buf[160];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    Serial.println(buf);
}

static const char *NOTE_NAMES[12] = {"C", "C#", "D", "D#", "E", "F",
                                     "F#", "G", "G#", "A", "A#", "B"};

// DIP-16 pin of Y0..Y7, so the meter hint can name pins instead of pads.
static const uint8_t Y_PIN[8] = {13, 14, 15, 12, 1, 5, 2, 4};

// What position_map.cpp says lives at a keybed position, for the log.
static const char *describe(uint8_t col, uint8_t row)
{
    static char s[32];
    if (col >= N_COLS || row >= N_ROWS)
        return "outside the map";
    const PosMap &m = POSITION_MAP[POS(col, row)];
    switch (m.kind)
    {
    case K_NOTE:
        snprintf(s, sizeof(s), "note %u %s%d", m.data,
                 NOTE_NAMES[m.data % 12], (int)m.data / 12 - 1);
        break;
    case K_CC:
        snprintf(s, sizeof(s), "button %s (cc %u)", ccName(m.data), m.data);
        break;
    default:
        snprintf(s, sizeof(s), "unmapped");
        break;
    }
    return s;
}

// Inverse of the config tables: which keybed index uses this channel, or -1.
static int keybedColOf(uint8_t a)
{
    for (uint8_t c = 0; c < N_COLS; ++c)
        if (MUX_COL_OF[c] == a)
            return c;
    return -1;
}

static int keybedRowOf(uint8_t b)
{
    for (uint8_t r = 0; r < N_ROWS; ++r)
        if (MUX_ROW_OF[r] == b)
            return r;
    return -1;
}

// Mux control is inject.cpp, the production injector, so a pass here
// exercises what the firmware will use rather than a copy of it.

static void showState()
{
    p("raw: mux A ch %u (pin %u)  mux B ch %u (pin %u)  INH %s",
      inject::rawA(), Y_PIN[inject::rawA()], inject::rawB(), Y_PIN[inject::rawB()],
      inject::closed() ? "low  (connected)" : "high (open)");
    const int c = keybedColOf(inject::rawA()), r = keybedRowOf(inject::rawB());
    if (c < 0 || r < 0)
        p("     = no keybed position: channel not in MUX_COL_OF / MUX_ROW_OF");
    else
        p("     = keybed col %d row %d  %s", c, r, describe(c, r));
}

static void printGrid()
{
    char line[96];
    int n = snprintf(line, sizeof(line), "keybed  ");
    for (uint8_t c = 0; c < N_COLS; ++c)
        n += snprintf(line + n, sizeof(line) - n, " c%-7u", c);
    p("%s", line);
    for (uint8_t r = 0; r < N_ROWS; ++r)
    {
        n = snprintf(line, sizeof(line), "   r%u   ", r);
        for (uint8_t c = 0; c < N_COLS; ++c)
        {
            const PosMap &m = POSITION_MAP[POS(c, r)];
            char cell[10];
            if (m.kind == K_NOTE)
                snprintf(cell, sizeof(cell), "%s%d",
                         NOTE_NAMES[m.data % 12], (int)m.data / 12 - 1);
            else if (m.kind == K_CC)
                snprintf(cell, sizeof(cell), "%s", ccName(m.data));
            else
                snprintf(cell, sizeof(cell), "-");
            n += snprintf(line + n, sizeof(line) - n, " %-8s", cell);
        }
        p("%s", line);
    }
}

// ---------------------------------------------------------------------------
//  Sweeps, in keybed positions through the tables (the INH check is raw).
//  Non-blocking so a keypress can stop one; each step is a connect/release
//  pair on a millis() schedule.
// ---------------------------------------------------------------------------
enum Sweep : uint8_t { SW_NONE, SW_POS, SW_NOTES, SW_CC, SW_INH };

static Sweep    sweep   = SW_NONE;
static uint16_t swIndex = 0;
static uint8_t  swPhase = 0;
static uint32_t swNext  = 0;

static uint8_t order[N_POS];
static uint8_t orderLen = 0;

static constexpr uint32_t HOLD_MS  = 250; // a key: well above the blob's 10-20 ms poll
static constexpr uint32_t GAP_MS   = 100;
static constexpr uint32_t PRESS_MS = 50;  // a button: one-shot, as the firmware will do it

static void orderNotes()
{
    orderLen = 0;
    for (int n = 0; n < 128; ++n)
        for (uint8_t pos = 0; pos < N_POS; ++pos)
            if (POSITION_MAP[pos].kind == K_NOTE && POSITION_MAP[pos].data == n)
                order[orderLen++] = pos;
}

// Panel buttons only: the button-board ones start rhythms and recordings.
static void orderButtons()
{
    orderLen = 0;
    for (uint8_t pos = 0; pos < N_POS; ++pos)
        if (POSITION_MAP[pos].kind == K_CC && POSITION_MAP[pos].data < CC_RECORD)
            order[orderLen++] = pos;
}

static uint8_t lowestNotePos()
{
    for (int n = 0; n < 128; ++n)
        for (uint8_t pos = 0; pos < N_POS; ++pos)
            if (POSITION_MAP[pos].kind == K_NOTE && POSITION_MAP[pos].data == n)
                return pos;
    return 0xFF;
}

static void logKeybed(uint8_t pos)
{
    const uint8_t col = pos / N_ROWS, row = pos % N_ROWS;
    p("  pos %2u  keybed col %u row %u  (raw %u,%u)  %s", pos, col, row,
      MUX_COL_OF[col], MUX_ROW_OF[row], describe(col, row));
}

static void sweepEnd(const char *msg)
{
    inject::open();
    sweep = SW_NONE;
    p("%s", msg);
}

static void sweepBegin(Sweep mode)
{
    inject::open();
    sweep   = mode;
    swIndex = 0;
    swPhase = 0;
    swNext  = millis();
    switch (mode)
    {
    case SW_POS:
        p("sweeping all %u keybed positions, %lu ms each - any key stops",
          N_POS, (unsigned long)HOLD_MS);
        break;
    case SW_NOTES:
        orderNotes();
        p("sweeping %u keys in note order - expect a scale from the lowest key up",
          orderLen);
        break;
    case SW_CC:
        orderButtons();
        p("sweeping %u panel buttons - each is pressed, then the lowest key is played",
          orderLen);
        break;
    case SW_INH:
        p("INH check: every raw channel cycled with INH high for ~3 s - the toy must stay silent");
        break;
    default:
        break;
    }
}

static void sweepTick()
{
    const uint32_t now = millis();
    if ((int32_t)(now - swNext) < 0)
        return;

    switch (sweep)
    {
    case SW_POS:
    case SW_NOTES:
    {
        const uint16_t count = (sweep == SW_POS) ? N_POS : orderLen;
        if (swIndex >= count)
        {
            sweepEnd(sweep == SW_POS
                         ? "sweep done"
                         : "scale done - a wrong note is a wrong entry in MUX_COL_OF / MUX_ROW_OF");
            return;
        }
        const uint8_t pos = (sweep == SW_POS) ? (uint8_t)swIndex : order[swIndex];
        if (swPhase == 0)
        {
            inject::selectPos(pos);
            inject::close();
            logKeybed(pos);
            swPhase = 1;
            swNext  = now + HOLD_MS;
        }
        else
        {
            inject::open();
            ++swIndex;
            swPhase = 0;
            swNext  = now + GAP_MS;
        }
        break;
    }

    case SW_CC:
    {
        if (swIndex >= orderLen)
        {
            sweepEnd("buttons done");
            return;
        }
        const uint8_t pos = order[swIndex];
        switch (swPhase)
        {
        case 0:
            inject::selectPos(pos);
            inject::close();
            logKeybed(pos);
            swPhase = 1;
            swNext  = now + PRESS_MS;
            break;
        case 1:
            inject::open();
            swPhase = 2;
            swNext  = now + 150;
            break;
        case 2:
        {
            const uint8_t key = lowestNotePos();
            if (key == 0xFF)
            {
                swPhase = 4;
                break;
            }
            inject::selectPos(key);
            inject::close();
            swPhase = 3;
            swNext  = now + 300;
            break;
        }
        case 3:
            inject::open();
            swPhase = 4;
            swNext  = now + 500;
            break;
        default:
            ++swIndex;
            swPhase = 0;
            break;
        }
        break;
    }

    case SW_INH:
        if (swIndex >= 2 * 64)
        {
            sweepEnd("INH check done - if anything sounded, INH is not holding: "
                     "10 k pull-up on the INH net missing, or a select and INH wire swapped");
            return;
        }
        inject::selectRaw(swIndex & 7, (swIndex >> 3) & 7); // raises INH, never lowers it
        ++swIndex;
        swNext = now + 20;
        break;

    default:
        break;
    }
}

// ---------------------------------------------------------------------------

static void banner()
{
    p("");
    p("=== 74HCT4051 injection self test ==============================");
    p("    mux A (columns) S0/S1/S2 = GPIO%d/%d/%d", PIN_MUXA_S0, PIN_MUXA_S1, PIN_MUXA_S2);
    p("    mux B (rows)    S0/S1/S2 = GPIO%d/%d/%d", PIN_MUXB_S0, PIN_MUXB_S1, PIN_MUXB_S2);
    p("    INH (both)               = GPIO%d, parked high at boot", PIN_MUX_INH);
    p("    keybed map: %u cols x %u rows from position_map.cpp", N_COLS, N_ROWS);
    p("    MUX_COL_OF = {%u,%u,%u,%u,%u,%u,%u,%u}  MUX_ROW_OF = {%u,%u,%u,%u,%u,%u}",
      MUX_COL_OF[0], MUX_COL_OF[1], MUX_COL_OF[2], MUX_COL_OF[3],
      MUX_COL_OF[4], MUX_COL_OF[5], MUX_COL_OF[6], MUX_COL_OF[7],
      MUX_ROW_OF[0], MUX_ROW_OF[1], MUX_ROW_OF[2], MUX_ROW_OF[3],
      MUX_ROW_OF[4], MUX_ROW_OF[5]);
    p("");
    p("    the muxes need 5 V and the ESP32's ground: a floating ground reads ~1.7 V");
    p("    on the selects and passes nothing");
    p("    meter (blob off): the two Y pins named after o read ~100-300 ohm");
    p("    ears (blob on):   a connected pair plays; k should play a scale");
    p("");
    p("raw: 0-7 mux A channel   a-h mux B channel   o connect   x open   p press 50 ms");
    p("t keybed grid   s sweep positions   k scale   v buttons   i INH check   z stop   ? this");
    p("================================================================");
    showState();
}

void setup()
{
    inject::begin(); // INH high before the selects are touched

    Serial.begin(USB_BAUD);
    delay(300); // let the host reopen the port after the reset
    banner();
}

void loop()
{
    if (Serial.available())
    {
        const int  ch           = Serial.read();
        const bool wasConnected = inject::closed();
        switch (ch)
        {
        // A monitor that sends a line ending would otherwise hit the default
        // case and stop a running sweep.
        case '\r':
        case '\n':
        case ' ':
            break;

        case '0': case '1': case '2': case '3':
        case '4': case '5': case '6': case '7':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            inject::selectRaw(ch - '0', inject::rawB());
            if (wasConnected)
                inject::close(); // stepping channels with a meter attached
            showState();
            break;

        case 'a': case 'b': case 'c': case 'd':
        case 'e': case 'f': case 'g': case 'h':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            inject::selectRaw(inject::rawA(), ch - 'a');
            if (wasConnected)
                inject::close();
            showState();
            break;

        case 'o':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            inject::close();
            showState();
            p("     meter: mux A pin %u to mux B pin %u, expect ~100-300 ohm",
              Y_PIN[inject::rawA()], Y_PIN[inject::rawB()]);
            break;
        case 'x':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            inject::open();
            showState();
            break;
        case 'p':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            inject::close();
            delay(PRESS_MS);
            inject::open();
            p("pressed raw %u,%u for %lu ms", inject::rawA(), inject::rawB(), (unsigned long)PRESS_MS);
            break;

        case 't':
            printGrid();
            break;
        case 's':
            sweepBegin(SW_POS);
            break;
        case 'k':
            sweepBegin(SW_NOTES);
            break;
        case 'v':
            sweepBegin(SW_CC);
            break;
        case 'i':
            sweepBegin(SW_INH);
            break;
        case 'z':
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            else
                inject::open();
            showState();
            break;
        case '?':
            banner();
            break;

        default:
            if (sweep != SW_NONE)
                sweepEnd("sweep stopped");
            break;
        }
    }

    if (sweep != SW_NONE)
        sweepTick();

    delay(1);
}
