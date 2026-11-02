// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: WAVESHAPER.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "fx/wave_shaper.h"
#include "test_support.h"

namespace {

using sidefx::Frame;
using sidefx::ProcessContext;
using sidefx::WaveShaper;

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

typedef void (*BlockHook)(size_t block_index, float* params, void* user);

class Rig {
 public:
  Rig() : memory_(1u << 20, 64u << 10) {
    block_ = memory_.internal().Create<WaveShaper>();
    ok_ = block_ && block_->Init(memory_.memory());
    context_ = test::Context(test::Tempo120(), 0);
    Defaults();
    if (ok_) {
      block_->Reset();
    }
  }

  bool ok() const { return ok_; }
  WaveShaper* block() { return block_; }
  ProcessContext& context() { return context_; }
  float* params() { return params_; }

  void Defaults() {
    const sidefx::BlockInfo& info = block_->info();
    for (int i = 0; i < info.num_params; ++i) {
      params_[i] = info.params[i].default_value;
    }
  }

  // Runs a mono signal (both channels) through, returns the left output;
  // the right one goes to *right when given.
  std::vector<float> Run(const std::vector<float>& input,
                         BlockHook hook = NULL, void* user = NULL,
                         std::vector<float>* right = NULL) {
    std::vector<float> output(input.size(), 0.0f);
    if (right) {
      right->assign(input.size(), 0.0f);
    }
    Frame in[kBlock];
    Frame out[kBlock];
    for (size_t start = 0, b = 0; start + kBlock <= input.size();
         start += kBlock, ++b) {
      if (hook) {
        hook(b, params_, user);
      }
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = in[i].r = input[start + i];
      }
      block_->Process(context_, params_, in, out, kBlock);
      for (size_t i = 0; i < kBlock; ++i) {
        output[start + i] = out[i].l;
        if (right) {
          (*right)[start + i] = out[i].r;
        }
      }
    }
    return output;
  }

 private:
  test::TestMemory memory_;
  WaveShaper* block_;
  bool ok_;
  ProcessContext context_;
  float params_[sidefx::kMaxBlockParams];
};

std::vector<float> SineWave(float hz, float amplitude, size_t n) {
  std::vector<float> x(n);
  for (size_t i = 0; i < n; ++i) {
    x[i] = amplitude * sinf(float(6.283185307179586 * fmod(
        double(hz) * double(i) / double(kFs), 1.0)));
  }
  return x;
}

// Amplitude of the component at hz in x[start, start + n), Hann window.
double Amplitude(const std::vector<float>& x, size_t start, size_t n,
                 double hz) {
  double re = 0.0, im = 0.0, wsum = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double w = 0.5 - 0.5 * cos(6.283185307179586 * double(i) /
                                     double(n));
    const double phase = 6.283185307179586 * hz * double(i) / double(kFs);
    re += w * x[start + i] * cos(phase);
    im -= w * x[start + i] * sin(phase);
    wsum += w;
  }
  return 2.0 * sqrt(re * re + im * im) / wsum;
}

double Rms(const std::vector<float>& x, size_t start, size_t n) {
  double s = 0.0;
  for (size_t i = start; i < start + n; ++i) {
    s += double(x[i]) * x[i];
  }
  return sqrt(s / double(n));
}

double Db(double ratio) {
  return 20.0 * log10(ratio > 1e-12 ? ratio : 1e-12);
}

float MaxStep(const std::vector<float>& x, size_t start) {
  float m = 0.0f;
  for (size_t i = start + 1; i < x.size(); ++i) {
    m = fmaxf(m, fabsf(x[i] - x[i - 1]));
  }
  return m;
}

void SetParams(float* params, float mode, float drive, float bias, float tone,
               float bits, float rate, float level) {
  params[WaveShaper::PARAM_MODE] = mode;
  params[WaveShaper::PARAM_DRIVE] = drive;
  params[WaveShaper::PARAM_BIAS] = bias;
  params[WaveShaper::PARAM_TONE] = tone;
  params[WaveShaper::PARAM_BITS] = bits;
  params[WaveShaper::PARAM_RATE] = rate;
  params[WaveShaper::PARAM_LEVEL] = level;
}

