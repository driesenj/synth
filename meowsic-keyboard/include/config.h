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
//  0 = human-readable log on UART0: every key, command and state change, and
//      's' dumps the state - what the acceptance runs in docs/tests.md read.
//      DIN MIDI keeps working in this mode.
//  The 'text' environment in platformio.ini builds the same firmware with
//  this at 0, so neither the acceptance runs nor debugging need to edit it:
//      pio run -e text -t upload
#ifndef USB_MIDI
#define USB_MIDI 1
#endif

static constexpr uint32_t USB_BAUD = 115200;

// ---- I2C bus: MCP23017 + two MCP4725 --------------------------------------
// All three sit on the I2C board with the bus's only 2.2k pull-up pair
// (docs/pinout.md section 2).
static constexpr int PIN_SDA = 21;
static constexpr int PIN_SCL = 22;
static constexpr uint32_t I2C_HZ = 400000; // needs the external 2.2k pull-ups
static constexpr uint8_t MCP_ADDR = 0x20;  // A2:A0 = GND
static constexpr uint8_t DAC_ADDR = 0x60;  // MCP4725 #1, CV1 - ADDR jumper open
static constexpr uint8_t DAC2_ADDR = 0x61; // MCP4725 #2, CV2 - ADDR jumper closed

// ---- CV out -----------------------------------------------------------------
// 3.3 V / 4096 = 0.806 mV per code, x1.5 at the TL074 = 1.209 mV at the jack;
// 83.33 mV per semitone at 1 V/oct -> 68.96 codes nominal. Each channel is
// calibrated on its own with the self test's octave mode ('o') and a meter:
// adjust until two codes 12 semitones apart differ by 1.000 V at the jack.
static constexpr float CV_CODES_PER_SEMITONE = 68.96f;  // CV1, TL074 A1
static constexpr float CV2_CODES_PER_SEMITONE = 68.96f; // CV2, TL074 A4

// ---- MIDI DIN (UART2) -------------------------------------------------------
static constexpr int PIN_MIDI_TX = 17;
static constexpr int PIN_MIDI_RX = 16; // 4N35 collector, 1k to 3.3 V

// ---- Injection muxes --------------------------------------------------------
// Injection is not implemented yet, but the firmware must still park INH high
// at boot or the cat holds a meow (gotcha checklist, section 11).
//
// Mux A selects a column, mux B a row. Both chips' selects landed on other
// GPIOs than the design document's when the board was wired; the constants
// follow the wiring, so channel n in the code is Y<n> on the chip.
static constexpr int PIN_MUX_INH = 19;
static constexpr int PIN_MUXA_S0 = 27;
static constexpr int PIN_MUXA_S1 = 14;
static constexpr int PIN_MUXA_S2 = 13;
static constexpr int PIN_MUXB_S0 = 32;
static constexpr int PIN_MUXB_S1 = 33;
static constexpr int PIN_MUXB_S2 = 4;

// ---- CV select switch -------------------------------------------------------
// GPIO34 is input-only and has no internal pull-up. External 10k to 3.3 V,
// slide switch to GND, read as a level: open (high) = the keys drive channel
// A (CV1 / gate 1), closed (low) = channel B. The other channel is MIDI
// in's. This used to be the panic button; panic is a long press of the toy's
// STOP button now (docs/firmware.md section 2).
static constexpr int PIN_CV_SELECT = 34;

// ---- Buttons ----------------------------------------------------------------
// One threshold for every long press - panic, undo, clear and the settings
// behind the rhythm buttons. Buttons that have a long-press function act on
// release, so a short press costs the release time; the voice buttons and
// catface have none and act on the press, as the toy did.
static constexpr uint32_t LONG_PRESS_MS = 1000;

