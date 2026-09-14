#pragma once
#include <stdint.h>

// ============================================================================
//  Meowsic MIDI - build configuration
//  Pin numbers follow design doc section 6. Do not move anything to 6-11
//  (flash) or 0/2/12/15 (strapping).
// ============================================================================

// ---- USB (UART0) role -------------------------------------------------------
//  1 = raw MIDI bytes on UART0. Pair with Hairless MIDI or ttymidi on the PC,
//      both configured for USB_BAUD.
//  0 = human-readable position log on UART0, for the section 10 mapping sweep.
//      DIN MIDI keeps working in this mode.
#define USB_MIDI 1

static constexpr uint32_t USB_BAUD = 115200;

// ---- I2C / MCP23017 ---------------------------------------------------------
static constexpr int      PIN_SDA  = 21;
static constexpr int      PIN_SCL  = 22;
static constexpr uint32_t I2C_HZ   = 400000;   // needs the external 2.2k pull-ups
static constexpr uint8_t  MCP_ADDR = 0x20;     // A2:A0 = GND

// ---- MIDI DIN (UART2) -------------------------------------------------------
static constexpr int PIN_MIDI_TX = 17;
static constexpr int PIN_MIDI_RX = 16;         // unused until the MIDI-in stage

// ---- Injection muxes --------------------------------------------------------
// Injection is not implemented yet, but the firmware must still park INH high
// at boot or the cat holds a meow (gotcha checklist, section 11).
//
// Mux A selects a column, mux B a row. Both chips' selects landed on other
// GPIOs than the design document's when the board was wired; the constants
// follow the wiring, so channel n in the code is Y<n> on the chip.
static constexpr int PIN_MUX_INH  = 19;
static constexpr int PIN_MUXA_S0  = 27;
static constexpr int PIN_MUXA_S1  = 14;
static constexpr int PIN_MUXA_S2  = 13;
static constexpr int PIN_MUXB_S0  = 32;
static constexpr int PIN_MUXB_S1  = 33;
static constexpr int PIN_MUXB_S2  = 4;

// ---- Panic button -----------------------------------------------------------
// GPIO34 is input-only and has no internal pull-up. External 10k to 3.3 V,
// switch to GND, so the pin is active low.
static constexpr int PIN_PANIC = 34;

// ---- Matrix geometry --------------------------------------------------------
static constexpr uint8_t N_COLS = 8;
static constexpr uint8_t N_ROWS = 6;
static constexpr uint8_t N_POS  = N_COLS * N_ROWS;      // 48

// Which MCP23017 port carries the 8 column strobes. The two ports are
// electrically identical - both have the 100k pull-ups and the input inversion
// the returns need - so this follows the harness rather than forcing a rewire.
//
// Worth knowing when tracing it out: the DIP pinout runs GPB0-7 on physical
// pins 1-8 and GPA0-7 on pins 21-28, so port B is the one nearest pin 1.
//
//   1 = strobes on GPA0-7, returns on GPB0-5   (design doc default)
//   0 = strobes on GPB0-7, returns on GPA0-5   (8-way connector on port B)
#define COLS_ON_PORT_A 0

static constexpr uint8_t POS(uint8_t col, uint8_t row) { return col * N_ROWS + row; }

// ---- Injection channel map --------------------------------------------------
// The keybed side of the cut was mapped through the expander (position_map.cpp);
// the blob side was wired to the muxes in whatever order the wires fell. These
// translate a keybed column/row index into the mux channel that reaches the
// same blob line: MUX_COL_OF[c] is the mux A channel for keybed column c,
// MUX_ROW_OF[r] the mux B channel for keybed row r. Found with the mapping
// walk in the README (bring-up step 4) - fill in, do not rewire.
//
// Measured with the mapping walk, all 48 positions accounted for: columns
// from three note rows read independently, rows from their notes (rows 3-5,
// ascending pitch = keybed rows 4, 5, 3 on Y7, Y4, Y5) and buttons (0-2).
// Mux B Y0 and Y3 are tied to ground and must never appear here.
static constexpr uint8_t MUX_COL_OF[N_COLS] = {6, 4, 1, 5, 0, 7, 3, 2};
static constexpr uint8_t MUX_ROW_OF[N_ROWS] = {1, 6, 2, 5, 7, 4};