float ModeValue(int mode) {
  return sidefx::StepValue(mode, WaveShaper::MODE_LAST);
}

}  // namespace

TEST(wave_shaper, info) {
  Rig rig;
  CHECK(rig.ok());
  const sidefx::BlockInfo& info = rig.block()->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params == 7);
  CHECK(info.default_mix == 1.0f);
  for (int i = 0; i < info.num_params; ++i) {
    CHECK(strlen(info.params[i].name) <= 8);
    CHECK(info.params[i].default_value >= 0.0f &&
          info.params[i].default_value <= 1.0f);
  }
  CHECK(sizeof(WaveShaper) < 8192);
  test::Note("sizeof(WaveShaper) = %d bytes", int(sizeof(WaveShaper)));
}

TEST(wave_shaper, silence) {
  Rig rig;
  CHECK(rig.ok());
  const std::vector<float> zeros(kBlock * 200, 0.0f);
  // The defaults, then settings that would leak DC or noise if they could.
  const float settings[][7] = {
    { 0.0f, 0.3f, 0.5f, 0.5f, 1.0f, 1.0f, 0.5f },
    { ModeValue(0), 1.0f, 1.0f, 0.0f, 0.0f, 0.0f, 1.0f },
    { ModeValue(1), 1.0f, 0.0f, 1.0f, 0.3f, 0.2f, 1.0f },
    { ModeValue(2), 0.7f, 0.9f, 0.7f, 1.0f, 0.5f, 0.8f },
    { ModeValue(3), 1.0f, 0.2f, 0.2f, 0.5f, 1.0f, 1.0f },
    { ModeValue(4), 1.0f, 1.0f, 1.0f, 0.0f, 0.0f, 1.0f },
    { ModeValue(5), 1.0f, 0.75f, 0.5f, 0.6f, 0.4f, 1.0f },
  };
  for (size_t s = 0; s < sizeof(settings) / sizeof(settings[0]); ++s) {
    // Dirty the state first, then Reset.
    rig.Defaults();
    rig.Run(SineWave(440.0f, 1.0f, kBlock * 50));
    rig.block()->Reset();
    memcpy(rig.params(), settings[s], sizeof(settings[s]));
    std::vector<float> right;
    const std::vector<float> out = rig.Run(zeros, NULL, NULL, &right);
    bool silent = true;
    for (size_t i = 0; i < out.size(); ++i) {
      silent = silent && out[i] == 0.0f && right[i] == 0.0f;
    }
    CHECK(silent);
  }
}

namespace {

struct RandomParams {
  uint32_t state;
};

void Randomise(size_t, float* params, void* user) {
  RandomParams* r = static_cast<RandomParams*>(user);
  for (int i = 0; i < WaveShaper::PARAM_LAST; ++i) {
    params[i] = 0.5f + 0.5f * test::Noise(&r->state);
  }
}

bool Bounded(const std::vector<float>& x, const std::vector<float>& y,
             float* peak) {
  bool ok = true;
  for (size_t i = 0; i < x.size(); ++i) {
    ok = ok && isfinite(x[i]) && isfinite(y[i]) && fabsf(x[i]) < 4.0f &&
        fabsf(y[i]) < 4.0f;
    *peak = fmaxf(*peak, fmaxf(fabsf(x[i]), fabsf(y[i])));
  }
  return ok;
}

}  // namespace

