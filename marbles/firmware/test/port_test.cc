// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy host tests: the port on a model of the board (hal_fake.cc), with
// Marbles' own code compiled unchanged. Run with test/run_port_test.sh; a
// group name runs one group.

#include <math.h>
#include <stdio.h>
#include <string.h>

#include <random>
#include <vector>

#include "hal_fake.h"
#include "marblesy.h"

#include "marbles/drivers/adc.h"
#include "marbles/drivers/dac.h"
#include "marbles/drivers/leds.h"
#include "marbles/drivers/switches.h"
#include "stmlib/system/system_clock.h"

#include "board_tables.h"
#include "storage.h"

using namespace marbles;
using marblesy::hal::CvInput;

namespace {

int checks = 0;
int failures = 0;
const char* group = "";

#define CHECK(cond, ...) do { \
    ++checks; \
    if (!(cond)) { \
      ++failures; \
      printf("FAIL %s:%d [%s] %s: ", __FILE__, __LINE__, group, #cond); \
      printf(__VA_ARGS__); \
      printf("\n"); \
    } \
  } while (0)

#define CHECK_NEAR(a, b, tolerance, ...) do { \
    const double a_ = (a), b_ = (b); \
    CHECK(fabs(a_ - b_) <= (tolerance), \
          "%s = %.6g, expected %.6g +- %.3g; ", #a, a_, b_, \
          static_cast<double>(tolerance)); \
    if (fabs(a_ - b_) > (tolerance)) { printf(__VA_ARGS__); printf("\n"); } \
  } while (0)

// 74HC165 inputs.
const int kTDejaVu = 0;
const int kTMode = 1;
const int kTRange = 2;
const int kXDejaVu = 3;
const int kXMode = 4;
const int kXRange = 5;
const int kXExt = 6;

void Start() {
  // A power-up: RAM starts zeroed, as the startup code leaves .bss, and
  // Marbles counts on that (Ui::Init() does not set the UI mode).
  memset(static_cast<void*>(&ui), 0, sizeof(ui));
  memset(static_cast<void*>(&settings), 0, sizeof(settings));
  memset(static_cast<void*>(&cv_reader), 0, sizeof(cv_reader));
  memset(static_cast<void*>(&io_buffer), 0, sizeof(io_buffer));
  marblesy::Init();
  marblesy::hal::StartInterrupts(&marblesy::IoTick, &marblesy::DspTick);
}

void Boot() {
  fake::Reset();
  Start();
}

void Reboot() {
  fake::Reboot();
  Start();
}

// The main loop runs between milliseconds.
void Run(uint32_t ms) {
  while (ms--) {
    fake::RunMilliseconds(1);
    marblesy::Persist();
  }
}

void Press(int input, uint32_t ms = 60) {
  fake::SetButton(input, true);
  Run(ms);
  fake::SetButton(input, false);
  Run(60);
}

// Holds `held`, presses and releases `pressed`, lets go of `held`.
void Chord(int held, int pressed) {
  fake::SetButton(held, true);
  Run(100);
  Press(pressed);
  fake::SetButton(held, false);
  Run(100);
}

int Slot(size_t channel) {
  return static_cast<int>(Dac::Slot(channel));
}

// The word DAC channel `channel` gets for `volts` with the calibration in
// RAM, as Marbles' DacCode() computes it.
uint16_t ModelWord(size_t channel, float volts) {
  const CalibrationData& c = settings.calibration_data();
  CONSTRAIN(volts, -5.0f, 5.0f);
  int32_t code = static_cast<int32_t>(
      volts * c.dac_scale[channel] + c.dac_offset[channel]);
  if (code < 0) code = 0;
  if (code > 65535) code = 65535;
  return Dac::Word(channel, static_cast<uint16_t>(code));
}

// ... and what comes out: at the op-amp, and at the jack into a 1V/oct
// input (100k to ground), which the output calibration is made for.
float ModelOutput(size_t channel, float volts) {
  return fake::OutputVoltsFor(Slot(channel), ModelWord(channel, volts));
}

float LoadedOutput(size_t channel, float volts) {
  return fake::LoadedOutputVoltsFor(Slot(channel), ModelWord(channel, volts));
}

// Longer than the save delays: the state alone, and a calibration or a
// scale.
const uint32_t kStateSaved = 31000;
const uint32_t kDataSaved = 6000;

fake::Parts RandomParts(int seed, float tolerance) {
  std::mt19937 g(seed);
  std::uniform_real_distribution<float> u(-tolerance, tolerance);
  fake::Parts p;
  for (int i = 0; i < marblesy::hal::CV_INPUT_LAST; ++i) {
    p.cv_rin[i] = u(g);
    p.cv_rf[i] = u(g);
  }
  p.cv_bias = u(g);
  p.vref = u(g) * 0.5f;
  for (int i = 0; i < 4; ++i) {
    p.dac_rin[i] = u(g);
    p.dac_rref[i] = u(g);
    p.dac_rf[i] = u(g);
    p.dac_gain[i] = u(g) * 0.5f;
    p.dac_offset[i] = u(g) * 0.3f;  // up to 3 mV at 1 %
  }
  return p;
}

// Marbles' calibration procedure: hold X range, press t range; 1 V and 3 V
// into t RATE, then into X SPREAD, a range button after each.
void CalibrateInputs() {
  Chord(kXRange, kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 1.0f);
  Run(500);
  Press(kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 3.0f);
  Run(500);
  Press(kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 0.0f);
  fake::SetCv(marblesy::hal::CV_X_SPREAD, 1.0f);
  Run(500);
  Press(kXRange);
  fake::SetCv(marblesy::hal::CV_X_SPREAD, 3.0f);
  Run(500);
  Press(kXRange);
  fake::SetCv(marblesy::hal::CV_X_SPREAD, 0.0f);
  Run(1000);
}

