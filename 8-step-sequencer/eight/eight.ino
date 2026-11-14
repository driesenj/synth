// Eight: the Kosmo 8-step sequencer (../8-step-sequencer.ino) rebuilt as a
// Eurorack module, played the Korg SQ-1 way (docs/design.md, "Firmware").
//
// Two rows of eight steps. ROWS says how the rows make up the sequence and
// DIRECTION which way it runs, so the SQ-1's eight modes and twelve more are
// combinations of the two. Every step keeps three settings at once: gate (the
// step sounds or rests), skip (the step is in the sequence or left out) and
// slide (the step ties into the next and glides to it). BUTTONS picks the one
// the step buttons show and edit, or makes them jump. RESET makes the next
// clock play step 1.

#include <EEPROM.h>
#include "MCP4725.h"
#include "ADS1X15.h"

MCP4725 cvA(0x61);
MCP4725 cvB(0x60);
MCP4725* const DACS[2] = {&cvA, &cvB};

ADS1115 ADS(0x48);

// Print the raw readings of the four ADS1115 inputs instead of running the
// sequencer, for checking the knob wiring
const bool DEBUG_KNOBS = false;

// Gain of the output amp: the jack's volts per DAC volt. The stages are built
// for x2; measure each on the module with a 1 V/oct check and put it here.
const double CV_FACTOR[2] = {2.0, 2.0};
// The DACs' supply, which is their reference: the LM4040's 5.000 V
const double DAC_VOLTS = 5.0;

// One line through both rows (A→B, ABAB) plays on both outputs, as on the
// SQ-1. True plays row A's steps on output A and row B's on output B instead,
// as the Kosmo build did.
const bool SPLIT_ROWS = false;

// ROWS knob: how the two rows make up the sequence
const int ROWS_CHAIN = 0;         // A→B: row A's eight steps, then row B's
const int ROWS_ALTERNATE = 1;     // ABAB: a step of row A, then one of row B
const int ROWS_PARALLEL = 2;      // A+B: two sequences of eight, row A on output A, row B on output B
const int ROWS_CV_DUTY = 3;       // CV/DUTY: row A plays, row B sets each step's gate length
const int ROWS_CV_SLIDE = 4;      // CV/SLIDE: row A plays, row B sets each step's glide into the next
const int ROWS_POSITIONS = 5;

// DIRECTION knob
const int DIRECTION_FORWARD = 0;
const int DIRECTION_REVERSE = 1;
const int DIRECTION_PING_PONG = 2;
const int DIRECTION_RANDOM = 3;

// BUTTONS knob: the step setting the step buttons show and edit, or jumping
const int BUTTONS_GATE = 0;
const int BUTTONS_SKIP = 1;
const int BUTTONS_SLIDE = 2;
const int BUTTONS_JUMP = 3;

// The settings every step keeps, all at once
const int SETTING_GATE = 0;       // on: the step sounds; off: a rest, its CV holds the last note
const int SETTING_PLAYS = 1;      // on: the step is in the sequence; off: skipped
const int SETTING_SLIDE = 2;      // on: the gate stays open into the next step, which glides in
const int SETTINGS = 3;

// QUANTIZATION MODES
const int QUANTIZE_LINEAR = 0;
const int QUANTIZE_MINOR = 1;
const int QUANTIZE_MAJOR = 2;
const int QUANTIZE_CHROMA = 3;

// Scale definitions in semitones (relative to root 0)
const int CHROMA_SCALE[12] = { 0,1,2,3,4,5,6,7,8,9,10,11 };
const int MAJOR_SCALE[7]      = { 0,2,4,5,7,9,11 };
const int MINOR_SCALE[7]      = { 0,2,3,5,7,8,10 };

// SHIFT + step 1-4 of a row sets its range
const int RANGES[4] = {1, 2, 5, 8};

const int LED_ON = LOW;
const int LED_OFF = HIGH;

const int SEQ_LENGTH = 8;

