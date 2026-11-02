// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy host tests: a model of the board behind hal.h (see hal_fake.h).

#include "hal_fake.h"

#include <math.h>
#include <string.h>

#include <random>

#include "board_tables.h"

namespace {

using namespace marblesy::hal;

const float kSupply = 3.3f;  // 3V3A: ADC reference, bias divider, pots
const uint32_t kFlashBytes = 0x20000;

fake::Parts parts;
float cv_volts[CV_INPUT_LAST];
int cv_patch[CV_INPUT_LAST];
float pot_position[POT_LAST];
float adc_noise;
std::mt19937 noise_generator(1);
bool clock_patched[2];
bool clock_high[2];
uint8_t buttons;  // pressed, by 74HC165 input
bool probe;
uint32_t gates;
uint16_t dac_words[4];
uint32_t dac_writes;
uint16_t led_bits;
uint32_t led_writes;
uint32_t button_reads;
uint32_t rng_state;

Callback io_callback;
Callback dsp_callback;
bool dsp_pending;
uint32_t ticks;
uint32_t extra_ms;
uint32_t dsp_runs;
uint32_t watchdog_feeds;
bool bootloader;

uint8_t flash[kFlashBytes];
uint32_t flash_erases;
uint32_t flash_writes;
int operations_left;
bool power_cut;
bool buttons_dead;
int failing_operations;

uint16_t AdcReading(float volts) {
  float x = volts / kSupply;
  if (adc_noise > 0.0f) {
    std::normal_distribution<float> n(0.0f, adc_noise / 65536.0f);
    x += n(noise_generator);
  }
  if (x < 0.0f) {
    x = 0.0f;
  }
  if (x > 1.0f) {
    x = 1.0f;
  }
  return static_cast<uint16_t>(x * 65535.0f + 0.5f);
}

// Whether the next flash operation runs, and whether it is the one the
// power cut interrupts half way.
bool FlashOperation(bool* interrupted) {
  *interrupted = false;
  if (power_cut) {
    return false;
  }
  if (failing_operations > 0) {
    --failing_operations;
    return false;
  }
  if (operations_left >= 0) {
    if (operations_left == 0) {
      power_cut = true;
      *interrupted = true;
      return true;
    }
    --operations_left;
  }
  return true;
}

}  // namespace

namespace fake {

void NominalParts() {
  memset(&parts, 0, sizeof(parts));
}

void SetParts(const Parts& p) {
  parts = p;
}

void Reboot() {
  NominalParts();
  for (int i = 0; i < CV_INPUT_LAST; ++i) {
    cv_volts[i] = 0.0f;
    cv_patch[i] = -1;
  }
  for (int i = 0; i < POT_LAST; ++i) {
    pot_position[i] = 0.5f;
  }
  adc_noise = 0.0f;
  noise_generator.seed(1);
  clock_patched[0] = clock_patched[1] = false;
  clock_high[0] = clock_high[1] = false;
  buttons = 0;
  probe = false;
  gates = 0;
  memset(dac_words, 0, sizeof(dac_words));
  dac_writes = 0;
  led_bits = 0;
  led_writes = 0;
  button_reads = 0;
  rng_state = 12345;
  io_callback = nullptr;
  dsp_callback = nullptr;
  dsp_pending = false;
  ticks = 0;
  extra_ms = 0;
  dsp_runs = 0;
  watchdog_feeds = 0;
  bootloader = false;
  flash_erases = 0;
  flash_writes = 0;
  operations_left = -1;
  power_cut = false;
  buttons_dead = false;
  failing_operations = 0;
}

void Reset() {
  Reboot();
  memset(flash, 0xff, sizeof(flash));
}

void SetCv(CvInput input, float volts) { cv_volts[input] = volts; }
void SetPot(Pot pot, float position) { pot_position[pot] = position; }
void SetAdcNoise(float lsb_rms) { adc_noise = lsb_rms; }
void PatchOutput(CvInput input, int slot) { cv_patch[input] = slot; }
void PatchClock(int input, bool patched) { clock_patched[input] = patched; }
void SetClock(int input, bool high) { clock_high[input] = high; }

void SetButton(int input, bool pressed) {
  if (pressed) {
    buttons |= 1 << input;
  } else {
    buttons &= ~(1 << input);
  }
}

void ReleaseAllButtons() { buttons = 0; }

float OutputVolts(int slot) {
  return OutputVoltsFor(slot, dac_words[slot]);
}

float OutputVoltsFor(int slot, uint16_t word) {
  const bool b = word & 0x8000;
  if (b != (slot & 1)) {
    return NAN;  // the word was for the other DAC of that chip
  }
  const float vref = board::kReference * (1.0f + parts.vref);
  float dac = 0.0f;
  if (word & 0x1000) {  // active; shut down, the output stage sees 0 V
    const float gain = (word & 0x2000) ? 1.0f : 2.0f;
    dac = vref * gain * (1.0f + parts.dac_gain[slot]) * \
        static_cast<float>(word & 0xfff) / 4096.0f + parts.dac_offset[slot];
  }
  const float rin = board::kDacInputResistor * (1.0f + parts.dac_rin[slot]);
  const float rref = board::kDacOffsetResistor * (1.0f + parts.dac_rref[slot]);
  const float rf = board::kDacFeedbackResistor * (1.0f + parts.dac_rf[slot]);
  // The -2.5 V the offset resistor sees: the reference through the
  // inverter (R42, R43).
  const float negative_reference = -vref * board::kInverterFeedback / \
      board::kInverterInput;
  return -rf / rref * negative_reference - rf / rin * dac;
}

float LoadedOutputVoltsFor(int slot, uint16_t word) {
  const float rout = board::kOutputResistor * (1.0f + parts.dac_rout[slot]);
  const float rload = 100.0e3f;
  return OutputVoltsFor(slot, word) * rload / (rload + rout);
}

void SetButtonsDead(bool dead) { buttons_dead = dead; }
void FailFlashOperations(int operations) { failing_operations = operations; }

uint16_t DacWord(int slot) { return dac_words[slot]; }
uint32_t DacWrites() { return dac_writes; }
uint32_t Gates() { return gates; }
uint16_t LedBits() { return led_bits; }
uint32_t LedWrites() { return led_writes; }
uint32_t ButtonReads() { return button_reads; }
bool Probe() { return probe; }

void Tick() {
  if (io_callback) {
    io_callback();
    ++ticks;
  }
  if (dsp_pending && dsp_callback) {
    dsp_pending = false;
    ++dsp_runs;
    dsp_callback();
  }
}

void Run(uint32_t n) {
  while (n--) {
    Tick();
  }
}

void RunMilliseconds(uint32_t ms) {
  Run(ms * (kIoRate / 1000));
}

bool InterruptsStarted() { return io_callback != nullptr; }
uint32_t DspRuns() { return dsp_runs; }
uint32_t WatchdogFeeds() { return watchdog_feeds; }
bool BootloaderRequested() { return bootloader; }
void AdvanceTime(uint32_t ms) { extra_ms += ms; }

uint8_t* Flash() { return flash; }
uint32_t FlashSize() { return kFlashBytes; }
uint32_t FlashErases() { return flash_erases; }
uint32_t FlashWrites() { return flash_writes; }

void CutPowerAfter(int operations) {
  operations_left = operations;
  power_cut = false;
}

bool PowerCut() { return power_cut; }

}  // namespace fake