// The output calibration: hold t range, press X range; each output in turn
// into X SPREAD, then a range button.
void CalibrateOutputs(bool patch = true) {
  Chord(kTRange, kXRange);
  for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
    if (patch) {
      fake::PatchOutput(marblesy::hal::CV_X_SPREAD, Slot(channel));
    }
    Run(200);
    Press(kXRange);
    Run(1500);
  }
  fake::PatchOutput(marblesy::hal::CV_X_SPREAD, -1);
  Run(1000);
}

uint32_t CountRisingEdges(uint32_t gate_bit, uint32_t ticks) {
  uint32_t edges = 0;
  bool previous = fake::Gates() & gate_bit;
  for (uint32_t i = 0; i < ticks; ++i) {
    fake::Tick();
    if (i % 32 == 31) {
      marblesy::Persist();
    }
    const bool now = fake::Gates() & gate_bit;
    edges += now && !previous;
    previous = now;
  }
  return edges;
}

// --- Groups ---------------------------------------------------------------

void TestCv() {
  Boot();
  // Every input reads back the jack voltage through the nominal stage, and
  // Marbles' reading for it, 0.5 - V / 10 of full scale.
  for (int input = 0; input < marblesy::hal::CV_INPUT_LAST; ++input) {
    for (float v = -5.0f; v <= 5.0f; v += 0.25f) {
      fake::SetCv(CvInput(input), v);
      const float back = Adc::JackVoltage(marblesy::hal::ReadCv(CvInput(input)));
      CHECK_NEAR(back, v, 0.001, "input %d", input);
      const float reading = Adc::MarblesReading(back) / 65536.0f;
      CHECK_NEAR(reading, 0.5f - v / 10.0f, 2.0 / 65536.0, "input %d", input);
    }
    fake::SetCv(CvInput(input), 0.0f);
  }
  // Clipped where Marbles' stage clips.
  CHECK(Adc::MarblesReading(6.0f) == 0, "+6 V");
  CHECK(Adc::MarblesReading(-6.0f) == 65535, "-6 V");

  // The CV slots in Marbles' order, X SPREAD in both of its slots.
  fake::SetCv(marblesy::hal::CV_X_SPREAD, 2.0f);
  fake::SetCv(marblesy::hal::CV_T_JITTER, -1.0f);
  Run(5);
  const uint16_t* raw = nullptr;
  {
    Adc adc;
    adc.Convert();
    raw = adc.values();
    CHECK_NEAR(raw[ADC_GROUP_CV + ADC_CHANNEL_X_SPREAD] / 65536.0, 0.3, 3e-5, "%s", "");
    CHECK_NEAR(raw[ADC_GROUP_CV + ADC_CHANNEL_X_SPREAD_2] / 65536.0, 0.3, 3e-5, "%s", "");
    CHECK_NEAR(raw[ADC_GROUP_CV + ADC_CHANNEL_T_JITTER] / 65536.0, 0.6, 3e-5, "%s", "");
    CHECK_NEAR(raw[ADC_GROUP_CV + ADC_CHANNEL_T_RATE] / 65536.0, 0.5, 3e-5, "%s", "");
  }
  fake::SetCv(marblesy::hal::CV_X_SPREAD, 0.0f);
  fake::SetCv(marblesy::hal::CV_T_JITTER, 0.0f);

  // Pots in Marbles' order, from the mux channels as routed.
  {
    const marblesy::hal::Pot pots[ADC_CHANNEL_LAST] = {
      marblesy::hal::POT_DEJA_VU, marblesy::hal::POT_DEJA_VU_LENGTH,
      marblesy::hal::POT_T_RATE, marblesy::hal::POT_T_BIAS,
      marblesy::hal::POT_T_JITTER, marblesy::hal::POT_X_SPREAD,
      marblesy::hal::POT_X_BIAS, marblesy::hal::POT_X_STEPS,
    };
    for (int i = 0; i < ADC_CHANNEL_LAST; ++i) {
      fake::SetPot(pots[i], 0.1f + 0.1f * i);
    }
    Adc adc;
    adc.Convert();
    for (int i = 0; i < ADC_CHANNEL_LAST; ++i) {
      CHECK_NEAR(adc.value(ADC_GROUP_POT + i) / 65536.0, 0.1 + 0.1 * i, 1e-4,
                 "pot %d", i);
    }
  }

  // Marbles' calibration with 1 % parts.
  for (int seed = 1; seed <= 4; ++seed) {
    fake::Reset();
    fake::SetParts(RandomParts(seed, 0.01f));
    Start();
    CalibrateInputs();
    const CvReaderChannel& rate = cv_reader.channel(ADC_CHANNEL_T_RATE);
    const CvReaderChannel& spread = cv_reader.channel(ADC_CHANNEL_X_SPREAD);
    for (float v = -4.0f; v <= 4.0f; v += 1.0f) {
      fake::SetCv(marblesy::hal::CV_T_RATE, v);
      fake::SetCv(marblesy::hal::CV_X_SPREAD, v);
      Run(20);
      CHECK_NEAR(rate.scaled_raw_cv(), 12.0f * v, 0.02,
                 "seed %d: t RATE at %.1f V", seed, v);
      CHECK_NEAR(spread.scaled_raw_cv(), v / 5.0f, 0.0002,
                 "seed %d: X SPREAD at %.1f V", seed, v);
    }
    fake::SetCv(marblesy::hal::CV_T_RATE, 0.0f);
    fake::SetCv(marblesy::hal::CV_X_SPREAD, 0.0f);
    Run(20);
    // The zeros of the other inputs, measured at step 1.
    const int others[] = {
      ADC_CHANNEL_DEJA_VU_AMOUNT, ADC_CHANNEL_T_BIAS, ADC_CHANNEL_T_JITTER,
      ADC_CHANNEL_X_BIAS, ADC_CHANNEL_X_STEPS
    };
    for (int i : others) {
      CHECK_NEAR(cv_reader.channel(i).cv(), 0.0, 0.001, "seed %d: %d", seed, i);
    }
    // Saved, and back after a power cycle.
    CalibrationData before = settings.calibration_data();
    Run(6000);
    Reboot();
    CHECK(memcmp(&before, &settings.calibration_data(), sizeof(before)) == 0,
          "seed %d: calibration kept", seed);
  }
}

