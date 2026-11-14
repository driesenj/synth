// Runs eight.ino on a PC against a stand-in Arduino core and checks how the
// sequence plays: ROWS x DIRECTION, the step settings, holds, jumps, RESET
// timing, gates, glides and the saved settings. Each test runs in its own
// process, so every one starts from power up.
//
//   ./run.sh            (WSL or Linux: g++ with the address and UB sanitizers)
#include "Arduino.h"
#include "ADS1X15.h"
#include "EEPROM.h"
#include "MCP4725.h"
#include <string>
#include <sys/wait.h>
#include <unistd.h>

unsigned long fakeMillis = 1000;
int pinLevel[PINS];
int pinModes[PINS];
int analogLevel[PINS];
void (*isr[PINS])();
FakeSerial Serial;
FakeWire Wire;
FakeEEPROM EEPROM;

// The prototypes the Arduino builder would generate
void loadSettings();
void saveSettings();
void printKnobs();
void hardwareCheck();
void readStepButton(int row, int step, bool pressed);
void readKnob(int knob, int raw);
int knobPosition(int raw, int positions, int current);
int shownSetting();
void setRowsMode(int mode);
int lineCount();
int lineLength();
int rowAt(int line, int pos);
int stepAt(int line, int pos);
int lineOf(int row);
int positionOf(int row, int step);
bool playsAt(int line, int pos);
int playingFrom(int line, int start, int dir);
int nextPosition(int line, int pos);
void resetSteps();
void advance();
void onClockRising();
void onResetRising();
void handleClock();
void startSteps();
double readPot(int pin, float &val, int &lastPin);
double slideProgress(double currentDuty, double length);
void handleOutput();
bool isPlaying(int row, int step);
void showSteps();
void settingsChanged();
float quantizeCV(float inVolts, int mode);
int quantizeToScale(float fracSemi, const int* scale, int scaleSize);

#include "../eight.ino"

#define CHECK(cond, ...) do { if (!(cond)) { std::printf("    line %d: ", __LINE__); std::printf(__VA_ARGS__); \
                                              std::printf("\n"); std::exit(1); } } while (0)
#define CHECK_SEQ(got, want) CHECK((got) == (want), "played  %s\n             wanted  %s", (got).c_str(), (want).c_str())

const unsigned long PERIOD = 100;     // ms per clock, 16ths at 150 BPM
const int A = 0, B = 1;

void run(unsigned long ms) {
  for (unsigned long i = 0; i < ms; i++) {
    loop();
    fakeMillis++;
  }
}

void setKnob(int channel, int position, int positions) {
  ADS.knob[channel] = (int16_t)((position + 0.5) * KNOB_MAX / positions);
}

// Set the four control knobs and give the ADS1115 time to read them all
void knobs(int rows, int dir, int buttons, double dutyFraction = 0.5) {
  setKnob(ROWS_KNOB, rows, ROWS_POSITIONS);
  setKnob(DIRECTION_KNOB, dir, 4);
  setKnob(BUTTONS_KNOB, buttons, 4);
  ADS.knob[DUTY_KNOB] = (int16_t)((1 - dutyFraction) * 26500);
  run(120);
}

// Step k (1-8) of a row at k volts on the 8 V range: the pots are wired CW to GND
void potsAtStepVolts() {
  for (int row = 0; row < 2; row++)
    for (int step = 0; step < SEQ_LENGTH; step++)
      analogLevel[POTS[row][step]] = (int)(1023 * (1 - (step + 1) / 8.0) + 0.5);
}

void clockEdgeNow() { isr[CLOCK_IN](); }
void resetEdgeNow() { isr[RESET_IN](); }

std::string played(int line) {
  if (playStep[line] < 0) return "-";
  return std::string(1, (char)('A' + playRow[line])) + std::to_string(playStep[line] + 1);
}

// n clocks, a period apart; what the line played on each
std::string ticks(int n, int line = 0) {
  std::string s;
  for (int i = 0; i < n; i++) {
    clockEdgeNow();
    run(PERIOD);
    s += (i ? " " : "") + played(line);
  }
  return s;
}

void press(int row, int step) { pinLevel[STEPS[row][step]] = HIGH; }
void release(int row, int step) { pinLevel[STEPS[row][step]] = LOW; run(40); }
void tap(int row, int step) { press(row, step); run(60); release(row, step); }