// ---- Panel side: gates, AUX, clock in, pots, LED (docs/pinout.md section 1) --
// All through the op-amp board except the pots and the LED. Gate 2 is the
// DAC2 pin used as a plain GPIO; AUX is DAC1 proper. GPIO34-39 are input-only
// with no internal pull-ups: the clock collector has its 10k on the ESP32
// board, the pots are dividers, the CV select switch has its own 10k.
// As built, the two gate wires landed the other way round from the pinout
// document: GPIO26 ends at the gate 1 jack and GPIO23 at gate 2 (found with
// the stage 1 acceptance run). The constants follow the jacks.
static constexpr int PIN_GATE = 26;     // channel A gate -> the gate 1 jack, 0 / 4.5 V
static constexpr int PIN_GATE2 = 23;    // channel B gate -> the gate 2 jack
static constexpr int PIN_AUX = 25;      // 8-bit DAC1 -> TL072 B2; loop phase for now
static constexpr int PIN_CLOCK_IN = 35; // BC549 collector, falling edge = rising edge at the jack
static constexpr int PIN_POT_BASE = 39; // ADC1_CH3 (VN), base pitch - as built, the pots are on the
static constexpr int PIN_POT_TUNE = 36; // ADC1_CH0 (VP), tune         other pins from the pinout document
// The LED legs sit on J9 as wired; only the red leg is bound to a pin, since
// the 330 ohm behind GPIO2 is sized for red's 2 V drop and starves green or
// blue (3 V). Green and blue share 100 ohm legs and could swap.
static constexpr int PIN_LED_RED = 2;    // J9.4, 330 ohm; also the DevKit's own LED
static constexpr int PIN_LED_BLUE = 5;   // J9.3, 100 ohm
static constexpr int PIN_LED_GREEN = 18; // J9.2, 100 ohm

// What the op-amp board makes of a 3.3 V logic high at the gate and AUX
// inputs: x1.5, behind the 100k / 1M divider that holds the input at 0 V
// when the ESP32 board is unplugged.
static constexpr float PANEL_LOGIC_GAIN = 1.5f * 1000.0f / 1100.0f; // 1.364 -> 4.5 V

// ---- CV pitch ---------------------------------------------------------------
// 1 V/oct with 0 V at CV_ZERO_NOTE (A2). The lowest key, A3, is then 1 V with
// the base pitch pot centred and C6 is 3.25 V; the pot's +-12 semitones stay
// inside the DAC's 59 (0-4.95 V). Anything beyond clamps. The pots act on
// the keys' channel only - MIDI in's channel gets the note the DAW sent.
static constexpr uint8_t CV_ZERO_NOTE = 45;
static constexpr float BASE_PITCH_SEMIS = 12.0f; // base pitch pot, +- this
static constexpr float TUNE_SEMIS = 0.5f;        // tune pot, +-50 cents, CV only
static constexpr uint8_t CV_STACK_LEN = 16;      // held notes remembered per channel

// Gate retrigger: how long the gate dips when a new note lands on a held
// one. Envelopes want a few ms of low to restart; one scan frame is ~2.6 ms.
static constexpr uint32_t GATE_RETRIG_MS = 3;

// Glide, per setting: off, short, long. Time constant of the slew towards
// the new pitch, so a semitone step settles in about three of these.
static constexpr uint16_t GLIDE_MS[3] = {0, 50, 250};

// ---- Pots -------------------------------------------------------------------
// ESP32 ADC1 at 12 bits and 11 dB: about +-20 counts of noise, reads 0 up to
// ~0.1 V and 4095 from ~3.15 V. Sampled every POT_SAMPLE_MS and smoothed;
// the dead ends are clipped so the knob reaches both extremes of its range.
// The quantised base pitch only changes step once the reading is this far
// past the boundary, in steps, so noise cannot flicker it.
static constexpr uint32_t POT_SAMPLE_MS = 10;
static constexpr uint16_t POT_ADC_LO = 150;
static constexpr uint16_t POT_ADC_HI = 3950;
static constexpr float POT_STEP_HYST = 0.15f;
// J5 and J6 carry their rails in opposite order (docs/pinout.md section 1),
// so with the pots mounted alike one knob runs backwards. Flip it here, not
// on the board. Clockwise should raise the pitch on both.
#define POT_BASE_REVERSED 0
#define POT_TUNE_REVERSED 1

