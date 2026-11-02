// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: TAPE SIM.

#include <math.h>
#include <string.h>

#include <algorithm>
#include <vector>

#include "check.h"
#include "fx/tape_sim.h"
#include "test_support.h"

namespace {

using sidefx::Frame;
using sidefx::ProcessContext;
using sidefx::TapeSim;

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

typedef void (*BlockHook)(size_t block_index, float* params, void* user);

class Rig {
 public:
  Rig() : memory_(1u << 20, 64u << 10) {
    block_ = memory_.internal().Create<TapeSim>();
    ok_ = block_ && block_->Init(memory_.memory());
    context_ = test::Context(test::Tempo120(), 0);
    Defaults();
    if (ok_) {
      block_->Reset();
    }
  }

  bool ok() const { return ok_; }
  TapeSim* block() { return block_; }
  ProcessContext& context() { return context_; }
  float* params() { return params_; }
  size_t internal_used() { return memory_.internal().used(); }

  void Defaults() {
    const sidefx::BlockInfo& info = block_->info();
    for (int i = 0; i < info.num_params; ++i) {
      params_[i] = info.params[i].default_value;
    }
  }

  // Every effect off: a clean machine at unity.
  void Clean() {
    for (int i = 0; i < TapeSim::PARAM_LAST; ++i) {
      params_[i] = 0.0f;
    }
  }

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
  TapeSim* block_;
  bool ok_;
  ProcessContext context_;
  float params_[sidefx::kMaxBlockParams];
};

size_t Blocks(float seconds) {
  return size_t(seconds * kFs) / kBlock * kBlock;
}

std::vector<float> SineWave(float hz, float amplitude, size_t n) {
  std::vector<float> x(n);
  for (size_t i = 0; i < n; ++i) {
    x[i] = amplitude * sinf(float(6.283185307179586 * fmod(
        double(hz) * double(i) / double(kFs), 1.0)));
  }
  return x;
}

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

// The frequency of x over time from its rising zero crossings (linearly
// interpolated), each value averaged over `periods` periods.
std::vector<double> Frequencies(const std::vector<float>& x, size_t start,
                                int periods) {
  std::vector<double> crossings;
  for (size_t i = start + 1; i < x.size(); ++i) {
    if (x[i - 1] < 0.0f && x[i] >= 0.0f) {
      crossings.push_back(double(i - 1) + double(x[i - 1]) /
                          double(x[i - 1] - x[i]));
    }
  }
  std::vector<double> f;
  for (size_t i = periods; i < crossings.size(); ++i) {
    f.push_back(double(periods) * kFs / (crossings[i] -
                                          crossings[i - periods]));
  }
  return f;
}

// Peak deviation from the median (a fraction) and how often the deviation
// changes sign upwards per second.
void Modulation(const std::vector<double>& f, double hz, double* depth,
                double* rate) {
  std::vector<double> sorted(f);
  std::sort(sorted.begin(), sorted.end());
  const double median = sorted[sorted.size() / 2];
  *depth = 0.0;
  size_t ups = 0;
  for (size_t i = 0; i < f.size(); ++i) {
    *depth = std::max(*depth, fabs(f[i] / median - 1.0));
    ups += i > 0 && f[i - 1] < median && f[i] >= median;
  }
  *rate = double(ups) / (double(f.size()) / hz);
}

}  // namespace

TEST(tape_sim, info) {
  Rig rig;
  CHECK(rig.ok());
  const sidefx::BlockInfo& info = rig.block()->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params == 7);
  CHECK(info.default_mix == 1.0f);
  for (int i = 0; i < info.num_params; ++i) {
    CHECK(strlen(info.params[i].name) <= 8);
  }
  CHECK(rig.internal_used() < 8192);
  test::Note("internal arena: %d bytes (object %d)", int(rig.internal_used()),
             int(sizeof(TapeSim)));
}

