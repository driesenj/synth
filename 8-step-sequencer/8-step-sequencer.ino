#include "MCP4725.h"
#include "ADS1X15.h"

MCP4725 cvA(0x61);
MCP4725 cvB(0x60);

ADS1115 ADS(0x48);

const bool DEBUG = false;
// Print the raw readings of the four ADS1115 inputs instead of running the
// sequencer, for checking the knob wiring
const bool DEBUG_KNOBS = false;
// cvA input of 1V outputs a voltage of 1.98V
const double CV_A_FACTOR = 1.98;
const double CV_B_FACTOR = 1.64;

// MODES
const int MODE_A_THEN_B = 0;
const int MODE_PING_PONG = 1;
const int MODE_CV_DUTY = 2;
const int MODE_CV_DUTY_RANDOM = 3;
const int MODE_RANDOM = 4;
const int MODE_CV_SLIDE = 5;
const int MODE_A_B_A_B = 6;
const int MODE_A_AND_B = 7;

// TRANSITIONS
const int TRANSITION_GATE_ON_OFF = 0;
const int TRANSITION_ACTIVE_STEP = 1;
const int TRANSITION_SLIDE = 2;
const int TRANSITION_STEP_JUMP = 3;

// QAUNTIZATION MODES
const int QUANTIZE_LINEAR = 0;
const int QUANTIZE_MINOR = 1;
const int QUANTIZE_MAJOR = 2;
const int QUANTIZE_CHROMA = 3;

// Scale definitions in semitones (relative to root 0)
const int CHROMA_SCALE[12] = { 0,1,2,3,4,5,6,7,8,9,10,11 };
const int MAJOR_SCALE[7]      = { 0,2,4,5,7,9,11 };
const int MINOR_SCALE[7]      = { 0,2,3,5,7,8,10 };

const int LED_ON = LOW;
const int LED_OFF = HIGH;

const int SHIFT_ON = HIGH;
const int SHIFT_OFF = LOW;

const int SEQ_LENGTH = 8;

const int POTS_A [] = {A7, A0, A1, A2, A3, A4, A5, A6 };
const int POTS_B [] = {A8, A9, A10, A11, A12, A13, A14, A15};

const int STEPS_A [] = {52, 50, 48, 46, 44, 42, 40, 38};
const int STEPS_B [] = {53, 51, 49, 47, 45, 43, 41, 39};

const int LEDS_A [] = {35, 37, 33, 25, 27, 31, 23, 29};
const int LEDS_B [] = {36, 34, 22, 24, 26, 28, 30, 32};

const int TRANSITION_LEDS [] = {10, 9, 7, 6};
const int MODE_LEDS [] = {5, 11, 3, 12, 2, 16, 14, 4};

const int DUTY_KNOB = 1;
const int MODE_KNOB = 3;
const int TRANSITION_KNOB = 2;
const int SHIFT_BUTTON = 19;

const int CLOCK_IN = 18;
const int GATE_A = 17;
const int GATE_B = 15;

// Low pass filtered readings of the potentiometers driving outputs A and B,
// and which potentiometer pin each one is following
float potValA = 0;
float potValB = 0;
int potPinA = -1;
int potPinB = -1;

// Last known values of the step buttons
int stepsEnabledA [] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};
int stepsEnabledB [] = {HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH, HIGH};

// Current pressed status of the step buttons
int stepsPressedA [] = {LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW};
int stepsPressedB [] = {LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW};

// Last selected mode
int currentMode = -1;
// Last selected transition
int currentTransition = -1;
// Last selected shift function
bool shift = false;
// Last known duty value
double duty = 0.0;

// Voltage range of sequences
int rangeA = 8;
int rangeB = 8;

// Quantization mode of sequences
int quantizeA = QUANTIZE_LINEAR;
int quantizeB = QUANTIZE_LINEAR;