// ---- LED --------------------------------------------------------------------
// Full-scale duty per leg. Green and blue sit on 100 ohm, red on 330, and the
// eye weighs them differently again; balance is done here, not in resistors.
// Starting guesses - trim until white is white.
static constexpr uint32_t LED_PWM_HZ = 5000;
static constexpr uint8_t LED_LEVEL_RED = 255;
static constexpr uint8_t LED_LEVEL_GREEN = 140;
static constexpr uint8_t LED_LEVEL_BLUE = 140;

// ---- Matrix geometry --------------------------------------------------------
static constexpr uint8_t N_COLS = 8;
static constexpr uint8_t N_ROWS = 6;
static constexpr uint8_t N_POS = N_COLS * N_ROWS; // 48

// Which MCP23017 port carries the 8 column strobes. The two ports are
// electrically identical - both have the 100k pull-ups and the input inversion
// the returns need - so this follows the harness rather than forcing a rewire.
//
// Worth knowing when tracing it out: the DIP pinout runs GPB0-7 on physical
// pins 1-8 and GPA0-7 on pins 21-28, so port B is the one nearest pin 1.
//
//   1 = strobes on GPA, returns on GPB   (design doc default, and the I2C
//                                         board as built - which bits, below)
//   0 = strobes on GPB, returns on GPA
#define COLS_ON_PORT_A 1

static constexpr uint8_t POS(uint8_t col, uint8_t row) { return col * N_ROWS + row; }

// ---- Matrix bit order -------------------------------------------------------
// Which bit of the strobe port carries keybed column c, and which bit of the
// return port carries keybed row r. Keybed coordinates, position_map.cpp and
// the injection tables are untouched; only mcp23017.h looks here. Fill in, do
// not rewire: the self test's monitor ('m') prints the physical pair behind
// every lit cell, so a wrong entry is visible and a one-number fix, and its
// pin-pair mode ('p') names the pins behind a key these tables do not cover.
//
// As built, read off the I2C board with the monitor and confirmed key by
// key: the eight column lines went to GPA and the six row lines to GPB,
// neither group in order. GPB0 and GPB7 are the spare inputs. The button
// board's seven wires join these same pins (docs/pinout.md section 5).
static constexpr uint8_t COL_BIT[N_COLS] = {3, 4, 2, 6, 1, 5, 0, 7};
static constexpr uint8_t ROW_BIT[N_ROWS] = {3, 2, 4, 5, 6, 1};

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

// ---- Injection timing -------------------------------------------------------
// Every press is one-shot to the blob - a held key does not sustain, a new
// press cuts the previous note off and starts the next. So a press is a tap:
// the switch closes for the hold, then opens for the gap before the next
// tap, or two taps of the same key read as one long press and the second
// note never happens. The blob polls every 10-20 ms but debounces keys on
// top of that: 30 ms closures are ignored, 60 ms ones play (the demo's
// shortest note). muxtest's l and r sweeps find the real floor of each by
// ear; these are the values known to work. One switch, so taps queue in
// press order: a chord comes out as a fast arpeggio, the mono constraint
// audible rather than hidden.
static constexpr uint8_t INJECT_NOTE_HOLD_MS = 60;
static constexpr uint8_t INJECT_NOTE_GAP_MS = 40;
static constexpr uint8_t INJECT_BUTTON_HOLD_MS = 60;
static constexpr uint8_t INJECT_BUTTON_GAP_MS = 60;

// Taps waiting for the switch. Each costs hold + gap, so this is ~0.8 s of
// backlog at the note timings; beyond it presses are dropped rather than
// arriving most of a second late.
static constexpr uint8_t INJECT_QUEUE_LEN = 8; // power of two

