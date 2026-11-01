// Plaitsy host tests: shared helpers.
//
// The tests drive the port's real sources (src/plaits/ui.cc, settings.cc,
// user_data.cc, drivers/*.cc, src/storage.cc, Plaits' voice) on the board
// model of hal_fake.h. Some checks look at private state of the UI and the
// voice: the headers are included with `private` defined as `public`, which
// changes nothing in the class layout.

#ifndef PLAITSY_TEST_PORT_TEST_H_
#define PLAITSY_TEST_PORT_TEST_H_

// Every standard header the port and Plaits' headers use, before the
// `private` trick, so it only reaches the project's headers.
#include <inttypes.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#define private public
#include "plaits/dsp/voice.h"
#include "plaits/settings.h"
#include "plaits/ui.h"
#include "plaits/user_data.h"
#include "storage.h"
#undef private

#include "board_tables.h"
#include "hal.h"
#include "hal_fake.h"

namespace test {

// ------------------------------------------------------------------ checks
// One line per named check: "PASS name: detail" or "FAIL name: detail".
bool Check(const std::string& name, bool ok, const char* format, ...)
    __attribute__((format(printf, 3, 4)));
void Note(const char* format, ...) __attribute__((format(printf, 1, 2)));
void Section(const char* title);
int failures();
int passes();
// A line for the summary at the end (measured numbers worth reporting).
void Observe(const char* format, ...) __attribute__((format(printf, 1, 2)));
void PrintObservations();

// ------------------------------------------------------------------ flash
// An erased chip (as a new Seed's QSPI is in the region the port uses).
void FreshFlash();

// ------------------------------------------------------------------ rig
// The port as main.cc runs it: Ui::Poll() at 4 kHz in the "audio callback",
// optionally followed by Voice::Render() and Ui::set_active_engine() as in
// AudioCallback(); the main loop (hal::Service(), Settings::Persist(),
// UserData::Persist()) once per millisecond.
struct Rig {
  explicit Rig(bool with_voice = false);
  ~Rig();

  // Settings::Init(), UserData::Init(), Ui::Init(), as main() does.
  bool Boot();
  void Poll(int n = 1);
  void MainLoop();
  void RunMs(double ms);

  // Buttons through the board model, with the time running.
  void Press(int button);
  void Release(int button);
  void Tap(int button, double hold_ms = 80.0, double gap_ms = 80.0);

  plaits::Ui& ui() { return *ui_; }
  plaits::Settings& settings() { return *settings_; }

  plaits::Patch patch;
  plaits::Modulations modulations;
  std::unique_ptr<plaits::Settings> settings_;
  std::unique_ptr<plaits::Ui> ui_;
  std::unique_ptr<plaits::Voice> voice;
  std::vector<char> shared_buffer;
  stmlib::BufferAllocator allocator;
  long polls;
  // Largest |sample| on OUT / AUX since the last reset (with the voice).
  int peak_out;
  int peak_aux;
};

// The LEDs over some time: how often each colour of each LED was lit in the
// frames UpdateLEDs() produced.
struct LedObservation {
  int frames;
  int red[8];
  int green[8];
  // 'o' off, 'r', 'g', 'y' (both), lower case when lit in < 90 % of frames.
  std::string Pattern() const;
};
LedObservation ObserveLeds(Rig* rig, double ms);

// Plaits' own CV input stage (plaits_v50, sheet 3): the SDADC value for a
// jack voltage, computed from the schematic alone.
struct PlaitsStage {
  double rf;    // kOhm
  double rref;  // kOhm, to the -10 V reference
};
// In CvAdcChannel order (MODEL, V/OCT, FM, HARMONICS, TIMBRE, MORPH,
// TRIGGER, LEVEL).
extern const PlaitsStage kPlaitsStages[plaits::CV_ADC_CHANNEL_LAST];
extern const plaitsy::hal::AdcInput kHalInputOf[plaits::CV_ADC_CHANNEL_LAST];
extern const char* const kChannelName[plaits::CV_ADC_CHANNEL_LAST];
double PlaitsSdadcValue(int channel, double volts);  // unclipped, unrounded
double PlaitsSdadcValueClipped(int channel, double volts);

// Plaits' default calibration (settings.cc), copied here independently.
struct DefaultCalibration {
  float offset;
  float scale;
  int16_t threshold;
};
extern const DefaultCalibration kPlaitsDefaults[plaits::CV_ADC_CHANNEL_LAST];

// What Plaits' calibration would measure as the offset on its nominal
// circuit (0 V reads 0), from the schematic alone. The port boots with these
// offsets and Plaits' scales and thresholds.
double PlaitsNominalOffset(int channel);

// Moves the board model's clock without polling (for code that only looks
// at time, such as Settings::Persist()'s hold-off).
void AdvanceTimeMs(double ms);

void SetBiasErrorOnNet(const char* net, double relative);

// ------------------------------------------------------------------ groups
void TestCvMapping();
void TestNormalization();
void TestNavigation();
void TestBoardTables();
void TestCalibration();
void TestStorage();
void TestUserData();
void TestDataTransfer();

}  // namespace test

#endif  // PLAITSY_TEST_PORT_TEST_H_