// The Kosmo build's pins, step 1 first (hardware/tools/circuit.py checks the
// board against these tables)
const int POTS_A [] = {A7, A0, A1, A2, A3, A4, A5, A6 };
const int POTS_B [] = {A8, A9, A10, A11, A12, A13, A14, A15};

const int STEPS_A [] = {52, 50, 48, 46, 44, 42, 40, 38};
const int STEPS_B [] = {53, 51, 49, 47, 45, 43, 41, 39};

const int LEDS_A [] = {35, 37, 33, 25, 27, 31, 23, 29};
const int LEDS_B [] = {36, 34, 22, 24, 26, 28, 30, 32};

const int* const POTS[2] = {POTS_A, POTS_B};
const int* const STEPS[2] = {STEPS_A, STEPS_B};
const int* const LEDS[2] = {LEDS_A, LEDS_B};

// ADS1115 inputs
const int DIRECTION_KNOB = 0;
const int DUTY_KNOB = 1;
const int BUTTONS_KNOB = 2;
const int ROWS_KNOB = 3;
// The order they are read in, one per conversion
const int KNOB_ORDER[4] = {ROWS_KNOB, DIRECTION_KNOB, BUTTONS_KNOB, DUTY_KNOB};

const int SHIFT_BUTTON = 19;
const int CLOCK_IN = 18;
const int RESET_IN = 2;
const int GATE_A = 17;
const int GATE_B = 15;
const int GATES[2] = {GATE_A, GATE_B};

// The step settings, [setting][row][step]; set from EEPROM in setup()
bool stepSetting[SETTINGS][2][SEQ_LENGTH];

// Knob positions
int rowsMode = ROWS_CHAIN;
int direction = DIRECTION_FORWARD;
int buttonsMode = BUTTONS_GATE;
// Gate length as a fraction of the clock period, from the DUTY knob
double duty = 0.5;
bool shift = false;

// Voltage range and quantizer of each row
int range[2] = {8, 8};
int quantize[2] = {QUANTIZE_LINEAR, QUANTIZE_LINEAR};

// Set by the clock and reset interrupts on a rising edge, picked up by handleClock()
volatile bool clockEdge = false;
volatile unsigned long clockEdgeTime = 0;
volatile bool resetEdge = false;
volatile unsigned long resetEdgeTime = 0;
// Edges this soon after the previous one are noise on the line
const unsigned long CLOCK_HOLDOFF = 2; // ms
// A reset up to this long after a clock edge still counts for that clock: the
// clock module sends its reset together with the first tick of the bar, and
// either can get here first
const unsigned long RESET_WINDOW = 5; // ms
// A reset waiting for the next clock
bool resetPending = false;

// Last time in millis the clock had a rising edge
unsigned long lastClockTime = 0;
// Clock period the gate lengths are based on, 0 until it is known
unsigned long lastClockDuration = 0;
// Time between the last 2 rising edges of the clock, including pauses
unsigned long lastClockGap = 0;

// A line is the order the steps play in: one line through both rows (A→B,
// ABAB), one line per row (A+B), or row A alone (CV/DUTY, CV/SLIDE). Each
// line has a position on it, -1 before its start: the next clock plays its
// first step then.
int linePos[2] = {-1, -1};
// PING-PONG: which way each line is going
bool lineForward[2] = {true, true};
// The step each line plays now, -1 for none
int playRow[2] = {-1, -1};
int playStep[2] = {-1, -1};

// A step held down repeats on every clock; its line waits where it was and
// carries on from there on release. -1 for none.
int heldStep[2] = {-1, -1};
const unsigned long HOLD_THRESHOLD = 200; // ms
// BUTTONS on JUMP: the step pressed since the last clock, played by the next one
int jumpStep[2] = {-1, -1};

bool stepPressed[2][SEQ_LENGTH];
unsigned long stepPressTime[2][SEQ_LENGTH];