// ---- Timing -----------------------------------------------------------------
// A frame is 8 x (write IODIRA + read GPIOB) = ~1.4 ms at 400 kHz. A 2 ms
// period leaves ~0.6 ms of idle for the FreeRTOS idle task and the task
// watchdog. 500 Hz frame rate is still 6x the blob's own scan.
static constexpr uint32_t SCAN_PERIOD_MS = 2;

// Asymmetric by construction: a press is emitted on the first frame that sees
// it, then that key is frozen for DEBOUNCE_US. Press latency is one frame
// (~2 ms), bounce inside the guard window is invisible.
static constexpr uint32_t DEBOUNCE_US = 5000;

// A release is only accepted once the contact has read open for RELEASE_US
// with no closed frame in between. A membrane contact of more than ~25k sits
// in the expander's undefined input band against the 100k pull-up, so a held
// key reads open for a frame now and then; each dropout would otherwise be a
// release and a fresh press - a repeated note from the blob while the key is
// held, a double from a tap that passes through the make or break ramp.
// Press latency is untouched; note-off is late by this much, which nothing
// hears.
static constexpr uint32_t RELEASE_US = 30000;

// Consecutive failed I2C frames before the MCP23017 is re-initialised. The
// usual cause is a floating RESET pin (section 11).
static constexpr uint8_t I2C_FAIL_LIMIT = 10;

// ---- MIDI -------------------------------------------------------------------
static constexpr uint8_t NOTE_CHANNEL = 0; // 0-15 on the wire = 1-16 in a DAW
static constexpr uint8_t CTRL_CHANNEL = 0;
static constexpr uint8_t NOTE_VELOCITY = 100; // keybed has one contact per key,
                                              // so there is no velocity to read
// Transposition is the base pitch pot now (BASE_PITCH_SEMIS); it moves MIDI
// out and CV together and leaves the toy at its own pitch.

// ---- MIDI in ----------------------------------------------------------------
// Channels are 0-based on the wire, so 0 is channel 1 in a DAW. Notes on the
// keys channel are performance events - the toy, the keys' CV/gate pair, the
// loop - exactly like a key; notes on the other channel drive the CV/gate
// pair the switch did not select, straight, with no pot offset. Both DIN
// (UART2) and USB (UART0, with USB_MIDI 1) are read; docs/firmware.md 3.4.
static constexpr uint8_t MIDI_IN_KEYS_CH  = NOTE_CHANNEL;
static constexpr uint8_t MIDI_IN_OTHER_CH = NOTE_CHANNEL + 1;
static constexpr float   MIDI_BEND_SEMIS  = 2.0f;   // pitch bend range, +- this

// MIDI-in notes outside the keybed's range, for the toy: 1 = fold them by
// octaves onto the 28 keys, 0 = the toy stays silent for them. CV always
// gets the real note.
#define MIDI_IN_FOLD 1

// CC numbers received. 20-34 are the toy's buttons as the panel sends them
// (ButtonCC below) and tap that button; these continue the list with the
// four buttons that never scan, and the settings.
enum MidiInCC : uint8_t {
    CC_TEMPO_UP = 35, CC_TEMPO_DOWN = 36, CC_VOL_UP = 37, CC_VOL_DOWN = 38,
    CC_SET_QUANT_LOOP = 102, CC_SET_QUANT_PITCH = 103, CC_SET_AUX_WAVE = 104,
    CC_SET_AUX_RATE = 105, CC_SET_GATE_MODE = 106, CC_SET_GLIDE = 107,
    CC_SET_ARP = 108, CC_SET_ARP_ORDER = 109, CC_SET_ARP_DIV = 110,
    CC_SET_TOY_NOTES = 111,
};