void TestDac() {
  Boot();
  // Command words: the right DAC of each chip, buffered, gain 1, active,
  // 12-bit rounded.
  for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
    const uint16_t w = Dac::Word(channel, 0x1238);
    CHECK(((w >> 15) & 1) == (Slot(channel) & 1), "channel %zu A/B", channel);
    CHECK((w & 0x7000) == 0x7000, "channel %zu control bits %04x", channel, w);
    CHECK((w & 0xfff) == 0x124, "channel %zu data %03x", channel, w & 0xfff);
    CHECK((Dac::Word(channel, 0xfffc) & 0xfff) == 0xfff, "top");
    CHECK((Dac::Word(channel, 0) & 0xfff) == 0, "bottom");
  }
  // Marbles' channel order: Y, X1, X2, X3 on U8 B, U7 A, U7 B, U8 A.
  CHECK(Slot(0) == 3 && Slot(1) == 0 && Slot(2) == 1 && Slot(3) == 2,
        "slots %d %d %d %d", Slot(0), Slot(1), Slot(2), Slot(3));
  CHECK(board::kDacSlotOfChannel[0] == Slot(0) &&
        board::kDacSlotOfChannel[1] == Slot(1) &&
        board::kDacSlotOfChannel[2] == Slot(2) &&
        board::kDacSlotOfChannel[3] == Slot(3), "circuit.py's DAC wiring");

  // Right after the start-up, before the generators run: 0 V everywhere.
  Boot();
  CHECK(fake::DacWrites() > 0, "written");
  for (int slot = 0; slot < 4; ++slot) {
    CHECK_NEAR(fake::OutputVolts(slot), 0.0, 0.002, "slot %d", slot);
  }
  // The nominal calibration is circuit.py's output stage.
  CHECK_NEAR(kDacScale, -65536.0 * board::kDacInputResistor /
             (board::kDacFeedbackResistor * board::kReference), 0.01, "%s", "");
  CHECK_NEAR(kDacOffset, 65536.0 * board::kDacInputResistor /
             board::kDacOffsetResistor, 0.01, "%s", "");
  // Its reach: about +5.32 V and -5.10 V.
  CHECK(fake::OutputVoltsFor(0, Dac::Word(1, 0)) > 5.3f, "top");
  CHECK(fake::OutputVoltsFor(0, Dac::Word(1, 0xffff)) < -5.09f, "bottom");
  // The nominal calibration on the nominal stage.
  for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
    for (float v = -5.0f; v <= 5.0f; v += 0.5f) {
      CHECK_NEAR(ModelOutput(channel, v), v, 0.0015, "channel %zu", channel);
    }
  }
  // The two codes the output calibration uses.
  CHECK_NEAR(fake::OutputVoltsFor(0, Dac::Word(1, 0x1d90)), 4.115, 0.01, "%s", "");
  CHECK_NEAR(fake::OutputVoltsFor(0, Dac::Word(1, 0xaf30)), -1.81, 0.01, "%s", "");
}

void TestOutputCalibration() {
  for (int seed = 11; seed <= 14; ++seed) {
    fake::Reset();
    fake::SetParts(RandomParts(seed, 0.01f));
    Start();
    CalibrateInputs();
    float worst_before = 0.0f;
    for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
      for (float v = -4.0f; v <= 5.0f; v += 1.0f) {
        worst_before = fmaxf(worst_before, fabsf(ModelOutput(channel, v) - v));
      }
    }
    CHECK(worst_before > 0.01f, "seed %d: uncalibrated already within %.4f V",
          seed, worst_before);
    CalibrateOutputs();
    CHECK(!ui.calibrating_outputs(), "seed %d: done", seed);
    for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
      for (float v = -4.0f; v <= 5.0f; v += 0.5f) {
        CHECK_NEAR(LoadedOutput(channel, v), v, 0.0025,
                   "seed %d channel %zu", seed, channel);
      }
    }
    // Saved, and back after a power cycle.
    CalibrationData before = settings.calibration_data();
    Run(6000);
    Reboot();
    CHECK(memcmp(&before, &settings.calibration_data(), sizeof(before)) == 0,
          "seed %d: kept", seed);
  }

  // Nothing patched: the first measurement fails, the panic LEDs show, the
  // outputs keep their calibration and nothing is saved.
  Boot();
  const CalibrationData before = settings.calibration_data();
  Chord(kTRange, kXRange);
  CHECK(ui.calibrating_outputs(), "started");
  Press(kXRange);
  bool panic_seen = false;
  for (int ms = 0; ms < 1500; ++ms) {
    Run(1);
    // The panic LEDs: the four red/green LEDs red, two by two.
    const uint16_t bits = fake::LedBits();
    if ((bits & ((1 << 1) | (1 << 8))) && !(bits & ((1 << 2) | (1 << 9)))) {
      panic_seen = true;
    }
  }
  CHECK(panic_seen, "panic LEDs");
  CHECK(!ui.calibrating_outputs(), "left");
  CHECK(memcmp(&before, &settings.calibration_data(), sizeof(before)) == 0,
        "calibration untouched");
  const uint32_t writes = fake::FlashWrites();
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == writes, "nothing saved");

  // Any other button gives up while an output waits, and so does a
  // minute without a press: the outputs keep their calibration and play.
  Boot();
  Run(500);
  Chord(kTRange, kXRange);
  CHECK(ui.calibrating_outputs(), "started");
  Press(kTMode);
  CHECK(!ui.calibrating_outputs(), "given up");
  CHECK(settings.state().t_model == 0, "and nothing else: %u",
        settings.state().t_model);
  CHECK(memcmp(&before, &settings.calibration_data(), sizeof(before)) == 0,
        "calibration untouched");
  Chord(kTRange, kXRange);
  Run(59000);
  CHECK(ui.calibrating_outputs(), "still waiting");
  Run(2000);
  CHECK(!ui.calibrating_outputs(), "timed out");

  // During the calibration the other outputs sit at 0 V and the gates low.
  Boot();
  Chord(kTRange, kXRange);
  fake::PatchOutput(marblesy::hal::CV_X_SPREAD, Slot(0));
  Press(kXRange);
  Run(100);
  CHECK(fake::Gates() == 0, "gates %u", fake::Gates());
  for (size_t channel = 1; channel < kNumDacChannels; ++channel) {
    CHECK_NEAR(fake::OutputVolts(Slot(channel)), 0.0, 0.002, "%zu", channel);
  }
  CHECK_NEAR(fake::OutputVolts(Slot(0)), 4.115, 0.01, "Y at the high point");

  // While an output waits to be measured, all four sit at 0 V: the
  // README's first power-up check.
  Boot();
  Chord(kTRange, kXRange);
  Run(100);
  for (size_t channel = 0; channel < kNumDacChannels; ++channel) {
    CHECK_NEAR(fake::OutputVolts(Slot(channel)), 0.0, 0.002, "%zu", channel);
  }
}