// Each output: the step it plays (-1 for none), the voltage it is at (held
// while it plays no step or a rest), where the step's glide starts and how
// much of the step the glide takes (0: none), and whether the gate stays open
// into the next step
int outRow[2] = {-1, -1};
int outStep[2] = {-1, -1};
double outVolts[2] = {0, 0};
double glideFrom[2] = {0, 0};
double glideLength[2] = {0, 0};
bool tied[2] = {false, false};
int currentGate[2] = {LOW, LOW};
// The outputs as they were before the last clock, for a reset just after it
int clockOutRow[2], clockOutStep[2];
double clockOutVolts[2];

// A step with SLIDE on glides into the next over this much of a step (about a
// 303's slide at 16ths of 120 BPM). Its gate stays open until the next clock,
// or this much of a step if the clock stops.
const double SLIDE_LENGTH = 0.5;
const double TIE_LIMIT = 1.25;

// Low pass filtered readings of the step potentiometers each output follows,
// and of row B's in CV/DUTY
float potVal[2] = {0, 0};
int potPin[2] = {-1, -1};
float dutyVal = 0;
int dutyPin = -1;

int knobIndex = 0;
unsigned long lastADCStart = 0;
const unsigned long adcInterval = 2; // ms

// ADS reading of a knob turned all the way up
const long KNOB_MAX = 27000;
// How far the position knobs have to move past the border of their current
// position before they change
const long KNOB_HYSTERESIS = 400;

// The step settings and each row's range and scale are kept over a power
// cycle. Saving waits until nothing has changed for a while, so a run of taps
// costs one write, and EEPROM.update() only writes the bytes that changed.
const byte EEPROM_MAGIC = 0xE8;   // marks a saved set; change it when the layout below changes
const unsigned long SAVE_DELAY = 3000; // ms
bool unsaved = false;
unsigned long lastChange = 0;


void setup() {
  if (DEBUG_KNOBS) Serial.begin(9600);

  for (int row = 0; row < 2; row++) {
    for (int step = 0; step < SEQ_LENGTH; step++) {
      pinMode(POTS[row][step], INPUT);
      pinMode(STEPS[row][step], INPUT);
      pinMode(LEDS[row][step], OUTPUT);
      digitalWrite(LEDS[row][step], LED_OFF);
      stepPressed[row][step] = false;
      stepSetting[SETTING_GATE][row][step] = true;
      stepSetting[SETTING_PLAYS][row][step] = true;
      stepSetting[SETTING_SLIDE][row][step] = false;
    }
  }
  pinMode(SHIFT_BUTTON, INPUT_PULLUP);
  pinMode(GATE_A, OUTPUT);
  pinMode(GATE_B, OUTPUT);
  loadSettings();

  Wire.begin();
  cvA.begin();
  cvB.begin();
  cvA.setMaxVoltage(DAC_VOLTS);
  cvB.setMaxVoltage(DAC_VOLTS);
  ADS.begin();
  ADS.setMode(ADS1X15_MODE_SINGLE);
  ADS.requestADC(KNOB_ORDER[0]);

  // Catch clock and reset edges in interrupts, so short trigger pulses aren't missed
  pinMode(CLOCK_IN, INPUT);
  attachInterrupt(digitalPinToInterrupt(CLOCK_IN), onClockRising, RISING);
  pinMode(RESET_IN, INPUT);
  attachInterrupt(digitalPinToInterrupt(RESET_IN), onResetRising, RISING);
}


void loop() {
  if (DEBUG_KNOBS) {
    printKnobs();
    return;
  }

  hardwareCheck();
  handleClock();
  handleOutput();
  saveSettings();
}

// Knob test: what each ADS1115 input reads, from about 0 at 0V to about 26700
// at 5V. Turn one knob at a time and see which input follows it.
void printKnobs() {
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint < 250) return;
  lastPrint = millis();

  for (int channel = 0; channel < 4; channel++) {
    const char* name = channel == ROWS_KNOB ? "rows"
                     : channel == DIRECTION_KNOB ? "direction"
                     : channel == BUTTONS_KNOB ? "buttons" : "duty";
    Serial.print("A");
    Serial.print(channel);
    Serial.print(" (");
    Serial.print(name);
    Serial.print("): ");
    Serial.print(ADS.readADC(channel));
    Serial.print("   ");
  }
  Serial.println("");
}