double jackVolts(int out) { return DACS[out]->volts * CV_FACTOR[out]; }

// ---------------------------------------------------------------- the tests

void chainForward() {
  knobs(ROWS_CHAIN, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(17), std::string("A1 A2 A3 A4 A5 A6 A7 A8 B1 B2 B3 B4 B5 B6 B7 B8 A1"));
  CHECK(outStep[0] == outStep[1] && outRow[0] == outRow[1], "both outputs play the one line");
}

void alternate() {
  knobs(ROWS_ALTERNATE, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(17), std::string("A1 B1 A2 B2 A3 B3 A4 B4 A5 B5 A6 B6 A7 B7 A8 B8 A1"));
}

void chainPingPong() {
  knobs(ROWS_CHAIN, DIRECTION_PING_PONG, BUTTONS_GATE);
  CHECK_SEQ(ticks(19), std::string("A1 A2 A3 A4 A5 A6 A7 A8 B1 B2 B3 B4 B5 B6 B7 B8 B7 B6 B5"));
}

void parallelPingPongWithSkips() {
  knobs(ROWS_PARALLEL, DIRECTION_PING_PONG, BUTTONS_SKIP);
  tap(A, 5); tap(A, 6); tap(A, 7);           // row A plays steps 1-5 only
  std::string a, b;
  for (int i = 0; i < 10; i++) {
    clockEdgeNow();
    run(PERIOD);
    a += (i ? " " : "") + played(0);
    b += (i ? " " : "") + played(1);
  }
  CHECK_SEQ(a, std::string("A1 A2 A3 A4 A5 A4 A3 A2 A1 A2"));
  CHECK_SEQ(b, std::string("B1 B2 B3 B4 B5 B6 B7 B8 B7 B6"));
}

void reverse() {
  knobs(ROWS_PARALLEL, DIRECTION_REVERSE, BUTTONS_GATE);
  CHECK_SEQ(ticks(9), std::string("A8 A7 A6 A5 A4 A3 A2 A1 A8"));
  clockEdgeNow(); run(PERIOD - 10); resetEdgeNow(); run(10);
  CHECK_SEQ(ticks(2), std::string("A8 A7"));   // reverse starts at its first step, step 8
}

void randomPlaysOnlyPlayingSteps() {
  knobs(ROWS_PARALLEL, DIRECTION_RANDOM, BUTTONS_SKIP);
  tap(A, 1); tap(A, 3);                      // skip A2 and A4
  int seen[SEQ_LENGTH] = {0};
  for (int i = 0; i < 300; i++) {
    clockEdgeNow();
    run(5);
    CHECK(playRow[0] == A && playStep[0] >= 0, "row A plays");
    seen[playStep[0]]++;
  }
  CHECK(seen[1] == 0 && seen[3] == 0, "skipped steps never play");
  for (int step : {0, 2, 4, 5, 6, 7}) CHECK(seen[step] > 10, "step %d plays (%d times)", step + 1, seen[step]);
  run(PERIOD);
  resetEdgeNow(); run(20);
  CHECK_SEQ(ticks(1), std::string("A1"));    // after a reset, step 1 first
}

void cvModesHaveOneLine() {
  knobs(ROWS_CV_DUTY, DIRECTION_RANDOM, BUTTONS_GATE);
  for (int i = 0; i < 50; i++) {
    clockEdgeNow();
    run(5);
    CHECK(playRow[0] == A && playStep[1] < 0, "CV/DUTY + RANDOM plays row A alone");
  }
  bool before = stepSetting[SETTING_GATE][B][2];
  tap(B, 2);
  CHECK(stepSetting[SETTING_GATE][B][2] == before, "row B's buttons do nothing in CV/DUTY");
  showSteps();
  for (int step = 0; step < SEQ_LENGTH; step++)
    CHECK((pinLevel[LEDS_B[step]] == LED_ON) == (step == playStep[0]), "row B lights the knob in use");
}

void resetBeforeClock() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(3), std::string("A1 A2 A3"));
  clockEdgeNow(); run(PERIOD - 10);          // A4
  resetEdgeNow(); run(10);
  CHECK_SEQ(played(0), std::string("A4"));
  CHECK_SEQ(ticks(2), std::string("A1 A2"));
  CHECK_SEQ(played(1), std::string("B2"));
}

