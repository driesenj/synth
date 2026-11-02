// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: MODAL (src/fx/modal_reverb.cc).

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "fx/modal_reverb.h"
#include "test_support.h"

using sidefx::Frame;
using sidefx::ModalReverb;
using sidefx::ProcessContext;
using sidefx::kBlockSize;

namespace {

const float kFs = 48014.32f;
const int kNumParams = 7;
enum { PITCH, STRUCT, DECAY, BRIGHT, DENSITY, WIDTH, DRIFT };

struct Fixture {
  test::TestMemory memory;
  ModalReverb* block;
  Fixture() : memory(8u << 20, 64u << 10) {
    block = memory.internal().Create<ModalReverb>();
    if (!block->Init(memory.memory())) {
      block = NULL;
    }
  }
};

void Defaults(float* params) {
  ModalReverb block;
  const sidefx::BlockInfo& info = block.info();
  for (int i = 0; i < info.num_params; ++i) {
    params[i] = info.params[i].default_value;
  }
}

// Runs `samples` samples of in (mono, both channels) through the block.
void Run(ModalReverb* block, const ProcessContext& context,
         const float* params, const std::vector<float>& in,
         std::vector<Frame>* out) {
  out->resize(in.size());
  Frame input[kBlockSize];
  for (size_t start = 0; start < in.size(); start += kBlockSize) {
    const size_t n = in.size() - start < kBlockSize ? in.size() - start
                                                     : kBlockSize;
    for (size_t i = 0; i < n; ++i) {
      input[i].l = input[i].r = in[start + i];
    }
    block->Process(context, params, input, &(*out)[start], n);
  }
}

// The energy at hz (Goertzel over the whole signal), left channel.
double Power(const std::vector<Frame>& x, double hz) {
  const double w = 2.0 * M_PI * hz / kFs;
  const double coefficient = 2.0 * cos(w);
  double s1 = 0.0, s2 = 0.0;
  for (size_t i = 0; i < x.size(); ++i) {
    const double s = x[i].l + coefficient * s1 - s2;
    s2 = s1;
    s1 = s;
  }
  return s1 * s1 + s2 * s2 - coefficient * s1 * s2;
}

// RT60 from the slope of the energy envelope (50 ms windows) between
// `from` seconds and where it has fallen 40 dB below the window at `from`.
float MeasureRt60(const std::vector<Frame>& x, float from) {
  const size_t window = 2400;
  std::vector<double> db;
  for (size_t start = 0; start + window <= x.size(); start += window) {
    double e = 1e-30;
    for (size_t i = start; i < start + window; ++i) {
      e += double(x[i].l) * x[i].l + double(x[i].r) * x[i].r;
    }
    db.push_back(10.0 * log10(e));
  }
  const size_t first = size_t(from * kFs / window);
  double sx = 0, sy = 0, sxx = 0, sxy = 0;
  int n = 0;
  for (size_t k = first; k < db.size() && db[k] > db[first] - 40.0; ++k) {
    const double t = double(k * window) / kFs;
    sx += t;
    sy += db[k];
    sxx += t * t;
    sxy += t * db[k];
    ++n;
  }
  if (n < 3) {
    return 0.0f;
  }
  const double slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
  return slope < 0.0 ? float(-60.0 / slope) : 1e9f;
}

std::vector<float> Impulse(size_t samples) {
  std::vector<float> x(samples, 0.0f);
  x[0] = 1.0f;
  return x;
}

float MaxStep(const std::vector<Frame>& x, size_t from) {
  float m = 0.0f;
  for (size_t i = from + 1; i < x.size(); ++i) {
    m = fmaxf(m, fabsf(x[i].l - x[i - 1].l));
    m = fmaxf(m, fabsf(x[i].r - x[i - 1].r));
  }
  return m;
}

}  // namespace