// ==========================================
// Buttons and knobs
// ==========================================

// Reading the buttons every 20ms debounces them: that's longer than a switch
// bounces, so a bounce changes at most one reading, and shorter than any press
const unsigned long HARDWARE_CHECK_INTERVAL = 20; // ms
unsigned long lastHardwareCheck = 0;

// Check inputs and update known values
void hardwareCheck() {
  if (millis() - lastHardwareCheck < HARDWARE_CHECK_INTERVAL) {
    return;
  }
  lastHardwareCheck = millis();

  shift = !digitalRead(SHIFT_BUTTON);
  for (int row = 0; row < 2; row++) {
    for (int step = 0; step < SEQ_LENGTH; step++) {
      readStepButton(row, step, digitalRead(STEPS[row][step]) == HIGH);
    }
  }

  if (millis() - lastADCStart > adcInterval && ADS.isReady()) {
    readKnob(KNOB_ORDER[knobIndex], ADS.getValue());
    knobIndex = (knobIndex + 1) % 4;
    ADS.requestADC(KNOB_ORDER[knobIndex]);
    lastADCStart = millis();
  }
}

// A step button: with SHIFT held, steps 1-4 set the row's range and 5-8 its
// quantizer. Otherwise a tap toggles the setting BUTTONS shows (on JUMP the
// press makes the next clock play the step), and holding it repeats the step.
void readStepButton(int row, int step, bool pressed) {
  if (shift) {
    if (pressed) {
      if (step < 4 && range[row] != RANGES[step]) {
        range[row] = RANGES[step];
        settingsChanged();
      } else if (step >= 4 && quantize[row] != step - 4) {
        quantize[row] = step - 4;
        settingsChanged();
      }
    }
    return;
  }

  // Row B has no steps of its own in CV/DUTY and CV/SLIDE: its knobs set row A's
  bool onLine = lineOf(row) >= 0;
  unsigned long now = millis();

  if (pressed && !stepPressed[row][step]) {
    stepPressed[row][step] = true;
    stepPressTime[row][step] = now;
    if (buttonsMode == BUTTONS_JUMP && onLine) jumpStep[row] = step;
  }

  if (pressed && stepPressed[row][step] && onLine && heldStep[row] == -1 &&
      now - stepPressTime[row][step] > HOLD_THRESHOLD) {
    heldStep[row] = step;
  }

  if (!pressed && stepPressed[row][step]) {
    stepPressed[row][step] = false;
    if (heldStep[row] == step) {
      heldStep[row] = -1;
    } else if (buttonsMode != BUTTONS_JUMP && onLine) {
      // short press → toggle the setting the buttons show
      int setting = shownSetting();
      stepSetting[setting][row][step] = !stepSetting[setting][row][step];
      settingsChanged();
    }
  }
}

void readKnob(int knob, int raw) {
  if (knob == ROWS_KNOB) {
    int mode = knobPosition(raw, ROWS_POSITIONS, rowsMode);
    if (mode != rowsMode) setRowsMode(mode);
  } else if (knob == DIRECTION_KNOB) {
    direction = knobPosition(raw, 4, direction);
  } else if (knob == BUTTONS_KNOB) {
    int mode = knobPosition(raw, 4, buttonsMode);
    if (mode != buttonsMode) {
      buttonsMode = mode;
      jumpStep[0] = jumpStep[1] = -1;
    }
  } else {
    // Turned the other way round: clockwise is longer
    duty = 1 - min(1.0, abs(raw) / 26500.0);
  }
}

// Map a knob reading to one of a number of positions. The knob has to move a
// bit past the border of its current position before it changes, so a knob
// resting on a border doesn't flip back and forth.
int knobPosition(int raw, int positions, int current) {
  long size = KNOB_MAX / positions;
  if (current >= 0 && raw > current * size - KNOB_HYSTERESIS && raw < (current + 1) * size + KNOB_HYSTERESIS) {
    return current;
  }
  return constrain(raw / size, 0, positions - 1);
}