TEST(wave_shaper, stability) {
  Rig rig;
  CHECK(rig.ok());
  uint32_t noise_state = 1;
  std::vector<float> noise(size_t(20.0f * kFs) / kBlock * kBlock);
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = test::Noise(&noise_state);
  }
  RandomParams random = { 99 };
  std::vector<float> right;
  float peak = 0.0f;
  std::vector<float> out = rig.Run(noise, Randomise, &random, &right);
  CHECK(Bounded(out, right, &peak));
  test::Note("random parameters: peak %.3f", peak);

  // Every parameter at 0 and at 1, with +-1 and +-4 noise.
  std::vector<float> loud(size_t(2.0f * kFs) / kBlock * kBlock);
  for (int extreme = 0; extreme < 2; ++extreme) {
    for (float gain = 1.0f; gain <= 4.0f; gain += 3.0f) {
      for (size_t i = 0; i < loud.size(); ++i) {
        loud[i] = gain * test::Noise(&noise_state);
      }
      for (int p = 0; p < WaveShaper::PARAM_LAST; ++p) {
        rig.params()[p] = float(extreme);
      }
      peak = 0.0f;
      out = rig.Run(loud, NULL, NULL, &right);
      CHECK(Bounded(out, right, &peak));
      test::Note("all params %d, noise +-%.0f: peak %.3f", extreme, gain,
                 peak);
    }
  }
  // Each mode with full drive and bias, and loud sines.
  for (int mode = 0; mode < WaveShaper::MODE_LAST; ++mode) {
    for (int bias = 0; bias < 2; ++bias) {
      SetParams(rig.params(), ModeValue(mode), 1.0f, float(bias), 1.0f, 1.0f,
                1.0f, 1.0f);
      peak = 0.0f;
      out = rig.Run(SineWave(60.0f, 4.0f, kBlock * 3000), NULL, NULL, &right);
      CHECK(Bounded(out, right, &peak));
    }
  }
}

TEST(wave_shaper, drive_adds_harmonics) {
  const size_t n = 32768;
  const float f0 = 187.5f;
  for (int mode = 0; mode < WaveShaper::MODE_LAST; ++mode) {
    double h3[2], rms[2];
    for (int d = 0; d < 2; ++d) {
      Rig rig;
      SetParams(rig.params(), ModeValue(mode), float(d), 0.5f, 0.5f, 1.0f,
                1.0f, 0.5f);
      const std::vector<float> out = rig.Run(SineWave(f0, 0.5f, n + 8192));
      const double a1 = Amplitude(out, 8192, n, f0);
      h3[d] = Amplitude(out, 8192, n, 3.0 * f0) / a1;
      rms[d] = Rms(out, 8192, n);
      if (mode == WaveShaper::MODE_RECTIFY) {
        // Full-wave rectified: the octave, not the fundamental.
        const double a2 = Amplitude(out, 8192, n, 2.0 * f0);
        test::Note("RECTIFY drive %d: H2/H1 %.1f dB", d, Db(a2 / a1));
        CHECK(a2 > 3.0 * a1);
        h3[d] = a2 / 0.5;
      }
    }
    test::Note("mode %d: H3/H1 %.1f dB at drive 0, %.1f dB at 40 dB; "
               "level %.1f dB -> %.1f dB", mode, Db(h3[0]), Db(h3[1]),
               Db(rms[0]), Db(rms[1]));
    if (mode != WaveShaper::MODE_RECTIFY) {
      CHECK(h3[1] > 0.1);
      CHECK(h3[1] > 3.0 * h3[0]);
    }
    // Level compensation: 40 dB of drive moves the level by a few dB only.
    CHECK(fabs(Db(rms[1] / rms[0])) < 6.0);
  }
}

TEST(wave_shaper, bias_adds_even_harmonics) {
  const size_t n = 32768;
  const float f0 = 187.5f;
  double h2[2], dc[2];
  for (int b = 0; b < 2; ++b) {
    Rig rig;
    SetParams(rig.params(), ModeValue(WaveShaper::MODE_SOFT), 0.4f,
              b ? 0.85f : 0.5f, 0.5f, 1.0f, 1.0f, 0.5f);
    const std::vector<float> out = rig.Run(SineWave(f0, 0.5f, n + 16384));
    h2[b] = Amplitude(out, 16384, n, 2.0 * f0) /
        Amplitude(out, 16384, n, f0);
    double sum = 0.0;
    for (size_t i = 16384; i < 16384 + n; ++i) {
      sum += out[i];
    }
    dc[b] = sum / double(n);
  }
  test::Note("H2/H1 %.1f dB without bias, %.1f dB with; DC %.4f, %.4f",
             Db(h2[0]), Db(h2[1]), dc[0], dc[1]);
  CHECK(h2[0] < 0.003);
  CHECK(h2[1] > 0.05);
  CHECK(fabs(dc[0]) < 0.005);
  CHECK(fabs(dc[1]) < 0.005);
}