TEST(modal_reverb, init_and_silence) {
  Fixture f;
  CHECK(f.block != NULL);
  if (!f.block) {
    return;
  }
  test::Note("internal arena use: %u bytes (object %u)",
             unsigned(f.memory.internal().used()),
             unsigned(sizeof(ModalReverb)));
  CHECK(f.memory.internal().used() < 8192);
  CHECK(f.memory.external().used() == 0);
  CHECK(f.block->info().num_params == kNumParams);

  // Ring it, reset, then silence must give exact silence.
  float params[kNumParams];
  Defaults(params);
  ProcessContext context = test::Context(test::Tempo120(), 0);
  std::vector<Frame> out;
  std::vector<float> noise(48000);
  uint32_t seed = 1;
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = test::Noise(&seed);
  }
  Run(f.block, context, params, noise, &out);
  f.block->Reset();
  Run(f.block, context, params, std::vector<float>(48000, 0.0f), &out);
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(modal_reverb, stability) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  uint32_t seed = 7;
  float peak = 0.0f;
  bool finite = true;
  Frame in[kBlockSize], out[kBlockSize];
  // 20 s of noise, every parameter random every block, sync bits random.
  for (int block = 0; block < int(20.0f * kFs / kBlockSize); ++block) {
    for (int p = 0; p < kNumParams; ++p) {
      params[p] = 0.5f + 0.5f * test::Noise(&seed);
    }
    context.sync_mask = (test::Noise(&seed) > 0.0f) ? 0xffff : 0;
    for (size_t i = 0; i < kBlockSize; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    f.block->Process(context, params, in, out, kBlockSize);
    for (size_t i = 0; i < kBlockSize; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  // Every parameter at 0, then at 1 (20 s decay), with noise and with a
  // +-4 sine right at the fundamental (the worst case for a resonator).
  context.sync_mask = 0;
  for (int setting = 0; setting < 4; ++setting) {
    for (int p = 0; p < kNumParams; ++p) {
      params[p] = (setting & 1) ? 1.0f : 0.0f;
    }
    const float hz = 65.40639f * ((setting & 1) ? 4.0f : 0.25f);
    float phase = 0.0f;
    for (int block = 0; block < int(5.0f * kFs / kBlockSize); ++block) {
      for (size_t i = 0; i < kBlockSize; ++i) {
        if (setting < 2) {
          in[i].l = test::Noise(&seed);
          in[i].r = test::Noise(&seed);
        } else {
          in[i].l = in[i].r = 4.0f * sinf(phase);
          phase += 2.0f * float(M_PI) * hz / kFs;
          if (phase > 2.0f * float(M_PI)) {
            phase -= 2.0f * float(M_PI);
          }
        }
      }
      f.block->Process(context, params, in, out, kBlockSize);
      for (size_t i = 0; i < kBlockSize; ++i) {
        finite = finite && test::Finite(out[i]);
        peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
      }
    }
  }
  test::Note("peak %.3f", peak);
  CHECK(finite);
  CHECK(peak < 4.0f);
}

TEST(modal_reverb, level) {
  // Noise in at the defaults: a sensible wet level.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  std::vector<float> noise(size_t(4.0f * kFs));
  uint32_t seed = 3;
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = test::Noise(&seed);
  }
  std::vector<Frame> out;
  Run(f.block, context, params, noise, &out);
  double e = 0.0;
  for (size_t i = out.size() / 2; i < out.size(); ++i) {
    e += double(out[i].l) * out[i].l;
  }
  const double rms = sqrt(e / double(out.size() / 2));
  test::Note("noise rms out %.3f (in 0.577)", rms);
  CHECK(rms > 0.1 && rms < 1.0);

  // A hit at the shortest and longest decays: within +-10 dB of each other.
  float peaks[2];
  for (int k = 0; k < 2; ++k) {
    f.block->Reset();
    params[DECAY] = float(k);
    Run(f.block, context, params, Impulse(24000), &out);
    peaks[k] = 0.0f;
    for (size_t i = 0; i < out.size(); ++i) {
      peaks[k] = fmaxf(peaks[k], fabsf(out[i].l));
    }
  }
  test::Note("impulse peak: decay min %.4f, max %.4f", peaks[0], peaks[1]);
  CHECK(peaks[0] > 0.0f && peaks[1] > 0.0f);
  CHECK(peaks[0] / peaks[1] < 4.0f && peaks[1] / peaks[0] < 4.0f);
}

TEST(modal_reverb, resonates_at_pitch) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[STRUCT] = 0.0f;   // harmonic
  params[DENSITY] = 0.0f;  // 8 modes
  params[BRIGHT] = 1.0f;
  params[DECAY] = sidefx::ExpUnmap(1.0f, 0.1f, 20.0f);
  params[WIDTH] = 0.0f;
  params[DRIFT] = 0.0f;
  for (int octave = 0; octave < 2; ++octave) {
    params[PITCH] = octave ? 0.75f : 0.5f;  // C2, C3
    const double f0 = 65.40639 * (octave ? 2.0 : 1.0);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(48000), &out);
    const double on = Power(out, f0) + Power(out, 2 * f0) + Power(out, 3 * f0);
    const double off = Power(out, 1.5 * f0) + Power(out, 2.5 * f0) +
        Power(out, 3.5 * f0);
    const double below = Power(out, f0 * 0.5);
    test::Note("f0 %.2f Hz: on/off %.1f dB, below %.1f dB", f0,
               10.0 * log10(on / off), 10.0 * log10(on / below));
    CHECK(on > 100.0 * off);
    CHECK(on > 100.0 * below);
  }
}

