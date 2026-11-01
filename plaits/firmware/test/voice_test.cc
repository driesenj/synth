// Plaitsy host test: Plaits 1.2's DSP, vendored unchanged, rendered through
// the port's src/plaits/dsp/dsp.h and src/plaits/user_data.{h,cc}.
//
//   bash test/run_voice_test.sh            (WSL: g++, ASan + UBSan; ~2 min)
//   bash test/run_voice_test.sh --quick    (10 settings per model, not 82)
//   ... --engine N --verbose               (one model, every run listed)
//
// Each check prints one PASS/FAIL line; the exit code is the number of
// failed checks (0 = all passed).
//
//   clock_derivation     the Seed's audio frame rate, from libDaisy v9.0.0's
//                        clock tree, against kCorrectedSampleRate
//   engine_memory        every engine fits Plaits' 16 kB shared buffer
//   engines_unpatched    all 24 models, 2 s per setting, TRIG unpatched
//   engines_triggered    the same, TRIG patched: a 50 ms gate every 250 ms
//   engines_cv_patched   every CV input patched with slow LFOs, TRIG patched
//   sparse_dust          why two models are silent for their first 2 s
//   engine_switching     one voice hopping between models (shared buffer)
//   tuning_*             2-op FM, timbre 0: a sine, 440 Hz on the Seed
//   user_data_*          UserData::Save(), Voice::ReloadUserData(),
//                        UserData::Persist() and Init() on a flash model
//
// A run fails on NaN / Inf, on a wrong active_engine(), on an output frozen
// at a non-zero level or pinned to a rail, and on silence, except where
// Plaits is silent by design: SilentByDesign() lists those cases and checks
// each against the vendored code's data (presets, LPC frames, gains).
//
// The models render through plaits::Voice exactly as in src/main.cc: one
// 16384-byte BufferAllocator shared by all engines, blocks of 12 samples,
// Voice::Frame (int16) out. The engines' float output, before the int16
// conversion, is read from Voice's private buffers to catch NaN and Inf
// (the int16 conversion would hide them).

#include <stdint.h>
#include <string.h>

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <new>
#include <string>
#include <vector>

#include "plaits/dsp/chords/chord_bank.h"
#include "plaits/dsp/dsp.h"
#include "plaits/dsp/engine/engine.h"
#include "plaits/dsp/fm/algorithms.h"
#include "plaits/dsp/fm/patch.h"
#include "plaits/dsp/oscillator/sine_oscillator.h"
#include "plaits/dsp/speech/lpc_speech_synth_controller.h"
#include "plaits/dsp/speech/lpc_speech_synth_words.h"
#include "plaits/dsp/voice.h"
#include "plaits/resources.h"
#include "plaits/user_data.h"
#include "stmlib/dsp/hysteresis_quantizer.h"
#include "stmlib/utils/random.h"

#include "hal.h"

using plaits::Modulations;
using plaits::Patch;
using plaits::UserData;
using plaits::Voice;

// ---------------------------------------------------------------------------
// The board, as far as src/plaits/user_data.cc needs it: the Seed's QSPI
// flash. Erased flash reads 0xFF; programming can only clear bits.

namespace plaitsy {
namespace hal {

const uint32_t kFlashModelSize = 0x20000;
uint8_t flash_model[kFlashModelSize];
bool flash_model_erased = false;
int flash_erase_calls = 0;
int flash_write_calls = 0;
uint32_t flash_last_erase[2];  // offset, size
uint32_t flash_last_write[2];

static void EraseFlashModel() {
  memset(flash_model, 0xff, sizeof(flash_model));
  flash_model_erased = true;
}

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  if (!flash_model_erased) {
    EraseFlashModel();
  }
  uint8_t* d = static_cast<uint8_t*>(destination);
  for (uint32_t i = 0; i < size; ++i) {
    const uint32_t address = offset + i;
    d[i] = address < kFlashModelSize ? flash_model[address] : 0xff;
  }
}

bool FlashErase(uint32_t offset, uint32_t size) {
  if (!flash_model_erased) {
    EraseFlashModel();
  }
  ++flash_erase_calls;
  flash_last_erase[0] = offset;
  flash_last_erase[1] = size;
  if (offset % kFlashSectorSize || size % kFlashSectorSize ||
      offset + size > kFlashModelSize) {
    return false;
  }
  memset(&flash_model[offset], 0xff, size);
  return true;
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  if (!flash_model_erased) {
    EraseFlashModel();
  }
  ++flash_write_calls;
  flash_last_write[0] = offset;
  flash_last_write[1] = size;
  if (offset + size > kFlashModelSize) {
    return false;
  }
  const uint8_t* s = static_cast<const uint8_t*>(data);
  for (uint32_t i = 0; i < size; ++i) {
    flash_model[offset + i] &= s[i];
  }
  return true;
}

}  // namespace hal
}  // namespace plaitsy

// ---------------------------------------------------------------------------
// Read access to Voice::out_buffer_ and Voice::aux_buffer_ (private): an
// explicit instantiation may name private members ([temp.explicit]), so this
// needs no change to the vendored class.

template<typename Tag, typename Tag::type kMember>
struct PrivateMember {
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wnon-template-friend"
  friend typename Tag::type Member(Tag) { return kMember; }
#pragma GCC diagnostic pop
};

struct VoiceOutBuffer {
  typedef float (Voice::*type)[plaits::kMaxBlockSize];
  friend type Member(VoiceOutBuffer);
};

struct VoiceAuxBuffer {
  typedef float (Voice::*type)[plaits::kMaxBlockSize];
  friend type Member(VoiceAuxBuffer);
};

template struct PrivateMember<VoiceOutBuffer, &Voice::out_buffer_>;
template struct PrivateMember<VoiceAuxBuffer, &Voice::aux_buffer_>;

namespace {

// ---------------------------------------------------------------------------
// Test bookkeeping.

int num_failures = 0;
bool verbose = false;
int only_engine = -1;  // --engine N: the model checks render model N only

void Report(bool pass, const char* name, const std::string& detail) {
  std::printf("%s %s: %s\n", pass ? "PASS" : "FAIL", name, detail.c_str());
  std::fflush(stdout);
  if (!pass) {
    ++num_failures;
  }
}

std::string Format(const char* format, ...)
    __attribute__((format(printf, 1, 2)));

std::string Format(const char* format, ...) {
  char buffer[1024];
  va_list args;
  va_start(args, format);
  vsnprintf(buffer, sizeof(buffer), format, args);
  va_end(args);
  return std::string(buffer);
}

// ---------------------------------------------------------------------------
// The models.

const int kNumEngines = 24;
const char* const kEngineNames[kNumEngines] = {
  // Yellow bank: Plaits 1.2 (2022).
  "VA + VCF", "phase distortion", "6-op FM bank 1", "6-op FM bank 2",
  "6-op FM bank 3", "wave terrain", "string machine", "chiptune",
  // Green bank.
  "virtual analog", "waveshaping", "2-op FM", "granular formant",
  "harmonic", "wavetable", "chords", "speech",
  // Red bank.
  "swarm", "filtered noise", "particle noise", "inharmonic string",
  "modal resonator", "bass drum", "snare drum", "hi-hat",
};

const double kRate = 48000.0;            // what the DSP assumes per sample
const size_t kBlock = plaits::kBlockSize;  // 12, as main.cc
const size_t kSharedBufferSize = 16384;    // as main.cc
const int kSeconds = 2;

// The Seed's frame clock, from libDaisy v9.0.0 (see CheckClockDerivation):
// 16 MHz * 295 / 6 / 16 (PLL3P) / 4 (MCKDIV) / 256.
const double kSeedSampleRate = 16.0e6 * 295.0 / (6.0 * 16.0 * 4.0 * 256.0);
const double kSeedSampleRateNominal = 48014.32;  // the figure in dsp.h
const double kUpstreamCorrectedSampleRate = 47872.34;  // Plaits' dsp.h

// One Voice with its own shared buffer, as main.cc has them: zeroed static
// memory at power-up, then Voice::Init() over a BufferAllocator. Separate
// heap blocks, so that AddressSanitizer sees any access past the 16 kB.
struct Rig {
  char* shared_buffer;
  unsigned char* voice_storage;
  Voice* voice;

  Rig() {
    shared_buffer = new char[kSharedBufferSize];
    voice_storage = static_cast<unsigned char*>(
        ::operator new(sizeof(Voice)));
    voice = NULL;
  }

  ~Rig() {
    if (voice) {
      voice->~Voice();
    }
    ::operator delete(voice_storage);
    delete[] shared_buffer;
  }