// The setting the step buttons show and edit; JUMP shows the gates
int shownSetting() {
  if (buttonsMode == BUTTONS_SKIP) return SETTING_PLAYS;
  if (buttonsMode == BUTTONS_SLIDE) return SETTING_SLIDE;
  return SETTING_GATE;
}

// A new ROWS position keeps the sequence going: the lines carry on from the
// same place, cut to the new length, so turning the knob doesn't lose the beat
void setRowsMode(int mode) {
  rowsMode = mode;
  int n = lineLength();
  if (linePos[0] >= n) linePos[0] %= n;
  linePos[1] = linePos[0];
  lineForward[1] = lineForward[0];
  heldStep[1] = lineOf(1) >= 0 ? heldStep[1] : -1;
  jumpStep[0] = jumpStep[1] = -1;
}

// ==========================================
// Lines
// ==========================================

int lineCount() {
  return rowsMode == ROWS_PARALLEL ? 2 : 1;
}

int lineLength() {
  return rowsMode == ROWS_CHAIN || rowsMode == ROWS_ALTERNATE ? 2 * SEQ_LENGTH : SEQ_LENGTH;
}

// The row and step at a position of a line
int rowAt(int line, int pos) {
  if (rowsMode == ROWS_CHAIN) return pos / SEQ_LENGTH;
  if (rowsMode == ROWS_ALTERNATE) return pos % 2;
  if (rowsMode == ROWS_PARALLEL) return line;
  return 0;
}

int stepAt(int line, int pos) {
  if (rowsMode == ROWS_CHAIN) return pos % SEQ_LENGTH;
  if (rowsMode == ROWS_ALTERNATE) return pos / 2;
  return pos;
}

// The line a row's steps are on, -1 for row B in CV/DUTY and CV/SLIDE
int lineOf(int row) {
  if (rowsMode == ROWS_PARALLEL) return row;
  if (rowsMode == ROWS_CV_DUTY || rowsMode == ROWS_CV_SLIDE) return row == 0 ? 0 : -1;
  return 0;
}

int positionOf(int row, int step) {
  if (rowsMode == ROWS_CHAIN) return row * SEQ_LENGTH + step;
  if (rowsMode == ROWS_ALTERNATE) return step * 2 + row;
  return step;
}

bool playsAt(int line, int pos) {
  return stepSetting[SETTING_PLAYS][rowAt(line, pos)][stepAt(line, pos)];
}

// The first position from `start` on that plays, going round the line in
// steps of `dir`; -1 when every step is skipped
int playingFrom(int line, int start, int dir) {
  int n = lineLength();
  for (int i = 0; i < n; i++) {
    int pos = ((start + dir * i) % n + n) % n;
    if (playsAt(line, pos)) return pos;
  }
  return -1;
}

// The position a line plays after `pos`, in the DIRECTION knob's direction,
// leaving out skipped steps; -1 when every step of the line is skipped
int nextPosition(int line, int pos) {
  int n = lineLength();
  int playing = 0;
  for (int p = 0; p < n; p++) {
    if (playsAt(line, p)) playing++;
  }
  if (playing == 0) return -1;

  // From before the start (power up, reset) a line starts at step 1, or at
  // its last step when it runs in reverse
  if (pos < 0) {
    lineForward[line] = true;
    return direction == DIRECTION_REVERSE ? playingFrom(line, n - 1, -1) : playingFrom(line, 0, 1);
  }

  if (direction == DIRECTION_FORWARD) return playingFrom(line, pos + 1, 1);
  if (direction == DIRECTION_REVERSE) return playingFrom(line, pos - 1, -1);

  if (direction == DIRECTION_RANDOM) {
    int pick = random(playing);
    for (int p = 0; p < n; p++) {
      if (playsAt(line, p) && pick-- == 0) return p;
    }
  }

  // PING-PONG: turn round at the last step that plays, so the ends play once
  int dir = lineForward[line] ? 1 : -1;
  for (int p = pos + dir; p >= 0 && p < n; p += dir) {
    if (playsAt(line, p)) return p;
  }
  lineForward[line] = !lineForward[line];
  for (int p = pos - dir; p >= 0 && p < n; p -= dir) {
    if (playsAt(line, p)) return p;
  }
  return playsAt(line, pos) ? pos : playingFrom(line, 0, 1);
}