TEST(modal_reverb, bell_is_inharmonic) {
  // The bell's tierce (2.366 f0) rings, a harmonic body has nothing there.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[DENSITY] = 0.0f;
  params[BRIGHT] = 1.0f;
  params[DECAY] = sidefx::ExpUnmap(1.0f, 0.1f, 20.0f);
  params[DRIFT] = 0.0f;
  params[PITCH] = 0.5f;
  double tierce[2], octave[2];
  for (int k = 0; k < 2; ++k) {
    params[STRUCT] = k ? 2.0f / 3.0f : 0.0f;
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(48000), &out);
    tierce[k] = Power(out, 65.40639 * 2.366);
    octave[k] = Power(out, 65.40639 * 2.0);
  }
  test::Note("tierce/octave: harmonic %.1f dB, bell %.1f dB",
             10.0 * log10(tierce[0] / octave[0]),
             10.0 * log10(tierce[1] / octave[1]));
  CHECK(tierce[1] / octave[1] > 0.1);
  CHECK(tierce[0] / octave[0] < 0.001);
}

TEST(modal_reverb, rt60) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[BRIGHT] = 1.0f;  // every mode decays alike
  params[DRIFT] = 0.0f;
  const float decays[] = { 0.3f, 2.0f, 8.0f };
  for (int k = 0; k < 3; ++k) {
    params[DECAY] = sidefx::ExpUnmap(decays[k], 0.1f, 20.0f);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(kFs * decays[k] * 0.8f +
                                                 kFs * 0.2f)), &out);
    const float rt60 = MeasureRt60(out, 0.05f);
    test::Note("DECAY %.1f s: measured RT60 %.2f s", decays[k], rt60);
    CHECK(rt60 > 0.5f * decays[k] && rt60 < 2.0f * decays[k]);
  }
}

TEST(modal_reverb, bright_tilts_decay) {
  // At BRIGHT 0 the spectrum darkens as it decays: the share of energy in
  // the sample-to-sample difference (a brightness measure) falls.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[DECAY] = sidefx::ExpUnmap(2.0f, 0.1f, 20.0f);
  params[DRIFT] = 0.0f;
  params[DENSITY] = 1.0f;
  float ratio[2];
  for (int k = 0; k < 2; ++k) {
    params[BRIGHT] = float(k);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(kFs)), &out);
    double brightness[2];
    for (int w = 0; w < 2; ++w) {
      const size_t start = w ? 24000 : 1;
      double e = 1e-30, d = 0.0;
      for (size_t i = start; i < start + 4800; ++i) {
        e += double(out[i].l) * out[i].l;
        const double step = out[i].l - out[i - 1].l;
        d += step * step;
      }
      brightness[w] = d / e;
    }
    ratio[k] = float(brightness[1] / brightness[0]);
  }
  test::Note("late/early brightness: BRIGHT 0 %.3f, BRIGHT 1 %.3f",
             ratio[0], ratio[1]);
  CHECK(ratio[0] < 0.7f * ratio[1]);
}

TEST(modal_reverb, width) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  for (int k = 0; k < 2; ++k) {
    params[WIDTH] = float(k);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(24000), &out);
    double lr = 0.0, ll = 1e-30, rr = 1e-30;
    bool same = true;
    for (size_t i = 0; i < out.size(); ++i) {
      lr += double(out[i].l) * out[i].r;
      ll += double(out[i].l) * out[i].l;
      rr += double(out[i].r) * out[i].r;
      same = same && out[i].l == out[i].r;
    }
    const double correlation = lr / sqrt(ll * rr);
    test::Note("WIDTH %d: L/R correlation %.3f", k, correlation);
    if (k == 0) {
      CHECK(same);
    } else {
      CHECK(correlation < 0.7);
    }
  }
}

