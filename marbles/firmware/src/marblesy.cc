// Copyright 2015 Emilie Gillet.
// 
// Author: Emilie Gillet (emilie.o.gillet@gmail.com)
// 
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// 
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// 
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
// 
// See http://creativecommons.org/licenses/MIT/ for more information.

// -----------------------------------------------------------------------------
//
// Marblesy: Mutable Instruments Marbles on a Daisy Seed.
//
// Port of marbles/marbles.cc (Emilie Gillet, MIT licence) without its
// hardware set-up, which is in main.cc and hal_daisy.cc. Marbles fills its
// DAC one sample at a time from a 32 kHz interrupt, which also writes the
// gates, reads the clock inputs and, every 5 samples, takes the ADC readings,
// and it renders those blocks of 5 samples in its main loop. Here IoTick()
// is that interrupt (a 32 kHz timer), writing the two SPI DACs itself, and
// the main loop's work, Ui::DoEvents() and the rendering, moves into
// DspTick(), a low-priority interrupt that IoTick() pends at every block:
// the main loop is left to the flash writes, which take tens of
// milliseconds on the Seed's QSPI chip. IoTick() also shares the SPI bus
// with the panel: the LED shift registers every 4 samples, the buttons and
// Ui::Poll() (Marbles' 1 kHz SysTick) every 32. Process() and the rest are
// Marbles' code; the changes are marked.

#include "marblesy.h"

#include <algorithm>

#include "marbles/drivers/clock_inputs.h"
#include "marbles/drivers/dac.h"
#include "marbles/drivers/gate_outputs.h"
#include "marbles/drivers/leds.h"
#include "marbles/drivers/rng.h"
#include "marbles/drivers/switches.h"

#include "marbles/ramp/ramp_extractor.h"
#include "marbles/random/random_generator.h"
#include "marbles/random/random_stream.h"
#include "marbles/random/t_generator.h"
#include "marbles/random/x_y_generator.h"

#include "marbles/clock_self_patching_detector.h"
#include "marbles/cv_reader.h"
#include "marbles/io_buffer.h"
#include "marbles/note_filter.h"
#include "marbles/resources.h"
#include "marbles/scale_recorder.h"
#include "marbles/settings.h"
#include "marbles/ui.h"

#include "stmlib/dsp/dsp.h"
#include "stmlib/dsp/hysteresis_quantizer.h"
#include "stmlib/dsp/units.h"

#include "hal.h"
#include "output_calibrator.h"

#define PROFILE_INTERRUPT 0
#define PROFILE_RENDER 0

// Marbles' profiling pin (drivers/debug_pin.h), not wired here.
#define TIC
#define TOC

using namespace marbles;
using namespace std;
using namespace stmlib;

const bool test_adc_noise = false;

const int kSampleRate = 32000;
const int kGateDelay = 2;

ClockInputs clock_inputs;
ClockSelfPatchingDetector self_patching_detector[kNumGateOutputs];
CvReader cv_reader;
Dac dac;
GateOutputs gate_outputs;
HysteresisQuantizer2 deja_vu_length_quantizer;
IOBuffer io_buffer;
NoteFilter note_filter;
Rng rng;
ScaleRecorder scale_recorder;
Settings settings;
Ui ui;

RandomGenerator random_generator;
RandomStream random_stream;
TGenerator t_generator;
XYGenerator xy_generator;

namespace marblesy {

// The panel's share of the SPI bus, in samples.
const uint32_t kLedRefreshPeriod = 4;
const uint32_t kUiPollPeriod = 32;
const uint32_t kUiPollPhase = 2;  // never on an LED refresh
uint32_t io_counter;

uint8_t OutputLedLevel(float volts) {
  // Marbles drives each output LED from its jack, green for positive
  // voltages and red for negative, at a current in proportion to the
  // voltage. Marblesy's single green LEDs show the size of it, whatever the
  // sign: full brightness at 5 V.
  float x = fabsf(volts) / 5.0f;
  CONSTRAIN(x, 0.0f, 1.0f);
  return static_cast<uint8_t>(x * kOutputLedLevels + 0.5f);
}

// Marblesy: FillBuffer(), plus what Marbles' DAC driver and SysTick do.
void IoTick() {
  if (PROFILE_INTERRUPT) {
    TIC;
  }
  IOBuffer::Slice s = io_buffer.NextSlice(1);

  gate_outputs.Write(s);
  clock_inputs.Read(s, 1);

  if (io_buffer.new_block()) {
    cv_reader.Copy(&s.block->adc_value[0]);
    clock_inputs.ReadNormalization(s.block);
    hal::PendDsp();
  }

  if (rng.readable()) {
    random_stream.Write(rng.data());
  }

  uint16_t codes[kNumCvOutputs];
  for (size_t i = 0; i < kNumCvOutputs; ++i) {
    codes[i] = s.block->cv_output[i][s.frame_index];
  }
  dac.Write(codes);

  const uint32_t n = io_counter++;
  if (n % kUiPollPeriod == kUiPollPhase) {
    ui.Poll();
  }
  if (n % kLedRefreshPeriod == 0) {
    hal::WriteLeds(Leds::ShiftRegisterBits(n / kLedRefreshPeriod));
  }

  if (PROFILE_INTERRUPT) {
    TOC;
  }
}

}  // namespace marblesy

