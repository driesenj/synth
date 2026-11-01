// Plaitsy host tests of the port's UI, drivers and storage on a model of
// the board. Build and run with run_port_test.sh (WSL g++).
//
// Groups (each check prints one PASS / FAIL line; the exit code is the
// number of failed checks, capped at 100):
//   1. CV mapping against Plaits' own input stages, and the musical results
//      with Plaits' default calibration
//   2. normalization (cable) detection, with ADC latency
//   3. navigation, classic and the 2022 one, and its persistence
//   4. LED bits and pot mux channels against circuit.py, HAL pin map
//   5. calibration, with the probe held low, nominal and 1 % bias errors
//   6. the QSPI record store: wrap, erase counts, power loss, garbage
//   7. user data (custom wavetables / DX7 banks)
//   8. receiving user data through TIMBRE, with the ADC's timing

#include "port_test.h"

#include <stdarg.h>

namespace test {

using namespace plaits;
using plaitsy::hal::AdcInput;

namespace {

int g_passes = 0;
int g_failures = 0;
std::vector<std::string> g_failed_names;
std::vector<std::string> g_observations;

std::string Format(const char* format, va_list args) {
  char text[2048];
  vsnprintf(text, sizeof(text), format, args);
  return text;
}

}  // namespace

bool Check(const std::string& name, bool ok, const char* format, ...) {
  va_list args;
  va_start(args, format);
  std::string detail = Format(format, args);
  va_end(args);
  printf("%s %s: %s\n", ok ? "PASS" : "FAIL", name.c_str(), detail.c_str());
  fflush(stdout);
  if (ok) {
    ++g_passes;
  } else {
    ++g_failures;
    g_failed_names.push_back(name + ": " + detail);
  }
  return ok;
}

void Note(const char* format, ...) {
  va_list args;
  va_start(args, format);
  std::string text = Format(format, args);
  va_end(args);
  printf("     %s\n", text.c_str());
}

void Observe(const char* format, ...) {
  va_list args;
  va_start(args, format);
  std::string text = Format(format, args);
  va_end(args);
  printf("     observation: %s\n", text.c_str());
  g_observations.push_back(text);
}

void PrintObservations() {
  printf("\n==== observations\n");
  for (const std::string& o : g_observations) {
    printf("- %s\n", o.c_str());
  }
}

void Section(const char* title) {
  printf("\n==== %s\n", title);
  fflush(stdout);
}

int failures() { return g_failures; }
int passes() { return g_passes; }

void FreshFlash() {
  fake::PowerOn();
  fake::FlashFill(0xff);
  fake::ResetFlashStats();
}

// ------------------------------------------------------------------ Plaits
// plaits_v50 sheet 3: MCP6004 on 0..3.3 V, Rin 100k, Rf, an offset from the
// -10 V reference through Rref; SDADC single-ended on 0..3.3 V.
const PlaitsStage kPlaitsStages[CV_ADC_CHANNEL_LAST] = {
  { 33.0, 200.0 },  // MODEL
  { 33.0, 140.0 },  // V/OCT
  { 20.0, 120.0 },  // FM
  { 33.0, 200.0 },  // HARMONICS
  { 20.0, 120.0 },  // TIMBRE
  { 20.0, 120.0 },  // MORPH
  { 56.0, 200.0 },  // TRIGGER
  { 33.0, 110.0 },  // LEVEL
};

const AdcInput kHalInputOf[CV_ADC_CHANNEL_LAST] = {
  plaitsy::hal::ADC_MODEL, plaitsy::hal::ADC_V_OCT, plaitsy::hal::ADC_FM,
  plaitsy::hal::ADC_HARMONICS, plaitsy::hal::ADC_TIMBRE,
  plaitsy::hal::ADC_MORPH, plaitsy::hal::ADC_TRIGGER, plaitsy::hal::ADC_LEVEL,
};

const char* const kChannelName[CV_ADC_CHANNEL_LAST] = {
  "MODEL", "V/OCT", "FM", "HARMONICS", "TIMBRE", "MORPH", "TRIG", "LEVEL",
};

double PlaitsSdadcValue(int channel, double volts) {
  const PlaitsStage& s = kPlaitsStages[channel];
  const double v_adc = 10.0 * s.rf / s.rref - s.rf / 100.0 * volts;
  return v_adc / 3.3 * 65536.0 - 32768.0;
}

double PlaitsSdadcValueClipped(int channel, double volts) {
  return std::min(32767.0, std::max(-32768.0, PlaitsSdadcValue(channel, volts)));
}

double PlaitsNominalOffset(int channel) {
  return -kPlaitsDefaults[channel].scale * PlaitsSdadcValue(channel, 0.0) /
      32768.0;
}

void AdvanceTimeMs(double ms) {
  fake::SetTimeUs(fake::TimeUs() + ms * 1000.0);
}

// Plaits 1.2 settings.cc, Settings::Init().
const DefaultCalibration kPlaitsDefaults[CV_ADC_CHANNEL_LAST] = {
  { 0.025f, -1.03f, 0 },      // MODEL
  { 25.71f, -60.0f, 0 },      // V/OCT
  { 0.0f, -60.0f, -2945 },    // FM
  { 0.0f, -1.0f, 0 },         // HARMONICS
  { 0.0f, -1.6f, -2945 },     // TIMBRE
  { 0.0f, -1.6f, -2945 },     // MORPH
  { 0.4f, -0.6f, 13663 },     // TRIGGER
  { 0.49f, -0.6f, 21403 },    // LEVEL
};

void SetBiasErrorOnNet(const char* net, double relative) {
  for (int i = 0; i < board::kNumAdcInputs; ++i) {
    if (strcmp(board::kBiasNet[i], net) == 0) {
      fake::SetBiasError(AdcInput(i), relative);
    }
  }
}

// ------------------------------------------------------------------ rig
Rig::Rig(bool with_voice) : polls(0), peak_out(0), peak_aux(0) {
  memset(&patch, 0, sizeof(patch));
  memset(&modulations, 0, sizeof(modulations));
  settings_.reset(new Settings);
  ui_.reset(new Ui);
  if (with_voice) {
    shared_buffer.resize(16384);
    allocator.Init(shared_buffer.data(), shared_buffer.size());
    voice.reset(new Voice);
    voice->Init(&allocator);
  }
}

Rig::~Rig() { }

bool Rig::Boot() {
  const bool loaded = settings_->Init();
  UserData::Init();
  ui_->Init(&patch, &modulations, settings_.get());
  return loaded;
}

void Rig::Poll(int n) {
  for (int i = 0; i < n; ++i) {
    fake::SetInInterrupt(true);
    ui_->Poll();
    if (voice && !ui_->test_mode()) {
      Voice::Frame frames[kMaxBlockSize];
      voice->Render(patch, modulations, frames, kBlockSize);
      ui_->set_active_engine(voice->active_engine());
      for (size_t k = 0; k < kBlockSize; ++k) {
        peak_out = std::max(peak_out, abs(static_cast<int>(frames[k].out)));
        peak_aux = std::max(peak_aux, abs(static_cast<int>(frames[k].aux)));
      }
    } else {
      // What the voice reports with nothing in MODEL.
      ui_->set_active_engine(patch.engine);
    }
    fake::SetInInterrupt(false);
    fake::SetTimeUs(fake::TimeUs() + 250.0);
    ++polls;
  }
}

void Rig::MainLoop() {
  plaitsy::hal::Service();
  settings_->Persist();
  UserData::Persist();
}

void Rig::RunMs(double ms) {
  const long n = lround(ms * 4.0);
  for (long i = 0; i < n; ++i) {
    Poll();
    if (polls % 4 == 0) {
      MainLoop();
    }
  }
}

void Rig::Press(int button) {
  fake::SetButton(plaitsy::hal::Button(button), true);
}

void Rig::Release(int button) {
  fake::SetButton(plaitsy::hal::Button(button), false);
}

void Rig::Tap(int button, double hold_ms, double gap_ms) {
  Press(button);
  RunMs(hold_ms);
  Release(button);
  RunMs(gap_ms);
}

std::string LedObservation::Pattern() const {
  std::string s;
  for (int i = 0; i < 8; ++i) {
    const bool r = red[i] > 0;
    const bool g = green[i] > 0;
    char c = r && g ? 'y' : (r ? 'r' : (g ? 'g' : 'o'));
    const int on = r && g ? std::min(red[i], green[i]) : std::max(red[i], green[i]);
    if (c != 'o' && on * 10 >= frames * 9) {
      c = static_cast<char>(c - 'a' + 'A');
    }
    s += c;
  }
  return s;
}

LedObservation ObserveLeds(Rig* rig, double ms) {
  LedObservation o;
  memset(&o, 0, sizeof(o));
  const long n = lround(ms * 4.0);
  for (long i = 0; i < n; ++i) {
    rig->Poll();
    if (rig->polls % 4 == 0) {
      rig->MainLoop();
    }
    if (rig->ui().ui_task_ == 0) {  // UpdateLEDs() ran in this Poll()
      const uint16_t word = fake::led_word_written();
      for (int led = 0; led < 8; ++led) {
        o.red[led] += (word >> board::kLedRedBit[led]) & 1;
        o.green[led] += (word >> board::kLedGreenBit[led]) & 1;
      }
      ++o.frames;
    }
  }
  return o;
}

}  // namespace test