void resetTogetherWithClock() {
  knobs(ROWS_CHAIN, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(5), std::string("A1 A2 A3 A4 A5"));
  resetEdgeNow(); clockEdgeNow(); run(PERIOD);
  CHECK_SEQ(played(0), std::string("A1"));
}

void resetJustAfterClock() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  potsAtStepVolts();
  CHECK_SEQ(ticks(5), std::string("A1 A2 A3 A4 A5"));
  clockEdgeNow(); run(3);                    // A6 starts...
  CHECK_SEQ(played(0), std::string("A6"));
  resetEdgeNow(); run(PERIOD - 3);           // ...and a reset 3 ms later makes it step 1
  CHECK_SEQ(played(0), std::string("A1"));
  CHECK_SEQ(played(1), std::string("B1"));
  CHECK(std::fabs(jackVolts(0) - 1.0) < 0.01, "CV A at step 1's 1 V, not %.3f", jackVolts(0));
  CHECK_SEQ(ticks(2), std::string("A2 A3"));
}

void resetLateWaitsForNextClock() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(3), std::string("A1 A2 A3"));
  clockEdgeNow(); run(8);
  resetEdgeNow(); run(PERIOD - 8);           // 8 ms late: outside the 5 ms window
  CHECK_SEQ(played(0), std::string("A4"));
  CHECK_SEQ(ticks(1), std::string("A1"));
}

void holdRepeatsAndResumes() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(2), std::string("A1 A2"));
  press(A, 4); run(250);                     // hold A5
  CHECK_SEQ(ticks(3), std::string("A5 A5 A5"));
  release(A, 4);
  CHECK(stepSetting[SETTING_GATE][A][4], "a hold does not toggle the step");
  CHECK_SEQ(ticks(2), std::string("A3 A4"));
}

void holdInOneLinePausesIt() {
  knobs(ROWS_CHAIN, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(9), std::string("A1 A2 A3 A4 A5 A6 A7 A8 B1"));
  press(A, 2); run(250);
  CHECK_SEQ(ticks(2), std::string("A3 A3"));
  release(A, 2);
  CHECK_SEQ(ticks(2), std::string("B2 B3"));
}

void jump() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_JUMP);
  CHECK_SEQ(ticks(2), std::string("A1 A2"));
  tap(A, 5);
  CHECK(stepSetting[SETTING_GATE][A][5], "a jump does not toggle the step");
  CHECK_SEQ(ticks(3), std::string("A6 A7 A8"));
  tap(B, 0);
  CHECK_SEQ(ticks(2, 1), std::string("B1 B2"));
}

void rowsChangeKeepsThePlace() {
  knobs(ROWS_CHAIN, DIRECTION_FORWARD, BUTTONS_GATE);
  CHECK_SEQ(ticks(12), std::string("A1 A2 A3 A4 A5 A6 A7 A8 B1 B2 B3 B4"));
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  clockEdgeNow(); run(PERIOD);
  CHECK_SEQ(played(0) + " " + played(1), std::string("A5 B5"));
}

// Gate high (or not) at each ms of one clock period
std::string gateDuringStep(int out) {
  std::string g;
  clockEdgeNow();
  for (unsigned long t = 0; t < PERIOD; t++) {
    loop();
    g += pinLevel[GATES[out]] ? '#' : '.';
    fakeMillis++;
  }
  return g;
}

void restHoldsTheCV() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE, 0.5);
  potsAtStepVolts();
  tap(A, 2);                                 // A3 rests
  ticks(8);                                  // a full round, so the clock period is known
  std::string g1 = gateDuringStep(0);
  CHECK(g1 == std::string(50, '#') + std::string(50, '.'), "A1's gate: half the step\n%s", g1.c_str());
  gateDuringStep(0);                         // A2
  CHECK(std::fabs(jackVolts(0) - 2.0) < 0.01, "A2 at 2 V");
  std::string g3 = gateDuringStep(0);        // A3, the rest
  CHECK(g3 == std::string(100, '.'), "a rest has no gate\n%s", g3.c_str());
  CHECK(std::fabs(jackVolts(0) - 2.0) < 0.01, "a rest holds the CV at A2's 2 V, not %.3f", jackVolts(0));
}