inline uint16_t DacCode(int index, float voltage) {
  CONSTRAIN(voltage, -5.0f, 5.0f);
  const float scale = settings.calibration_data().dac_scale[index];
  const float offset = settings.calibration_data().dac_offset[index];
  return ClipU16(static_cast<int32_t>(voltage * scale + offset));
}

void ProcessTest(IOBuffer::Block* block, size_t size) {
  float parameters[kNumParameters];
  GateFlags hidden_gates[kNumParameters];
  static float phase;
  cv_reader.Process(false, &block->adc_value[0], parameters, hidden_gates);
  for (size_t i = 0; i < size; ++i) {
    phase += 100.0f / static_cast<float>(kSampleRate);
    if (phase >= 1.0f) {
      phase -= 1.0f;
    }
    block->cv_output[0][i] = DacCode(
        0, 4.0 * Interpolate(lut_sine, phase, 256.0f));
    block->cv_output[1][i] = DacCode(
        1, -8.0f * phase + 4.0f);
    block->cv_output[2][i] = DacCode(
        2, (phase < 0.5f ? phase : 1.0f - phase) * 16.0f - 4.0f);
    block->cv_output[3][i] = DacCode(
        3, phase < 0.5f ? -4.0f : 4.0f);

    for (int j = 0; j < 4; ++j) {
      uint16_t dac_code = ui.output_test_forced_dac_code(j);
      if (dac_code) {
        block->cv_output[j][i] = dac_code;
      }
    }
    
    block->gate_output[0][i] = block->input_patched[0]
        ? block->input[0][i]
        : phase < 0.2f;
    block->gate_output[1][i] = phase < 0.5f;
    block->gate_output[2][i] = block->input_patched[1]
        ? block->input[1][i]
        : phase < 0.8f;
  }
}

Ratio y_divider_ratios[] = {
  { 1, 64 },
  { 1, 48 },
  { 1, 32 },
  { 1, 24 },
  { 1, 16 },
  { 1, 12 },
  { 1, 8 },
  { 1, 6 },
  { 1, 4 },
  { 1, 3 },
  { 1, 2 },
  { 1, 1 },
};

int loop_length[] = {
  1,
  2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2,
  3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
  4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
  5, 5, 5, 5,
  6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 6,
  7, 7,
  8, 8, 8, 8, 8, 8, 8, 8, 8,
  10, 10, 10,
  12, 12, 12, 12, 12, 12, 12,
  14, 14,
  16
};
GateFlags hidden_gates[kNumParameters];
float parameters[kNumParameters];
float ramp_buffer[kBlockSize * 4];
bool gates[kBlockSize * 2];
float voltages[kBlockSize * 4];
Ramps ramps;
GroupSettings x, y;
bool gate_delay_tail[kNumGateOutputs][kGateDelay];

float SineOscillator(float voltage) {
  static float phase = 0.0f;
  CONSTRAIN(voltage, -5.0f, 5.0f);
  float frequency = stmlib::SemitonesToRatio(voltage * 12.0f) * 220.0f / kSampleRate;
  phase += frequency;
  if (phase >= 1.0f) {
    phase -= 1.0f;
  }
  return 5.0f * Interpolate(lut_sine, phase, 256.0f);
}