void TestLeds() {
  // Each LED in each colour, against circuit.py's 74HC595 wiring.
  const uint32_t colors[] = {
    LED_COLOR_OFF, LED_COLOR_RED, LED_COLOR_GREEN, LED_COLOR_YELLOW
  };
  uint8_t levels[kNumOutputLeds] = { 0 };
  for (int led = 0; led < LED_LAST; ++led) {
    for (uint32_t color : colors) {
      uint32_t frame[LED_LAST] = { 0 };
      frame[led] = color;
      const int red = board::kLedRedBit[led];
      const int green = board::kLedGreenBit[led];
      for (uint32_t phase = 0; phase < 4; ++phase) {
        const uint16_t bits = Leds::Bits(frame, levels, phase);
        uint16_t expected = 0;
        const bool r = color & 0x800000;
        const bool g = color & 0x008000;
        if (red < 0) {
          expected = g ? (1 << green) : 0;
        } else if (r && g) {
          expected = 1 << ((phase & 1) ? red : green);
        } else if (r) {
          expected = 1 << red;
        } else if (g) {
          expected = 1 << green;
        }
        CHECK(bits == expected, "led %d color %06x phase %u: %04x, want %04x",
              led, color, phase, bits, expected);
      }
    }
  }
  // Output LEDs: level L lights L refreshes out of 16.
  uint32_t frame[LED_LAST] = { 0 };
  for (size_t channel = 0; channel < kNumOutputLeds; ++channel) {
    for (uint8_t level = 0; level <= kOutputLedLevels; ++level) {
      uint8_t l[kNumOutputLeds] = { 0 };
      l[channel] = level;
      int lit = 0;
      for (uint32_t phase = 0; phase < 16; ++phase) {
        const uint16_t bits = Leds::Bits(frame, l, phase);
        CHECK((bits & ~(1 << board::kOutputLedBit[channel])) == 0, "stray");
        lit += (bits >> board::kOutputLedBit[channel]) & 1;
      }
      CHECK(lit == level, "channel %zu level %u lit %d", channel, level, lit);
    }
  }
  CHECK(marblesy::OutputLedLevel(0.0f) == 0, "zero");
  CHECK(marblesy::OutputLedLevel(5.0f) == kOutputLedLevels, "full");
  CHECK(marblesy::OutputLedLevel(-5.0f) == kOutputLedLevels, "negative");
  CHECK(marblesy::OutputLedLevel(2.5f) == 8, "half: %u",
        marblesy::OutputLedLevel(2.5f));
  CHECK(marblesy::OutputLedLevel(-7.0f) == kOutputLedLevels, "clipped");

  // On the module: the default state (t mode green, t range yellow, X mode
  // green, X range red) and the LED frame every 4 samples.
  Boot();
  const uint32_t before = fake::LedWrites();
  fake::Run(400);
  CHECK(fake::LedWrites() - before == 100, "%u refreshes",
        fake::LedWrites() - before);
  bool range_red = false, range_green = false;
  for (int i = 0; i < 8; ++i) {
    fake::Run(4);
    const uint16_t bits = fake::LedBits();
    CHECK(bits & (1 << board::kLedGreenBit[LED_T_MODEL]), "t mode green");
    CHECK(bits & (1 << board::kLedGreenBit[LED_X_CONTROL_MODE]), "X mode");
    CHECK(bits & (1 << board::kLedRedBit[LED_X_RANGE]), "X range red");
    range_red |= bits & (1 << board::kLedRedBit[LED_T_RANGE]);
    range_green |= bits & (1 << board::kLedGreenBit[LED_T_RANGE]);
  }
  CHECK(range_red && range_green, "t range yellow alternates");
}