TEST(tape_sim, silence) {
  Rig rig;
  CHECK(rig.ok());
  const std::vector<float> zeros(Blocks(3.0f), 0.0f);
  for (int setting = 0; setting < 3; ++setting) {
    rig.Defaults();
    rig.Run(SineWave(440.0f, 1.0f, kBlock * 100));
    rig.block()->Reset();
    rig.Defaults();
    for (int p = 0; p < TapeSim::PARAM_LAST && setting > 0; ++p) {
      rig.params()[p] = setting == 1 ? 1.0f : 0.5f;
    }
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
  for (int i = 0; i < TapeSim::PARAM_LAST; ++i) {
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

TEST(tape_sim, stability) {
  Rig rig;
  CHECK(rig.ok());
  uint32_t noise_state = 7;
  std::vector<float> noise(Blocks(20.0f));
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = test::Noise(&noise_state);
  }
  RandomParams random = { 3 };
  std::vector<float> right;
  float peak = 0.0f;
  std::vector<float> out = rig.Run(noise, Randomise, &random, &right);
  CHECK(Bounded(out, right, &peak));
  test::Note("random parameters: peak %.3f", peak);

  std::vector<float> loud(Blocks(2.0f));
  for (int extreme = 0; extreme < 2; ++extreme) {
    for (float gain = 1.0f; gain <= 4.0f; gain += 3.0f) {
      for (size_t i = 0; i < loud.size(); ++i) {
        loud[i] = gain * test::Noise(&noise_state);
      }
      for (int p = 0; p < TapeSim::PARAM_LAST; ++p) {
        rig.params()[p] = float(extreme);
      }
      peak = 0.0f;
      out = rig.Run(loud, NULL, NULL, &right);
      CHECK(Bounded(out, right, &peak));
      test::Note("all params %d, noise +-%.0f: peak %.3f", extreme, gain,
                 peak);
    }
  }
  // A loud low sine into the bump at full drive.
  for (int p = 0; p < TapeSim::PARAM_LAST; ++p) {
    rig.params()[p] = 1.0f;
  }
  peak = 0.0f;
  out = rig.Run(SineWave(60.0f, 4.0f, Blocks(2.0f)), NULL, NULL, &right);
  CHECK(Bounded(out, right, &peak));
  test::Note("60 Hz at +-4, everything at 1: peak %.3f", peak);
}

TEST(tape_sim, clean_is_transparent) {
  // Everything at 0: unity gain through the band, one sample late.
  Rig rig;
  rig.Clean();
  const std::vector<float> in = SineWave(1000.0f, 0.1f, Blocks(1.0f));
  const std::vector<float> out = rig.Run(in);
  const double gain = Amplitude(out, 8192, 32768, 1000.0) / 0.1;
  test::Note("clean 1 kHz: %.2f dB", Db(gain));
  CHECK(fabs(Db(gain)) < 0.5);
}

TEST(tape_sim, wow_bends_pitch_slowly) {
  double depth[2], rate[2];
  for (int w = 0; w < 2; ++w) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_WOW] = float(w);
    const std::vector<float> out = rig.Run(SineWave(1000.0f, 0.25f,
                                                    Blocks(12.0f)));
    Modulation(Frequencies(out, 4800, 8), 1000.0, &depth[w], &rate[w]);
  }
  test::Note("WOW 0: %.4f%%; WOW 1: %.3f%% at %.2f Hz", 100.0 * depth[0],
             100.0 * depth[1], rate[1]);
  CHECK(depth[0] < 0.0002);
  CHECK(depth[1] > 0.003 && depth[1] < 0.009);
  CHECK(rate[1] > 1.2 && rate[1] < 3.0);
}

TEST(tape_sim, flutter_is_faster_and_shallower) {
  Rig rig;
  rig.Clean();
  rig.params()[TapeSim::PARAM_FLUTTER] = 1.0f;
  const std::vector<float> out = rig.Run(SineWave(1000.0f, 0.25f,
                                                  Blocks(6.0f)));
  double depth, rate;
  Modulation(Frequencies(out, 4800, 4), 1000.0, &depth, &rate);
  test::Note("FLUTTER 1: %.3f%% at %.1f Hz", 100.0 * depth, rate);
  CHECK(depth > 0.001 && depth < 0.005);
  CHECK(rate > 10.0 && rate < 20.0);
}

TEST(tape_sim, drive_saturates) {
  const size_t n = 32768;
  const float f0 = 187.5f;
  double h3[2], rms[2];
  for (int d = 0; d < 2; ++d) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_DRIVE] = float(d);
    const std::vector<float> out = rig.Run(SineWave(f0, 0.5f, n + 8192));
    h3[d] = Amplitude(out, 8192, n, 3.0 * f0) / Amplitude(out, 8192, n, f0);
    rms[d] = Rms(out, 8192, n);
  }
  test::Note("H3/H1 %.1f dB at drive 0, %.1f dB at +24 dB; level %.1f -> "
             "%.1f dB", Db(h3[0]), Db(h3[1]), Db(rms[0]), Db(rms[1]));
  CHECK(h3[1] > 0.03);
  CHECK(h3[1] > 4.0 * h3[0]);
  CHECK(fabs(Db(rms[1] / rms[0])) < 6.0);
}