void Process(IOBuffer::Block* block, size_t size) {
  if (PROFILE_RENDER) {
    TIC;
  }

  // Filter CV values (3.5%)
  cv_reader.Process(
      settings.explicit_reset(),
      &block->adc_value[0],
      parameters,
      hidden_gates);
  
  float deja_vu = parameters[ADC_CHANNEL_DEJA_VU_AMOUNT];
  
  //  Deadband near 12 o'clock for the deja vu parameter.
  const float d = fabsf(deja_vu - 0.5f);
  if (d > 0.03f) {
    ui.set_deja_vu_lock(false);
  } else if (d < 0.02f) {
    ui.set_deja_vu_lock(true);
  }
  if (deja_vu < 0.47f) {
    deja_vu *= 1.06382978723f;
  } else if (deja_vu > 0.53f) {
    deja_vu = 0.5f + (deja_vu - 0.53f) * 1.06382978723f;
  } else {
    deja_vu = 0.5f;
  }
  
  GateFlags* t_clock = block->input[0];
  GateFlags* xy_clock = block->input[1];
  
  // Determine the clock source for the XY section (2%)
  ClockSource xy_clock_source = CLOCK_SOURCE_INTERNAL_T1_T2_T3;
  if (block->input_patched[1]) {
    xy_clock_source = CLOCK_SOURCE_EXTERNAL;
    size_t best_score = 8;
    for (size_t i = 0; i < kNumGateOutputs; ++i) {
      size_t score = self_patching_detector[i].Process(block, size);
      if (score >= best_score) {
        xy_clock_source = ClockSource(CLOCK_SOURCE_INTERNAL_T1 + i);
        best_score = score;
      }
    }
  }
  
  // Generate gates for T-section (16%).
  ramps.master = &ramp_buffer[0];
  ramps.external = &ramp_buffer[kBlockSize];
  ramps.slave[0] = &ramp_buffer[kBlockSize * 2];
  ramps.slave[1] = &ramp_buffer[kBlockSize * 3];
  
  const State& state = settings.state();
  int deja_vu_length = deja_vu_length_quantizer.Lookup(
      loop_length,
      parameters[ADC_CHANNEL_DEJA_VU_LENGTH]);
  
  bool t_section_reset = settings.explicit_reset() && \
      hidden_gates[ADC_CHANNEL_T_JITTER] & GATE_FLAG_RISING;
  
  t_generator.set_model(TGeneratorModel(state.t_model));
  t_generator.set_range(TGeneratorRange(state.t_range));
  t_generator.set_rate(parameters[ADC_CHANNEL_T_RATE]);
  t_generator.set_bias(parameters[ADC_CHANNEL_T_BIAS]);
  t_generator.set_jitter(parameters[ADC_CHANNEL_T_JITTER]);
  t_generator.set_deja_vu(
      state.t_deja_vu == DEJA_VU_LOCKED
          ? 0.5f
          : (state.t_deja_vu == DEJA_VU_ON ? deja_vu : 0.0f));
  t_generator.set_length(deja_vu_length);
  t_generator.set_pulse_width_mean(float(state.t_pulse_width_mean) / 256.0f);
  t_generator.set_pulse_width_std(float(state.t_pulse_width_std) / 256.0f);
  t_generator.Process(
      block->input_patched[0],
      &t_section_reset,
      t_clock,
      ramps,
      gates,
      size);

  // Generate voltages for X-section (40%).
  float note_cv_1 = cv_reader.channel(ADC_CHANNEL_X_SPREAD).scaled_raw_cv();
  float note_cv_2 = cv_reader.channel(ADC_CHANNEL_X_SPREAD_2).scaled_raw_cv();
  float note_cv = 0.5f * (note_cv_1 + note_cv_2);
  float u = note_filter.Process(0.5f * (note_cv + 1.0f));
  
  if (test_adc_noise) {
    static float note_lp = 0.0f;
    float note = note_cv_1;
    ONE_POLE(note_lp, note, 0.0001f);
    float cents = (note - note_lp) * 1200.0f * 5.0f;
    fill(&voltages[0], &voltages[4 * size], cents);
  } else if (ui.recording_scale()) {
    float voltage = (u - 0.5f) * 10.0f;
    for (size_t i = 0; i < size; ++i) {
      GateFlags gate = block->input_patched[1]
          ? block->input[1][i]
          : GATE_FLAG_LOW;
      if (gate & GATE_FLAG_RISING) {
        scale_recorder.NewNote(voltage);
      }
      if (gate & GATE_FLAG_HIGH) {
        scale_recorder.UpdateVoltage(voltage);
      }
      if (gate & GATE_FLAG_FALLING) {
        scale_recorder.AcceptNote();
      }
    }
    fill(&voltages[0], &voltages[4 * size], voltage);
  } else {
    x.control_mode = ControlMode(state.x_control_mode);
    x.voltage_range = VoltageRange(state.x_range % 3);
    x.register_mode = state.x_register_mode;
    x.register_value = u;
    cv_reader.set_attenuverter(
        ADC_CHANNEL_X_SPREAD, state.x_register_mode ? 0.5f : 1.0f);
  
    x.spread = parameters[ADC_CHANNEL_X_SPREAD];
    x.bias = parameters[ADC_CHANNEL_X_BIAS];
    x.steps = parameters[ADC_CHANNEL_X_STEPS];
    x.deja_vu = state.x_deja_vu == DEJA_VU_LOCKED
        ? 0.5f
        : (state.x_deja_vu == DEJA_VU_ON ? deja_vu : 0.0f);
    x.length = deja_vu_length;
    x.ratio.p = 1;
    x.ratio.q = 1;
  
    y.control_mode = CONTROL_MODE_IDENTICAL;
    y.voltage_range = VoltageRange(state.y_range);
    y.register_mode = false;
    y.register_value = 0.0f;
    y.spread = float(state.y_spread) / 256.0f;
    y.bias = float(state.y_bias) / 256.0f;
    y.steps = float(state.y_steps) / 256.0f;
    y.deja_vu = 0.0f;
    y.length = 1;
    y.ratio = y_divider_ratios[
        static_cast<uint16_t>(state.y_divider) * 12 >> 8];
    
    if (settings.dirty_scale_index() != -1) {
      int i = settings.dirty_scale_index();
      xy_generator.LoadScale(i, settings.persistent_data().scale[i]);
      // Marblesy: Y's too (see Init()).
      xy_generator.LoadScale(kNumXChannels, i, settings.persistent_data().scale[i]);
      settings.set_dirty_scale_index(-1);
    }
    
    y.scale_index = x.scale_index = state.x_scale;
    
    bool x_section_reset = settings.explicit_reset() && \
        hidden_gates[ADC_CHANNEL_X_STEPS] & GATE_FLAG_RISING;
    if (xy_clock_source != CLOCK_SOURCE_EXTERNAL) {
      x_section_reset |= t_section_reset;
    }

    xy_generator.Process(
        xy_clock_source,
        x,
        y,
        &x_section_reset,
        xy_clock,
        ramps,
        voltages,
        size);
  }
  
  const float* v = voltages;
  const bool* g = gates;
  for (size_t i = 0; i < size; ++i) {
    //block->cv_output[1][i] = DacCode(1, SineOscillator(*v++));
    block->cv_output[1][i] = DacCode(1, *v++);
    block->cv_output[2][i] = DacCode(2, *v++);
    block->cv_output[3][i] = DacCode(3, *v++);
    block->cv_output[0][i] = DacCode(0, *v++);
    block->gate_output[0][i + kGateDelay] = *g++;
    block->gate_output[1][i + kGateDelay] = ramps.master[i] < 0.5f;
    block->gate_output[2][i + kGateDelay] = *g++;
  }
  
  for (size_t i = 0; i < kNumGateOutputs; ++i) {
    for (size_t j = 0; j < kGateDelay; ++j) {
      block->gate_output[i][j] = gate_delay_tail[i][j];
      gate_delay_tail[i][j] = block->gate_output[i][size + j];
    }
  }
  
  // Marblesy: the output LEDs show the last voltage of the block (X1, X2,
  // X3 and Y, written to DAC channels 1, 2, 3 and 0 above).
  const float* last = &voltages[4 * (size - 1)];
  ui.set_output_level(0, marblesy::OutputLedLevel(last[3]));
  for (size_t i = 0; i < 3; ++i) {
    ui.set_output_level(i + 1, marblesy::OutputLedLevel(last[i]));
  }
  
  if (PROFILE_RENDER) {
    TOC;
  }
}