void TestButtons() {
  for (int s = 0; s < SWITCH_LAST; ++s) {
    const uint8_t reading = static_cast<uint8_t>(~(1 << board::kSwitchInput[s]));
    for (int t = 0; t < SWITCH_LAST; ++t) {
      CHECK(Switches::Level(reading, Switch(t)) == (s != t), "%d %d", s, t);
    }
  }
  Boot();
  // The pots' filters start from 0: while they settle, a knob "moves", and
  // Marbles takes a held t mode for a hidden-setting edit.
  Run(500);
  CHECK(settings.state().t_model == 0, "model");
  Press(kTMode);
  CHECK(settings.state().t_model == 1, "t mode: %u", settings.state().t_model);
  Press(kTMode);
  Press(kTMode);
  CHECK(settings.state().t_model == 0, "wraps");
  Press(kTMode, 2300);  // long press: the second bank
  CHECK(settings.state().t_model == 3, "bank: %u", settings.state().t_model);
  Press(kXExt);
  CHECK(settings.state().x_register_mode == 1, "X ext");
  Press(kXRange);
  CHECK(settings.state().x_range == 2, "no range change in ext mode");
  Press(kXExt);
  Press(kXRange);
  CHECK(settings.state().x_range == 0, "range: %u", settings.state().x_range);
  Press(kTDejaVu);
  CHECK(settings.state().t_deja_vu == DEJA_VU_ON, "deja vu");
  Press(kXDejaVu, 2300);
  CHECK(settings.state().x_deja_vu == DEJA_VU_LOCKED, "locked");
  // t deja vu held while DEJA VU turns: Marbles' empty hidden-setting slot.
  // Nothing is written; the knob freezes and the release is taken, as on
  // Marbles.
  {
    const uint8_t before = settings.state().t_deja_vu;
    fake::SetButton(kTDejaVu, true);
    Run(100);
    fake::SetPot(marblesy::hal::POT_DEJA_VU, 0.9f);
    fake::SetPot(marblesy::hal::POT_DEJA_VU_LENGTH, 0.1f);
    Run(300);
    fake::SetButton(kTDejaVu, false);
    Run(100);
    CHECK(settings.state().t_deja_vu == before, "release taken");
    fake::SetPot(marblesy::hal::POT_DEJA_VU, 0.5f);
    fake::SetPot(marblesy::hal::POT_DEJA_VU_LENGTH, 0.5f);
    Run(300);
  }
  // t mode + X mode: the explicit reset mode.
  Chord(kTMode, kXMode);
  CHECK(settings.state().explicit_reset == 1, "reset mode");
  Run(kStateSaved);
  // X mode at power-up: colour-blind mode, saved.
  fake::Reboot();
  fake::SetButton(kXMode, true);
  Start();
  fake::SetButton(kXMode, false);
  CHECK(settings.state().color_blind == 1, "colour blind");
  CHECK(settings.state().explicit_reset == 1, "reset mode kept");
  Run(kStateSaved);
  Reboot();
  CHECK(settings.state().color_blind == 1, "kept");

  // X mode held through power-up, long enough to see the LEDs (and past a
  // long press): only the colour-blind mode changes. On Marbles the knobs'
  // filters ramp up from 0 meanwhile, so the held button took them for
  // hidden-setting edits, rewriting Y's settings and freezing four knobs,
  // and its release stepped the X mode.
  for (int hold = 300; hold <= 2500; hold += 2200) {
    Boot();
    Run(500);
    State* s = settings.mutable_state();
    s->y_divider = 200;
    s->y_spread = 30;
    s->y_bias = 220;
    s->y_steps = 10;
    settings.SaveState();
    fake::SetPot(marblesy::hal::POT_T_RATE, 0.5f);
    fake::SetPot(marblesy::hal::POT_X_SPREAD, 0.7f);
    fake::SetPot(marblesy::hal::POT_X_BIAS, 0.3f);
    fake::SetPot(marblesy::hal::POT_X_STEPS, 0.9f);
    Run(kStateSaved);
    fake::Reboot();
    fake::SetPot(marblesy::hal::POT_T_RATE, 0.5f);
    fake::SetPot(marblesy::hal::POT_X_SPREAD, 0.7f);
    fake::SetPot(marblesy::hal::POT_X_BIAS, 0.3f);
    fake::SetPot(marblesy::hal::POT_X_STEPS, 0.9f);
    fake::SetButton(kXMode, true);
    Start();
    Run(hold);
    fake::SetButton(kXMode, false);
    Run(500);
    const State& t = settings.state();
    CHECK(t.color_blind == 1, "hold %d: colour blind", hold);
    CHECK(t.y_divider == 200 && t.y_spread == 30 && t.y_bias == 220 &&
          t.y_steps == 10, "hold %d: Y %u %u %u %u", hold, t.y_divider,
          t.y_spread, t.y_bias, t.y_steps);
    CHECK(t.x_control_mode == 0, "hold %d: X mode %u", hold, t.x_control_mode);
    CHECK_NEAR(cv_reader.channel(ADC_CHANNEL_T_RATE).pot(), 0.0, 0.6,
               "hold %d: RATE follows its knob", hold);
    CHECK_NEAR(cv_reader.channel(ADC_CHANNEL_X_STEPS).unscaled_pot(), 0.9,
               0.01, "hold %d: STEPS", hold);
  }

  // A 74HC165 that does not answer reads all seven buttons held: no
  // firmware update gesture, no presses.
  Boot();
  Run(500);
  fake::SetButtonsDead(true);
  CHECK(!marblesy::BootloaderGesture(), "dead 74HC165: no gesture");
  fake::Reboot();
  fake::SetButtonsDead(true);
  Start();
  Run(5000);
  CHECK(settings.state().t_model == 0 && settings.state().x_deja_vu == 0 &&
        settings.state().x_control_mode == 0 && !ui.recording_scale(),
        "dead 74HC165: no presses");
  fake::SetButtonsDead(false);
  // ... and one that stops answering later, while the module runs.
  Boot();
  Run(500);
  fake::SetButtonsDead(true);
  Run(5000);
  CHECK(settings.state().t_model == 0 && settings.state().x_deja_vu == 0 &&
        settings.state().x_control_mode == 0 && !ui.recording_scale() &&
        settings.state().t_range == 1, "74HC165 lost: no presses");
  fake::SetButtonsDead(false);
  // A button pressed right after the start: the knobs' filters start
  // settled, so it is not taken for a hidden-setting edit.
  Boot();
  Press(kTMode);
  CHECK(settings.state().t_model == 1, "first press: %u",
        settings.state().t_model);
  // The gesture itself: t deja vu alone.
  fake::SetButton(kTDejaVu, true);
  CHECK(marblesy::BootloaderGesture(), "t deja vu");
  fake::SetButton(kXMode, true);
  CHECK(!marblesy::BootloaderGesture(), "with another button");
  fake::ReleaseAllButtons();
  CHECK(!marblesy::BootloaderGesture(), "nothing held");
}