namespace marblesy {
namespace hal {

void Init(daisy::DaisySeed* seed) { }

uint32_t Milliseconds() {
  return ticks / (kIoRate / 1000) + extra_ms;
}

void Delay(uint32_t ms) { extra_ms += ms; }

void StartInterrupts(Callback io, Callback dsp) {
  io_callback = io;
  dsp_callback = dsp;
}

void PendDsp() { dsp_pending = true; }

void StartWatchdog() { }
void FeedWatchdog() { ++watchdog_feeds; }

void InitAdc() { }

uint16_t ReadCv(CvInput input) {
  const float rin = board::kCvInputResistor * (1.0f + parts.cv_rin[input]);
  const float rf = board::kCvFeedbackResistor * (1.0f + parts.cv_rf[input]);
  const float bias = kSupply * board::kBiasRatio * (1.0f + parts.cv_bias);
  float volts = cv_volts[input];
  const int slot = cv_patch[input];
  if (slot >= 0) {
    // An output through its 1k into this input's Rin, whose far end sits
    // at the bias (the op-amp's virtual earth).
    const float rout = board::kOutputResistor * (1.0f + parts.dac_rout[slot]);
    const float source = fake::OutputVolts(slot);
    volts = source - (source - bias) * rout / (rout + rin);
  }
  return AdcReading(bias * (1.0f + rf / rin) - volts * rf / rin);
}

uint16_t ReadPot(Pot pot) {
  return AdcReading(pot_position[pot] * kSupply);
}

void InitGpio() { }

uint32_t ReadClockPins() {
  uint32_t pins = 0;
  for (int i = 0; i < 2; ++i) {
    // The jack's tip into an inverting transistor stage: unpatched, the
    // switch lug feeds it the probe.
    const bool high = clock_patched[i] ? clock_high[i] : probe;
    if (!high) {
      pins |= 1 << i;
    }
  }
  return pins;
}

void WriteProbe(bool high) { probe = high; }
void WriteGates(uint32_t g) { gates = g; }

void InitBus() { }

void WriteDacs(const uint16_t words[4]) {
  memcpy(dac_words, words, sizeof(dac_words));
  ++dac_writes;
}

void WriteLeds(uint16_t bits) {
  led_bits = bits;
  ++led_writes;
}

uint8_t ReadButtons() {
  ++button_reads;
  if (buttons_dead) {
    return 0;
  }
  return static_cast<uint8_t>(~buttons) & 0x7f;  // D7 is tied low
}

void InitRng() { }
bool RngReady() { return true; }

uint32_t RngData() {
  rng_state = rng_state * 1664525u + 1013904223u;
  return rng_state;
}

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  memcpy(destination, &flash[offset], size);
}

bool FlashErase(uint32_t offset, uint32_t size) {
  if (offset % kFlashSectorSize || size != kFlashSectorSize ||
      offset + size > kFlashBytes) {
    return false;
  }
  bool interrupted;
  if (!FlashOperation(&interrupted)) {
    return false;
  }
  ++flash_erases;
  memset(&flash[offset], 0xff, interrupted ? size / 2 : size);
  return !interrupted;
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  if (offset + size > kFlashBytes) {
    return false;
  }
  bool interrupted;
  if (!FlashOperation(&interrupted)) {
    return false;
  }
  ++flash_writes;
  const uint8_t* p = static_cast<const uint8_t*>(data);
  const uint32_t n = interrupted ? size / 2 : size;
  for (uint32_t i = 0; i < n; ++i) {
    flash[offset + i] &= p[i];  // NOR: a write only clears bits
  }
  return !interrupted;
}

uint32_t EnterCritical() { return 0; }
void ExitCritical(uint32_t state) { }

void ResetToBootloader() { bootloader = true; }

}  // namespace hal
}  // namespace marblesy