void slideTiesAndGlides() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_SLIDE, 0.5);
  potsAtStepVolts();
  tap(A, 1);                                 // A2 slides into A3
  ticks(8);
  gateDuringStep(0);                         // A1
  std::string g2 = gateDuringStep(0);        // A2: tied, open to the end
  CHECK(g2 == std::string(100, '#'), "A2's gate stays open into A3\n%s", g2.c_str());
  clockEdgeNow(); loop();                    // A3 starts: no gap, the glide begins at A2's 2 V
  CHECK(pinLevel[GATE_A] == HIGH, "legato into A3");
  CHECK(std::fabs(jackVolts(0) - 2.0) < 0.05, "A3 glides from 2 V (%.3f)", jackVolts(0));
  fakeMillis += 25; loop();                  // a quarter step: halfway through a half-step glide
  CHECK(std::fabs(jackVolts(0) - 2.5) < 0.05, "halfway at 2.5 V (%.3f)", jackVolts(0));
  fakeMillis += 30; loop();
  CHECK(std::fabs(jackVolts(0) - 3.0) < 0.01, "at A3's 3 V after half a step (%.3f)", jackVolts(0));
  CHECK(pinLevel[GATE_A] == LOW, "A3 itself does not tie: its gate closes at half the step");
  run(PERIOD - 56);
  clockEdgeNow(); loop();                    // A4: no glide
  CHECK(std::fabs(jackVolts(0) - 4.0) < 0.01, "A4 jumps straight to 4 V (%.3f)", jackVolts(0));
}

void tieClosesWhenTheClockStops() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_SLIDE, 0.5);
  tap(A, 1);
  ticks(9);                                  // ... A1, then A2 (tied)
  CHECK_SEQ(played(0), std::string("A1"));
  clockEdgeNow(); run(120);
  CHECK(pinLevel[GATE_A] == HIGH, "still tied 1.2 periods in");
  run(10);
  CHECK(pinLevel[GATE_A] == LOW, "a tie lets go 1.25 periods in, when no clock came");
}

void cvDuty() {
  knobs(ROWS_CV_DUTY, DIRECTION_FORWARD, BUTTONS_GATE, 0.5);
  analogLevel[POTS_B[0]] = (int)(1023 * 0.75);       // B1: a quarter of the step
  analogLevel[POTS_B[1]] = (int)(1023 * 0.25);       // B2: three quarters
  ticks(8);
  std::string g1 = gateDuringStep(0);
  std::string g2 = gateDuringStep(0);
  CHECK(std::abs(std::count(g1.begin(), g1.end(), '#') - 25) <= 1, "B1 sets A1's gate to a quarter\n%s", g1.c_str());
  CHECK(std::abs(std::count(g2.begin(), g2.end(), '#') - 75) <= 1, "B2 sets A2's gate to three quarters\n%s", g2.c_str());
  CHECK(pinLevel[GATE_B] == pinLevel[GATE_A], "output B plays the same line");
}

void cvSlide() {
  knobs(ROWS_CV_SLIDE, DIRECTION_FORWARD, BUTTONS_GATE, 0.5);
  potsAtStepVolts();
  analogLevel[POTS_B[0]] = 0;                // B1 fully clockwise: A1 glides into A2 over the whole step
  analogLevel[POTS_B[1]] = 1023;             // B2 fully counter-clockwise: no glide into A3
  ticks(8);
  gateDuringStep(0);                         // A1
  clockEdgeNow(); loop();
  fakeMillis += 50; loop();
  CHECK(std::fabs(jackVolts(0) - 1.5) < 0.05, "halfway from 1 V to 2 V (%.3f)", jackVolts(0));
  run(PERIOD - 50);
  clockEdgeNow(); loop();
  CHECK(std::fabs(jackVolts(0) - 3.0) < 0.01, "straight to A3's 3 V (%.3f)", jackVolts(0));
}

void rangeAndQuantizer() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  analogLevel[POTS_A[0]] = (int)(1023 * (1 - 3.3 / 8.0));   // 3.3 V on the 8 V range
  ticks(1);
  CHECK(std::fabs(jackVolts(0) - 3.3) < 0.01, "linear: 3.3 V (%.3f)", jackVolts(0));
  pinLevel[SHIFT_BUTTON] = LOW;
  tap(A, 7);                                 // SHIFT + A8: chromatic
  tap(B, 1);                                 // SHIFT + B2: row B on the 2 V range
  pinLevel[SHIFT_BUTTON] = HIGH;
  CHECK(quantize[A] == QUANTIZE_CHROMA && range[B] == 2, "SHIFT sets each row's own quantizer and range");
  CHECK(range[A] == 8 && quantize[B] == QUANTIZE_LINEAR, "and leaves the other row's alone");
  run(5);
  CHECK(std::fabs(jackVolts(0) - 40 / 12.0) < 0.01, "chromatic: 3.333 V (%.3f)", jackVolts(0));
}