void TestIo() {
  Boot();
  const uint32_t dsp = fake::DspRuns();
  const uint32_t dac = fake::DacWrites();
  const uint32_t reads = fake::ButtonReads();
  const uint32_t ms = stmlib::system_clock.milliseconds();
  const uint32_t feeds = fake::WatchdogFeeds();
  fake::Run(32000);
  CHECK(fake::DspRuns() - dsp == 6400, "DSP %u", fake::DspRuns() - dsp);
  CHECK(fake::WatchdogFeeds() - feeds == 6400, "watchdog");
  CHECK(fake::DacWrites() - dac == 32000, "DAC %u", fake::DacWrites() - dac);
  CHECK(fake::ButtonReads() - reads == 1000, "buttons %u",
        fake::ButtonReads() - reads);
  CHECK(stmlib::system_clock.milliseconds() - ms == 1000, "UI clock");

  // The internal clock: RATE at noon is 120 BPM, t2 at 2 Hz.
  Boot();
  Run(100);
  uint32_t edges = CountRisingEdges(2, 32000 * 10);
  CHECK(edges >= 19 && edges <= 21, "t2 at noon: %u in 10 s", edges);
  fake::SetPot(marblesy::hal::POT_T_RATE, 1.0f);
  Run(100);
  edges = CountRisingEdges(2, 32000 * 2);
  CHECK(edges > 40, "t2 at full rate: %u in 2 s", edges);
  fake::SetPot(marblesy::hal::POT_T_RATE, 0.5f);
  fake::SetCv(marblesy::hal::CV_T_RATE, 1.0f);  // one octave up
  Run(500);
  edges = CountRisingEdges(2, 32000 * 10);
  CHECK(edges >= 39 && edges <= 41, "t2 at +1 V: %u in 10 s", edges);
  fake::SetCv(marblesy::hal::CV_T_RATE, 0.0f);

  // An external clock: the probe stops getting through, and t2 follows the
  // clock (in t mode's first model, t2 is the clock itself). Counted from
  // 0.2 s on: until the probe has told the cable apart (10 ms), the internal
  // clock runs.
  Boot();
  fake::PatchClock(0, true);
  uint32_t clock_edges = 0;
  bool previous_t2 = false;
  uint32_t t2_edges = 0;
  for (uint32_t i = 0; i < 32000 * 4; ++i) {
    // 5 Hz, 10 % duty.
    fake::SetClock(0, (i % 6400) < 640);
    const bool counting = i >= 6400;
    clock_edges += counting && (i % 6400) == 0;
    fake::Tick();
    const bool t2 = fake::Gates() & 2;
    t2_edges += counting && t2 && !previous_t2;
    previous_t2 = t2;
  }
  CHECK(t2_edges >= clock_edges - 3 && t2_edges <= clock_edges,
        "t2 %u for %u clocks", t2_edges, clock_edges);

  // CV before gate: X1 (clocked by t1) never changes in the sample t1 rises.
  Boot();
  fake::SetPot(marblesy::hal::POT_X_STEPS, 1.0f);  // stepped
  Run(100);
  uint16_t last_word = fake::DacWord(Slot(1));
  uint32_t last_change = 0;
  bool previous_t1 = false;
  int rises = 0;
  int violations = 0;
  for (uint32_t i = 1; i < 32000 * 6; ++i) {
    fake::Tick();
    if (fake::DacWord(Slot(1)) != last_word) {
      last_word = fake::DacWord(Slot(1));
      last_change = i;
    }
    const bool t1 = fake::Gates() & 1;
    if (t1 && !previous_t1) {
      ++rises;
      if (last_change == i) {
        ++violations;
      }
    }
    previous_t1 = t1;
  }
  CHECK(rises > 3, "t1 rose %d times", rises);
  CHECK(violations == 0, "%d of %d", violations, rises);
}

void TestStorage() {
  using marblesy::RecordStore;
  fake::Reset();
  RecordStore store;
  store.Init(0, 4, 1024, 0x12345678);
  uint8_t record[952];
  uint8_t back[952];
  CHECK(!store.Load(back, sizeof(back)), "blank");
  for (int i = 0; i < 40; ++i) {
    memset(record, i, sizeof(record));
    CHECK(store.Save(record, sizeof(record)), "save %d", i);
  }
  CHECK(fake::FlashErases() == 10, "erases %u", fake::FlashErases());
  RecordStore again;
  again.Init(0, 4, 1024, 0x12345678);
  CHECK(again.Load(back, sizeof(back)), "load");
  CHECK(back[0] == 39 && back[951] == 39, "newest: %u", back[0]);
  CHECK(!again.Load(back, 951), "size must match");

  // A power cut in any operation of a save: the previous record or the new
  // one, never neither.
  for (int cut = 0; cut < 3; ++cut) {
    for (int start = 0; start < 9; ++start) {
      fake::Reset();
      RecordStore s;
      s.Init(0, 4, 1024, 0x12345678);
      for (int i = 0; i <= start; ++i) {
        memset(record, i + 1, sizeof(record));
        s.Save(record, sizeof(record));
      }
      fake::CutPowerAfter(cut);
      memset(record, 0xaa, sizeof(record));
      s.Save(record, sizeof(record));
      fake::CutPowerAfter(-1);
      RecordStore r;
      r.Init(0, 4, 1024, 0x12345678);
      CHECK(r.Load(back, sizeof(back)), "cut %d start %d: something", cut, start);
      CHECK(back[0] == 0xaa || back[0] == start + 1, "cut %d start %d: %02x",
            cut, start, back[0]);
      // And saving goes on afterwards.
      memset(record, 0x55, sizeof(record));
      CHECK(r.Save(record, sizeof(record)), "save after cut");
      RecordStore t;
      t.Init(0, 4, 1024, 0x12345678);
      CHECK(t.Load(back, sizeof(back)) && back[0] == 0x55, "after cut");
    }
  }
}