  void Boot() {
    if (voice) {
      voice->~Voice();
    }
    memset(shared_buffer, 0, kSharedBufferSize);
    memset(voice_storage, 0, sizeof(Voice));
    // Same noise every run, whatever ran before: stmlib's power-up seed.
    stmlib::Random::Seed(0x21);
    voice = new (voice_storage) Voice;
    stmlib::BufferAllocator allocator(shared_buffer, kSharedBufferSize);
    voice->Init(&allocator);
  }
};

enum Mode {
  MODE_UNPATCHED,
  MODE_TRIGGERED,
  MODE_CV_PATCHED,
};

const char* const kModeNames[] = { "unpatched", "triggered", "cv_patched" };

struct Setting {
  float note;
  float harmonics;
  float timbre;
  float morph;
  bool sweep;  // ramp everything instead (the values above are ignored)
};

std::string SettingName(const Setting& s) {
  if (s.sweep) {
    return "sweep";
  }
  return Format("n%.0f h%.1f t%.1f m%.1f", s.note, s.harmonics, s.timbre,
                s.morph);
}

float Triangle(double t, double period) {
  double x = std::fmod(t / period, 1.0);
  return static_cast<float>(x < 0.5 ? 2.0 * x : 2.0 - 2.0 * x);
}

float Lfo(double t, double frequency) {
  return static_cast<float>(std::sin(2.0 * M_PI * frequency * t));
}

// TRIG: a 50 ms gate every 250 ms. 1.0 is what Plaits' calibration makes of
// +5 V (offset 0.4, scale -0.6 on a full-scale reading), 0.0 of 0 V.
float TriggerAt(size_t block) {
  const size_t sample = block * kBlock;
  return (sample % 12000) < 2400 ? 1.0f : 0.0f;
}

void SetControls(
    int engine,
    const Setting& s,
    Mode mode,
    size_t block,
    Patch* patch,
    Modulations* m) {
  const double t = double(block * kBlock) / kRate;
  memset(patch, 0, sizeof(*patch));
  memset(m, 0, sizeof(*m));

  patch->engine = engine;
  patch->decay = 0.5f;       // Plaits' default (128 / 256)
  patch->lpg_colour = 0.0f;  // Plaits' default
  if (s.sweep) {
    patch->note = 24.0f + 72.0f * Triangle(t, 2.0);
    patch->harmonics = Triangle(t + 0.3, 1.9);
    patch->timbre = Triangle(t + 0.1, 1.3);
    patch->morph = Triangle(t, 0.7);
    patch->frequency_modulation_amount = 0.3f;
    patch->timbre_modulation_amount = 0.6f;
    patch->morph_modulation_amount = -0.6f;
    patch->decay = Triangle(t, 1.7);
    patch->lpg_colour = Triangle(t, 1.1);
  } else {
    patch->note = s.note;
    patch->harmonics = s.harmonics;
    patch->timbre = s.timbre;
    patch->morph = s.morph;
  }

  if (mode == MODE_TRIGGERED || mode == MODE_CV_PATCHED) {
    m->trigger_patched = true;
    m->trigger = TriggerAt(block);
  }
  if (mode == MODE_CV_PATCHED) {
    // Plaits' calibrated units: FM and V/OCT in semitones, the others in
    // knob units; LEVEL as Plaits' calibration makes of 0..5 V.
    m->frequency_patched = true;
    m->timbre_patched = true;
    m->morph_patched = true;
    m->level_patched = true;
    m->note = 12.0f * Lfo(t, 0.31);
    m->frequency = 12.0f * Lfo(t, 5.3);
    m->harmonics = 0.3f * Lfo(t, 0.7);
    m->timbre = 0.8f * Lfo(t, 1.1);
    m->morph = 0.8f * Lfo(t, 0.9);
    m->level = 0.5f + 0.5f * Lfo(t, 1.7);
    patch->frequency_modulation_amount = 0.5f;
    patch->timbre_modulation_amount = 0.6f;
    patch->morph_modulation_amount = -0.6f;
  }
}

// What a run produced, one per output (0 = OUT, 1 = AUX).
struct ChannelStats {
  int peak;          // max |x|, whole run
  double sum2;       // sum of x^2, whole run
  double mean;       // after the first 100 ms
  double ac_rms;     // around that mean
  int p2p;           // max - min after the first 100 ms
  double tail_mean;  // last 0.5 s
  int tail_p2p;
  int rail_run;      // longest stretch at -32768 or 32767, in samples
  long nonfinite;    // NaN / Inf samples in the engine's float output
  float max_abs_float;
};

struct RunResult {
  int engine;
  int active_engine;
  Setting setting;
  Mode mode;
  ChannelStats ch[2];
};

void Analyse(const std::vector<int16_t>& x, ChannelStats* s) {
  const size_t n = x.size();
  const size_t start = size_t(0.1 * kRate);
  const size_t tail = n - size_t(0.5 * kRate);
  int peak = 0;
  double sum2 = 0.0;
  double sum = 0.0;
  double window_sum2 = 0.0;
  int lo = 32767, hi = -32768, tail_lo = 32767, tail_hi = -32768;
  double tail_sum = 0.0;
  int rail_run = 0, run = 0;
  for (size_t i = 0; i < n; ++i) {
    const int v = x[i];
    peak = std::max(peak, std::abs(v));
    sum2 += double(v) * v;
    run = (v <= -32768 || v >= 32767) ? run + 1 : 0;
    rail_run = std::max(rail_run, run);
    if (i >= start) {
      sum += v;
      window_sum2 += double(v) * v;
      lo = std::min(lo, v);
      hi = std::max(hi, v);
    }
    if (i >= tail) {
      tail_sum += v;
      tail_lo = std::min(tail_lo, v);
      tail_hi = std::max(tail_hi, v);
    }
  }
  const double m = sum / double(n - start);
  s->peak = peak;
  s->sum2 = sum2;
  s->mean = m;
  s->ac_rms = std::sqrt(std::max(window_sum2 / double(n - start) - m * m, 0.0));
  s->p2p = hi - lo;
  s->tail_mean = tail_sum / double(n - tail);
  s->tail_p2p = tail_hi - tail_lo;
  s->rail_run = rail_run;
}

// Renders one model from power-up; keeps the int16 output.
RunResult RenderRun(
    Rig* rig,
    int engine,
    const Setting& setting,
    Mode mode,
    std::vector<int16_t>* out,
    std::vector<int16_t>* aux,
    double seconds = kSeconds) {
  RunResult r;
  r.engine = engine;
  r.setting = setting;
  r.mode = mode;
  rig->Boot();
  Voice* voice = rig->voice;
  const size_t num_blocks = size_t(seconds * kRate) / kBlock;
  out->resize(num_blocks * kBlock);
  aux->resize(num_blocks * kBlock);
  long nonfinite[2] = { 0, 0 };
  float max_abs[2] = { 0.0f, 0.0f };
  Patch patch;
  Modulations modulations;
  Voice::Frame frames[plaits::kMaxBlockSize];
  for (size_t b = 0; b < num_blocks; ++b) {
    SetControls(engine, setting, mode, b, &patch, &modulations);
    voice->Render(patch, modulations, frames, kBlock);
    const float* f[2] = {
      voice->*Member(VoiceOutBuffer()), voice->*Member(VoiceAuxBuffer())
    };
    for (size_t i = 0; i < kBlock; ++i) {
      for (int c = 0; c < 2; ++c) {
        if (!std::isfinite(f[c][i])) {
          ++nonfinite[c];
        } else {
          max_abs[c] = std::max(max_abs[c], std::fabs(f[c][i]));
        }
      }
      (*out)[b * kBlock + i] = frames[i].out;
      (*aux)[b * kBlock + i] = frames[i].aux;
    }
  }
  r.active_engine = voice->active_engine();
  Analyse(*out, &r.ch[0]);
  Analyse(*aux, &r.ch[1]);
  for (int c = 0; c < 2; ++c) {
    r.ch[c].nonfinite = nonfinite[c];
    r.ch[c].max_abs_float = max_abs[c];
  }
  return r;
}

// Thresholds, in int16 LSBs. Plaits' int16 conversion adds 1, so a silent
// output reads +1.
bool IsSilent(const ChannelStats& s) {
  return s.ac_rms < 1.0 && s.p2p <= 4;
}

// Frozen at a level other than Plaits' silence for the last half second.
bool IsStuckDc(const ChannelStats& s) {
  return s.tail_p2p <= 2 && std::fabs(s.tail_mean - 1.0) > 16.0;
}

// At a rail for 100 ms: no setting here plays a note below 32 Hz, so a
// legitimate waveform would have left the rail long before.
bool IsStuckAtRail(const ChannelStats& s) {
  return s.rail_run >= int(0.1 * kRate);
}

double Dbfs(double rms) {
  return rms > 0.0 ? 20.0 * std::log10(rms / 32767.0) : -999.0;
}

// ---------------------------------------------------------------------------
// Where Plaits 1.2 is silent by design. Each case is checked against the
// vendored code's own data, not just listed: a silent output that does not
// meet its case's condition fails.

// The 6-op preset HARMONICS selects: six_op_engine.cc quantizes
// harmonics * 1.02 to 32 patches (HysteresisQuantizer2(32, 0.005, false)).
int SixOpPatchIndex(float harmonics) {
  stmlib::HysteresisQuantizer2 quantizer;
  quantizer.Init(32, 0.005f, false);
  int index = 0;
  for (int i = 0; i < 4; ++i) {
    index = quantizer.Process(harmonics * 1.02f);
  }
  return index;
}

// True if every carrier of that preset has envelope level `level` (0..3 =
// L1..L4) at 0.
bool SixOpCarriersAtZero(int engine, float harmonics, int level) {
  static plaits::fm::Algorithms<6> algorithms;
  static bool algorithms_ready = false;
  if (!algorithms_ready) {
    algorithms.Init();
    algorithms_ready = true;
  }
  plaits::fm::Patch patch;
  patch.Unpack(plaits::fm_patches_table[engine - 2] +
               SixOpPatchIndex(harmonics) * plaits::fm::Patch::SYX_SIZE);
  for (int op = 0; op < 6; ++op) {
    if (!algorithms.is_modulator(patch.algorithm, op) &&
        patch.op[op].envelope.level[level] != 0) {
      return false;
    }
  }
  return true;
}

// The energy (0..255) of the LPC frame that the speech model's scan mode
// plays, or -1 outside the word banks. speech_engine.cc: above HARMONICS 1/3
// word_bank = HysteresisQuantizer2(6, 0.1, false) of (6h - 2) * 0.275,
// minus 1; with TRIG unpatched, lpc_speech_synth_controller.cc plays
// PlayFrame(frames, MORPH * (num_frames - 1.0001), interpolated).
float ScannedLpcEnergy(float harmonics, float morph) {
  const float group = harmonics * 6.0f;
  if (group <= 2.0f) {
    return -1.0f;
  }
  stmlib::HysteresisQuantizer2 quantizer;
  quantizer.Init(LPC_SPEECH_SYNTH_NUM_WORD_BANKS + 1, 0.1f, false);
  int bank = -1;
  for (int i = 0; i < 4; ++i) {
    bank = quantizer.Process((group - 2.0f) * 0.275f) - 1;
  }
  if (bank < 0) {
    return -1.0f;
  }
  static char buffer[16384];
  stmlib::BufferAllocator allocator(buffer, sizeof(buffer));
  plaits::LPCSpeechSynthWordBank word_bank;
  word_bank.Init(plaits::word_banks_, LPC_SPEECH_SYNTH_NUM_WORD_BANKS,
                 &allocator);
  word_bank.Load(bank);
  const float position = morph * (float(word_bank.num_frames()) - 1.0001f);
  const int i = int(position);
  const float fraction = position - float(i);
  const plaits::LPCSpeechSynth::Frame* frames = word_bank.frames();
  return float(frames[i].energy) +
      (float(frames[i + 1].energy) - float(frames[i].energy)) * fraction;
}

// The loudest partial the harmonic model can play, in int16 LSB. A copy of
// additive_engine.cc's UpdateAmplitudes() gains (OUT: harmonics 1..24, AUX:
// the organ set 1, 2, 3, 4, 6, 8, 10, 12), normalised to their sum as the
// engine does; HarmonicOscillator::Render() then scales each partial by
// 1 - 2f, i.e. to 0 from Nyquist up; the post-processing gain is 0.8.
double AdditiveLoudestPartial(float note, float harmonics, float timbre,
                              float morph, int channel) {
  static const int kOrganHarmonics[8] = { 0, 1, 2, 3, 5, 7, 9, 11 };
  const int num_harmonics = channel == 0 ? 24 : 8;
  const float raw_bumps = harmonics;
  const float raw_slope = (1.0f - 0.6f * raw_bumps) * morph;
  const float slope = 0.01f + 1.99f * raw_slope * raw_slope * raw_slope;
  const float bumps = 16.0f * raw_bumps * raw_bumps;
  const float n = static_cast<float>(num_harmonics) - 1.0f;
  const float margin = (1.0f / slope - 1.0f) / (1.0f + bumps);
  const float center = timbre * (n + margin) - 0.5f * margin;
  double gains[24];
  double sum = 0.0;
  for (int i = 0; i < num_harmonics; ++i) {
    const float order = std::fabs(static_cast<float>(i) - center) * slope;
    float gain = 1.0f - order;
    gain += std::fabs(gain);
    gain *= gain;
    gain *= 1.0f + plaits::Sine(0.25f + order * bumps);
    gain *= gain;
    gain *= gain;
    gains[i] = gain;
    sum += gain;
  }
  const float f0 = plaits::NoteToFrequency(note);
  double loudest = 0.0;
  for (int i = 0; i < num_harmonics && sum > 0.0; ++i) {
    const int harmonic = (channel == 0 ? i : kOrganHarmonics[i]) + 1;
    const double f = std::min(double(f0) * harmonic, 0.5);
    loudest = std::max(loudest, gains[i] / sum * (1.0 - 2.0 * f));
  }
  return loudest * 0.8 * 32767.0;
}

// True if no chord voice the channel carries can sound. chord_engine.cc:
// each of the five voices plays a divide-down organ at gain
// clamp(4 - 32 f, 0, 1) (off from 6 kHz up) times 1 - wavetable_amount, and
// a wavetable voice at wavetable_amount = clamp(50 (MORPH - fade_point), 0,
// 1); AUX carries the voices in ComputeChordInversion()'s mask, OUT all.
bool ChordsSilent(float note, float harmonics, float timbre, float morph,
                  int channel) {
  // chord_engine.cc's fade_point[].
  static const float kFadePoint[plaits::kChordNumVoices] = {
    0.55f, 0.47f, 0.49f, 0.51f, 0.53f
  };
  static char buffer[1024];
  stmlib::BufferAllocator allocator(buffer, sizeof(buffer));
  plaits::ChordBank chords;
  chords.Init(&allocator);
  chords.Reset();
  for (int i = 0; i < 4; ++i) {
    chords.set_chord(harmonics);
  }
  float ratios[plaits::kChordNumVoices];
  float amplitudes[plaits::kChordNumVoices];
  const int aux_mask = chords.ComputeChordInversion(timbre, ratios,
                                                    amplitudes);
  const float f0 = plaits::NoteToFrequency(note) * 0.998f;
  for (int v = 0; v < plaits::kChordNumVoices; ++v) {
    if (channel == 1 && !((1 << v) & aux_mask)) {
      continue;
    }
    float wavetable_amount = 50.0f * (morph - kFadePoint[v]);
    CONSTRAIN(wavetable_amount, 0.0f, 1.0f);
    float divide_down_gain = 4.0f - f0 * ratios[v] * 32.0f;
    CONSTRAIN(divide_down_gain, 0.0f, 1.0f);
    const float divide_down_amount =
        (1.0f - wavetable_amount) * divide_down_gain;
    if (amplitudes[v] > 0.0f &&
        (wavetable_amount > 0.0f || divide_down_amount > 0.0f)) {
      return false;
    }
  }
  return true;
}

// Returns why this silent output is by design, or "" if it is a failure.
std::string SilentByDesign(const RunResult& r, int channel) {
  const int e = r.engine;
  const Setting& s = r.setting;
  if (s.sweep || r.mode == MODE_CV_PATCHED) {
    return "";
  }
  // These three hold with TRIG patched or not.
  if (e == 8 && channel == 1 && s.harmonics == 0.5f && s.timbre == 1.0f) {
    // virtual_analog_engine.cc (VA_VARIANT 2): AUX = (sync osc 2 - sync
    // osc 1) / 2. ComputeDetuning(0.5) is exactly 0, so both run at the
    // same pitch, and TIMBRE 1 syncs them at 48 semitones, a ratio of 16;
    // osc 2 starts a quarter of a master period late (set_master_phase
    // (0.25f)), which is exactly 4 slave cycles: they cancel.
    return "virtual analog AUX, HARMONICS 0.5, TIMBRE 1: two identical sync "
           "oscillators 4 slave cycles apart (ratio 16, phase 1/4) cancel";
  }
  if (e == 12) {
    const double loudest = AdditiveLoudestPartial(
        s.note, s.harmonics, s.timbre, s.morph, channel);
    if (loudest < 1.0) {
      return Format("harmonic: no partial below Nyquist louder than 1 LSB "
                    "(the spectral peak is above it, or falls between two "
                    "harmonics), %s", channel ? "AUX" : "OUT");
    }
  }
  if (e == 14 && ChordsSilent(s.note, s.harmonics, s.timbre, s.morph,
                              channel)) {
    return Format("chords: every %s voice is above the divide-down organ's "
                  "6 kHz cut-off and below its wavetable fade-in point",
                  channel ? "AUX" : "OUT");
  }
  if (r.mode != MODE_UNPATCHED) {
    return "";
  }
  if (e >= 21 && s.morph == 0.0f) {
    // bass_drum_engine.cc, snare_drum_engine.cc, hi_hat_engine.cc pass
    // TRIGGER_UNPATCHED as "sustain"; drums/*.h then run free and scale
    // everything by sustain_gain = accent * decay, decay being MORPH.
    return "drums, TRIG unpatched: free-running at accent x MORPH = 0";
  }
  if (e >= 2 && e <= 4) {
    // six_op_engine.cc, TRIG unpatched: voice 0 "sustains", and fm/voice.h
    // renders every operator envelope at t = 1.5 s * MORPH (RenderAtSample):
    // MORPH 1 is the end of the 1.5 s gate (the sustain level L3), MORPH 0
    // the start of the attack (level L4). Keyboard level scaling adds a
    // note-dependent amount on top, so such presets are silent at some notes.
    if (s.morph == 1.0f && SixOpCarriersAtZero(e, s.harmonics, 2)) {
      return Format("6-op FM, TRIG unpatched, MORPH 1: envelopes scrubbed to "
                    "the end of the gate; every carrier of preset %d has "
                    "sustain level L3 = 0", SixOpPatchIndex(s.harmonics) + 1);
    }
    if (s.morph == 0.0f && SixOpCarriersAtZero(e, s.harmonics, 3)) {
      return Format("6-op FM, TRIG unpatched, MORPH 0: envelopes at the start "
                    "of the attack; every carrier of preset %d starts at "
                    "L4 = 0", SixOpPatchIndex(s.harmonics) + 1);
    }
  }
  if (e == 15) {
    const float energy = ScannedLpcEnergy(s.harmonics, s.morph);
    if (energy >= 0.0f && energy < 1.0f) {
      return "speech, word banks, TRIG unpatched: MORPH scans the bank's LPC "
             "frames and sits on a frame of energy 0 (before the first word "
             "at MORPH 0, after the last at MORPH 1)";
    }
  }
  if ((e == 19 || e == 20) && s.timbre == 0.0f) {
    // string_voice.cc / modal_voice.cc, TRIG unpatched: the excitation is
    // Dust(0.00005 + 0.99995 * density^2), density = brightness^2, i.e. one
    // grain per 20000 samples on average at TIMBRE 0. Checked by the
    // sparse_dust check: the first grain comes after the first 2 s.
    return "string / modal, TRIG unpatched, TIMBRE 0: sparse dust excitation, "
           "first grain after 2 s from the power-up seed (see sparse_dust)";
  }
  return "";
}

// ---------------------------------------------------------------------------
// Checks.

void CheckClockDerivation() {
  // libDaisy v9.0.0, src/sys/system.cpp, ConfigureClocks(): PLL source HSE
  // (16 MHz on the Seed; HSE_VALUE=16000000 in the Makefile), PLL3M = 6,
  // PLL3N = 295, PLL3P = 16, PLL3FRACN = 0; Sai1ClockSelection =
  // RCC_SAI1CLKSOURCE_PLL3 (the P output).
  const double hse = 16.0e6;
  const int pll3m = 6, pll3n = 295, pll3p = 16, pll3fracn = 0;

  // HAL_RCCEx_GetPLL3ClockFreq() (stm32h7xx_hal_rcc_ex.c), which
  // HAL_SAI_Init() calls through HAL_RCCEx_GetPeriphCLKFreq(SAI1): float
  // arithmetic on the register fields (which hold N - 1 and P - 1), the
  // result truncated to uint32_t.
  const float vco = (16000000.0f / float(pll3m)) *
      (float(pll3n - 1) + float(pll3fracn) / float(0x2000) + 1.0f);
  const uint32_t sai_ck = static_cast<uint32_t>(vco / (float(pll3p - 1) + 1.0f));

  // src/per/sai.cpp: AudioFrequency = SAI_AUDIO_FREQUENCY_48K, NoDivider =
  // SAI_MASTERDIVIDER_ENABLE (NODIV = 0, master clock divider in use),
  // MckOverSampling never set (0 = disabled, OSR = 0). Seed audio is 24 bit,
  // I2S MSB-justified, 2 slots: SAI_InitI2S() makes 32-bit slots, a 64-bit
  // frame. HAL_SAI_Init() (stm32h7xx_hal_sai.c), NODIV = 0 branch:
  //   tmpval = (freq * 10) / (AudioFrequency * (OSR + 1) * 256)
  //   Mckdiv = tmpval / 10, plus 1 if (tmpval % 10) > 8
  const uint32_t tmpval = (sai_ck * 10U) / (48000U * 1U * 256U);
  uint32_t mckdiv = tmpval / 10U;
  if ((tmpval % 10U) > 8U) {
    mckdiv += 1U;
  }
  // RM0433, SAI clock generator, NODIV = 0: MCLK = SAI_CK / MCKDIV,
  // FS = MCLK / ((OSR + 1) * 256), SCK = FS * frame length.
  const double pll3p_hz = hse / pll3m * (pll3n + pll3fracn / 8192.0) / pll3p;
  const double mclk = pll3p_hz / mckdiv;
  const double fs = mclk / 256.0;
  const double sck = fs * 64.0;
  const double error_ppm =
      (double(plaits::kCorrectedSampleRate) - fs) / fs * 1.0e6;
  const bool pass = mckdiv == 4 && std::fabs(error_ppm) < 1.0 &&
      std::fabs(fs - kSeedSampleRate) < 1.0e-6;
  Report(pass, "clock_derivation", Format(
      "PLL3P %.4f MHz (HAL computes %u Hz), MCKDIV %u (tmpval %u), MCLK "
      "%.6f MHz, SCK %.6f MHz, fs %.6f Hz; kCorrectedSampleRate %.4f Hz is "
      "%+.3f ppm off (upstream 47872.34 would be %+.1f ppm, %+.2f cents)",
      pll3p_hz * 1e-6, sai_ck, mckdiv, tmpval, mclk * 1e-6, sck * 1e-6, fs,
      double(plaits::kCorrectedSampleRate), error_ppm,
      (kUpstreamCorrectedSampleRate - fs) / fs * 1.0e6,
      1200.0 * std::log2(fs / kUpstreamCorrectedSampleRate)));
}

template<typename E>
size_t EngineBytes() {
  // A buffer much bigger than Plaits', to see how much each engine takes.
  static char big[65536];
  static E engine;
  stmlib::BufferAllocator allocator(big, sizeof(big));
  engine.Init(&allocator);
  return sizeof(big) - allocator.free();
}

void CheckEngineMemory() {
  struct Entry {
    const char* name;
    size_t bytes;
  } entries[] = {
    { "VirtualAnalogVCFEngine", EngineBytes<plaits::VirtualAnalogVCFEngine>() },
    { "PhaseDistortionEngine", EngineBytes<plaits::PhaseDistortionEngine>() },
    { "SixOpEngine", EngineBytes<plaits::SixOpEngine>() },
    { "WaveTerrainEngine", EngineBytes<plaits::WaveTerrainEngine>() },
    { "StringMachineEngine", EngineBytes<plaits::StringMachineEngine>() },
    { "ChiptuneEngine", EngineBytes<plaits::ChiptuneEngine>() },
    { "VirtualAnalogEngine", EngineBytes<plaits::VirtualAnalogEngine>() },
    { "WaveshapingEngine", EngineBytes<plaits::WaveshapingEngine>() },
    { "FMEngine", EngineBytes<plaits::FMEngine>() },
    { "GrainEngine", EngineBytes<plaits::GrainEngine>() },
    { "AdditiveEngine", EngineBytes<plaits::AdditiveEngine>() },
    { "WavetableEngine", EngineBytes<plaits::WavetableEngine>() },
    { "ChordEngine", EngineBytes<plaits::ChordEngine>() },
    { "SpeechEngine", EngineBytes<plaits::SpeechEngine>() },
    { "SwarmEngine", EngineBytes<plaits::SwarmEngine>() },
    { "NoiseEngine", EngineBytes<plaits::NoiseEngine>() },
    { "ParticleEngine", EngineBytes<plaits::ParticleEngine>() },
    { "StringEngine", EngineBytes<plaits::StringEngine>() },
    { "ModalEngine", EngineBytes<plaits::ModalEngine>() },
    { "BassDrumEngine", EngineBytes<plaits::BassDrumEngine>() },
    { "SnareDrumEngine", EngineBytes<plaits::SnareDrumEngine>() },
    { "HiHatEngine", EngineBytes<plaits::HiHatEngine>() },
  };
  size_t worst = 0;
  const char* worst_name = "";
  bool pass = true;
  std::string list;
  for (size_t i = 0; i < sizeof(entries) / sizeof(entries[0]); ++i) {
    if (entries[i].bytes > worst) {
      worst = entries[i].bytes;
      worst_name = entries[i].name;
    }
    if (entries[i].bytes > kSharedBufferSize) {
      pass = false;
    }
    if (verbose) {
      std::printf("  memory %-24s %6zu bytes\n", entries[i].name,
                  entries[i].bytes);
    }
  }
  Report(pass, "engine_memory", Format(
      "largest %s: %zu of %zu shared bytes (host sizes; pointers are 8 bytes "
      "here, 4 on the Seed); sizeof(Voice) %zu",
      worst_name, worst, kSharedBufferSize, sizeof(Voice)));
}

struct EngineSummary {
  double sum2[2];
  long samples;
  int peak[2];
  double max_dc[2];  // largest |mean - 1| of a run, after its first 100 ms
  float max_abs_float[2];
  int silent_by_design;
  int runs;
};

// Renders every model with every setting in one mode and checks each run.
void CheckEngines(Mode mode, const std::vector<Setting>& settings,
                  const char* check_name) {
  Rig rig;
  std::vector<int16_t> out, aux;
  EngineSummary summary[kNumEngines];
  memset(summary, 0, sizeof(summary));
  int failed_runs = 0;
  int models = 0;
  int by_design = 0;
  long nonfinite_total = 0;
  std::string first_failure;
  std::map<std::string, int> by_design_reasons;

  for (int e = 0; e < kNumEngines; ++e) {
    if (only_engine >= 0 && e != only_engine) {
      continue;
    }
    ++models;
    for (size_t k = 0; k < settings.size(); ++k) {
      RunResult r = RenderRun(&rig, e, settings[k], mode, &out, &aux);
      EngineSummary* es = &summary[e];
      es->samples += long(out.size());
      ++es->runs;
      std::string problems;
      if (r.active_engine != e) {
        problems += Format(" active_engine=%d", r.active_engine);
      }
      for (int c = 0; c < 2; ++c) {
        const ChannelStats& s = r.ch[c];
        const char* channel = c == 0 ? "OUT" : "AUX";
        es->sum2[c] += s.sum2;
        es->peak[c] = std::max(es->peak[c], s.peak);
        es->max_dc[c] = std::max(es->max_dc[c], std::fabs(s.mean - 1.0));
        es->max_abs_float[c] = std::max(es->max_abs_float[c], s.max_abs_float);
        nonfinite_total += s.nonfinite;
        if (s.nonfinite) {
          problems += Format(" %s:%ld-non-finite", channel, s.nonfinite);
        }
        if (IsStuckAtRail(s)) {
          problems += Format(" %s:at-rail-%d-samples", channel, s.rail_run);
        }
        if (IsStuckDc(s)) {
          problems += Format(" %s:stuck-at-%.0f", channel, s.tail_mean);
        }
        if (IsSilent(s)) {
          const std::string why = SilentByDesign(r, c);
          if (!why.empty()) {
            ++es->silent_by_design;
            ++by_design;
            ++by_design_reasons[why];
            if (verbose) {
              std::printf("  silent by design: %d %s %s %s: %s\n", e,
                          kEngineNames[e], SettingName(r.setting).c_str(),
                          channel, why.c_str());
            }
          } else {
            problems += Format(" %s:silent", channel);
          }
        }
      }
      if (verbose || !problems.empty()) {
        std::printf(
            "  %s %-2d %-18s %-22s OUT pk %5d rms %7.1f dc %8.1f | "
            "AUX pk %5d rms %7.1f dc %8.1f |%s\n",
            problems.empty() ? "ok  " : "BAD ", e, kEngineNames[e],
            SettingName(r.setting).c_str(), r.ch[0].peak, r.ch[0].ac_rms,
            r.ch[0].mean - 1.0, r.ch[1].peak, r.ch[1].ac_rms,
            r.ch[1].mean - 1.0, problems.c_str());
      }
      if (!problems.empty()) {
        ++failed_runs;
        if (first_failure.empty()) {
          first_failure = Format("model %d %s, %s:%s", e, kEngineNames[e],
                                 SettingName(r.setting).c_str(),
                                 problems.c_str());
        }
      }
    }
  }

  std::printf("  %s, per model over %zu settings x %d s. int16 units "
              "(Voice::Frame), dBFS re 32767; |dc| is the largest mean offset "
              "of a run\n", kModeNames[mode], settings.size(), kSeconds);
  std::printf("  %-2s %-18s %6s %8s %6s %6s | %6s %8s %6s %6s | %s\n", "#",
              "model", "OUT pk", "OUT rms", "dBFS", "|dc|", "AUX pk",
              "AUX rms", "dBFS", "|dc|", "silent by design");
  for (int e = 0; e < kNumEngines; ++e) {
    const EngineSummary& es = summary[e];
    if (!es.samples) {
      continue;
    }
    const double rms_out = std::sqrt(es.sum2[0] / double(es.samples));
    const double rms_aux = std::sqrt(es.sum2[1] / double(es.samples));
    std::printf("  %-2d %-18s %6d %8.1f %6.1f %6.0f | %6d %8.1f %6.1f %6.0f | "
                "%d of %d\n", e, kEngineNames[e], es.peak[0], rms_out,
                Dbfs(rms_out), es.max_dc[0], es.peak[1], rms_aux,
                Dbfs(rms_aux), es.max_dc[1], es.silent_by_design,
                2 * es.runs);
  }
  float largest_float = 0.0f;
  int largest_float_engine = 0;
  for (int e = 0; e < kNumEngines; ++e) {
    for (int c = 0; c < 2; ++c) {
      if (summary[e].max_abs_float[c] > largest_float) {
        largest_float = summary[e].max_abs_float[c];
        largest_float_engine = e;
      }
    }
  }
  std::printf("  largest engine output before the int16 conversion: %.3f "
              "(model %d %s; full scale is about 1 / gain)\n", largest_float,
              largest_float_engine, kEngineNames[largest_float_engine]);
  for (std::map<std::string, int>::const_iterator it =
           by_design_reasons.begin(); it != by_design_reasons.end(); ++it) {
    std::printf("  silent by design, %3d outputs: %s\n", it->second,
                it->first.c_str());
  }

  Report(failed_runs == 0, check_name, Format(
      "%d models x %zu settings x %d s in blocks of %zu: %d bad runs, %ld "
      "non-finite samples, %d outputs silent by design%s%s",
      models, settings.size(), kSeconds, kBlock, failed_runs,
      nonfinite_total, by_design,
      first_failure.empty() ? "" : "; first: ", first_failure.c_str()));
}

// The string and modal models at TIMBRE 0, TRIG unpatched, are excited by
// dust of probability 5e-5 per sample (string_voice.cc, modal_voice.cc).
// stmlib's LCG, from its power-up seed 0x21, first returns a value below
// 5e-5 at draw 112021 (about 2.3 s at one draw per sample), so these settings
// are silent for the first 2 s on the module too. Check that the grains do
// come, a little later.
void CheckSparseDust() {
  Rig rig;
  std::vector<int16_t> out, aux;
  std::string detail;
  bool pass = true;
  const int models[2] = { 19, 20 };
  for (int k = 0; k < 2; ++k) {
    const Setting s = { 60.0f, 0.0f, 0.0f, 0.5f, false };
    RenderRun(&rig, models[k], s, MODE_UNPATCHED, &out, &aux, 8.0);
    size_t first = 0;
    long grains = 0;
    for (size_t i = 0; i < aux.size(); ++i) {
      // AUX carries the excitation itself.
      if (std::abs(aux[i] - 1) > 8) {
        if (!first) {
          first = i;
        }
        // Count onsets: a loud sample after 100 quiet ones.
        bool onset = true;
        for (size_t j = (i > 100 ? i - 100 : 0); j < i; ++j) {
          if (std::abs(aux[j] - 1) > 8) {
            onset = false;
            break;
          }
        }
        grains += onset;
      }
    }
    std::vector<int16_t> late(out.begin() + std::min(first, out.size()),
                              out.end());
    ChannelStats stats;
    Analyse(late.size() > size_t(kRate) ? late : out, &stats);
    const bool ok = first > size_t(kSeconds * kRate) && grains >= 2 &&
        !IsSilent(stats);
    pass = pass && ok;
    detail += Format("%smodel %d %s: first grain at %.3f s, %ld grains in "
                     "8 s, OUT rms %.0f LSB afterwards", k ? "; " : "",
                     models[k], kEngineNames[models[k]],
                     first ? double(first) / kRate : -1.0, grains,
                     stats.ac_rms);
  }
  Report(pass, "sparse_dust", detail);
}

// One voice, booted once, hopping between models every 0.1 s with random
// settings and TRIG pulses: every engine starts over whatever the others
// left in the shared buffer, as when MODEL is changed on the module.
void CheckEngineSwitching() {
  Rig rig;
  rig.Boot();
  Voice* voice = rig.voice;
  uint32_t rng = 12345;
  const size_t kSegmentBlocks = size_t(0.1 * kRate) / kBlock;
  const int kSegments = 480;
  long nonfinite = 0;
  int wrong_engine = 0;
  int stuck = 0;
  int visits[kNumEngines] = { 0 };
  Patch patch;
  Modulations m;
  Voice::Frame frames[plaits::kMaxBlockSize];
  size_t block = 0;
  std::string first_problem;
  for (int segment = 0; segment < kSegments; ++segment) {
    rng = rng * 1664525U + 1013904223U;
    const int engine = int((rng >> 16) % kNumEngines);
    ++visits[engine];
    Setting s;
    s.sweep = false;
    rng = rng * 1664525U + 1013904223U;
    s.note = 24.0f + float((rng >> 8) % 73);
    rng = rng * 1664525U + 1013904223U;
    s.harmonics = float((rng >> 8) % 1001) / 1000.0f;
    rng = rng * 1664525U + 1013904223U;
    s.timbre = float((rng >> 8) % 1001) / 1000.0f;
    rng = rng * 1664525U + 1013904223U;
    s.morph = float((rng >> 8) % 1001) / 1000.0f;
    const Mode mode = (segment % 3) == 0 ? MODE_UNPATCHED : MODE_TRIGGERED;
    int lo = 32767, hi = -32768;
    for (size_t b = 0; b < kSegmentBlocks; ++b, ++block) {
      SetControls(engine, s, mode, block, &patch, &m);
      voice->Render(patch, m, frames, kBlock);
      const float* f[2] = {
        voice->*Member(VoiceOutBuffer()), voice->*Member(VoiceAuxBuffer())
      };
      for (size_t i = 0; i < kBlock; ++i) {
        for (int c = 0; c < 2; ++c) {
          if (!std::isfinite(f[c][i])) {
            ++nonfinite;
          }
        }
        lo = std::min(lo, int(frames[i].out));
        hi = std::max(hi, int(frames[i].out));
      }
    }
    if (voice->active_engine() != engine) {
      ++wrong_engine;
    }
    // Pinned to a rail for the whole segment: a filter that blew up.
    if (hi == lo && (hi >= 32767 || lo <= -32768)) {
      ++stuck;
      if (first_problem.empty()) {
        first_problem = Format("segment %d model %d at %d", segment, engine,
                               hi);
      }
    }
  }
  int visited = 0;
  for (int e = 0; e < kNumEngines; ++e) {
    visited += visits[e] != 0;
  }
  Report(nonfinite == 0 && wrong_engine == 0 && stuck == 0 &&
         visited == kNumEngines, "engine_switching", Format(
      "%d switches, 0.1 s each, %d of %d models visited: %ld non-finite "
      "samples, %d wrong active_engine(), %d segments pinned to a rail%s%s",
      kSegments, visited, kNumEngines, nonfinite, wrong_engine, stuck,
      first_problem.empty() ? "" : "; first: ", first_problem.c_str()));
}

// Rising zero crossings (linear interpolation) and a least-squares line
// through them: the period in samples, and how far the crossings stray.
struct PeriodMeasurement {
  double period;
  int crossings;
  double max_jitter;  // samples
  double thd_n_db;    // residual after fitting one sine + DC, re the sine
  double amplitude;
};

PeriodMeasurement MeasurePeriod(const std::vector<int16_t>& x, size_t start) {
  PeriodMeasurement m;
  const size_t n = x.size();
  double mean = 0.0;
  for (size_t i = start; i < n; ++i) {
    mean += x[i];
  }
  mean /= double(n - start);
  std::vector<double> t;
  for (size_t i = start + 1; i < n; ++i) {
    const double y0 = x[i - 1] - mean;
    const double y1 = x[i] - mean;
    if (y0 < 0.0 && y1 >= 0.0) {
      t.push_back(double(i - 1) + (-y0) / (y1 - y0));
    }
  }
  m.crossings = int(t.size());
  // Least squares t_k = a + period * k.
  const double count = double(t.size());
  double sk = 0.0, st = 0.0, skk = 0.0, skt = 0.0;
  for (size_t k = 0; k < t.size(); ++k) {
    sk += double(k);
    st += t[k];
    skk += double(k) * double(k);
    skt += double(k) * t[k];
  }
  m.period = (count * skt - sk * st) / (count * skk - sk * sk);
  const double a = (st - m.period * sk) / count;
  m.max_jitter = 0.0;
  for (size_t k = 0; k < t.size(); ++k) {
    m.max_jitter = std::max(m.max_jitter,
                            std::fabs(t[k] - (a + m.period * double(k))));
  }

  // Fit x = A cos(wn) + B sin(wn) + C at that frequency (normal equations).
  const double w = 2.0 * M_PI / m.period;
  double g[3][3] = { { 0 } };
  double h[3] = { 0 };
  for (size_t i = start; i < n; ++i) {
    const double basis[3] = { std::cos(w * double(i)), std::sin(w * double(i)),
                              1.0 };
    for (int r = 0; r < 3; ++r) {
      for (int c = 0; c < 3; ++c) {
        g[r][c] += basis[r] * basis[c];
      }
      h[r] += basis[r] * x[i];
    }
  }
  // Gaussian elimination, 3x3.
  for (int p = 0; p < 3; ++p) {
    for (int r = p + 1; r < 3; ++r) {
      const double f = g[r][p] / g[p][p];
      for (int c = p; c < 3; ++c) {
        g[r][c] -= f * g[p][c];
      }
      h[r] -= f * h[p];
    }
  }
  double coefficients[3];
  for (int r = 2; r >= 0; --r) {
    double v = h[r];
    for (int c = r + 1; c < 3; ++c) {
      v -= g[r][c] * coefficients[c];
    }
    coefficients[r] = v / g[r][r];
  }
  double residual2 = 0.0;
  for (size_t i = start; i < n; ++i) {
    const double fit = coefficients[0] * std::cos(w * double(i)) +
        coefficients[1] * std::sin(w * double(i)) + coefficients[2];
    residual2 += (x[i] - fit) * (x[i] - fit);
  }
  m.amplitude = std::hypot(coefficients[0], coefficients[1]);
  const double residual_rms = std::sqrt(residual2 / double(n - start));
  m.thd_n_db = 20.0 * std::log10(residual_rms / (m.amplitude / std::sqrt(2.0)));
  return m;
}

void RenderTone(Rig* rig, float note, double seconds,
                std::vector<int16_t>* out) {
  rig->Boot();
  const size_t blocks = size_t(seconds * kRate) / kBlock;
  out->resize(blocks * kBlock);
  Patch patch;
  Modulations m;
  memset(&patch, 0, sizeof(patch));
  memset(&m, 0, sizeof(m));
  patch.engine = 10;  // 2-op FM
  patch.note = note;
  patch.harmonics = 0.5f;
  patch.timbre = 0.0f;  // modulation index 0: the carrier alone, a sine
  patch.morph = 0.5f;   // feedback 0
  patch.decay = 0.5f;
  Voice::Frame frames[plaits::kMaxBlockSize];
  for (size_t b = 0; b < blocks; ++b) {
    rig->voice->Render(patch, m, frames, kBlock);
    for (size_t i = 0; i < kBlock; ++i) {
      (*out)[b * kBlock + i] = frames[i].out;
    }
  }
}

void CheckTuning() {
  Rig rig;
  std::vector<int16_t> out;
  const size_t start = size_t(0.25 * kRate);

  RenderTone(&rig, 69.0f, 4.0, &out);
  const PeriodMeasurement a4 = MeasurePeriod(out, start);
  RenderTone(&rig, 57.0f, 4.0, &out);
  const PeriodMeasurement a3 = MeasurePeriod(out, start);
  RenderTone(&rig, 81.0f, 4.0, &out);
  const PeriodMeasurement a5 = MeasurePeriod(out, start);

  const bool clean = a4.thd_n_db < -60.0 && a4.max_jitter < 0.01 &&
      a4.crossings > 1000;
  Report(clean, "tuning_sine", Format(
      "model 10 (2-op FM), note 69, timbre 0, morph 0.5: %d periods, "
      "amplitude %.0f LSB, THD+N %.1f dB, zero-crossing jitter %.5f samples",
      a4.crossings, a4.amplitude, a4.thd_n_db, a4.max_jitter));

  // On the Seed every sample lasts 1 / 48014.32 s.
  const double f_port = kSeedSampleRateNominal / a4.period;
  const double f_port_exact = kSeedSampleRate / a4.period;
  const double error = (f_port - 440.0) / 440.0;
  // What the DSP thinks its rate is: the period scales with
  // kCorrectedSampleRate (a0 = 55 Hz / kCorrectedSampleRate).
  const double effective_rate = a4.period * 440.0;
  const double rate_error =
      (effective_rate - double(plaits::kCorrectedSampleRate)) /
      double(plaits::kCorrectedSampleRate);
  // Upstream's constant: the same patch would have a period shorter by
  // 47872.34 / 48014.32, played at the Seed's 48014.32 Hz.
  const double period_upstream = a4.period * kUpstreamCorrectedSampleRate /
      double(plaits::kCorrectedSampleRate);
  const double f_upstream = kSeedSampleRateNominal / period_upstream;
  const double cents_port = 1200.0 * std::log2(f_port / 440.0);
  const double cents_upstream = 1200.0 * std::log2(f_upstream / 440.0);
  Report(std::fabs(error) < 0.0005 && std::fabs(rate_error) < 1.0e-5,
         "tuning_a440", Format(
      "period %.5f samples -> %.4f Hz at 48014.32 Hz (%.4f Hz at the exact "
      "%.4f), %+.4f %% / %+.3f cents; DSP's rate %.2f Hz; with upstream's "
      "47872.34: period %.5f -> %.4f Hz, %+.2f cents",
      a4.period, f_port, f_port_exact, kSeedSampleRate, error * 100.0,
      cents_port, effective_rate, period_upstream, f_upstream,
      cents_upstream));

  const double octave_down = a3.period / a4.period;
  const double octave_up = a4.period / a5.period;
  Report(std::fabs(octave_down - 2.0) < 1.0e-4 &&
         std::fabs(octave_up - 2.0) < 1.0e-4, "tuning_octaves", Format(
      "note 57: %.4f Hz, note 81: %.4f Hz at 48014.32 Hz; period ratios %.6f, "
      "%.6f",
      kSeedSampleRateNominal / a3.period, kSeedSampleRateNominal / a5.period,
      octave_down, octave_up));
}

// Renders `seconds` more of one model on a running voice; *block carries the
// time (and the TRIG gate timing) on from the previous call.
void RenderMore(Rig* rig, int engine, const Setting& s, Mode mode,
                size_t* block, double seconds, std::vector<int16_t>* out,
                long* nonfinite) {
  const size_t blocks = size_t(seconds * kRate) / kBlock;
  Patch patch;
  Modulations m;
  Voice::Frame frames[plaits::kMaxBlockSize];
  for (size_t b = 0; b < blocks; ++b, ++*block) {
    SetControls(engine, s, mode, *block, &patch, &m);
    rig->voice->Render(patch, m, frames, kBlock);
    const float* f[2] = {
      rig->voice->*Member(VoiceOutBuffer()),
      rig->voice->*Member(VoiceAuxBuffer())
    };
    for (size_t i = 0; i < kBlock; ++i) {
      for (int c = 0; c < 2; ++c) {
        if (!std::isfinite(f[c][i])) {
          ++*nonfinite;
        }
      }
      out->push_back(frames[i].out);
    }
  }
}

double AcRms(const std::vector<int16_t>& x, size_t begin, size_t end) {
  double sum = 0.0, sum2 = 0.0;
  for (size_t i = begin; i < end; ++i) {
    sum += x[i];
    sum2 += double(x[i]) * x[i];
  }
  const double n = double(end - begin);
  return std::sqrt(std::max(sum2 / n - (sum / n) * (sum / n), 0.0));
}

void CheckUserData() {
  using plaitsy::hal::flash_erase_calls;
  using plaitsy::hal::flash_write_calls;
  using plaitsy::hal::flash_last_erase;
  using plaitsy::hal::flash_last_write;
  using plaitsy::hal::flash_model;

  UserData user_data;
  const int kSize = UserData::SIZE;

  // Power-up with erased flash: no custom data for any model.
  UserData::Init();
  int tagged = 0;
  for (int slot = 0; slot < kNumEngines; ++slot) {
    tagged += user_data.ptr(slot) != NULL;
  }
  Report(tagged == 0 && flash_write_calls == 0, "user_data_blank", Format(
      "erased flash (0xFF): ptr() NULL for all %d slots (%d not), so the "
      "6-op models use the factory banks", kNumEngines, tagged));

  // A DX7 bank as Plaits' web tool sends it: 32 packed patches (here the
  // factory bank 1, i.e. fm_patches_table[0]), the last two bytes the range
  // of models that may take it: 6-op models 2..4.
  std::vector<uint8_t> block(plaits::fm_patches_table[0],
                             plaits::fm_patches_table[0] + kSize);
  block[kSize - 2] = 2;
  block[kSize - 1] = 4;

  // Model 3 (6-op FM bank 2), TRIG patched: factory bank 2 first.
  Setting s;
  s.sweep = false;
  s.note = 60.0f;
  s.harmonics = 0.3f;  // preset 10 of 32
  s.timbre = 0.5f;
  s.morph = 0.5f;
  Rig z;
  z.Boot();
  std::vector<int16_t> z_out;
  size_t z_block = 0;
  long z_nonfinite = 0;
  RenderMore(&z, 3, s, MODE_TRIGGERED, &z_block, 1.0, &z_out, &z_nonfinite);

  // Model 2 (factory bank 1), from power-up, for comparison.
  Rig y;
  y.Boot();
  std::vector<int16_t> y_out;
  size_t y_block = 0;
  long y_nonfinite = 0;
  RenderMore(&y, 2, s, MODE_TRIGGERED, &y_block, 2.0, &y_out, &y_nonfinite);

  // What main.cc does at the end of a transfer, with model 3 active.
  const int slot = z.voice->active_engine();
  const bool saved = user_data.Save(&block[0], slot);
  z.voice->ReloadUserData();
  const uint8_t* p3 = user_data.ptr(3);
  const uint8_t* p2 = user_data.ptr(2);
  const uint8_t* p4 = user_data.ptr(4);
  bool content_ok = p3 != NULL &&
      memcmp(p3, plaits::fm_patches_table[0], kSize - 2) == 0 &&
      p3[kSize - 2] == 'U' && p3[kSize - 1] == ' ' + 3;
  Report(saved && slot == 3 && p3 != NULL && p2 == NULL && p4 == NULL &&
         content_ok, "user_data_save", Format(
      "Save(block allowing 2..4, active model %d) = %s; ptr(3) %s, ptr(2) "
      "%s, ptr(4) %s; RAM copy holds the bank and the tag 'U', ' '+3: %s",
      slot, saved ? "true" : "false", p3 ? "set" : "NULL",
      p2 ? "set" : "NULL", p4 ? "set" : "NULL", content_ok ? "yes" : "no"));

  // Keep playing model 3: now with the received bank.
  const size_t reload_at = z_out.size();
  RenderMore(&z, 3, s, MODE_TRIGGERED, &z_block, 1.0, &z_out, &z_nonfinite);
  const double rms_before = AcRms(z_out, 0, reload_at);
  const double rms_after = AcRms(z_out, reload_at, z_out.size());

  // Model 3 with the received bank, from power-up, must play exactly what
  // model 2 plays with the same bank from its factory table.
  Rig x;
  x.Boot();
  std::vector<int16_t> x_out;
  size_t x_block = 0;
  long x_nonfinite = 0;
  RenderMore(&x, 3, s, MODE_TRIGGERED, &x_block, 2.0, &x_out, &x_nonfinite);
  size_t same_as_bank_1 = 0, same_as_factory_3 = 0;
  for (size_t i = 0; i < x_out.size(); ++i) {
    same_as_bank_1 += x_out[i] == y_out[i];
  }
  for (size_t i = 0; i < reload_at; ++i) {
    same_as_factory_3 += x_out[i] == z_out[i];
  }
  // For information: after the reload rig z plays the received patches, but
  // from its own voice state, so it need not match model 2 sample for
  // sample.
  size_t z_after_like_y = 0;
  for (size_t i = reload_at; i < z_out.size(); ++i) {
    z_after_like_y += z_out[i] == y_out[i];
  }
  Report(z_nonfinite == 0 && x_nonfinite == 0 && y_nonfinite == 0 &&
         rms_after > 30.0 && same_as_bank_1 == x_out.size() &&
         same_as_factory_3 < reload_at / 2, "user_data_render",
         Format(
      "model 3 before / after ReloadUserData(): rms %.0f / %.0f LSB, %ld "
      "non-finite; from power-up with the received bank it is sample-exact "
      "with model 2's factory bank 1 (%zu of %zu samples) and unlike its own "
      "factory bank 2 (%zu of %zu equal); after the reload %zu of %zu "
      "samples match model 2's",
      rms_before, rms_after, z_nonfinite + x_nonfinite + y_nonfinite,
      same_as_bank_1, x_out.size(), same_as_factory_3, reload_at,
      z_after_like_y, z_out.size() - reload_at));

  // Not for this model: Save() refuses and changes nothing.
  std::vector<uint8_t> other(kSize, 0x11);
  other[kSize - 2] = 2;
  other[kSize - 1] = 4;
  const bool refused_5 = !user_data.Save(&other[0], 5);
  const bool refused_1 = !user_data.Save(&other[0], 1);
  const bool unchanged = user_data.ptr(3) != NULL &&
      memcmp(user_data.ptr(3), plaits::fm_patches_table[0], kSize - 2) == 0 &&
      other[kSize - 2] == 2 && other[kSize - 1] == 4;
  Report(refused_5 && refused_1 && unchanged, "user_data_refuse", Format(
      "Save(range 2..4, slot 5) refused: %s, slot 1 refused: %s, copy and "
      "rx buffer unchanged: %s", refused_5 ? "yes" : "no",
      refused_1 ? "yes" : "no", unchanged ? "yes" : "no"));

  // The main loop's Persist(): one erase and one write of the 4 kB block at
  // 0x10000; then nothing until the next Save().
  const int erases_before = flash_erase_calls;
  const int writes_before = flash_write_calls;
  UserData::Persist();
  const int erases = flash_erase_calls - erases_before;
  const int writes = flash_write_calls - writes_before;
  const bool where_ok = flash_last_erase[0] == 0x10000 &&
      flash_last_erase[1] == uint32_t(kSize) &&
      flash_last_write[0] == 0x10000 && flash_last_write[1] == uint32_t(kSize);
  const bool flash_ok = memcmp(&flash_model[0x10000], user_data.ptr(3),
                               kSize) == 0;
  UserData::Persist();
  const bool idle = flash_erase_calls - erases_before == erases &&
      flash_write_calls - writes_before == writes;
  // Power cycle: Init() reads the block back.
  UserData::Init();
  const uint8_t* reloaded = user_data.ptr(3);
  const bool back_ok = reloaded != NULL && user_data.ptr(2) == NULL &&
      memcmp(reloaded, plaits::fm_patches_table[0], kSize - 2) == 0;
  Report(erases == 1 && writes == 1 && where_ok && flash_ok && idle &&
         back_ok, "user_data_persist", Format(
      "Persist(): %d erase + %d write at 0x%05x (%u bytes), flash holds the "
      "copy: %s; second Persist() idle: %s; after Init() (power cycle) "
      "ptr(3) %s, ptr(2) %s",
      erases, writes, flash_last_write[0], flash_last_write[1],
      flash_ok ? "yes" : "no", idle ? "yes" : "no",
      reloaded ? "set" : "NULL", user_data.ptr(2) ? "set" : "NULL"));

  // The wavetable model reads its custom waves from the RAM copy while it
  // plays: 64 wave numbers (>= 192: custom) then 15 custom waves of 132
  // int16 (integrated, as Plaits' tool sends them).
  std::vector<uint8_t> waves(kSize, 0);
  for (int i = 0; i < 64; ++i) {
    waves[i] = uint8_t(192 + i % 15);
  }
  int16_t* custom = reinterpret_cast<int16_t*>(&waves[64]);
  for (int w = 0; w < 15; ++w) {
    double integral = 0.0;
    for (int i = 0; i < 132; ++i) {
      integral += std::sin(2.0 * M_PI * (w + 1) * i / 128.0) * 200.0;
      custom[w * 132 + i] = int16_t(std::lrint(integral));
    }
  }
  waves[kSize - 2] = 13;
  waves[kSize - 1] = 13;
  Rig wt;
  wt.Boot();
  Setting sw;
  sw.sweep = false;
  sw.note = 48.0f;
  sw.harmonics = 0.5f;  // bank 4 of 4, the custom one
  sw.timbre = 0.5f;
  sw.morph = 0.5f;
  std::vector<int16_t> wt_out;
  size_t wt_block = 0;
  long wt_nonfinite = 0;
  RenderMore(&wt, 13, sw, MODE_UNPATCHED, &wt_block, 0.5, &wt_out,
             &wt_nonfinite);
  const bool wt_saved = user_data.Save(&waves[0], wt.voice->active_engine());
  wt.voice->ReloadUserData();
  const size_t wt_reload = wt_out.size();
  RenderMore(&wt, 13, sw, MODE_UNPATCHED, &wt_block, 1.0, &wt_out,
             &wt_nonfinite);
  const double wt_rms = AcRms(wt_out, wt_reload, wt_out.size());
  // The engine reads int16 waves at ptr + 64: the copy is aligned(4).
  const bool wt_tagged = user_data.ptr(13) != NULL &&
      user_data.ptr(3) == NULL &&
      reinterpret_cast<uintptr_t>(user_data.ptr(13)) % 4 == 0;

  // The wave terrain model: a custom terrain is the ninth, at HARMONICS 1.
  std::vector<uint8_t> terrain(kSize);
  for (int i = 0; i < kSize; ++i) {
    const int u = i % 64, v = i / 64;
    terrain[i] = uint8_t(int8_t(std::lrint(
        100.0 * std::sin(u * 0.2) * std::cos(v * 0.15))));
  }
  terrain[kSize - 2] = 5;
  terrain[kSize - 1] = 5;
  Rig tr;
  tr.Boot();
  Setting st = sw;
  st.harmonics = 1.0f;
  std::vector<int16_t> tr_out;
  size_t tr_block = 0;
  long tr_nonfinite = 0;
  RenderMore(&tr, 5, st, MODE_UNPATCHED, &tr_block, 0.2, &tr_out,
             &tr_nonfinite);
  const bool tr_saved = user_data.Save(&terrain[0], tr.voice->active_engine());
  tr.voice->ReloadUserData();
  const size_t tr_reload = tr_out.size();
  RenderMore(&tr, 5, st, MODE_UNPATCHED, &tr_block, 1.0, &tr_out,
             &tr_nonfinite);
  const double tr_rms = AcRms(tr_out, tr_reload, tr_out.size());
  Report(wt_saved && wt_tagged && wt_nonfinite == 0 && wt_rms > 30.0 &&
         tr_saved && user_data.ptr(5) != NULL && tr_nonfinite == 0 &&
         tr_rms > 30.0, "user_data_waves", Format(
      "custom wavetable on model 13 (read from the RAM copy while playing): "
      "saved %s, tagged and 4-byte aligned %s, rms %.0f LSB, %ld non-finite; "
      "custom terrain on model 5: saved %s, rms %.0f LSB, %ld non-finite",
      wt_saved ? "yes" : "no", wt_tagged ? "yes" : "no", wt_rms, wt_nonfinite,
      tr_saved ? "yes" : "no", tr_rms, tr_nonfinite));
}

}  // namespace

