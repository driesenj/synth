// Plaitsy host tests: plaitsy::hal on a model of the board (see hal_fake.h).

#include "hal_fake.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include <algorithm>

#include "board_tables.h"
#include "hal.h"

namespace fake {

using plaitsy::hal::Button;

namespace {

double g_now = 0.0;
bool g_in_interrupt = false;

struct Jack {
  bool patched;
  std::function<double(double)> volts;
};
Jack g_jacks[plaitsy::hal::ADC_INPUT_LAST];
double g_bias_error[plaitsy::hal::ADC_INPUT_LAST];
double g_gain_error[plaitsy::hal::ADC_INPUT_LAST];
double g_latency = 0.0;
std::function<double(double)> g_latency_function;
double g_adc_noise = 0.0;
double g_pot_noise = 0.0;
uint64_t g_rng = 0x9e3779b97f4a7c15ull;

struct ProbeEvent {
  double t;
  bool level;
};
std::vector<ProbeEvent> g_probe;
bool g_probe_init = false;
int g_probe_writes = 0;
double g_probe_delay = 5.0;

double g_mux[8];

bool g_buttons_init = false;
bool g_button[2];
double g_button_edge[2] = { -1e12, -1e12 };
double g_bounce = 0.0;

bool g_leds_init = false;
uint16_t g_led_written = 0;
uint16_t g_led_bits = 0;
uint16_t g_led_latched = 0;
bool g_led_pending = false;
int g_led_frames = 0;
bool g_button_led[2];
int g_button_led_writes = 0;

uint8_t g_flash[kFlashSize];
FlashStats g_stats;
bool g_power_armed = false;
long g_ops_left = 0;
EraseInterruption g_style = ERASE_PREFIX;
uint64_t g_power_rng = 1;
bool g_power_lost = false;
long g_ops = 0;

int g_critical_depth = 0;
int g_critical_max = 0;
bool g_adc_started = false;
int g_adc_inits = 0;
int g_hal_violations = 0;
std::vector<std::string> g_hal_log;

uint64_t Next(uint64_t* state) {
  uint64_t x = *state;
  x ^= x << 13;
  x ^= x >> 7;
  x ^= x << 17;
  *state = x;
  return x;
}

double Uniform(uint64_t* state) {
  return static_cast<double>(Next(state) >> 11) * (1.0 / 9007199254740992.0);
}

double Gauss(uint64_t* state) {
  double u1 = std::max(Uniform(state), 1e-300);
  double u2 = Uniform(state);
  return sqrt(-2.0 * log(u1)) * cos(2.0 * M_PI * u2);
}

void Log(std::vector<std::string>* log, int* count, const char* format, ...) {
  char text[256];
  va_list args;
  va_start(args, format);
  vsnprintf(text, sizeof(text), format, args);
  va_end(args);
  ++*count;
  if (log->size() < 50) {
    log->push_back(text);
  }
}

#define HAL_VIOLATION(...) Log(&g_hal_log, &g_hal_violations, __VA_ARGS__)
#define FLASH_VIOLATION(...) \
  Log(&g_stats.violation_log, &g_stats.violations, __VA_ARGS__)

bool FlashRangeOk(const char* what, uint32_t offset, uint32_t size) {
  if (g_in_interrupt) {
    FLASH_VIOLATION("%s(0x%x, %u) from the audio callback", what, offset, size);
  }
  if (offset >= kFlashSize || size > kFlashSize - offset) {
    FLASH_VIOLATION(
        "%s(0x%x, %u) reaches past 0x%x (the program area)",
        what, offset, size, kFlashSize);
    return false;
  }
  return true;
}

}  // namespace

// ------------------------------------------------------------------ time
void SetTimeUs(double t) { g_now = t; }
double TimeUs() { return g_now; }
void SetInInterrupt(bool in_interrupt) { g_in_interrupt = in_interrupt; }

void ResetBoard() {
  for (int i = 0; i < plaitsy::hal::ADC_INPUT_LAST; ++i) {
    g_jacks[i].patched = false;
    g_jacks[i].volts = nullptr;
    g_bias_error[i] = 0.0;
    g_gain_error[i] = 0.0;
  }
  g_latency = 0.0;
  g_latency_function = nullptr;
  g_adc_noise = 0.0;
  g_pot_noise = 0.0;
  g_probe.clear();
  g_probe_init = false;
  g_probe_writes = 0;
  g_probe_delay = 5.0;
  for (int i = 0; i < 8; ++i) {
    g_mux[i] = 0.5;
  }
  g_mux[7] = 0.0;  // grounded
  g_button[0] = g_button[1] = false;
  g_button_edge[0] = g_button_edge[1] = -1e12;
  g_bounce = 0.0;
  g_led_written = g_led_bits = g_led_latched = 0;
  g_led_pending = false;
  g_led_frames = 0;
  g_button_led[0] = g_button_led[1] = false;
  g_button_led_writes = 0;
  g_critical_depth = 0;
  g_critical_max = 0;
  g_hal_violations = 0;
  g_hal_log.clear();
  g_in_interrupt = false;
}

// ------------------------------------------------------------------ CV
Stage StageOf(AdcInput input) {
  Stage s;
  s.g = board::kStageRf[input] / board::kStageRin[input] *
      (1.0 + g_gain_error[input]);
  s.bias = kVdd * board::kBiasBottom[input] /
      (board::kBiasTop[input] + board::kBiasBottom[input]) *
      (1.0 + g_bias_error[input]);
  s.v0 = s.bias * (1.0 + s.g);
  return s;
}

void SetBiasError(AdcInput input, double relative) {
  g_bias_error[input] = relative;
}

void SetGainError(AdcInput input, double relative) {
  g_gain_error[input] = relative;
}

void Unpatch(AdcInput input) {
  g_jacks[input].patched = false;
  g_jacks[input].volts = nullptr;
}

void UnpatchAll() {
  for (int i = 0; i < plaitsy::hal::ADC_INPUT_LAST; ++i) {
    Unpatch(AdcInput(i));
  }
}

void Patch(AdcInput input, double volts) {
  PatchFunction(input, [volts](double) { return volts; });
}

void PatchFunction(AdcInput input, std::function<double(double)> volts) {
  g_jacks[input].patched = true;
  g_jacks[input].volts = volts;
}

bool patched(AdcInput input) { return g_jacks[input].patched; }

double TipVoltage(AdcInput input, double t_us) {
  const Jack& jack = g_jacks[input];
  if (jack.patched) {
    return jack.volts(t_us);
  }
  const Stage s = StageOf(input);
  if (board::kNormalized[input]) {
    // Probe pin --Rp-- lug/tip --Rin-- virtual ground at the bias.
    const double vp = ProbeAt(t_us) ? kVdd : 0.0;
    const double rin = board::kStageRin[input];
    const double rp = board::kProbeR[input];
    return (vp * rin + s.bias * rp) / (rin + rp);
  }
  if (board::kLugGrounded[input]) {
    return 0.0;
  }
  return s.bias;  // open lug: the tip floats at the virtual ground
}

static double Code(AdcInput input, double v_tip) {
  const Stage s = StageOf(input);
  return (s.v0 - s.g * v_tip) / kVdd * 65536.0;
}

static uint16_t Quantize(double code) {
  code = floor(code + 0.5);
  if (code < 0.0) code = 0.0;
  if (code > 65535.0) code = 65535.0;
  return static_cast<uint16_t>(code);
}

uint16_t RawFor(AdcInput input, double v_tip) {
  return Quantize(Code(input, v_tip));
}

void SetAdcLatencyUs(double latency) { g_latency = latency; }
void SetAdcLatencyFunction(std::function<double(double)> latency) {
  g_latency_function = latency;
}
void SetAdcNoiseLsb(double sigma) { g_adc_noise = sigma; }
void SetPotNoiseLsb(double sigma) { g_pot_noise = sigma; }
void SeedNoise(uint64_t seed) { g_rng = seed ? seed : 1; }

// ------------------------------------------------------------------ probe
bool ProbeAt(double t_us) {
  for (size_t i = g_probe.size(); i-- > 0; ) {
    if (g_probe[i].t <= t_us) {
      return g_probe[i].level;
    }
  }
  return false;
}

void SetProbeWriteDelayUs(double delay) { g_probe_delay = delay; }
int probe_writes() { return g_probe_writes; }
bool probe_initialized() { return g_probe_init; }

// ------------------------------------------------------------------ pots
void SetMuxChannel(int channel, double fraction) { g_mux[channel] = fraction; }
double mux_channel(int channel) { return g_mux[channel]; }

// ------------------------------------------------------------------ buttons
void SetButton(Button button, bool pressed) {
  if (g_button[button] != pressed) {
    g_button[button] = pressed;
    g_button_edge[button] = g_now;
  }
}

void SetButtonBounceUs(double bounce) { g_bounce = bounce; }

// ------------------------------------------------------------------ LEDs
uint16_t led_word_written() { return g_led_written; }
uint16_t led_word_latched() { return g_led_latched; }
int led_frames_shifted() { return g_led_frames; }
bool button_led(int index) { return g_button_led[index]; }
int button_led_writes() { return g_button_led_writes; }

// ------------------------------------------------------------------ flash
uint8_t* flash() { return g_flash; }
void FlashFill(uint8_t value) { memset(g_flash, value, sizeof(g_flash)); }

void FlashFillRandom(uint64_t seed) {
  uint64_t state = seed ? seed : 1;
  for (uint32_t i = 0; i < kFlashSize; ++i) {
    g_flash[i] = static_cast<uint8_t>(Next(&state) >> 24);
  }
}

FlashStats& flash_stats() { return g_stats; }

void ResetFlashStats() {
  memset(g_stats.erases, 0, sizeof(g_stats.erases));
  g_stats.erase_calls = g_stats.write_calls = g_stats.read_calls = 0;
  g_stats.bytes_programmed = 0;
  g_stats.violations = 0;
  g_stats.violation_log.clear();
  g_ops = 0;
}

void ArmPowerLoss(long ops, EraseInterruption style, uint64_t seed) {
  g_power_armed = true;
  g_ops_left = ops;
  g_style = style;
  g_power_rng = seed ? seed : 1;
}

void DisarmPowerLoss() { g_power_armed = false; }
bool power_lost() { return g_power_lost; }

void PowerOn() {
  g_power_lost = false;
  g_power_armed = false;
}

long flash_ops() { return g_ops; }

// ------------------------------------------------------------------ misc
int critical_depth() { return g_critical_depth; }
int critical_max_depth() { return g_critical_max; }
int adc_init_calls() { return g_adc_inits; }
int hal_violations() { return g_hal_violations; }
std::vector<std::string>& hal_violation_log() { return g_hal_log; }

}  // namespace fake