void resetSteps() {
  // Start before the first step, so the next clock plays step 1
  linePos[0] = linePos[1] = -1;
  lineForward[0] = lineForward[1] = true;
}

// Move the sequence on by one clock. Each line plays its next step; a held
// step instead (the line waits where it was), or a jumped-to step (the line
// carries on from there). When both rows make one line, a held or jumped
// step of either row counts for the whole line.
void advance() {
  for (int line = 0; line < 2; line++) {
    playRow[line] = -1;
    playStep[line] = -1;
  }

  for (int line = 0; line < lineCount(); line++) {
    int holdRow = -1;
    int jumpRow = -1;
    for (int row = 0; row < 2; row++) {
      if (lineOf(row) != line) continue;
      if (heldStep[row] >= 0 && holdRow < 0) holdRow = row;
      if (jumpStep[row] >= 0 && jumpRow < 0) jumpRow = row;
    }

    if (holdRow >= 0) {
      playRow[line] = holdRow;
      playStep[line] = heldStep[holdRow];
      continue;
    }
    if (jumpRow >= 0) {
      linePos[line] = positionOf(jumpRow, jumpStep[jumpRow]);
    } else {
      linePos[line] = nextPosition(line, linePos[line]);
    }
    if (linePos[line] >= 0) {
      playRow[line] = rowAt(line, linePos[line]);
      playStep[line] = stepAt(line, linePos[line]);
    }
  }

  jumpStep[0] = jumpStep[1] = -1;
}

// ==========================================
// Clock and reset
// ==========================================

// Clock interrupt, flags the rising edge for handleClock()
void onClockRising() {
  unsigned long now = millis();
  if (now - clockEdgeTime < CLOCK_HOLDOFF) return;
  clockEdgeTime = now;
  clockEdge = true;
}

// Reset interrupt, flags the rising edge for handleClock()
void onResetRising() {
  unsigned long now = millis();
  if (now - resetEdgeTime < CLOCK_HOLDOFF) return;
  resetEdgeTime = now;
  resetEdge = true;
}

void handleClock() {
  // Pick up the edges flagged by the interrupts
  noInterrupts();
  bool clockRising = clockEdge;
  unsigned long currentTime = clockEdgeTime;
  clockEdge = false;
  bool resetRising = resetEdge;
  unsigned long resetTime = resetEdgeTime;
  resetEdge = false;
  interrupts();

  if (resetRising) resetPending = true;

  if (clockRising) {
    if (lastClockTime > 0) {
      // A gap more than twice as long as the one before means the clock was
      // stopped and started again. Keep the old duration then, so the first
      // step doesn't get a gate as long as the pause.
      unsigned long gap = currentTime - lastClockTime;
      if (lastClockDuration == 0 || gap <= 2 * lastClockGap) {
        lastClockDuration = gap;
      }
      lastClockGap = gap;
    } else {
      // Seed from the timing of the first clock, so the random modes play
      // something different after every power up
      randomSeed(micros());
    }
    lastClockTime = currentTime;

    for (int out = 0; out < 2; out++) {
      clockOutRow[out] = outRow[out];
      clockOutStep[out] = outStep[out];
      clockOutVolts[out] = outVolts[out];
    }
    if (resetPending) {
      resetSteps();
      resetPending = false;
    }
    advance();
    startSteps();
  } else if (resetRising && lastClockTime > 0 && resetTime - lastClockTime <= RESET_WINDOW) {
    // The reset came just after a clock: play step 1 on that clock after all,
    // as if the reset had come first
    for (int out = 0; out < 2; out++) {
      outRow[out] = clockOutRow[out];
      outStep[out] = clockOutStep[out];
      outVolts[out] = clockOutVolts[out];
    }
    resetSteps();
    resetPending = false;
    advance();
    startSteps();
  }
}

// ==========================================
// Outputs
// ==========================================