// Marblesy: the output calibration. All outputs at 0 V but the one being
// measured, the gates low, the CV inputs read as usual.
void ProcessOutputCalibration(IOBuffer::Block* block, size_t size) {
  float parameters[kNumParameters];
  GateFlags hidden_gates[kNumParameters];
  cv_reader.Process(false, &block->adc_value[0], parameters, hidden_gates);
  marblesy::OutputCalibrator* calibrator = ui.mutable_output_calibrator();
  calibrator->Process(
      cv_reader.channel(ADC_CHANNEL_X_SPREAD).scaled_raw_cv());
  for (size_t i = 0; i < kNumCvOutputs; ++i) {
    fill(&block->cv_output[i][0], &block->cv_output[i][size],
         calibrator->code(i));
  }
  for (size_t i = 0; i < kNumGateOutputs; ++i) {
    fill(&block->gate_output[i][0], &block->gate_output[i][size + kGateDelay],
         false);
    fill(&gate_delay_tail[i][0], &gate_delay_tail[i][kGateDelay], false);
  }
}

namespace marblesy {

void Init() {
  settings.Init();

  clock_inputs.Init();
  dac.Init();
  rng.Init();
  note_filter.Init();
  gate_outputs.Init();
  io_buffer.Init();

  deja_vu_length_quantizer.Init(
      sizeof(loop_length) / sizeof(int), 0.25f, false);
  cv_reader.Init(settings.mutable_calibration_data());
  scale_recorder.Init();

  // Marblesy: the CV reader's filters start at 0, so for the first 50 ms
  // or so every knob seems to move, and a button held at power-up (the
  // colour-blind gesture) reads as a hidden-setting edit. Settle them on
  // the readings first (0.99 ^ 1000: the knobs' filters are within 1e-4).
  {
    uint16_t adc_values[kNumParameters * 2];
    float settled[kNumParameters];
    GateFlags settled_gates[kNumParameters];
    for (int i = 0; i < 1000; ++i) {
      cv_reader.Copy(&adc_values[0]);
      cv_reader.Process(false, &adc_values[0], settled, settled_gates);
    }
  }

  ui.Init(&settings, &cv_reader, &scale_recorder, &clock_inputs);

  random_generator.Init(1);
  random_stream.Init(&random_generator);
  t_generator.Init(&random_stream, static_cast<float>(kSampleRate));
  xy_generator.Init(&random_stream, static_cast<float>(kSampleRate));

  for (size_t i = 0; i < kNumScales; ++i) {
    xy_generator.LoadScale(i, settings.persistent_data().scale[i]);
    // Marblesy: Y quantizes to the same scale (Process() gives it
    // x_scale), but XYGenerator::LoadScale() only fills X1..X3. Y's
    // quantizers kept a one-note scale with no note above the lowest
    // threshold, and Y STEPS past about 60 % then read voltage_[255] of a
    // 16-entry array.
    xy_generator.LoadScale(kNumXChannels, i, settings.persistent_data().scale[i]);
  }

  for (size_t i = 0; i < kNumGateOutputs; ++i) {
    self_patching_detector[i].Init(i);
  }

  // Marblesy: the outputs go to 0 V at once, and the first block played,
  // never rendered, holds 0 V too instead of code 0 (+5.3 V).
  uint16_t codes[kNumCvOutputs];
  for (size_t i = 0; i < kNumCvOutputs; ++i) {
    codes[i] = DacCode(i, 0.0f);
  }
  dac.Write(codes);
  for (size_t i = 0; i < kNumBlocks * kBlockSize; ++i) {
    IOBuffer::Slice s = io_buffer.NextSlice(1);
    for (size_t j = 0; j < kNumCvOutputs; ++j) {
      s.block->cv_output[j][s.frame_index] = codes[j];
    }
  }
  io_buffer.Init();
  io_counter = 0;

  // Marbles' main loop renders the second block before the DAC starts.
  DspTick();
}

void DspTick() {
  hal::FeedWatchdog();
  ui.DoEvents();
  io_buffer.Process(
      ui.calibrating_outputs()
          ? &ProcessOutputCalibration
          : (ui.output_test_mode() ? &ProcessTest : &Process));
}

void Persist() {
  settings.Persist();
}

bool BootloaderGesture() {
  for (int reading = 0; reading < 3; ++reading) {
    if (reading) {
      hal::Delay(10);
    }
    const uint8_t buttons = hal::ReadButtons();
    if (!Switches::Plausible(buttons)) {
      return false;  // a 74HC165 that does not answer
    }
    for (int s = 0; s < SWITCH_LAST; ++s) {
      const bool pressed = !Switches::Level(buttons, Switch(s));
      if (pressed != (s == SWITCH_T_DEJA_VU)) {
        return false;
      }
    }
  }
  return true;
}

}  // namespace marblesy
