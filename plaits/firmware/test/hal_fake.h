// Plaitsy host tests: a model of the board behind src/hal.h.
//
// hal_fake.cc implements every function of plaitsy::hal on this model:
// - the eight CV inputs: a voltage per jack (or a function of time), the
//   normalization probe into the switch lugs of the normalized jacks, and
//   Plaitsy's inverting stages (gain and bias from the netlist, see
//   board_tables.h) into a 16-bit ADC on 0..3.3 V, with an optional latency
//   (the reading reflects the board as it was that long ago) and noise;
// - the pots through the 74HC4051 (a value per mux channel);
// - the buttons (pressed or not, optional contact bounce);
// - the LED word and the button LEDs, as the HAL received them;
// - a NOR flash: erase sets whole 4 kB sectors to 0xff, programming can only
//   clear bits, with a power-loss knob;
// - critical sections, counted.
// Time is simulated, in microseconds; the tests advance it.

#ifndef PLAITSY_TEST_HAL_FAKE_H_
#define PLAITSY_TEST_HAL_FAKE_H_

#include <stdint.h>

#include <functional>
#include <string>
#include <vector>

#include "hal.h"

namespace fake {

using plaitsy::hal::AdcInput;

// ------------------------------------------------------------------ time
void SetTimeUs(double t);
double TimeUs();
// The HAL is being called from the audio callback (flash access is then a
// violation of hal.h's contract).
void SetInInterrupt(bool in_interrupt);

// Restores the default board: nothing patched, pots at 0.5, buttons up, no
// latency, no noise, nominal parts, probe history cleared. Keeps the time
// and the flash.
void ResetBoard();

// ------------------------------------------------------------------ CV
const double kVdd = 3.3;
// Plaitsy's stage for an input, with the perturbations below applied.
struct Stage {
  double g;     // Rf / Rin
  double bias;  // the (+) input, from the divider on 3V3A
  double v0;    // bias * (1 + g): V_adc = v0 - g * V_tip
};
Stage StageOf(AdcInput input);
// Relative errors: bias_error 0.01 = the divider's output 1 % high.
void SetBiasError(AdcInput input, double relative);
void SetGainError(AdcInput input, double relative);

void Unpatch(AdcInput input);
void UnpatchAll();
void Patch(AdcInput input, double volts);
void PatchFunction(AdcInput input, std::function<double(double t_us)> volts);
bool patched(AdcInput input);

// The tip voltage at time t, by the model (unpatched normalized jacks: the
// probe pin through the lug resistor against the stage's Rin to its bias).
double TipVoltage(AdcInput input, double t_us);
// What the ADC returns for a tip voltage, without noise.
uint16_t RawFor(AdcInput input, double v_tip);

void SetAdcLatencyUs(double latency);
// A latency that depends on when the reading is taken (a free-running scan
// hands Poll() samples of varying age). Overrides SetAdcLatencyUs() while
// set; nullptr to clear.
void SetAdcLatencyFunction(std::function<double(double now_us)> latency);
void SetAdcNoiseLsb(double sigma);  // Gaussian, in LSB
void SetPotNoiseLsb(double sigma);
void SeedNoise(uint64_t seed);

// ------------------------------------------------------------------ probe
// The probe's level at time t, from the history of WriteProbe() calls.
bool ProbeAt(double t_us);
// How long into a Poll() the probe is written (DetectNormalization runs
// after the conversions at the start of Poll).
void SetProbeWriteDelayUs(double delay);
int probe_writes();
bool probe_initialized();

// ------------------------------------------------------------------ pots
void SetMuxChannel(int channel, double fraction);  // 0..1 of 3V3A
double mux_channel(int channel);

// ------------------------------------------------------------------ buttons
void SetButton(plaitsy::hal::Button button, bool pressed);
// Contact bounce: for this long after each edge the pin reads at random.
void SetButtonBounceUs(double bounce);

// ------------------------------------------------------------------ LEDs
uint16_t led_word_written();  // last SetLedShiftRegisters() argument
uint16_t led_word_latched();  // what the 595 outputs show after Service()
int led_frames_shifted();
bool button_led(int index);   // 0 = BUTTON_A's LED
int button_led_writes();

// ------------------------------------------------------------------ flash
const uint32_t kFlashSize = 0x40000;  // what the Daisy bootloader leaves free
const uint32_t kSectorSize = 0x1000;
const uint32_t kNumSectors = kFlashSize / kSectorSize;

uint8_t* flash();
void FlashFill(uint8_t value);
void FlashFillRandom(uint64_t seed);

struct FlashStats {
  int erases[kNumSectors];
  int erase_calls;
  int write_calls;
  int read_calls;
  long bytes_programmed;
  int violations;  // contract violations, see violation_log
  std::vector<std::string> violation_log;
};
FlashStats& flash_stats();
void ResetFlashStats();

// Power loss: the operation after `ops` more operations is interrupted (an
// operation is one sector erase or one byte programmed). An interrupted
// erase leaves the sector partly erased (ERASE_PREFIX: its first part 0xff,
// the rest untouched) or as garbage (ERASE_GARBAGE); an interrupted byte gets
// a random part of its bits programmed. After that the flash is off: every
// call fails until PowerOn().
enum EraseInterruption { ERASE_PREFIX, ERASE_GARBAGE };
void ArmPowerLoss(long ops, EraseInterruption style, uint64_t seed);
void DisarmPowerLoss();
bool power_lost();
void PowerOn();
long flash_ops();  // operations done so far (since ResetFlashStats)

// ------------------------------------------------------------------ misc
int critical_depth();
int critical_max_depth();
int adc_init_calls();
// HAL contract violations outside the flash (bad mux channel...).
int hal_violations();
std::vector<std::string>& hal_violation_log();

}  // namespace fake

#endif  // PLAITSY_TEST_HAL_FAKE_H_