// ====================================================================== HAL

namespace plaitsy {
namespace hal {

using namespace fake;

void Init(daisy::DaisySeed* seed) { (void)seed; }

uint32_t Milliseconds() { return static_cast<uint32_t>(g_now / 1000.0); }

void StartWatchdog() { }
void FeedWatchdog() { }

void Service() {
  if (!g_led_pending) {
    return;
  }
  g_led_pending = false;
  g_led_latched = g_led_bits;
  ++g_led_frames;
}

void InitAdc() {
  ++g_adc_inits;
  g_adc_started = true;
}

uint16_t ReadAdc(AdcInput input) {
  if (input < 0 || input >= ADC_INPUT_LAST) {
    HAL_VIOLATION("ReadAdc(%d)", static_cast<int>(input));
    return 0;
  }
  if (!g_adc_started) {
    HAL_VIOLATION("ReadAdc before InitAdc");
  }
  const double latency = g_latency_function ? g_latency_function(g_now)
                                            : g_latency;
  const double t = g_now - latency;
  double code = Code(input, TipVoltage(input, t));
  if (g_adc_noise > 0.0) {
    code += g_adc_noise * Gauss(&g_rng);
  }
  return Quantize(code);
}

uint16_t ReadMux(int channel) {
  if (channel < 0 || channel >= kNumMuxChannels) {
    HAL_VIOLATION("ReadMux(%d): only channels 0..%d are scanned",
                  channel, kNumMuxChannels - 1);
    return 0;
  }
  if (!g_adc_started) {
    HAL_VIOLATION("ReadMux before InitAdc");
  }
  double code = g_mux[channel] * 65535.0;
  if (g_pot_noise > 0.0) {
    code += g_pot_noise * Gauss(&g_rng);
  }
  return Quantize(code);
}

void InitButtons() { g_buttons_init = true; }

bool ButtonPressed(Button button) {
  if (button != BUTTON_A && button != BUTTON_B) {
    HAL_VIOLATION("ButtonPressed(%d)", static_cast<int>(button));
    return false;
  }
  if (!g_buttons_init) {
    HAL_VIOLATION("ButtonPressed before InitButtons");
  }
  if (g_bounce > 0.0 && g_now - g_button_edge[button] < g_bounce) {
    return (Next(&g_rng) >> 40) & 1;
  }
  return g_button[button];
}

void InitProbe() {
  if (!g_probe_init) {
    // A GPIO comes up low; a second Init() keeps the pin where it is.
    g_probe.push_back({ g_now, false });
  }
  g_probe_init = true;
}

void WriteProbe(bool high) {
  if (!g_probe_init) {
    HAL_VIOLATION("WriteProbe before InitProbe");
  }
  ++g_probe_writes;
  g_probe.push_back({ g_now + g_probe_delay, high });
}

void InitLeds() {
  g_leds_init = true;
  g_led_bits = 0;
  g_led_pending = true;
}

void SetLedShiftRegisters(uint16_t bits) {
  if (!g_leds_init) {
    HAL_VIOLATION("SetLedShiftRegisters before InitLeds");
  }
  g_led_written = bits;
  if (bits != g_led_bits) {
    g_led_bits = bits;
    g_led_pending = true;
  }
}

void WriteButtonLeds(bool a, bool b) {
  if (!g_leds_init) {
    HAL_VIOLATION("WriteButtonLeds before InitLeds");
  }
  g_button_led[0] = a;
  g_button_led[1] = b;
  ++g_button_led_writes;
}

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  ++g_stats.read_calls;
  if (!FlashRangeOk("FlashRead", offset, size)) {
    memset(destination, 0xff, size);
    return;
  }
  memcpy(destination, &g_flash[offset], size);
}

bool FlashErase(uint32_t offset, uint32_t size) {
  ++g_stats.erase_calls;
  if (!FlashRangeOk("FlashErase", offset, size)) {
    return false;
  }
  if (offset % kSectorSize || size % kSectorSize || size == 0) {
    FLASH_VIOLATION("FlashErase(0x%x, %u) is not whole sectors", offset, size);
  }
  if (g_power_lost) {
    return false;
  }
  const uint32_t first = offset / kSectorSize;
  const uint32_t last = (offset + size + kSectorSize - 1) / kSectorSize;
  for (uint32_t s = first; s < last; ++s) {
    uint8_t* sector = &g_flash[s * kSectorSize];
    if (g_power_armed && g_ops_left == 0) {
      if (g_style == ERASE_PREFIX) {
        const uint32_t done = static_cast<uint32_t>(
            Uniform(&g_power_rng) * kSectorSize);
        memset(sector, 0xff, done);
      } else {
        for (uint32_t i = 0; i < kSectorSize; ++i) {
          sector[i] = static_cast<uint8_t>(Next(&g_power_rng) >> 32);
        }
      }
      g_power_lost = true;
      g_power_armed = false;
      return false;
    }
    if (g_power_armed) {
      --g_ops_left;
    }
    memset(sector, 0xff, kSectorSize);
    ++g_stats.erases[s];
    ++g_ops;
  }
  return true;
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  ++g_stats.write_calls;
  if (!FlashRangeOk("FlashWrite", offset, size)) {
    return false;
  }
  if (g_power_lost) {
    return false;
  }
  const uint8_t* bytes = static_cast<const uint8_t*>(data);
  for (uint32_t i = 0; i < size; ++i) {
    uint8_t& cell = g_flash[offset + i];
    const uint8_t want = bytes[i];
    if (g_power_armed && g_ops_left == 0) {
      cell &= want | static_cast<uint8_t>(Next(&g_power_rng) >> 32);
      g_power_lost = true;
      g_power_armed = false;
      return false;
    }
    if (g_power_armed) {
      --g_ops_left;
    }
    if ((cell & want) != want) {
      FLASH_VIOLATION(
          "FlashWrite at 0x%x: 0x%02x over 0x%02x needs an erase first",
          offset + i, want, cell);
    }
    cell &= want;
    ++g_stats.bytes_programmed;
    ++g_ops;
  }
  return true;
}

uint32_t EnterCritical() {
  const uint32_t state = g_critical_depth > 0 ? 1 : 0;
  ++g_critical_depth;
  g_critical_max = std::max(g_critical_max, g_critical_depth);
  return state;
}

void ExitCritical(uint32_t state) {
  --g_critical_depth;
  if (g_critical_depth < 0 ||
      state != static_cast<uint32_t>(g_critical_depth > 0 ? 1 : 0)) {
    HAL_VIOLATION("ExitCritical does not match EnterCritical");
  }
}

}  // namespace hal
}  // namespace plaitsy