// Set by the clock interrupt on a rising edge, picked up by handleClock()
volatile bool clockEdge = false;
// Time in millis of the last rising edge the clock interrupt accepted
volatile unsigned long clockEdgeTime = 0;
// Edges this soon after the previous one are noise on the clock line
const unsigned long CLOCK_HOLDOFF = 2; // ms

// Last time in millis the clock had a rising edge
unsigned long lastClockTime = 0;
// Clock period the gate lengths are based on, 0 until it is known
unsigned long lastClockDuration = 0;
// Time between the last 2 rising edges of the clock, including pauses
unsigned long lastClockGap = 0;

// The currently active step in the sequence, -1 when no step plays
int currentStepA = -1;
int currentStepB = -1;

// Keeps track of the current status of the gate outputs
int currentGateA = LOW;
int currentGateB = LOW;

// Voltage on the CV outputs, held while a channel has no step playing
double currentVoltageA = 0;
double currentVoltageB = 0;

// The voltage each output glides away from during the current step, for
// MODE_CV_SLIDE and TRANSITION_SLIDE
double slideFromA = 0;
double slideFromB = 0;

int adcWaitingOn = MODE_KNOB;
long lastADCStart = 0;
static const unsigned long adcInterval = 2; // ms

// ADS reading of a knob turned all the way up
const long KNOB_MAX = 27000;
// How far the mode and transition knobs have to move past the border of their
// current position before they change
const long KNOB_HYSTERESIS = 400;

// Step hold / repeat
int heldStepA = -1;
int heldStepB = -1;

// Where the sequence was when a hold started, it continues from there on release
int resumeStepA = -1;
int resumeStepB = -1;

// Whether the last clock played a held step
bool holdingA = false;
bool holdingB = false;

// For TRANSITION_STEP_JUMP, the step pressed since the last clock, -1 for none
int jumpStepA = -1;
int jumpStepB = -1;

unsigned long stepPressTimeA[8] = {0};
unsigned long stepPressTimeB[8] = {0};

const unsigned long HOLD_THRESHOLD = 200; // ms


void setup() {
  if (DEBUG || DEBUG_KNOBS) {
    Serial.begin(9600);
    while(!Serial);
    Serial.println("");
  }

  for (int i = 0; i < 8; i++) {
    pinMode(POTS_A[i], INPUT);
    pinMode(POTS_B[i], INPUT);
    pinMode(STEPS_A[i], INPUT);
    pinMode(STEPS_B[i], INPUT);
    pinMode(LEDS_A[i], OUTPUT);
    pinMode(LEDS_B[i], OUTPUT);
    pinMode(MODE_LEDS[i], OUTPUT);
    digitalWrite(LEDS_A[i], LED_OFF);
    digitalWrite(LEDS_B[i], LED_OFF);
    digitalWrite(MODE_LEDS[i], LED_OFF);
  }
  for (int i = 0; i < 4; i++) {
    pinMode(TRANSITION_LEDS[i], OUTPUT);
    digitalWrite(TRANSITION_LEDS[i], LED_OFF);
  }
  pinMode(SHIFT_BUTTON, INPUT_PULLUP);
  pinMode(GATE_A, OUTPUT);
  pinMode(GATE_B, OUTPUT);
  
  Wire.begin();
  if (DEBUG) {
    if (cvA.begin() == false) {
      Serial.println("Could not find sensor A");
    } else {
      Serial.println("Found sensor A");
    }
    if (cvB.begin() == false) {
      Serial.println("Could not find sensor B");
    } else {
      Serial.println("Found sensor B");
    }
  } else {
    cvA.begin();
    cvB.begin();
  }
  ADS.begin();
  ADS.setMode(ADS1X15_MODE_SINGLE);
  ADS.requestADC(MODE_KNOB);
  
  //  calibrate max voltage
  cvA.setMaxVoltage(5.1);
  cvB.setMaxVoltage(5.1);

  // Catch clock edges in an interrupt, so short trigger pulses aren't missed
  pinMode(CLOCK_IN, INPUT);
  attachInterrupt(digitalPinToInterrupt(CLOCK_IN), onClockRising, RISING);
}