// Give each output the step it plays from this clock on. In A+B each line has
// its own output; otherwise the one line plays on both (see SPLIT_ROWS).
void startSteps() {
  for (int out = 0; out < 2; out++) {
    int line = rowsMode == ROWS_PARALLEL ? out : 0;
    int row = playRow[line];
    int step = playStep[line];
    if (SPLIT_ROWS && (rowsMode == ROWS_CHAIN || rowsMode == ROWS_ALTERNATE) && row != out) {
      row = -1;
      step = -1;
    }

    // Glide in when the step before on this output sounded with SLIDE on, or
    // in CV/SLIDE by as much as row B's knob of that step says
    int lastRow = outRow[out];
    int lastStep = outStep[out];
    glideLength[out] = 0;
    if (step >= 0 && lastStep >= 0 && stepSetting[SETTING_GATE][lastRow][lastStep]) {
      if (rowsMode == ROWS_CV_SLIDE) {
        glideLength[out] = 1 - analogRead(POTS_B[lastStep]) / 1023.0;
      } else if (stepSetting[SETTING_SLIDE][lastRow][lastStep]) {
        glideLength[out] = SLIDE_LENGTH;
      }
    }
    glideFrom[out] = outVolts[out];
    tied[out] = step >= 0 && stepSetting[SETTING_GATE][row][step] && stepSetting[SETTING_SLIDE][row][step];
    outRow[out] = row;
    outStep[out] = step;
  }
}

// Read a potentiometer as 0.0 - 1.0 through a low pass filter to reduce jitter.
// The filter starts over from a fresh reading when it switches to another
// potentiometer, so a new step doesn't glide in from the previous one.
double readPot(int pin, float &val, int &lastPin) {
  int raw = analogRead(pin);
  if (pin != lastPin) {
    val = raw;
    lastPin = pin;
  } else {
    val = val * 0.9 + raw * 0.1;
  }
  return val / 1023.0;
}

// How far along a glide to the current step's voltage is, 0.0 - 1.0, for a glide
// that takes `length` of the step. Instant while the clock period isn't known yet.
double slideProgress(double currentDuty, double length) {
  if (lastClockDuration == 0 || length <= 0) return 1.0;
  return min(1.0, currentDuty / length);
}

void handleOutput() {
  // How far into the current step we are, as a fraction of the clock period.
  // Until the period is known a step lasts until the next clock.
  double currentDuty = lastClockDuration > 0 ?
    (millis() - lastClockTime) / (double)lastClockDuration :
    0.0;

  for (int out = 0; out < 2; out++) {
    int row = outRow[out];
    int step = outStep[out];
    int gate = LOW;

    // An output without a step, or on a rest, keeps its voltage, so the
    // release of its last note stays in tune
    if (step >= 0 && stepSetting[SETTING_GATE][row][step]) {
      // Map the potentiometer value to the row's voltage range
      double target = quantizeCV((1 - readPot(POTS[row][step], potVal[out], potPin[out])) * range[row], quantize[row]);
      outVolts[out] = glideFrom[out] + slideProgress(currentDuty, glideLength[out]) * (target - glideFrom[out]);

      // Row B sets the gate length of each step in CV/DUTY, turned the same way as the duty knob
      double length = duty;
      if (rowsMode == ROWS_CV_DUTY) length = 1 - readPot(POTS_B[step], dutyVal, dutyPin);
      if (currentDuty < length || (tied[out] && currentDuty < TIE_LIMIT)) gate = HIGH;
    }

    // The library only writes to the DAC when the value changes
    DACS[out]->setVoltage(outVolts[out] / CV_FACTOR[out]);
    if (gate != currentGate[out]) {
      digitalWrite(GATES[out], gate);
      currentGate[out] = gate;
    }
  }

  showSteps();
}

bool isPlaying(int row, int step) {
  for (int line = 0; line < lineCount(); line++) {
    if (playRow[line] == row && playStep[line] == step) return true;
  }
  return false;
}