void TestSettings() {
  Boot();
  CHECK(settings.freshly_baked(), "fresh");
  CHECK(settings.state().t_range == 1 && settings.state().x_range == 2, "defaults");
  CHECK_NEAR(settings.calibration_data().dac_scale[0], kDacScale, 0.01, "%s", "");
  CHECK_NEAR(settings.calibration_data().dac_offset[0], kDacOffset, 0.01, "%s", "");
  // A state change is saved 30 s after the last one, once.
  Press(kTRange);
  Run(3000);
  Press(kTRange);
  Run(27000);
  CHECK(fake::FlashWrites() == 0, "too early: %u", fake::FlashWrites());
  Run(4000);
  CHECK(fake::FlashWrites() == 1, "once: %u", fake::FlashWrites());
  // Back where the flash already is: no write.
  Press(kTRange);
  Press(kTRange);
  Press(kTRange);
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == 1, "unchanged state: %u", fake::FlashWrites());
  Reboot();
  CHECK(!settings.freshly_baked(), "loaded");
  CHECK(settings.state().t_range == 0, "t range %u", settings.state().t_range);

  // An abandoned calibration never reaches the flash, even with a state
  // save in between.
  Boot();
  Chord(kXRange, kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 1.0f);
  fake::SetCv(marblesy::hal::CV_T_BIAS, 0.4f);  // a wrong zero
  Run(300);
  Press(kTRange);  // offsets and t RATE's first point, in RAM
  Press(kTMode);   // a state change, saved
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == 1, "state saved: %u", fake::FlashWrites());
  Reboot();
  CHECK_NEAR(settings.calibration_data().adc_offset[ADC_CHANNEL_T_BIAS], 1.0,
             1e-6, "calibration not saved");

  // A failed calibration leaves the previous one in use (Marbles keeps the
  // steps that passed until power-off).
  Boot();
  CalibrateInputs();
  const CalibrationData good = settings.calibration_data();
  Chord(kXRange, kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 1.0f);
  fake::SetCv(marblesy::hal::CV_X_BIAS, 0.5f);  // a wrong zero
  Run(300);
  Press(kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 3.0f);
  Run(300);
  Press(kTRange);
  fake::SetCv(marblesy::hal::CV_T_RATE, 0.0f);
  Run(300);
  Press(kXRange);  // nothing into X SPREAD: step 4 fails
  Run(300);
  Press(kXRange);
  fake::SetCv(marblesy::hal::CV_X_BIAS, 0.0f);
  Run(1500);
  CHECK(memcmp(&good, &settings.calibration_data(), sizeof(good)) == 0,
        "the previous calibration is back");

  // A record with values far off: Marbles' outlier check puts the nominal
  // ones back.
  Boot();
  CalibrationData* c = settings.mutable_calibration_data();
  c->dac_scale[2] = -3000.0f;
  c->dac_offset[3] = 50000.0f;
  c->adc_scale[ADC_CHANNEL_T_RATE] = -200.0f;
  settings.SavePersistentData();
  Run(6000);
  Reboot();
  CHECK_NEAR(settings.calibration_data().dac_scale[2], kDacScale, 0.01, "%s", "");
  CHECK_NEAR(settings.calibration_data().dac_offset[3], kDacOffset, 0.01, "%s", "");
  CHECK_NEAR(settings.calibration_data().adc_scale[ADC_CHANNEL_T_RATE], -120.0,
             1e-4, "%s", "");

  // Changes Marbles does not save by themselves (deja vu, the reset mode)
  // are saved too.
  Boot();
  Run(500);
  Press(kTDejaVu);
  Chord(kTMode, kXMode);
  Run(kStateSaved);
  Reboot();
  CHECK(settings.state().t_deja_vu == DEJA_VU_ON, "deja vu kept");
  CHECK(settings.state().explicit_reset == 1, "reset mode kept");

  // An input calibration left half way, by the reset-mode chord or by X
  // ext, leaves the previous one in use; the next save of a scale or of an
  // output calibration must not store the zeros measured at step 1.
  for (int way = 0; way < 2; ++way) {
    Boot();
    Run(500);
    Chord(kXRange, kTRange);
    fake::SetCv(marblesy::hal::CV_T_BIAS, 0.4f);  // a wrong zero
    fake::SetCv(marblesy::hal::CV_T_RATE, 1.0f);
    Run(300);
    Press(kTRange);
    fake::SetCv(marblesy::hal::CV_T_BIAS, 0.0f);
    fake::SetCv(marblesy::hal::CV_T_RATE, 0.0f);
    if (way == 0) {
      Chord(kTMode, kXMode);
      Run(5000);
      Press(kXExt, 2300);  // record a scale...
    } else {
      Press(kXExt, 2300);  // straight from the calibration into recording
    }
    Press(kXExt, 2300);    // ... and restore the preset: a save
    Run(kStateSaved);
    Reboot();
    CHECK_NEAR(settings.calibration_data().adc_offset[ADC_CHANNEL_T_BIAS], 1.0,
               1e-6, "way %d: the zero from step 1 is not kept", way);
  }

  // A save that fails is retried: an erase that fails, then a write.
  Boot();
  Run(500);
  fake::FailFlashOperations(1);
  Press(kTRange);
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == 0, "first try failed");
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == 1, "retried: %u", fake::FlashWrites());
  Press(kTRange);
  Run(500);
  fake::FailFlashOperations(1);  // the next write (no erase in this sector)
  Run(kStateSaved);
  CHECK(fake::FlashWrites() == 2, "tried again in the next slot: %u",
        fake::FlashWrites());
  Reboot();
  CHECK(settings.state().t_range == 0, "kept: %u", settings.state().t_range);

  // A recorded scale is saved: X ext held 2 s, notes through X SPREAD with
  // the X clock as gate, X ext again.
  Boot();
  Press(kXExt, 2300);
  CHECK(ui.recording_scale(), "recording");
  fake::PatchClock(1, true);
  const float notes[] = { 0.0f, 0.25f, 0.5833f, 0.25f, 0.0f };
  for (float v : notes) {
    fake::SetCv(marblesy::hal::CV_X_SPREAD, v);
    Run(30);
    fake::SetClock(1, true);
    Run(100);
    fake::SetClock(1, false);
    Run(30);
  }
  Press(kXExt);
  CHECK(!ui.recording_scale(), "stopped");
  CHECK(settings.scale(0).num_degrees == 3, "degrees %d",
        settings.scale(0).num_degrees);
  Run(6000);
  Reboot();
  CHECK(settings.scale(0).num_degrees == 3, "kept: %d",
        settings.scale(0).num_degrees);
}