void loop() {
  if (DEBUG_KNOBS) {
    printKnobs();
    return;
  }

  hardwareCheck();
  handleClock();
  handleOutput();
}

// Knob test: what each ADS1115 input reads, from about 0 at 0V to about 26700
// at 5V. Turn one knob at a time and see which input follows it.
void printKnobs() {
  static unsigned long lastPrint = 0;
  if (millis() - lastPrint < 250) return;
  lastPrint = millis();

  for (int channel = 0; channel < 4; channel++) {
    const char* name = channel == MODE_KNOB ? "mode"
                     : channel == TRANSITION_KNOB ? "transition"
                     : channel == DUTY_KNOB ? "duty" : "unused";
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

  if (shift) {
    if (digitalRead(STEPS_A[0])) {
      rangeA = 1;
    } else if (digitalRead(STEPS_A[1])) {
      rangeA = 2;
    } else if (digitalRead(STEPS_A[2])) {
      rangeA = 5;
    } else if (digitalRead(STEPS_A[3])) {
      rangeA = 8;
    }
    if (digitalRead(STEPS_A[4])) {
      quantizeA = QUANTIZE_LINEAR;
    } else if (digitalRead(STEPS_A[5])) {
      quantizeA = QUANTIZE_MINOR;
    } else if (digitalRead(STEPS_A[6])) {
      quantizeA = QUANTIZE_MAJOR;
    } else if (digitalRead(STEPS_A[7])) {
      quantizeA = QUANTIZE_CHROMA;
    }

    if (digitalRead(STEPS_B[0])) {
      rangeB = 1;
    } else if (digitalRead(STEPS_B[1])) {
      rangeB = 2;
    } else if (digitalRead(STEPS_B[2])) {
      rangeB = 5;
    } else if (digitalRead(STEPS_B[3])) {
      rangeB = 8;
    }
    if (digitalRead(STEPS_B[4])) {
      quantizeB = QUANTIZE_LINEAR;
    } else if (digitalRead(STEPS_B[5])) {
      quantizeB = QUANTIZE_MINOR;
    } else if (digitalRead(STEPS_B[6])) {
      quantizeB = QUANTIZE_MAJOR;
    } else if (digitalRead(STEPS_B[7])) {
      quantizeB = QUANTIZE_CHROMA;
    }
  } else {

    for (int i = 0; i < 8; i++) {
      int stepA = digitalRead(STEPS_A[i]);
      int stepB = digitalRead(STEPS_B[i]);

      if (stepA == HIGH && stepsPressedA[i] == LOW) {
        stepsPressedA[i] = HIGH;
        stepPressTimeA[i] = millis();

        // Step jump: the next clock plays this step
        if (currentTransition == TRANSITION_STEP_JUMP) jumpStepA = i;
      }

      if (stepA == HIGH && stepsPressedA[i] == HIGH) {
        if (heldStepA == -1 &&
            millis() - stepPressTimeA[i] > HOLD_THRESHOLD) {

          heldStepA = i;
        }
      }

      if (stepA == LOW && stepsPressedA[i] == HIGH) {
        stepsPressedA[i] = LOW;

        if (heldStepA == i) {
          heldStepA = -1;
        } else if (currentTransition != TRANSITION_STEP_JUMP) {
          // short press → toggle enable
          stepsEnabledA[i] = !stepsEnabledA[i];
        }
      }

      if (stepB == HIGH && stepsPressedB[i] == LOW) {
        stepsPressedB[i] = HIGH;
        stepPressTimeB[i] = millis();

        // Step jump: the next clock plays this step
        if (currentTransition == TRANSITION_STEP_JUMP) jumpStepB = i;
      }

      if (stepB == HIGH && stepsPressedB[i] == HIGH) {
        if (heldStepB == -1 &&
            millis() - stepPressTimeB[i] > HOLD_THRESHOLD) {

          heldStepB = i;
        }
      }

      if (stepB == LOW && stepsPressedB[i] == HIGH) {
        stepsPressedB[i] = LOW;

        if (heldStepB == i) {
          heldStepB = -1;
        } else if (currentTransition != TRANSITION_STEP_JUMP) {
          // short press → toggle enable
          stepsEnabledB[i] = !stepsEnabledB[i];
        }
      }
    }
  }

  if (millis() - lastADCStart > adcInterval && ADS.isReady()) {
    int raw = ADS.getValue();

    if (adcWaitingOn == MODE_KNOB) {
      int modeVal = knobPosition(raw, 8, currentMode);
      if (modeVal != currentMode) {
        if (currentMode >= 0)
          digitalWrite(MODE_LEDS[currentMode], LED_OFF);
        currentMode = modeVal;
        digitalWrite(MODE_LEDS[currentMode], LED_ON);

        resetSteps();
      }
      
      ADS.requestADC(TRANSITION_KNOB);
      adcWaitingOn = TRANSITION_KNOB;
    } else if (adcWaitingOn == TRANSITION_KNOB) {
      int transitionVal = knobPosition(raw, 4, currentTransition);
      if (transitionVal != currentTransition) {
        if (currentTransition >= 0)
          digitalWrite(TRANSITION_LEDS[currentTransition], LED_OFF);
        currentTransition = transitionVal;
        digitalWrite(TRANSITION_LEDS[currentTransition], LED_ON);

        resetSteps();
      }
      
      ADS.requestADC(DUTY_KNOB);
      adcWaitingOn = DUTY_KNOB;
    } else if (adcWaitingOn == DUTY_KNOB) {
      duty = 1 - min(1, abs(raw) / 26500.0);
      
      ADS.requestADC(MODE_KNOB);
      adcWaitingOn = MODE_KNOB;
    }


    lastADCStart = millis();
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

// For MODE_A_THEN_B
bool sequenceA = true;

// For MODE_PING_PONG
bool forwardA = true;
bool forwardB = true;

// For MODE_A_B_A_B
bool playA = true;
int previousStepA = -1;
int previousStepB = -1;

void resetSteps() {
  // Start before the first step, so the next clock plays step 0
  currentStepA = -1;
  currentStepB = -1;
  resumeStepA = -1;
  resumeStepB = -1;
  jumpStepA = -1;
  jumpStepB = -1;
  sequenceA = true;
  forwardA = true;
  forwardB = true;
  playA = true;
  previousStepA = -1;
  previousStepB = -1;
}

// Clock interrupt, flags the rising edge for handleClock()
void onClockRising() {
  unsigned long now = millis();
  if (now - clockEdgeTime < CLOCK_HOLDOFF) return;
  clockEdgeTime = now;
  clockEdge = true;
}

void handleClock() {
  // Pick up a rising edge flagged by the clock interrupt
  noInterrupts();
  bool clockRising = clockEdge;
  unsigned long currentTime = clockEdgeTime;
  clockEdge = false;
  interrupts();

  if (clockRising) {
    if (DEBUG) Serial.println("Clock L2H");

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

    // Slides start from wherever the outputs are now
    slideFromA = currentVoltageA;
    slideFromB = currentVoltageB;

    // Holding a step repeats it on every clock, and the sequence continues where
    // it was once the step is released. When A and B take turns in one sequence
    // a held step pauses the whole sequence, otherwise only its own row.
    bool linkedRows = currentMode == MODE_A_THEN_B || currentMode == MODE_RANDOM || currentMode == MODE_A_B_A_B;
    bool holdA = heldStepA >= 0 || (linkedRows && heldStepB >= 0);
    bool holdB = heldStepB >= 0 || (linkedRows && heldStepA >= 0);

    if (holdA && !holdingA) resumeStepA = currentStepA;
    if (!holdA && holdingA) currentStepA = resumeStepA;
    if (holdB && !holdingB) resumeStepB = currentStepB;
    if (!holdB && holdingB) currentStepB = resumeStepB;
    holdingA = holdA;
    holdingB = holdB;

    // Step jump: a step pressed since the last clock plays now instead of the
    // next one in line, and the sequence carries on from there. When A and B
    // take turns only one of them can jump, and row B has no steps of its own
    // in the CV/duty and slide modes.
    bool rowBSteps = currentMode != MODE_CV_DUTY && currentMode != MODE_CV_DUTY_RANDOM && currentMode != MODE_CV_SLIDE;
    int jumpA = holdA ? -1 : jumpStepA;
    int jumpB = (holdB || !rowBSteps || (linkedRows && jumpA >= 0)) ? -1 : jumpStepB;
    jumpStepA = -1;
    jumpStepB = -1;

    // Rows that repeat or jump don't move on by themselves
    bool stayA = holdA || jumpA >= 0 || (linkedRows && jumpB >= 0);
    bool stayB = holdB || jumpB >= 0 || (linkedRows && jumpA >= 0);

    // ==========================================
    // MODE A_THEN_B (play all A → then play all B)
    // ==========================================
    if (currentMode == MODE_A_THEN_B && !stayA) {
      while (true) {
        if (sequenceA) {
          if (currentStepA < SEQ_LENGTH - 1) {
            currentStepA++;
          } else {
            currentStepA = -1;
            currentStepB = 0;
            sequenceA = false;
          }
        } else {
          if (currentStepB < SEQ_LENGTH - 1) {
            currentStepB++;
          } else {
            currentStepB = -1;
            currentStepA = 0;
            sequenceA = true;
          }
        }

        if (currentTransition == TRANSITION_ACTIVE_STEP) {
          if (!hasAnyActive(stepsEnabledA, SEQ_LENGTH) && !hasAnyActive(stepsEnabledB, SEQ_LENGTH)) {
            currentStepA = -1;
            currentStepB = -1;

            break;
          }

          if (sequenceA && stepsEnabledA[currentStepA] == HIGH) break;
          if (!sequenceA && stepsEnabledB[currentStepB] == HIGH) break;
        } else {
          break;
        }
      }
    }

    // ==========================================
    // MODE PING_PONG
    // ==========================================
    if (currentMode == MODE_PING_PONG) {
      if (!stayA) currentStepA = pingPongStep(currentStepA, forwardA, stepsEnabledA);
      if (!stayB) currentStepB = pingPongStep(currentStepB, forwardB, stepsEnabledB);
    }

    // ==========================================
    // MODE CV/DUTY (SQ-1 style: A drives CV, B drives duty/gate)
    // ==========================================
    if ((currentMode == MODE_CV_DUTY || currentMode == MODE_CV_DUTY_RANDOM) && !stayA) {
      while (true) {
        currentStepB = -1;

        if (currentMode == MODE_CV_DUTY_RANDOM)
          currentStepA = random(0, SEQ_LENGTH);
        else
          currentStepA = (currentStepA + 1) % SEQ_LENGTH;

        if (currentTransition == TRANSITION_ACTIVE_STEP) {
          if (!hasAnyActive(stepsEnabledA, SEQ_LENGTH)) {
            currentStepA = -1;

            break;
          }

          if (currentStepA >= 0 && stepsEnabledA[currentStepA] == HIGH) break;
        } else {
          break;
        }
      }
    }

    // ==========================================
    // MODE RANDOM
    // ==========================================
    if (currentMode == MODE_RANDOM && !stayA) {
      while (true) {
        int step = random(0, 2 * SEQ_LENGTH);

        if (step < SEQ_LENGTH) {
          currentStepA = step;
          currentStepB = -1;
        } else {
          currentStepA = -1;
          currentStepB = step - SEQ_LENGTH;
        }

        if (currentTransition == TRANSITION_ACTIVE_STEP) {
          if (!hasAnyActive(stepsEnabledA, SEQ_LENGTH) && !hasAnyActive(stepsEnabledB, SEQ_LENGTH)) {
            currentStepA = -1;
            currentStepB = -1;

            break;
          }

          if (currentStepA >= 0 && stepsEnabledA[currentStepA] == HIGH) break;
          if (currentStepB >= 0 && stepsEnabledB[currentStepB] == HIGH) break;
        } else {
          break;
        }
      }
    }

    // ==========================================
    // MODE CV_SLIDE
    // ==========================================
    if (currentMode == MODE_CV_SLIDE && !stayA) {
      while (true) {
        // Slide does not affect step order
        currentStepA = (currentStepA + 1) % SEQ_LENGTH;

        if (currentTransition == TRANSITION_ACTIVE_STEP) {
          if (!hasAnyActive(stepsEnabledA, SEQ_LENGTH)) {
            currentStepA = -1;

            break;
          }

          if (currentStepA >= 0 && stepsEnabledA[currentStepA] == HIGH) break;
        } else {
          break;
        }
      }
    }

    // ==========================================
    // MODE A_B_A_B (alternate channels)
    // ==========================================
    if (currentMode == MODE_A_B_A_B && !stayA) {

      while (true) {
        if (playA) {
          currentStepA = (previousStepA + 1) % SEQ_LENGTH;
          previousStepA = currentStepA;
          currentStepB = -1;
        } else {
          currentStepB = (previousStepB + 1) % SEQ_LENGTH;
          previousStepB = currentStepB;
          currentStepA = -1;
        }

        if (currentTransition == TRANSITION_ACTIVE_STEP) {
          if (playA) {
            if (!hasAnyActive(stepsEnabledA, SEQ_LENGTH)) {
              currentStepA = -1;
              break;
            } else if (stepsEnabledA[currentStepA] == HIGH) {
              break;
            }
          } else {
            if (!hasAnyActive(stepsEnabledB, SEQ_LENGTH)) {
              currentStepB = -1;
              break;
            } else if (stepsEnabledB[currentStepB] == HIGH) {
              break;
            }
          }
        } else {
          break;
        }
      }
      
      playA = !playA;
    }

    // ==========================================
    // MODE A_AND_B (parallel sequencing)
    // ==========================================
    if (currentMode == MODE_A_AND_B) {
      // ---- A channel ----
      if (!stayA) {
        if (currentTransition == TRANSITION_ACTIVE_STEP && hasAnyActive(stepsEnabledA, SEQ_LENGTH))
          currentStepA = nextActiveForward(currentStepA, stepsEnabledA, SEQ_LENGTH);
        else
          currentStepA = (currentStepA + 1) % SEQ_LENGTH;
      }

      // ---- B channel ----
      if (!stayB) {
        if (currentTransition == TRANSITION_ACTIVE_STEP && hasAnyActive(stepsEnabledB, SEQ_LENGTH))
          currentStepB = nextActiveForward(currentStepB, stepsEnabledB, SEQ_LENGTH);
        else
          currentStepB = (currentStepB + 1) % SEQ_LENGTH;
      }
    }

    if (holdA) currentStepA = heldStepA;
    if (holdB) currentStepB = heldStepB;

    if (jumpA >= 0) currentStepA = jumpA;
    if (jumpB >= 0) currentStepB = jumpB;

    // When A and B take turns, the other row rests and the sequence carries on from the jumped to step
    if (linkedRows && jumpA >= 0) {
      currentStepB = -1;
      sequenceA = true;
      previousStepA = jumpA;
      playA = false;
    }
    if (linkedRows && jumpB >= 0) {
      currentStepA = -1;
      sequenceA = false;
      previousStepB = jumpB;
      playA = true;
    }
  }
}

// Next step of a row going back and forth, used by MODE_PING_PONG
int pingPongStep(int step, bool &forward, int enabled[]) {
  while (true) {
    // Turn around at the ends. Coming from no step at all starts again at step 0.
    if (step >= SEQ_LENGTH - 1) forward = false;
    if (step <= 0) forward = true;
    step += forward ? 1 : -1;

    if (currentTransition != TRANSITION_ACTIVE_STEP) return step;
    if (!hasAnyActive(enabled, SEQ_LENGTH)) return -1;
    if (enabled[step] == HIGH) return step;
  }
}

bool hasAnyActive(int arr[], int len) {
    for (int i = 0; i < len; i++)
        if (arr[i] == HIGH) return true;
    return false;
}

int nextActiveForward(int current, int arr[], int len) {
    int s = current;
    do {
        s = (s + 1) % len;
    } while (arr[s] == LOW);
    return s;
}

int nextActiveBackward(int current, int arr[], int len) {
    int s = current;
    do {
        s = (s - 1 + len) % len;
    } while (arr[s] == LOW);
    return s;
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

  // The step playing on output A. MODE_RANDOM plays the steps of both rows on output A.
  int potA = -1;
  int enabledA = LOW;
  if (currentStepA >= 0 && currentStepA < SEQ_LENGTH) {
    potA = POTS_A[currentStepA];
    enabledA = stepsEnabledA[currentStepA];
  } else if (currentMode == MODE_RANDOM && currentStepB >= 0 && currentStepB < SEQ_LENGTH) {
    potA = POTS_B[currentStepB];
    enabledA = stepsEnabledB[currentStepB];
  }

  double useDuty = duty;
  int gateA = LOW;
  int gateB = LOW;

  // A channel without a step keeps its voltage, so the release of its last note stays in tune
  if (potA >= 0) {
    if (currentMode == MODE_CV_DUTY || currentMode == MODE_CV_DUTY_RANDOM) {
      // Row B sets the gate length of each step, turned the same way as the duty knob
      useDuty = 1 - readPot(POTS_B[currentStepA], potValB, potPinB);
    }

    // Map the potentiometer value to a voltage range
    double inputVoltageA = (1 - readPot(potA, potValA, potPinA)) * rangeA;
    double outputVoltageA = quantizeCV(inputVoltageA, quantizeA);

    if (currentMode == MODE_CV_SLIDE) {
      // Glide from where output A was at the clock to this step's voltage over the length of the step
      currentVoltageA = slideFromA + slideProgress(currentDuty, 1.0) * (outputVoltageA - slideFromA);
    } else if (currentTransition == TRANSITION_SLIDE) {
      // Portamento: glide to this step's voltage while the gate is open
      currentVoltageA = slideFromA + slideProgress(currentDuty, useDuty) * (outputVoltageA - slideFromA);
    } else {
      currentVoltageA = outputVoltageA;
    }

    // Serial.print("input: ");
    // Serial.println(inputVoltageA);
    // Serial.print("output: ");
    // Serial.println(outputVoltageA);
    // Serial.print("set: ");
    // Serial.println(currentVoltageA / CV_A_FACTOR);

    if (enabledA == HIGH && currentDuty < useDuty) gateA = HIGH;
  }

  if (currentMode == MODE_CV_DUTY || currentMode == MODE_CV_DUTY_RANDOM || currentMode == MODE_CV_SLIDE || currentMode == MODE_RANDOM) {
    // Output B is not used in these modes
    currentVoltageB = 0;
  } else if (currentStepB >= 0 && currentStepB < SEQ_LENGTH) {
    double inputVoltageB = (1 - readPot(POTS_B[currentStepB], potValB, potPinB)) * rangeB;
    double outputVoltageB = quantizeCV(inputVoltageB, quantizeB);

    if (currentTransition == TRANSITION_SLIDE) {
      // Portamento: glide to this step's voltage while the gate is open
      currentVoltageB = slideFromB + slideProgress(currentDuty, duty) * (outputVoltageB - slideFromB);
    } else {
      currentVoltageB = outputVoltageB;
    }

    if (stepsEnabledB[currentStepB] == HIGH && currentDuty < duty) gateB = HIGH;
  }

  // The library only writes to the DAC when the value changes
  cvA.setVoltage(currentVoltageA / CV_A_FACTOR);
  cvB.setVoltage(currentVoltageB / CV_B_FACTOR);

  if (gateA != currentGateA) {
    digitalWrite(GATE_A, gateA);
    currentGateA = gateA;
  }
  if (gateB != currentGateB) {
    digitalWrite(GATE_B, gateB);
    currentGateB = gateB;
  }

  // Turn on/off step LEDs
  if (shift) {
    if (rangeA == 1) {
      digitalWrite(LEDS_A[0], LED_ON);
    } else {
      digitalWrite(LEDS_A[0], LED_OFF);
    }
    if (rangeA == 2) {
      digitalWrite(LEDS_A[1], LED_ON);
    } else {
      digitalWrite(LEDS_A[1], LED_OFF);
    }
    if (rangeA == 5) {
      digitalWrite(LEDS_A[2], LED_ON);
    } else {
      digitalWrite(LEDS_A[2], LED_OFF);
    }
    if (rangeA == 8) {
      digitalWrite(LEDS_A[3], LED_ON);
    } else {
      digitalWrite(LEDS_A[3], LED_OFF);
    }
    if (quantizeA == QUANTIZE_LINEAR) {
      digitalWrite(LEDS_A[4], LED_ON);
    } else {
      digitalWrite(LEDS_A[4], LED_OFF);
    }
    if (quantizeA == QUANTIZE_MINOR) {
      digitalWrite(LEDS_A[5], LED_ON);
    } else {
      digitalWrite(LEDS_A[5], LED_OFF);
    }
    if (quantizeA == QUANTIZE_MAJOR) {
      digitalWrite(LEDS_A[6], LED_ON);
    } else {
      digitalWrite(LEDS_A[6], LED_OFF);
    }
    if (quantizeA == QUANTIZE_CHROMA) {
      digitalWrite(LEDS_A[7], LED_ON);
    } else {
      digitalWrite(LEDS_A[7], LED_OFF);
    }

    if (rangeB == 1) {
      digitalWrite(LEDS_B[0], LED_ON);
    } else {
      digitalWrite(LEDS_B[0], LED_OFF);
    }
    if (rangeB == 2) {
      digitalWrite(LEDS_B[1], LED_ON);
    } else {
      digitalWrite(LEDS_B[1], LED_OFF);
    }
    if (rangeB == 5) {
      digitalWrite(LEDS_B[2], LED_ON);
    } else {
      digitalWrite(LEDS_B[2], LED_OFF);
    }
    if (rangeB == 8) {
      digitalWrite(LEDS_B[3], LED_ON);
    } else {
      digitalWrite(LEDS_B[3], LED_OFF);
    }
    if (quantizeB == QUANTIZE_LINEAR) {
      digitalWrite(LEDS_B[4], LED_ON);
    } else {
      digitalWrite(LEDS_B[4], LED_OFF);
    }
    if (quantizeB == QUANTIZE_MINOR) {
      digitalWrite(LEDS_B[5], LED_ON);
    } else {
      digitalWrite(LEDS_B[5], LED_OFF);
    }
    if (quantizeB == QUANTIZE_MAJOR) {
      digitalWrite(LEDS_B[6], LED_ON);
    } else {
      digitalWrite(LEDS_B[6], LED_OFF);
    }
    if (quantizeB == QUANTIZE_CHROMA) {
      digitalWrite(LEDS_B[7], LED_ON);
    } else {
      digitalWrite(LEDS_B[7], LED_OFF);
    }
  } else {
    for (int i = 0; i < 8; i++) {
      if (i == currentStepA) {
        digitalWrite(LEDS_A[i], stepsEnabledA[i]);
      } else {
        digitalWrite(LEDS_A[i], !stepsEnabledA[i]);
      }
      if (i == currentStepB) {
        digitalWrite(LEDS_B[i], stepsEnabledB[i]);
      } else {
        digitalWrite(LEDS_B[i], !stepsEnabledB[i]);
      }
    }
  }
}

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