// ---- Clock ------------------------------------------------------------------
// One tick engine at 96 per beat, whichever source drives it (docs/firmware.md
// 3.3): the internal clock from tap tempo, MIDI clock (24 per beat, so four
// ticks each), or the jack (CLOCK_PPQN pulses per beat, one per 16th by
// default). A bar is BEATS_PER_BAR beats from beat 1 - no clock source knows
// the bar, so it is an assumption used only where being wrong is harmless.
static constexpr uint16_t TICKS_PER_BEAT       = 96;
static constexpr uint8_t  BEATS_PER_BAR        = 4;
static constexpr uint8_t  CLOCK_PPQN           = 4;
static constexpr uint16_t BPM_MIN              = 40;
static constexpr uint16_t BPM_MAX              = 300;
static constexpr uint32_t CLOCK_EXT_TIMEOUT_MS = 2000;   // no external tick this long: internal resumes
static constexpr uint32_t TAP_MAX_MS           = 2000;   // a tap later than this starts a new series
static constexpr uint32_t TAP_MIN_MS           = 200;    // bounce
// MIDI clock out (24 per beat, plus start / stop with the loop) whenever the
// master is not MIDI clock in - internal or the jack. Never re-sent from MIDI
// clock in: that is a loop.
#define MIDI_CLOCK_OUT 1

// ---- Looper -----------------------------------------------------------------
static constexpr uint16_t LOOP_MAX_EVENTS  = 1024;  // 6 bytes each
static constexpr uint16_t LOOP_MAX_BEATS   = 64;    // recording closes itself here
static constexpr uint8_t  LOOP_TAP_LATE_MS = 40;    // a loop tap the toy would play later than this is dropped, for the toy only

// ---- AUX --------------------------------------------------------------------
static constexpr uint32_t AUX_PULSE_MS = 10;    // the clock and reset shapes' pulse
static constexpr uint32_t AUX_ENV_MS   = 300;   // the envelope shape's decay, full scale to silence

// ---- Settings ---------------------------------------------------------------
// Written to NVS this long after the last change, so a cycle through a
// setting's options is one flash write.
static constexpr uint32_t SETTINGS_SAVE_DELAY_MS = 2000;

// ---- Arpeggiator ------------------------------------------------------------
static constexpr uint8_t ARP_HELD_MAX     = 16;   // keys remembered
static constexpr uint8_t ARP_GATE_PERCENT = 50;   // of a step, before the note-off

// ---- Position map -----------------------------------------------------------
enum PosKind : uint8_t
{
    K_NONE = 0, // position ignored
    K_NOTE,     // data = MIDI note number, sent on NOTE_CHANNEL
    K_CC        // data = CC number, 127 on press / 0 on release, CTRL_CHANNEL
};

struct PosMap
{
    PosKind kind;
    uint8_t data;
};

// ---- Mapping sweep ----------------------------------------------------------
// Starting values the self test hands out while recording the 48 positions.
// Notes ascend chromatically from the first key you press, CCs ascend from the
// first button. Both are only a starting point for the generated table.
static constexpr uint8_t SWEEP_BASE_NOTE = 57; // A3, the toy's lowest key (measured)
static constexpr uint8_t SWEEP_BASE_CC = 20;   // 20-31 are undefined in the spec

extern const PosMap POSITION_MAP[N_POS];

// ---- Button identities ------------------------------------------------------
// CC numbers the mapping sweep handed the 8 keybed-side buttons, identified by
// injecting each and listening (docs/pinout.md, section 5), plus the 7 on the
// button board, which is on the expander side too.
enum ButtonCC : uint8_t
{
    CC_PIANO = 20,
    CC_BELLS = 21,
    CC_MEOW = 22,
    CC_ORGAN = 23,
    CC_BANJO = 24,
    CC_MUSIC = 25,
    CC_STOP = 26,
    CC_CATFACE = 27,
    CC_RECORD = 28,
    CC_PLAY = 29, // button board
    CC_ROCK = 30,
    CC_BLUES = 31,
    CC_SAMBA = 32,
    CC_TECHNO = 33,
    CC_DISCO = 34,
    CC_LAST = CC_DISCO
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
static constexpr uint8_t POS_TEMPO_UP = POS(0, 0);
static constexpr uint8_t POS_TEMPO_DOWN = POS(1, 0);
static constexpr uint8_t POS_VOL_UP = POS(2, 0);
static constexpr uint8_t POS_VOL_DOWN = POS(5, 0);