TEST(wave_shaper, oversampling_removes_aliases) {
  // A hard-clipped 7 kHz: its 5th harmonic (35 kHz) would fold to
  // fs - 35 kHz = 13.0 kHz without oversampling.
  const size_t n = 32768;
  const float f0 = 7000.0f;
  const float drive_db = 20.0f;
  Rig rig;
  SetParams(rig.params(), ModeValue(WaveShaper::MODE_HARD),
            drive_db / 40.0f, 0.5f, 0.5f, 1.0f, 1.0f, 0.5f);
  const std::vector<float> in = SineWave(f0, 0.5f, n + 4096);
  const std::vector<float> out = rig.Run(in);
  std::vector<float> naive(in.size());
  const float g = powf(10.0f, drive_db / 20.0f);
  for (size_t i = 0; i < in.size(); ++i) {
    naive[i] = WaveShaper::Shape(WaveShaper::MODE_HARD, in[i] * g);
  }
  const double alias_hz = kFs - 5.0 * f0;
  const double ours = Amplitude(out, 4096, n, alias_hz) /
      Amplitude(out, 4096, n, f0);
  const double theirs = Amplitude(naive, 4096, n, alias_hz) /
      Amplitude(naive, 4096, n, f0);
  test::Note("alias at %.0f Hz: %.1f dB oversampled, %.1f dB naive",
             alias_hz, Db(ours), Db(theirs));
  CHECK(Db(ours) < Db(theirs) - 30.0);
}

TEST(wave_shaper, bits_quantise) {
  Rig rig;
  SetParams(rig.params(), ModeValue(WaveShaper::MODE_SOFT), 0.0f, 0.5f, 0.5f,
            0.0f, 1.0f, 0.5f);
  // 2 bits: steps of 0.5. TONE's lowpass (out of the way at the centre)
  // rounds each step over a sample or two; the rest sits on the grid.
  const std::vector<float> out = rig.Run(SineWave(110.0f, 0.8f, 16384));
  rig.params()[WaveShaper::PARAM_BITS] = 1.0f;
  const std::vector<float> clean = rig.Run(SineWave(110.0f, 0.8f, 16384));
  size_t on_grid = 0;
  size_t clean_on_grid = 0;
  for (size_t i = 4096; i < out.size(); ++i) {
    on_grid += fabsf(out[i] * 2.0f - roundf(out[i] * 2.0f)) < 0.01f;
    clean_on_grid += fabsf(clean[i] * 2.0f - roundf(clean[i] * 2.0f)) <
        0.01f;
  }
  const double fraction = double(on_grid) / double(out.size() - 4096);
  const double clean_fraction = double(clean_on_grid) /
      double(out.size() - 4096);
  test::Note("2 bits: %.1f%% of samples on the 0.5 grid (clean: %.1f%%)",
             100.0 * fraction, 100.0 * clean_fraction);
  CHECK(fraction > 0.95);
  CHECK(clean_fraction < 0.1);
}

TEST(wave_shaper, rate_holds_samples) {
  Rig rig;
  SetParams(rig.params(), ModeValue(WaveShaper::MODE_SOFT), 0.0f, 0.5f, 0.5f,
            1.0f, 0.0f, 0.5f);
  const std::vector<float> out = rig.Run(SineWave(37.0f, 0.8f, 48000));
  // A held value starts where the output begins to move after resting
  // (TONE's lowpass spreads each step over a few samples).
  size_t changes = 0;
  for (size_t i = 4098; i < out.size(); ++i) {
    changes += fabsf(out[i] - out[i - 1]) > 1e-4f &&
        fabsf(out[i - 1] - out[i - 2]) <= 1e-4f;
  }
  const double run = double(out.size() - 4097) / double(changes);
  test::Note("RATE 0: a new value every %.1f samples (expect %.1f)", run,
             kFs / 500.0f);
  CHECK(fabs(run - kFs / 500.0) < 0.1 * kFs / 500.0);
}

