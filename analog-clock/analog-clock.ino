// =====================================================
// Arduino Clock / Clock Divider
// =====================================================
// - TM1637 4-digit display shows BPM
// - Encoder adjusts BPM
// - Play/Pause button controls clock output
// - BPM LED can blink at 1/1 or 1/4 rate
// - 7 clock outputs with programmable divisions
// =====================================================

#include <TM1637.h>

#define ENCODER_OPTIMIZE_INTERRUPTS
#include <Encoder.h>

// =====================================================
// Pin assignments
// =====================================================

const uint8_t CLK = 19;
const uint8_t DIO = 18;

const uint8_t ENC_A  = 2;
const uint8_t ENC_B  = 3;
const uint8_t ENC_SW = 10;

const uint8_t CLOCK_PINS[7] = {6, 8, 9, 16, 7, 14, 17};

const uint8_t BPM_LED  = 11;
const uint8_t BPM_SW   = 5;

const uint8_t PLAY_LED = 13;
const uint8_t PLAY_SW  = 12;

// =====================================================
// Constants
// =====================================================

const float    MS_PER_MIN   = 60000.0;
const float    BPM_MIN      = 20.0;
const float    BPM_MAX      = 300.0;

const uint16_t CLOCK_PULSE_MS = 15;
const uint16_t LED_PULSE_MS   = 15;

const uint8_t  NUM_CLOCKS = 7;
const uint8_t  NUM_PROGS  = 24;

// Encoder button behavior
const unsigned long ENC_DEBOUNCE_MS = 30;
const unsigned long ENC_LONGPRESS_MS = 600;

// =====================================================
// Clock output state structure
// =====================================================

struct ClockOut {
  uint8_t pin;
  bool    isHigh;
  unsigned long highStart;
};

// =====================================================
// Objects
// =====================================================

TM1637 tm(CLK, DIO);
Encoder bpmKnob(ENC_A, ENC_B);

// =====================================================
// Clock outputs
// =====================================================

ClockOut clocks[NUM_CLOCKS];
ClockOut bpmLed;

// =====================================================
// Clock division programs
// =====================================================

const uint16_t pgm[NUM_PROGS][NUM_CLOCKS] = {
  {2,4,8,16,32,64,128}, {3,5,7,9,11,13,15}, {2,3,4,5,6,7,8},
  {3,5,8,13,21,34,55}, {2,3,5,7,11,13,17}, {3,6,10,15,21,28,36},
  {4,9,16,25,36,49,64}, {4,10,20,35,56,84,120},
  {5,14,30,55,91,140,204}, {8,27,64,125,216,343,512},
  {32,243,1024,3125,7776,16807,32768},
  {13,37,73,121,181,253,337},
  {14,51,124,245,426,679,1016},
  {2,4,8,12,24,48,72},
  {16,22,34,36,46,56,64},
  {72,108,200,288,392,432,500},
  {6,21,28,301,325,496,697},
  {2,8,20,28,50,82,126},
  {21,33,57,69,77,93,129},
  {2,3,2,5,6,7,2},
  {30,42,66,70,78,102,105},
  {9,45,55,99,297,703,999},
  {70,836,4030,5830,7192,7912,9272},
  {15,34,65,111,175,260,369},
};

const char  pgmStr0[] PROGMEM = "1,2,4,8,16,32,64,128";
const char  pgmStr1[] PROGMEM = "1,3,5,7,9,11,13,15";
const char  pgmStr2[] PROGMEM = "1,2,3,4,5,6,7,8";
const char  pgmStr3[] PROGMEM = "1,3,5,8,13,21,34,55";
const char  pgmStr4[] PROGMEM = "1,2,3,5,7,11,13,17";
const char  pgmStr5[] PROGMEM = "1,3,6,10,15,21,28,36";
const char  pgmStr6[] PROGMEM = "1,4,9,16,25,36,49,64";
const char  pgmStr7[] PROGMEM = "1,4,10,20,35,56,84,120";
const char  pgmStr8[] PROGMEM = "1,5,14,30,55,91,140,204";
const char  pgmStr9[] PROGMEM = "1,8,27,64,125,216,343,512";
const char  pgmStr10[] PROGMEM = "1,32,243,1024,3125,7776,16807,32768";
const char  pgmStr11[] PROGMEM = "1,13,37,73,121,181,253,337";
const char  pgmStr12[] PROGMEM = "1,14,51,124,245,426,679,1016";
const char  pgmStr13[] PROGMEM = "1,2,4,8,12,24,48,72";
const char  pgmStr14[] PROGMEM = "1,16,22,34,36,46,56,64";
const char  pgmStr15[] PROGMEM = "1,72,108,200,288,392,432,500";
const char  pgmStr16[] PROGMEM = "1,6,21,28,301,325,496,697";
const char  pgmStr17[] PROGMEM = "1,2,8,20,28,50,82,126";
const char  pgmStr18[] PROGMEM = "1,21,33,57,69,77,93,129";
const char  pgmStr19[] PROGMEM = "1,2,3,2,5,6,7,2";
const char  pgmStr20[] PROGMEM = "1,30,42,66,70,78,102,105";
const char  pgmStr21[] PROGMEM = "1,9,45,55,99,297,703,999";
const char  pgmStr22[] PROGMEM = "1,70,836,4030,5830,7192,7912,9272";
const char  pgmStr23[] PROGMEM = "1,15,34,65,111,175,260,369";