void ledsShowTheSettingAndThePlayingStep() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  tap(A, 2);                                 // A3 gate off
  ticks(1);                                  // A1 plays
  for (int step = 0; step < SEQ_LENGTH; step++) {
    bool on = (step != 2) != (step == 0);
    CHECK((pinLevel[LEDS_A[step]] == LED_ON) == on, "GATE view, A%d %s", step + 1, on ? "lit" : "dark");
  }
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_SLIDE);
  for (int step = 0; step < SEQ_LENGTH; step++)
    CHECK((pinLevel[LEDS_A[step]] == LED_ON) == (step == 0), "SLIDE view: none on, the playing A1 inverted");
}

void settingsSurvivePowerOff() {
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_GATE);
  tap(A, 2);
  knobs(ROWS_PARALLEL, DIRECTION_FORWARD, BUTTONS_SLIDE);
  tap(B, 6);
  pinLevel[SHIFT_BUTTON] = LOW;
  tap(B, 1); tap(A, 6);
  pinLevel[SHIFT_BUTTON] = HIGH;
  CHECK(EEPROM.writes == 0, "nothing written while changes are still coming");
  run(SAVE_DELAY + 50);
  int writes = EEPROM.writes;
  CHECK(writes > 0 && writes <= 11, "one save after the changes stop (%d bytes)", writes);
  run(SAVE_DELAY * 2);
  CHECK(EEPROM.writes == writes, "no more writes while nothing changes");
  setup();                                   // power up again
  CHECK(!stepSetting[SETTING_GATE][A][2] && stepSetting[SETTING_GATE][A][3], "A3's gate stays off");
  CHECK(stepSetting[SETTING_SLIDE][B][6] && !stepSetting[SETTING_SLIDE][B][5], "B7's slide stays on");
  CHECK(range[B] == 2 && quantize[A] == QUANTIZE_MAJOR, "ranges and scales stay");
}

struct Test { const char* name; void (*fn)(); };
const Test TESTS[] = {
  {"A->B forward", chainForward},
  {"ABAB", alternate},
  {"A->B ping-pong over 16 steps", chainPingPong},
  {"A+B ping-pong, skipped steps", parallelPingPongWithSkips},
  {"reverse, and reset in reverse", reverse},
  {"random plays only playing steps", randomPlaysOnlyPlayingSteps},
  {"CV modes: one line, row B marks its knob", cvModesHaveOneLine},
  {"reset before a clock", resetBeforeClock},
  {"reset together with a clock", resetTogetherWithClock},
  {"reset 3 ms after a clock", resetJustAfterClock},
  {"reset 8 ms after a clock", resetLateWaitsForNextClock},
  {"hold repeats, release resumes", holdRepeatsAndResumes},
  {"hold in A->B pauses the line", holdInOneLinePausesIt},
  {"jump", jump},
  {"ROWS change keeps the place", rowsChangeKeepsThePlace},
  {"rest: no gate, CV holds", restHoldsTheCV},
  {"slide: tie and glide", slideTiesAndGlides},
  {"tie lets go when the clock stops", tieClosesWhenTheClockStops},
  {"CV/DUTY", cvDuty},
  {"CV/SLIDE", cvSlide},
  {"range and quantizer per row", rangeAndQuantizer},
  {"LEDs", ledsShowTheSettingAndThePlayingStep},
  {"settings survive power off", settingsSurvivePowerOff},
};

int main() {
  int failed = 0;
  for (const Test& t : TESTS) {
    std::fflush(stdout);
    pid_t pid = fork();
    if (pid == 0) {
      setup();
      t.fn();
      std::exit(0);
    }
    int status = 0;
    waitpid(pid, &status, 0);
    bool ok = WIFEXITED(status) && WEXITSTATUS(status) == 0;
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", t.name);
    failed += !ok;
  }
  std::printf("%d of %d passed\n", (int)(sizeof TESTS / sizeof TESTS[0]) - failed, (int)(sizeof TESTS / sizeof TESTS[0]));
  return failed ? 1 : 0;
}