TEST(wave_shaper, tone_darkens_and_brightens) {
  const size_t n = 16384;
  const float f0 = 6000.0f;
  double a[3];
  const float tone[3] = { 0.0f, 0.5f, 1.0f };
  for (int t = 0; t < 3; ++t) {
    Rig rig;
    SetParams(rig.params(), ModeValue(WaveShaper::MODE_SOFT), 0.0f, 0.5f,
              tone[t], 1.0f, 1.0f, 0.5f);
    const std::vector<float> out = rig.Run(SineWave(f0, 0.05f, n + 4096));
    a[t] = Amplitude(out, 4096, n, f0);
  }
  test::Note("6 kHz: dark %.1f dB, flat %.1f dB, bright %.1f dB",
             Db(a[0] / 0.05), Db(a[1] / 0.05), Db(a[2] / 0.05));
  CHECK(fabs(Db(a[1] / 0.05)) < 0.5);
  CHECK(Db(a[0] / a[1]) < -15.0);
  CHECK(Db(a[2] / a[1]) > 6.0);
}

TEST(wave_shaper, level_trims) {
  const size_t n = 16384;
  double a[2];
  for (int l = 0; l < 2; ++l) {
    Rig rig;
    SetParams(rig.params(), ModeValue(WaveShaper::MODE_SOFT), 0.0f, 0.5f,
              0.5f, 1.0f, 1.0f, float(l));
    const std::vector<float> out = rig.Run(SineWave(500.0f, 0.05f, n + 4096));
    a[l] = Amplitude(out, 4096, n, 500.0);
  }
  CHECK_NEAR(Db(a[0] / 0.05), -12.0, 0.3);
  CHECK_NEAR(Db(a[1] / 0.05), 12.0, 0.3);
}

namespace {

struct Jumps {
  int param;
  size_t period_blocks;
  int num_values;
  const float* values;
};

void Jump(size_t block, float* params, void* user) {
  const Jumps* j = static_cast<const Jumps*>(user);
  params[j->param] = j->values[(block / j->period_blocks) % j->num_values];
}

}  // namespace

TEST(wave_shaper, no_clicks) {
  const size_t n = size_t(kFs * 2.0f) / kBlock * kBlock;
  const std::vector<float> sine = SineWave(110.0f, 0.5f, n);
  struct Case {
    int param;
    int num_values;
    float values[WaveShaper::MODE_LAST];
    float base_mode;
  };
  const Case cases[] = {
    { WaveShaper::PARAM_DRIVE, 2, { 0.0f, 1.0f }, ModeValue(0) },
    { WaveShaper::PARAM_DRIVE, 2, { 0.0f, 1.0f }, ModeValue(2) },
    { WaveShaper::PARAM_BIAS, 2, { 0.0f, 1.0f }, ModeValue(0) },
    { WaveShaper::PARAM_LEVEL, 2, { 0.0f, 1.0f }, ModeValue(1) },
    { WaveShaper::PARAM_TONE, 2, { 0.0f, 1.0f }, ModeValue(0) },
    { WaveShaper::PARAM_MODE, 6, { ModeValue(0), ModeValue(3), ModeValue(1),
                                   ModeValue(4), ModeValue(2), ModeValue(5) },
      0.0f },
  };
  for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); ++c) {
    const Case& k = cases[c];
    // The largest step of each steady setting: what the jump is held to.
    float normal = 0.0f;
    for (int v = 0; v < k.num_values; ++v) {
      Rig rig;
      SetParams(rig.params(), k.base_mode, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f,
                0.5f);
      rig.params()[k.param] = k.values[v];
      normal = fmaxf(normal, MaxStep(rig.Run(sine), 4096));
    }
    Rig rig;
    SetParams(rig.params(), k.base_mode, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f, 0.5f);
    Jumps jumps = { k.param, 75, k.num_values, k.values };
    const float jumped = MaxStep(rig.Run(sine, Jump, &jumps), 4096);
    test::Note("param %d jumping: max step %.4f, steady %.4f", k.param,
               jumped, normal);
    CHECK(jumped < 2.0f * normal);
  }
}