// The step LEDs: with SHIFT held each row's range (steps 1-4) and quantizer
// (5-8); otherwise the setting BUTTONS shows, the playing step inverted. In
// CV/DUTY and CV/SLIDE row B lights the step whose knob is in use.
void showSteps() {
  for (int row = 0; row < 2; row++) {
    for (int step = 0; step < SEQ_LENGTH; step++) {
      bool lit;
      if (shift) {
        lit = step < 4 ? range[row] == RANGES[step] : quantize[row] == step - 4;
      } else if (lineOf(row) < 0) {
        lit = step == playStep[0];
      } else {
        lit = stepSetting[shownSetting()][row][step] != isPlaying(row, step);
      }
      digitalWrite(LEDS[row][step], lit ? LED_ON : LED_OFF);
    }
  }
}

// ==========================================
// Settings kept over a power cycle
// ==========================================

void settingsChanged() {
  unsaved = true;
  lastChange = millis();
}

// EEPROM layout: the magic byte, then per row its range, its quantizer and a
// byte per step setting (bit k = step k + 1)
void saveSettings() {
  if (!unsaved || millis() - lastChange < SAVE_DELAY) return;
  int address = 0;
  EEPROM.update(address++, EEPROM_MAGIC);
  for (int row = 0; row < 2; row++) {
    EEPROM.update(address++, range[row]);
    EEPROM.update(address++, quantize[row]);
    for (int setting = 0; setting < SETTINGS; setting++) {
      byte bits = 0;
      for (int step = 0; step < SEQ_LENGTH; step++) {
        if (stepSetting[setting][row][step]) bits |= 1 << step;
      }
      EEPROM.update(address++, bits);
    }
  }
  unsaved = false;
}

void loadSettings() {
  int address = 0;
  if (EEPROM.read(address++) != EEPROM_MAGIC) return;    // nothing saved yet: the defaults
  for (int row = 0; row < 2; row++) {
    byte savedRange = EEPROM.read(address++);
    byte savedQuantize = EEPROM.read(address++);
    for (int i = 0; i < 4; i++) {
      if (savedRange == RANGES[i]) range[row] = savedRange;
    }
    if (savedQuantize <= QUANTIZE_CHROMA) quantize[row] = savedQuantize;
    for (int setting = 0; setting < SETTINGS; setting++) {
      byte bits = EEPROM.read(address++);
      for (int step = 0; step < SEQ_LENGTH; step++) {
        stepSetting[setting][row][step] = bits & (1 << step);
      }
    }
  }
}

// ==========================================
// Quantizer
// ==========================================

float quantizeCV(float inVolts, int mode) {

  if (mode == QUANTIZE_LINEAR) {
    return inVolts;         // No quantization
  }

  // Convert voltage → semitones
  float inSemis = inVolts * 12.0;

  // Integer octave and fractional part
  int baseOct = floor(inSemis / 12.0);
  float frac  = inSemis - baseOct * 12.0;

  int nearestSemi = 0;

  switch (mode) {

    case QUANTIZE_CHROMA: {
      // Snap to nearest integer semitone
      nearestSemi = quantizeToScale(frac, CHROMA_SCALE, 12);
      break;
    }

    case QUANTIZE_MAJOR: {
      nearestSemi = quantizeToScale(frac, MAJOR_SCALE, 7);
      break;
    }

    case QUANTIZE_MINOR: {
      nearestSemi = quantizeToScale(frac, MINOR_SCALE, 7);
      break;
    }
  }

  // Compute final semitone index
  float outSemis = baseOct * 12 + nearestSemi;

  // Convert back to volts
  return outSemis / 12.0;
}

int quantizeToScale(float fracSemi, const int* scale, int scaleSize) {
  int best = scale[0];
  float bestDist = fabs(fracSemi - best);

  for (int i = 1; i < scaleSize; i++) {
    float dist = fabs(fracSemi - scale[i]);
    if (dist < bestDist) {
      bestDist = dist;
      best = scale[i];
    }
  }

  // The root of the next octave counts too, so notes near the top of the octave can round up to it
  if (fabs(fracSemi - (scale[0] + 12)) < bestDist) {
    best = scale[0] + 12;
  }
  return best;
}