// ---- Timing -----------------------------------------------------------------
// A frame is 8 x (write IODIRA + read GPIOB) = ~1.4 ms at 400 kHz. A 2 ms
// period leaves ~0.6 ms of idle for the FreeRTOS idle task and the task
// watchdog. 500 Hz frame rate is still 6x the blob's own scan.
static constexpr uint32_t SCAN_PERIOD_MS = 2;

// Asymmetric by construction: a state change is emitted on the first frame that
// sees it, then that key is frozen for DEBOUNCE_US. Press latency is one frame
// (~2 ms), bounce inside the guard window is invisible.
static constexpr uint32_t DEBOUNCE_US = 5000;

// Consecutive failed I2C frames before the MCP23017 is re-initialised. The
// usual cause is a floating RESET pin (section 11).
static constexpr uint8_t I2C_FAIL_LIMIT = 10;

// ---- MIDI -------------------------------------------------------------------
static constexpr uint8_t NOTE_CHANNEL   = 0;    // 0-15 on the wire = 1-16 in a DAW
static constexpr uint8_t CTRL_CHANNEL   = 0;
static constexpr uint8_t NOTE_VELOCITY  = 100;  // keybed has one contact per key,
                                                // so there is no velocity to read
static constexpr int8_t  TRANSPOSE      = 0;    // semitones, applied at note-on

// ---- Position map -----------------------------------------------------------
enum PosKind : uint8_t {
    K_NONE = 0,   // position ignored
    K_NOTE,       // data = MIDI note number, sent on NOTE_CHANNEL
    K_CC          // data = CC number, 127 on press / 0 on release, CTRL_CHANNEL
};

struct PosMap {
    PosKind kind;
    uint8_t data;
};

// ---- Mapping sweep ----------------------------------------------------------
// Starting values the self test hands out while recording the 48 positions.
// Notes ascend chromatically from the first key you press, CCs ascend from the
// first button. Both are only a starting point for the generated table.
static constexpr uint8_t SWEEP_BASE_NOTE = 57;  // A3, the toy's lowest key (measured)
static constexpr uint8_t SWEEP_BASE_CC   = 20;  // 20-31 are undefined in the spec

extern const PosMap POSITION_MAP[N_POS];

// ---- Button identities ------------------------------------------------------
// CC numbers the mapping sweep handed the 8 keybed-side buttons, identified by
// injecting each and listening (docs/pinout.md, section 5), plus the 7 on the
// button board, which scan once that board is on the expander side.
enum ButtonCC : uint8_t {
    CC_PIANO   = 20, CC_BELLS  = 21, CC_MEOW   = 22, CC_ORGAN  = 23,
    CC_BANJO   = 24, CC_MUSIC  = 25, CC_STOP   = 26, CC_CATFACE = 27,
    CC_RECORD  = 28, CC_PLAY   = 29,                  // button board
    CC_ROCK    = 30, CC_BLUES  = 31, CC_SAMBA  = 32, CC_TECHNO = 33, CC_DISCO = 34,
    CC_LAST    = CC_DISCO
};

static constexpr const char *CC_NAME[CC_LAST - CC_PIANO + 1] = {
    "piano", "bells", "meow", "organ", "banjo", "music", "stop", "catface",
    "record", "play", "rock", "blues", "samba", "techno", "disco"};

static inline const char *ccName(uint8_t cc)
{
    return (cc >= CC_PIANO && cc <= CC_LAST) ? CC_NAME[cc - CC_PIANO] : "?";
}

// Positions with no keybed-side contact: the toy's own volume and tempo
// buttons, whose traces run straight to its PCB. Never scanned, but the
// injector can press them.
static constexpr uint8_t POS_TEMPO_UP   = POS(0, 0);
static constexpr uint8_t POS_TEMPO_DOWN = POS(1, 0);
static constexpr uint8_t POS_VOL_UP     = POS(2, 0);
static constexpr uint8_t POS_VOL_DOWN   = POS(5, 0);