TEST(modal_reverb, no_clicks) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[DECAY] = sidefx::ExpUnmap(0.5f, 0.1f, 20.0f);
  const size_t settle = size_t(kFs);
  const size_t length = 4500 * kBlockSize;  // 3 s
  std::vector<float> sine(length);
  for (size_t i = 0; i < length; ++i) {
    sine[i] = 0.5f * sinf(2.0f * float(M_PI) * 220.0f * float(i) / kFs);
  }
  // Each parameter jumps between two settings every 100 ms; the largest
  // step must stay near the largest step of either setting held still.
  // PITCH jumps an octave: a mode ringing at the low setting keeps its
  // amplitude at twice the frequency, so its steps double (that is the
  // pitch change, not a click): the low setting's reference counts twice.
  struct Jump { int param; float low, high; };
  const Jump kJumps[] = {
    { PITCH, 0.5f, 0.75f },
    { STRUCT, 0.15f, 0.85f },
    { DECAY, 0.15f, 0.85f },
    { BRIGHT, 0.0f, 1.0f },
    { DENSITY, 0.0f, 1.0f },
    { WIDTH, 0.0f, 1.0f },
    { DRIFT, 0.0f, 1.0f },
  };
  for (size_t j = 0; j < sizeof(kJumps) / sizeof(kJumps[0]); ++j) {
    const Jump& jump = kJumps[j];
    float reference = 0.0f;
    std::vector<Frame> out;
    for (int k = 0; k < 2; ++k) {
      Defaults(params);
      params[DECAY] = sidefx::ExpUnmap(0.5f, 0.1f, 20.0f);
      params[jump.param] = k ? jump.high : jump.low;
      f.block->Reset();
      Run(f.block, context, params, sine, &out);
      const float held = MaxStep(out, settle);
      reference = fmaxf(reference,
                        (jump.param == PITCH && k == 0) ? 2.0f * held : held);
    }
    Defaults(params);
    params[DECAY] = sidefx::ExpUnmap(0.5f, 0.1f, 20.0f);
    f.block->Reset();
    out.resize(length);
    Frame input[kBlockSize];
    for (size_t start = 0; start < length; start += kBlockSize) {
      params[jump.param] = ((start / 4800) & 1) ? jump.high : jump.low;
      for (size_t i = 0; i < kBlockSize; ++i) {
        input[i].l = input[i].r = sine[start + i];
      }
      f.block->Process(context, params, input, &out[start], kBlockSize);
    }
    const float jumping = MaxStep(out, settle);
    test::Note("%s jumps: max step %.4f, held %.4f",
               f.block->info().params[jump.param].name, jumping, reference);
    CHECK(jumping < 4.0f * reference);
  }
}

TEST(modal_reverb, format) {
  Fixture f;
  const sidefx::BlockInfo& info = f.block->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  for (int p = 0; p < info.num_params; ++p) {
    CHECK(strlen(info.params[p].name) <= 8);
    for (int synced = 0; synced < 2; ++synced) {
      ProcessContext context = test::Context(test::Tempo120(),
                                             synced ? 0xffff : 0);
      for (int v = 0; v <= 20; ++v) {
        char text[32];
        memset(text, 0, sizeof(text));
        f.block->Format(p, float(v) / 20.0f, context, text, 11);
        if (v % 10 == 0) {
          test::Note("%s %.1f%s: \"%s\"", info.params[p].name,
                     float(v) / 20.0f, synced ? " synced" : "", text);
        }
        CHECK(strlen(text) > 0 && strlen(text) <= 10);
      }
    }
  }
}

TEST(modal_reverb, synced_decay_follows_tempo) {
  Fixture f;
  float params[kNumParams];
  Defaults(params);
  params[BRIGHT] = 1.0f;
  params[DRIFT] = 0.0f;
  int bar = 0;
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, "1 BAR")) {
      bar = i;
    }
  }
  CHECK(bar > 0);
  params[DECAY] = sidefx::StepValue(bar, sidefx::kNumNoteValues);
  float rt60[2];
  for (int k = 0; k < 2; ++k) {
    sidefx::TempoState tempo = test::Tempo120();
    tempo.beat_seconds = k ? 0.5f : 0.25f;  // a bar of 2 s or 1 s
    ProcessContext context = test::Context(tempo, 1 << DECAY);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(2.0f * kFs)), &out);
    rt60[k] = MeasureRt60(out, 0.05f);
    test::Note("bar %.1f s: RT60 %.2f s", 4.0f * tempo.beat_seconds,
               rt60[k]);
    CHECK(rt60[k] > 0.5f * 4.0f * tempo.beat_seconds &&
          rt60[k] < 2.0f * 4.0f * tempo.beat_seconds);
  }
  CHECK(rt60[1] > 1.5f * rt60[0] && rt60[1] < 2.7f * rt60[0]);
}

TEST(modal_reverb, synced_decay_shows_the_clamped_time) {
  // A note value DECAY cannot ring (over 20 s) shows the time it rings.
  Fixture f;
  char text[16];
  int bars4 = -1;
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, "4 BAR")) bars4 = i;
  }
  CHECK(bars4 >= 0);
  const float value = sidefx::StepValue(bars4, sidefx::kNumNoteValues);
  sidefx::TempoState tempo = test::Tempo120();
  ProcessContext context = test::Context(tempo, 1 << DECAY);
  f.block->Format(DECAY, value, context, text, 11);
  CHECK(strcmp(text, "4 BAR") == 0);
  context.beat_seconds = 1.5f;  // 40 BPM: 4 bars = 24 s, rings 20 s
  f.block->Format(DECAY, value, context, text, 11);
  test::Note("4 BAR at 40 BPM: \"%s\"", text);
  CHECK(strcmp(text, "20.0s") == 0);
}