const char* const pgmStrings[NUM_PROGS] PROGMEM = {
  pgmStr0, pgmStr1, pgmStr2, pgmStr3, pgmStr4, pgmStr5, pgmStr6, pgmStr7, pgmStr8,
  pgmStr9, pgmStr10, pgmStr11, pgmStr12, pgmStr13, pgmStr14, pgmStr15, pgmStr16, pgmStr17,
  pgmStr18, pgmStr19, pgmStr20, pgmStr21, pgmStr22, pgmStr23
};

// =====================================================
// Runtime state
// =====================================================

float BPM = 125.0;
uint8_t programIndex = 0;

bool isPlaying = true;
uint8_t bpmLedDivider = 1;

unsigned long bpmCounter = 0;

// Timing, in micros()
unsigned long nextTick = 0;

// Encoder
long lastEncoderPos = 0;

// Display
int displayedBPM = -1;

// Button debounce
unsigned long lastButtonTime = 0;

bool encButtonState = false;
bool encButtonLast  = false;
unsigned long encPressTime = 0;

// =====================================================
// Program select mode state
// =====================================================

bool programSelectMode = false;
long programEncoderBase = 0;

// Display scrolling
unsigned long lastScrollTime = 0;
uint8_t scrollPos = 0;
const unsigned long SCROLL_INTERVAL_MS = 250;

// =====================================================
// Setup
// =====================================================

void setup() {
  tm.begin();
  tm.setBrightness(1);

  pinMode(ENC_SW, INPUT_PULLUP);
  pinMode(BPM_SW, INPUT_PULLUP);
  pinMode(PLAY_SW, INPUT);

  pinMode(BPM_LED, OUTPUT);
  pinMode(PLAY_LED, OUTPUT);

  bpmLed = {BPM_LED, false, 0};

  for (uint8_t i = 0; i < NUM_CLOCKS; i++) {
    clocks[i] = {CLOCK_PINS[i], false, 0};
    pinMode(CLOCK_PINS[i], OUTPUT);
    digitalWrite(CLOCK_PINS[i], LOW);
  }

  digitalWrite(PLAY_LED, HIGH);
}

// =====================================================
// Main loop
// =====================================================

void loop() {
  readEncoder();
  handleEncoderButton();
  readButtons();
  updateDisplay();
  updateClockEngine();
  updateOutputs();
}

// =====================================================
// Encoder handling (BPM)
// =====================================================

void readEncoder() {
  long pos = bpmKnob.read();

  if (programSelectMode) {
    // Encoder scrolls programs
    long delta = (pos - programEncoderBase) / 4;

    if (delta != 0) {
      programIndex = (programIndex + delta + NUM_PROGS) % NUM_PROGS;
      programEncoderBase += delta * 4;
    }
  } else {
    // Encoder controls BPM
    long delta = (pos - lastEncoderPos) / 4;

    if (delta != 0) {
      BPM += delta;
      BPM = constrain(BPM, BPM_MIN, BPM_MAX);
      lastEncoderPos += delta * 4;
    }
  }
}

void handleEncoderButton() {
  static bool lastState = HIGH;
  static unsigned long lastChange = 0;
  bool currentState = digitalRead(ENC_SW);

  // Ignore the contacts bouncing for a moment after each change
  if (currentState == lastState || millis() - lastChange < ENC_DEBOUNCE_MS) return;
  lastState = currentState;
  lastChange = millis();

  if (currentState == LOW) {
    programSelectMode = !programSelectMode;

    if (programSelectMode) {
      programEncoderBase = bpmKnob.read();
    } else {
      bpmCounter = 0;
      nextTick = micros();
      displayedBPM = -1;
    }
  }
}