void TestDsp() {
  // Marbles' DSP across its modes: outputs finite and in range, gates moving.
  int combinations = 0;
  for (int t_model = 0; t_model < 6; ++t_model) {
    for (int x_mode = 0; x_mode < 3; ++x_mode) {
      for (int clocks = 0; clocks < 3; ++clocks) {
        Boot();
        State* s = settings.mutable_state();
        s->t_model = t_model;
        s->x_control_mode = x_mode;
        s->t_range = (t_model + clocks) % 3;
        s->x_range = (x_mode + clocks) % 3;
        s->t_deja_vu = clocks % 3;
        s->x_deja_vu = (clocks + 1) % 3;
        // Y STEPS high enough to quantize, in every scale: the scales must
        // reach Y too.
        s->y_steps = static_cast<uint8_t>(120 + 45 * clocks + 5 * x_mode);
        s->y_divider = 255;
        s->x_scale = static_cast<uint8_t>((t_model + 2 * x_mode + clocks) % 6);
        fake::SetPot(marblesy::hal::POT_T_RATE, 0.7f);
        fake::SetPot(marblesy::hal::POT_X_SPREAD, 0.3f * x_mode + 0.2f);
        fake::SetPot(marblesy::hal::POT_X_STEPS, 0.5f * clocks);
        fake::SetPot(marblesy::hal::POT_T_JITTER, 0.3f * clocks);
        fake::SetCv(marblesy::hal::CV_X_BIAS, -2.0f + clocks * 2.0f);
        fake::PatchClock(0, clocks == 1);
        fake::PatchClock(1, clocks == 2);
        uint32_t toggles = 0;
        uint32_t previous = fake::Gates();
        float lo[4] = { 9, 9, 9, 9 }, hi[4] = { -9, -9, -9, -9 };
        bool finite = true;
        for (uint32_t i = 0; i < 32000 * 3; ++i) {
          fake::SetClock(0, (i % 3000) < 300);
          fake::SetClock(1, (i % 4100) < 400);
          fake::Tick();
          toggles += fake::Gates() != previous;
          previous = fake::Gates();
          for (int slot = 0; slot < 4; ++slot) {
            const float v = fake::OutputVolts(slot);
            finite = finite && isfinite(v);
            lo[slot] = fminf(lo[slot], v);
            hi[slot] = fmaxf(hi[slot], v);
          }
        }
        ++combinations;
        CHECK(finite, "model %d mode %d clocks %d: NaN", t_model, x_mode, clocks);
        CHECK(toggles > 4, "model %d mode %d clocks %d: gates %u",
              t_model, x_mode, clocks, toggles);
        for (int slot = 0; slot < 4; ++slot) {
          CHECK(lo[slot] >= -5.01f && hi[slot] <= 5.01f, "slot %d %.3f..%.3f",
                slot, lo[slot], hi[slot]);
        }
        CHECK(hi[0] - lo[0] > 0.05f, "model %d mode %d clocks %d: X1 still",
              t_model, x_mode, clocks);
      }
    }
  }
  CHECK(combinations == 54, "%d", combinations);
}

struct Group {
  const char* name;
  void (*fn)();
};

const Group groups[] = {
  { "cv", &TestCv },
  { "dac", &TestDac },
  { "outcal", &TestOutputCalibration },
  { "leds", &TestLeds },
  { "buttons", &TestButtons },
  { "io", &TestIo },
  { "storage", &TestStorage },
  { "settings", &TestSettings },
  { "dsp", &TestDsp },
};

}  // namespace

int main(int argc, char** argv) {
  for (const Group& g : groups) {
    bool run = argc < 2;
    for (int i = 1; i < argc; ++i) {
      run = run || strcmp(argv[i], g.name) == 0;
    }
    if (!run) {
      continue;
    }
    group = g.name;
    const int before_checks = checks;
    const int before_failures = failures;
    g.fn();
    printf("%-9s %5d checks, %d failed\n", g.name, checks - before_checks,
           failures - before_failures);
  }
  printf("%d checks, %d failed\n", checks, failures);
  return failures ? 1 : 0;
}