int main(int argc, char** argv) {
  bool quick = false;
  for (int i = 1; i < argc; ++i) {
    if (!strcmp(argv[i], "--quick")) {
      quick = true;
    } else if (!strcmp(argv[i], "--verbose")) {
      verbose = true;
    } else if (!strcmp(argv[i], "--engine") && i + 1 < argc) {
      only_engine = atoi(argv[++i]);
    } else {
      std::fprintf(stderr,
                   "usage: %s [--quick] [--verbose] [--engine N]\n", argv[0]);
      return 2;
    }
  }

  std::printf("Plaitsy voice test: Plaits 1.2 DSP (vendor/) through the "
              "port's dsp.h (kCorrectedSampleRate %.2f Hz) and user_data\n",
              double(plaits::kCorrectedSampleRate));

  CheckClockDerivation();
  CheckEngineMemory();

  std::vector<Setting> settings;
  const float levels[3] = { 0.0f, 0.5f, 1.0f };
  const float notes[3] = { 36.0f, 60.0f, 84.0f };
  for (int n = 0; n < 3; ++n) {
    for (int h = 0; h < 3; ++h) {
      for (int t = 0; t < 3; ++t) {
        for (int m = 0; m < 3; ++m) {
          if (quick && !(h == t && t == m)) {
            continue;
          }
          Setting s = { notes[n], levels[h], levels[t], levels[m], false };
          settings.push_back(s);
        }
      }
    }
  }
  Setting sweep = { 0.0f, 0.0f, 0.0f, 0.0f, true };
  settings.push_back(sweep);

  CheckEngines(MODE_UNPATCHED, settings, "engines_unpatched");
  CheckEngines(MODE_TRIGGERED, settings, "engines_triggered");
  std::vector<Setting> sweep_only(1, sweep);
  CheckEngines(MODE_CV_PATCHED, sweep_only, "engines_cv_patched");
  CheckSparseDust();
  CheckEngineSwitching();
  CheckTuning();
  CheckUserData();

  std::printf("%s: %d check(s) failed\n", num_failures ? "FAIL" : "PASS",
              num_failures);
  return num_failures;
}