int main(int argc, char** argv) {
  using namespace test;
  const char* only = argc > 1 ? argv[1] : nullptr;
  struct Group {
    const char* name;
    void (*run)();
  } groups[] = {
    { "cv", TestCvMapping },
    { "norm", TestNormalization },
    { "nav", TestNavigation },
    { "tables", TestBoardTables },
    { "cal", TestCalibration },
    { "storage", TestStorage },
    { "userdata", TestUserData },
    { "transfer", TestDataTransfer },
  };
  fake::SetTimeUs(0.0);
  for (const Group& g : groups) {
    if (only && strcmp(only, g.name) != 0) {
      continue;
    }
    fake::ResetBoard();
    FreshFlash();
    g.run();
    // Contract checks over the whole group.
    Check(std::string(g.name) + ": HAL used as hal.h says",
          fake::hal_violations() == 0, "%d violations%s%s",
          fake::hal_violations(),
          fake::hal_violations() ? ", first: " : "",
          fake::hal_violations() ? fake::hal_violation_log()[0].c_str() : "");
  }
  PrintObservations();
  printf("\n==== %d passed, %d failed\n", passes(), failures());
  if (failures()) {
    printf("failed checks:\n");
    for (const std::string& f : g_failed_names) {
      printf("  %s\n", f.c_str());
    }
  }
  return failures() > 100 ? 100 : failures();
}