// =====================================================
// Button handling (debounced)
// =====================================================

void readButtons() {
  if (millis() - lastButtonTime < 30) return;

  // Play / Pause
  if (digitalRead(PLAY_SW) == HIGH && !isPlaying) {
    isPlaying = true;
    digitalWrite(PLAY_LED, HIGH);
    nextTick = micros();
  }
  else if (digitalRead(PLAY_SW) == LOW && isPlaying) {
    isPlaying = false;
    digitalWrite(PLAY_LED, LOW);
    bpmCounter = 0;
  }

  // BPM LED divider
  if (digitalRead(BPM_SW) == HIGH) bpmLedDivider = 1;
  else bpmLedDivider = 4;

  lastButtonTime = millis();
}

// =====================================================
// Display update
// =====================================================

void updateDisplay() {
  if (programSelectMode) {
    updateProgramDisplay();
    return;
  }

  int bpmInt = round(BPM);

  if (bpmInt != displayedBPM) {
    displayedBPM = bpmInt;
    tm.display(bpmInt, false, false, bpmInt < 100 ? 2 : 1);
  }
}

void updateProgramDisplay() {
  static uint8_t lastProgram = 255;
  static String scrollStr;

  // Only reconfigure display when program changes
  if (programIndex != lastProgram) {
    lastProgram = programIndex;

    const char* ptr;

    switch(programIndex) {
      case 0: ptr = pgmStr0; break;
      case 1: ptr = pgmStr1; break;
      case 2: ptr = pgmStr2; break;
      case 3: ptr = pgmStr3; break;
      case 4: ptr = pgmStr4; break;
      case 5: ptr = pgmStr5; break;
      case 6: ptr = pgmStr6; break;
      case 7: ptr = pgmStr7; break;
      case 8: ptr = pgmStr8; break;
      case 9: ptr = pgmStr9; break;
      case 10: ptr = pgmStr10; break;
      case 11: ptr = pgmStr11; break;
      case 12: ptr = pgmStr12; break;
      case 13: ptr = pgmStr13; break;
      case 14: ptr = pgmStr14; break;
      case 15: ptr = pgmStr15; break;
      case 16: ptr = pgmStr16; break;
      case 17: ptr = pgmStr17; break;
      case 18: ptr = pgmStr18; break;
      case 19: ptr = pgmStr19; break;
      case 20: ptr = pgmStr20; break;
      case 21: ptr = pgmStr21; break;
      case 22: ptr = pgmStr22; break;
      case 23: ptr = pgmStr23; break;
      default: ptr = pgmStr0; break;
    }

    // Copy from flash into String (once per change)
    scrollStr = String((__FlashStringHelper*)ptr);
  }

  tm.display(scrollStr)->scrollLeft(150);
}

// =====================================================
// Clock engine
// =====================================================

void updateClockEngine() {
  if (!isPlaying) return;

  // Whole microseconds, so no fraction of a tick gets dropped and the grid doesn't
  // lose precision over hours. The signed difference keeps working when micros()
  // wraps around every 71 minutes.
  unsigned long now = micros();
  unsigned long tickLength = (unsigned long)(MS_PER_MIN * 1000.0 / BPM / 4.0);

  if ((long)(now - nextTick) >= 0) {
    nextTick += tickLength;
    bpmCounter++;

    triggerClock(clocks[0]); // always tick

    if (bpmCounter % bpmLedDivider == 0) triggerClock(bpmLed);

    for (uint8_t i = 1; i < NUM_CLOCKS; i++) {
      if (bpmCounter % pgm[programIndex][i - 1] == 0) {
        triggerClock(clocks[i]);
      }
    }
  }
}

// =====================================================
// Output pulse helpers
// =====================================================

void triggerClock(ClockOut &clk) {
  digitalWrite(clk.pin, HIGH);
  clk.isHigh = true;
  clk.highStart = millis();
}

void updateOutputs() {
  unsigned long now = millis();

  for (uint8_t i = 0; i < NUM_CLOCKS; i++) {
    if (clocks[i].isHigh && now - clocks[i].highStart >= CLOCK_PULSE_MS) {
      digitalWrite(clocks[i].pin, LOW);
      clocks[i].isHigh = false;
    }
  }

  if (bpmLed.isHigh && now - bpmLed.highStart >= LED_PULSE_MS) {
    digitalWrite(bpmLed.pin, LOW);
    bpmLed.isHigh = false;
  }
}