TEST(tape_sim, drive_compresses_highs_first) {
  // With the record emphasis, a loud 8 kHz loses more to the drive than a
  // loud 200 Hz does.
  double loss[2];
  const float hz[2] = { 200.0f, 8000.0f };
  for (int f = 0; f < 2; ++f) {
    double a[2];
    for (int d = 0; d < 2; ++d) {
      Rig rig;
      rig.Clean();
      rig.params()[TapeSim::PARAM_DRIVE] = 0.5f * float(d);
      const std::vector<float> out = rig.Run(SineWave(hz[f], 0.5f, 40960));
      a[d] = Amplitude(out, 8192, 32768, hz[f]);
    }
    loss[f] = Db(a[1] / a[0]);
  }
  test::Note("+12 dB drive changes 200 Hz by %.1f dB, 8 kHz by %.1f dB",
             loss[0], loss[1]);
  CHECK(loss[1] < loss[0] - 2.0);
}

TEST(tape_sim, age_rolls_off_highs) {
  double a[2];
  for (int g = 0; g < 2; ++g) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_AGE] = float(g);
    const std::vector<float> out = rig.Run(SineWave(10000.0f, 0.05f, 40960));
    a[g] = Amplitude(out, 8192, 32768, 10000.0) / 0.05;
  }
  test::Note("10 kHz: %.1f dB new, %.1f dB worn", Db(a[0]), Db(a[1]));
  CHECK(Db(a[0]) > -1.5);
  CHECK(Db(a[1]) < Db(a[0]) - 15.0);
}

TEST(tape_sim, bump) {
  double gain[2];
  for (int b = 0; b < 2; ++b) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_BUMP] = float(b);
    const float hz = TapeSim::BumpHz(float(b));
    const std::vector<float> low = rig.Run(SineWave(hz, 0.05f, 65536));
    rig.block()->Reset();
    const std::vector<float> mid = rig.Run(SineWave(1000.0f, 0.05f, 65536));
    gain[b] = Db(Amplitude(low, 16384, 49152, hz) /
                 Amplitude(mid, 16384, 49152, 1000.0));
  }
  test::Note("bump: %.1f dB at 120 Hz (BUMP 0), %.1f dB at 60 Hz (BUMP 1)",
             gain[0], gain[1]);
  CHECK(fabs(gain[0]) < 1.0);
  CHECK(gain[1] > 4.5 && gain[1] < 7.5);
}

TEST(tape_sim, hiss) {
  // A 50 Hz sine keeps the gate open; the hiss shows above 2 kHz.
  double hf[2];
  for (int h = 0; h < 2; ++h) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_HISS] = float(h);
    std::vector<float> out = rig.Run(SineWave(50.0f, 0.2f, Blocks(2.0f)));
    // A crude highpass: the second difference.
    std::vector<float> d(out.size(), 0.0f);
    for (size_t i = 2; i < out.size(); ++i) {
      d[i] = out[i] - 2.0f * out[i - 1] + out[i - 2];
    }
    hf[h] = Rms(d, 8192, out.size() - 8192);
  }
  test::Note("high band RMS %.2e without hiss, %.2e with", hf[0], hf[1]);
  CHECK(hf[1] > 30.0 * hf[0]);
  CHECK(hf[1] > 0.005);

  // Silence after signal: the hiss fades away.
  Rig rig;
  rig.Clean();
  rig.params()[TapeSim::PARAM_HISS] = 1.0f;
  std::vector<float> in = SineWave(50.0f, 0.2f, Blocks(1.0f));
  in.resize(Blocks(9.0f), 0.0f);
  const std::vector<float> out = rig.Run(in);
  const double during = Rms(out, Blocks(1.2f), Blocks(0.5f));
  const double after = Rms(out, Blocks(8.0f), Blocks(0.5f));
  test::Note("RMS 0.2 s after the input stops %.2e, 7 s after %.2e",
             during, after);
  CHECK(during > 0.005);
  CHECK(after < 0.001 * during);
}