TEST(wave_shaper, format) {
  Rig rig;
  const sidefx::BlockInfo& info = rig.block()->info();
  const float values[] = { 0.0f, 0.25f, 0.5f, 0.75f, 0.998f, 1.0f };
  for (int synced = 0; synced < 2; ++synced) {
    ProcessContext context = test::Context(test::Tempo120(),
                                           synced ? 0xffff : 0);
    for (int p = 0; p < info.num_params; ++p) {
      for (size_t v = 0; v < sizeof(values) / sizeof(values[0]); ++v) {
        char text[32];
        memset(text, 'x', sizeof(text));
        rig.block()->Format(p, values[v], context, text, 11);
        const size_t length = strlen(text);
        CHECK(length > 0 && length <= 10);
        if (synced == 0 && v != 1 && v != 3) {
          test::Note("%s %.3f: \"%s\"", info.params[p].name, values[v], text);
        }
      }
    }
  }
}

TEST(wave_shaper, tempo_independent) {
  // No parameter is a time or a rate (RATE is a sample rate), so none may
  // follow the tempo: sync bits and tempo leave the output untouched.
  Rig a, b;
  const sidefx::BlockInfo& info = a.block()->info();
  for (int p = 0; p < info.num_params; ++p) {
    CHECK((info.params[p].flags & sidefx::PARAM_SYNC) == 0);
  }
  b.context().sync_mask = 0xffff;
  b.context().beat_seconds = 0.21f;
  SetParams(a.params(), ModeValue(4), 0.6f, 0.7f, 0.3f, 0.5f, 0.4f, 0.5f);
  memcpy(b.params(), a.params(), sizeof(float) * info.num_params);
  const std::vector<float> in = SineWave(220.0f, 0.7f, kBlock * 500);
  const std::vector<float> x = a.Run(in);
  const std::vector<float> y = b.Run(in);
  CHECK(x == y);
  char t1[16], t2[16];
  for (int p = 0; p < info.num_params; ++p) {
    a.block()->Format(p, 0.37f, a.context(), t1, sizeof(t1));
    b.block()->Format(p, 0.37f, b.context(), t2, sizeof(t2));
    CHECK(strcmp(t1, t2) == 0);
  }
}

TEST(wave_shaper, keeps_the_sub_bass) {
  // The output DC blocker sits under the sub bass: a quiet 30 or 40 Hz sine
  // comes out as loud as a 1 kHz one, in every mode (DRIVE 0, so the
  // shapers are about linear; MIX is 100 % wet by default).
  for (int mode = 0; mode < WaveShaper::MODE_LAST; ++mode) {
    if (mode == WaveShaper::MODE_RECTIFY || mode == WaveShaper::MODE_FUZZ) {
      continue;  // not linear even when quiet
    }
    double a[3];
    const float hz[] = { 30.0f, 40.0f, 1000.0f };
    for (int k = 0; k < 3; ++k) {
      Rig rig;
      SetParams(rig.params(), ModeValue(mode), 0.0f, 0.5f, 0.5f, 1.0f, 1.0f,
                0.5f);
      const size_t n = 32768;
      const std::vector<float> out = rig.Run(SineWave(hz[k], 0.05f,
                                                      n + 16384));
      a[k] = Amplitude(out, 16384, n, hz[k]);
    }
    char name[16];
    Rig rig;
    rig.block()->Format(WaveShaper::PARAM_MODE, ModeValue(mode),
                        rig.context(), name, sizeof(name));
    test::Note("%s: 30 Hz %+.2f dB, 40 Hz %+.2f dB against 1 kHz", name,
               Db(a[0] / a[2]), Db(a[1] / a[2]));
    CHECK(Db(a[0] / a[2]) > -0.5);
    CHECK(Db(a[1] / a[2]) > -0.3);
  }
}