TEST(tape_sim, dropouts_dip) {
  double lowest[2];
  int dips[2];
  for (int d = 0; d < 2; ++d) {
    Rig rig;
    rig.Clean();
    rig.params()[TapeSim::PARAM_DROPOUT] = float(d);
    const std::vector<float> out = rig.Run(SineWave(1000.0f, 0.5f,
                                                    Blocks(20.0f)));
    const size_t window = 240;  // 5 ms
    std::vector<double> levels;
    for (size_t i = 4800; i + window <= out.size(); i += window) {
      levels.push_back(Rms(out, i, window));
    }
    std::vector<double> sorted(levels);
    std::sort(sorted.begin(), sorted.end());
    const double median = sorted[sorted.size() / 2];
    lowest[d] = 1.0;
    dips[d] = 0;
    bool in_dip = false;
    for (size_t i = 0; i < levels.size(); ++i) {
      const double level = levels[i] / median;
      lowest[d] = std::min(lowest[d], level);
      if (level < 0.5 && !in_dip) {
        ++dips[d];
      }
      in_dip = level < 0.5;
    }
  }
  test::Note("DROPOUT 0: lowest %.2f; DROPOUT 1: lowest %.2f, %d dips of "
             "6 dB in 20 s", lowest[0], lowest[1], dips[1]);
  CHECK(lowest[0] > 0.95);
  CHECK(lowest[1] < 0.3);
  CHECK(dips[1] > 40 && dips[1] < 300);
}

namespace {

struct Jumps {
  int param;
  size_t period_blocks;
  float a;
  float b;
};

void Jump(size_t block, float* params, void* user) {
  const Jumps* j = static_cast<const Jumps*>(user);
  params[j->param] = (block / j->period_blocks) % 2 ? j->b : j->a;
}

}  // namespace

TEST(tape_sim, no_clicks) {
  const std::vector<float> sine = SineWave(220.0f, 0.5f, Blocks(3.0f));
  const int params[] = {
    TapeSim::PARAM_WOW, TapeSim::PARAM_FLUTTER, TapeSim::PARAM_DRIVE,
    TapeSim::PARAM_AGE, TapeSim::PARAM_BUMP,
  };
  for (size_t p = 0; p < sizeof(params) / sizeof(params[0]); ++p) {
    float normal = 0.0f;
    for (int v = 0; v < 2; ++v) {
      Rig rig;
      rig.Clean();
      rig.params()[params[p]] = float(v);
      normal = fmaxf(normal, MaxStep(rig.Run(sine), 4800));
    }
    Rig rig;
    rig.Clean();
    Jumps jumps = { params[p], 150, 0.0f, 1.0f };
    const float jumped = MaxStep(rig.Run(sine, Jump, &jumps), 4800);
    test::Note("%s jumping 0 <-> 1: max step %.4f, steady %.4f",
               rig.block()->info().params[params[p]].name, jumped, normal);
    CHECK(jumped < 1.5f * normal);
  }
}

TEST(tape_sim, format) {
  Rig rig;
  const sidefx::BlockInfo& info = rig.block()->info();
  const float values[] = { 0.0f, 0.001f, 0.25f, 0.5f, 0.75f, 1.0f };
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
        if (synced == 0 && (v == 0 || v == 3 || v == 5)) {
          test::Note("%s %.3f: \"%s\"", info.params[p].name, values[v], text);
        }
      }
    }
  }
}

TEST(tape_sim, tempo_independent) {
  // WOW and FLUTTER are depths (their rates follow them and wander), so no
  // parameter is synced: sync bits and tempo leave the output untouched.
  Rig a, b;
  const sidefx::BlockInfo& info = a.block()->info();
  for (int p = 0; p < info.num_params; ++p) {
    CHECK((info.params[p].flags & sidefx::PARAM_SYNC) == 0);
  }
  b.context().sync_mask = 0xffff;
  b.context().beat_seconds = 0.21f;
  for (int p = 0; p < info.num_params; ++p) {
    a.params()[p] = b.params()[p] = 0.6f;
  }
  const std::vector<float> in = SineWave(220.0f, 0.7f, Blocks(2.0f));
  CHECK(a.Run(in) == b.Run(in));
  char t1[16], t2[16];
  for (int p = 0; p < info.num_params; ++p) {
    a.block()->Format(p, 0.37f, a.context(), t1, sizeof(t1));
    b.block()->Format(p, 0.37f, b.context(), t2, sizeof(t2));
    CHECK(strcmp(t1, t2) == 0);
  }
}
