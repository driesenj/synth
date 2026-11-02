// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: MOD COMBS.

#include <math.h>
#include <string.h>

#include "check.h"
#include "test_support.h"
#include "fx/mod_combs.h"

namespace {

using sidefx::Frame;
using sidefx::ModCombs;
using sidefx::ProcessContext;

const float kFs = 48014.32f;
const size_t kB = sidefx::kBlockSize;

struct Rig {
  test::TestMemory memory;
  ModCombs* block;
  bool ok;
  float params[ModCombs::NUM_PARAMS];

  Rig() : memory(1u << 20, 32u << 10) {
    block = memory.memory()->internal->Create<ModCombs>();
    ok = block && block->Init(memory.memory());
    Defaults();
  }
  void Defaults() {
    const sidefx::BlockInfo& info = block->info();
    for (int i = 0; i < info.num_params; ++i) {
      params[i] = info.params[i].default_value;
    }
  }
  void Run(const ProcessContext& c, const Frame* in, Frame* out) {
    block->Process(c, params, in, out, kB);
  }
};

float FreqValue(float hz) {
  return sidefx::ExpUnmap(hz, 20.0f, 2000.0f);
}

float FeedbackValue(float feedback) {
  return 0.5f + 0.5f * feedback / 0.99f;
}

float VoicesValue(int voices) {
  return sidefx::StepValue(voices - 1, 4);
}

// Normalised autocorrelation of x at lag.
double Autocorrelation(const float* x, size_t n, size_t lag) {
  double xy = 0.0, xx = 0.0, yy = 0.0;
  for (size_t i = 0; i + lag < n; ++i) {
    xy += double(x[i]) * x[i + lag];
    xx += double(x[i]) * x[i];
    yy += double(x[i + lag]) * x[i + lag];
  }
  return xx > 0.0 && yy > 0.0 ? xy / sqrt(xx * yy) : 0.0;
}

// Noise through the block for `seconds`; keeps the left output's last
// `keep` samples.
void NoiseThrough(Rig* rig, const ProcessContext& c, float seconds,
                  float* kept_l, float* kept_r, size_t keep) {
  Frame in[kB];
  Frame out[kB];
  uint32_t seed = 99;
  const size_t total = size_t(seconds * kFs) / kB * kB;
  for (size_t n = 0; n < total; n += kB) {
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = in[i].r = 0.5f * test::Noise(&seed);
    }
    rig->Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      const size_t from_end = total - (n + i);
      if (from_end <= keep) {
        if (kept_l) {
          kept_l[keep - from_end] = out[i].l;
        }
        if (kept_r) {
          kept_r[keep - from_end] = out[i].r;
        }
      }
    }
  }
}

}  // namespace

TEST(mod_combs, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(sizeof(ModCombs) < 8192);
  CHECK(rig.memory.external().used() <= (1u << 20));
  test::Note("object %u bytes, external %u bytes",
             unsigned(sizeof(ModCombs)),
             unsigned(rig.memory.external().used()));
  const sidefx::BlockInfo& info = rig.block->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params <= 7);
  for (int i = 0; i < info.num_params; ++i) {
    CHECK(strlen(info.params[i].name) <= 8);
  }

  ProcessContext c = test::Context(test::Tempo120(), 0);
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  rig.params[ModCombs::PARAM_FEEDBACK] = 1.0f;
  rig.params[ModCombs::PARAM_VOICES] = 1.0f;
  bool silent = true;
  for (int b = 0; b < 1500; ++b) {
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);

  uint32_t seed = 3;
  for (int b = 0; b < 500; ++b) {
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Run(c, in, out);
  }
  rig.block->Reset();
  memset(in, 0, sizeof(in));
  silent = true;
  for (int b = 0; b < 500; ++b) {
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);
}

TEST(mod_combs, stability) {
  Rig rig;
  CHECK(rig.ok);
  sidefx::TempoState tempo = test::Tempo120();
  Frame in[kB];
  Frame out[kB];
  uint32_t seed = 11;
  sidefx::dsp::Random random;
  float peak = 0.0f;
  bool finite = true;
  const int blocks = int(20.0f * kFs / float(kB));
  for (int b = 0; b < blocks; ++b) {
    for (int p = 0; p < ModCombs::NUM_PARAMS; ++p) {
      rig.params[p] = random.Uniform();
    }
    tempo.bar_phase += tempo.bar_increment * float(kB);
    tempo.bar_phase -= floorf(tempo.bar_phase);
    ProcessContext c = test::Context(tempo, uint16_t(random.Next() & 0x7f));
    for (size_t i = 0; i < kB; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Run(c, in, out);
    for (size_t i = 0; i < kB; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  CHECK(finite);
  CHECK(peak < 4.0f);
  test::Note("random: peak %.3f", peak);

  // All at 0 (feedback -99 %), all at 1 (+99 %), and each with a positive
  // 99 % and the rest at 0; noise at +-1 and +-4.
  for (int setting = 0; setting < 3; ++setting) {
    for (int level = 1; level <= 4; level *= 4) {
      rig.block->Reset();
      for (int p = 0; p < ModCombs::NUM_PARAMS; ++p) {
        rig.params[p] = setting == 1 ? 1.0f : 0.0f;
      }
      if (setting == 2) {
        rig.params[ModCombs::PARAM_FEEDBACK] = 1.0f;
      }
      ProcessContext c = test::Context(tempo, 0);
      float peak_here = 0.0f;
      for (int b = 0; b < int(5.0f * kFs / float(kB)); ++b) {
        for (size_t i = 0; i < kB; ++i) {
          in[i].l = float(level) * test::Noise(&seed);
          in[i].r = float(level) * test::Noise(&seed);
        }
        rig.Run(c, in, out);
        for (size_t i = 0; i < kB; ++i) {
          finite = finite && test::Finite(out[i]);
          peak_here = fmaxf(peak_here,
                            fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
      }
      CHECK(finite);
      CHECK(peak_here < 4.0f);
      test::Note("setting %d, input +-%d: peak %.3f", setting, level,
                 peak_here);
    }
  }
}

TEST(mod_combs, resonates_at_freq) {
  // Positive feedback: periodic at 1 / FREQ. Negative: still periodic at
  // 1 / FREQ but antisymmetric over half of it (odd harmonics only).
  const size_t keep = 16384;
  static float x[16384];
  const float hz = 200.0f;
  const size_t period = size_t(kFs / hz + 0.5f);
  for (int sign = 0; sign < 2; ++sign) {
    Rig rig;
    CHECK(rig.ok);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    rig.params[ModCombs::PARAM_FREQ] = FreqValue(hz);
    rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(sign ? -0.95f
                                                              : 0.95f);
    rig.params[ModCombs::PARAM_DEPTH] = 0.0f;
    rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
    rig.params[ModCombs::PARAM_SPREAD] = 0.0f;
    rig.params[ModCombs::PARAM_DAMP] = 0.0f;
    NoiseThrough(&rig, c, 1.0f, x, NULL, keep);
    const double full = Autocorrelation(x, keep, period);
    const double half = Autocorrelation(x, keep, period / 2);
    test::Note("feedback %s: r(T) %.3f r(T/2) %.3f", sign ? "-95%" : "+95%",
               full, half);
    CHECK(full > 0.7);
    if (sign) {
      CHECK(half < -0.7);
    } else {
      CHECK(half < 0.5);
    }
  }
}

TEST(mod_combs, depth_moves_the_comb) {
  // DEPTH 0.5: the line sweeps over 2 * 0.5^2 = 0.5 octave at RATE; at
  // DEPTH 0 it stays put. The notches move with it.
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[ModCombs::PARAM_FREQ] = FreqValue(500.0f);
  rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.5f);
  rig.params[ModCombs::PARAM_RATE] = sidefx::ExpUnmap(1.0f, 0.02f, 10.0f);
  rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
  rig.params[ModCombs::PARAM_SPREAD] = 0.0f;
  // DAMP open: its lowpass delay (taken off the line) is under 0.2 sample.
  rig.params[ModCombs::PARAM_DAMP] = 0.0f;
  for (int with_depth = 0; with_depth < 2; ++with_depth) {
    rig.params[ModCombs::PARAM_DEPTH] = with_depth ? 0.5f : 0.0f;
    Frame in[kB];
    Frame out[kB];
    memset(in, 0, sizeof(in));
    for (int b = 0; b < 300; ++b) {
      rig.Run(c, in, out);  // settle the smoothing
    }
    float lo = 1e9f, hi = 0.0f;
    for (int b = 0; b < int(2.0f * kFs / float(kB)); ++b) {
      rig.Run(c, in, out);
      lo = fminf(lo, rig.block->voice_delay(0));
      hi = fmaxf(hi, rig.block->voice_delay(0));
    }
    test::Note("depth %d: delay %.2f..%.2f samples", with_depth, lo, hi);
    if (with_depth) {
      CHECK_NEAR(hi / lo, sqrtf(2.0f), 0.02);
      CHECK_NEAR(hi, kFs / 500.0f, 0.5);
    } else {
      CHECK(hi - lo < 0.01f);
    }
  }

  // The notches move: the output spectrum of noise differs between two
  // instants half an LFO cycle apart (compare r(T) of 4096-sample frames).
  rig.block->Reset();
  rig.params[ModCombs::PARAM_DEPTH] = 0.5f;
  rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.9f);
  rig.params[ModCombs::PARAM_RATE] = sidefx::ExpUnmap(0.25f, 0.02f, 10.0f);
  const size_t frame = 4096;
  static float x[4096];
  ProcessContext c2 = test::Context(test::Tempo120(), 0);
  // Phase 0 of the LFO at the start: the line is at its middle; one
  // second later (quarter cycle) the shortest, three seconds the longest.
  NoiseThrough(&rig, c2, 1.0f, x, NULL, frame);
  const size_t long_period = size_t(kFs / 500.0f + 0.5f);
  const double r_mid = Autocorrelation(x, frame, long_period);
  NoiseThrough(&rig, c2, 2.0f, x, NULL, frame);
  const double r_long = Autocorrelation(x, frame, long_period);
  test::Note("r at the 500 Hz period: shortest line %.3f, longest %.3f",
             r_mid, r_long);
  CHECK(r_long > 0.4);
  CHECK(r_mid < r_long - 0.3);
}

TEST(mod_combs, spread_makes_stereo) {
  const size_t keep = 8192;
  static float l[8192];
  static float r[8192];
  for (int spread = 0; spread < 2; ++spread) {
    Rig rig;
    CHECK(rig.ok);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.3f);
    rig.params[ModCombs::PARAM_DEPTH] = 0.4f;
    rig.params[ModCombs::PARAM_VOICES] = VoicesValue(3);
    rig.params[ModCombs::PARAM_SPREAD] = spread ? 1.0f : 0.0f;
    NoiseThrough(&rig, c, 1.5f, l, r, keep);
    double lr = 0.0, ll = 0.0, rr = 0.0, diff = 0.0;
    for (size_t i = 0; i < keep; ++i) {
      lr += double(l[i]) * r[i];
      ll += double(l[i]) * l[i];
      rr += double(r[i]) * r[i];
      diff = fmax(diff, fabs(double(l[i]) - r[i]));
    }
    const double correlation = lr / sqrt(ll * rr);
    test::Note("spread %d: L/R correlation %.3f, max |L - R| %.3g", spread,
               correlation, diff);
    if (spread) {
      CHECK(correlation < 0.8);
    } else {
      CHECK(diff == 0.0);
    }
  }
}

TEST(mod_combs, damp_darkens) {
  // DAMP 1 against 0 at +90 %: the ringing after the input stops (only
  // what went round the loop) has much less high end: its first difference
  // falls much more than its level.
  double brightness[2];
  for (int damp = 0; damp < 2; ++damp) {
    Rig rig;
    CHECK(rig.ok);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    rig.params[ModCombs::PARAM_FREQ] = FreqValue(100.0f);
    rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.9f);
    rig.params[ModCombs::PARAM_DEPTH] = 0.0f;
    rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
    rig.params[ModCombs::PARAM_DAMP] = float(damp);
    NoiseThrough(&rig, c, 0.5f, NULL, NULL, 0);
    Frame in[kB];
    Frame out[kB];
    memset(in, 0, sizeof(in));
    double e = 0.0, d = 0.0;
    float last = 0.0f;
    for (int b = 0; b < int(0.15f * kFs / float(kB)); ++b) {
      rig.Run(c, in, out);
      for (size_t i = 0; i < kB; ++i) {
        if (b > int(0.03f * kFs / float(kB))) {
          e += double(out[i].l) * out[i].l;
          d += double(out[i].l - last) * (out[i].l - last);
        }
        last = out[i].l;
      }
    }
    brightness[damp] = e > 0.0 ? d / e : 1e9;
  }
  test::Note("tail brightness: open %.4f, damped %.4f", brightness[0],
             brightness[1]);
  CHECK(brightness[1] < 0.25 * brightness[0]);
}

TEST(mod_combs, no_clicks) {
  Rig rig;
  CHECK(rig.ok);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[ModCombs::PARAM_FREQ] = FreqValue(100.0f);
  rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.3f);
  rig.params[ModCombs::PARAM_DEPTH] = 0.1f;
  rig.params[ModCombs::PARAM_VOICES] = VoicesValue(2);
  Frame in[kB];
  Frame out[kB];
  double phase = 0.0;
  float last = 0.0f;
  // Steady, FREQ jumps up 6 octaves, steady, feedback through zero (the
  // line halves), steady, VOICES jumps, steady.
  float steady_step = 0.0f;
  float jump_step = 0.0f;
  for (int stage = 0; stage < 7; ++stage) {
    if (stage == 1) {
      rig.params[ModCombs::PARAM_FREQ] = FreqValue(1600.0f);
    } else if (stage == 3) {
      rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(-0.3f);
    } else if (stage == 5) {
      rig.params[ModCombs::PARAM_VOICES] = VoicesValue(4);
    }
    const bool steady = (stage % 2) == 0;
    const int blocks = int(1.0f * kFs / float(kB));
    for (int b = 0; b < blocks; ++b) {
      for (size_t i = 0; i < kB; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(float(phase));
        phase += 2.0 * 3.14159265358979 * 300.0 / double(kFs);
      }
      rig.Run(c, in, out);
      for (size_t i = 0; i < kB; ++i) {
        const float step = fabsf(out[i].l - last);
        last = out[i].l;
        if (steady && b > blocks / 2) {
          steady_step = fmaxf(steady_step, step);
        } else if (!steady) {
          jump_step = fmaxf(jump_step, step);
        }
      }
    }
  }
  test::Note("largest step: steady %.4f, during jumps %.4f", steady_step,
             jump_step);
  CHECK(steady_step > 0.001f);
  CHECK(jump_step < 3.0f * steady_step);
}

TEST(mod_combs, format) {
  Rig rig;
  CHECK(rig.ok);
  const float values[] = { 0.0f, 0.5f, 1.0f };
  for (int synced = 0; synced < 2; ++synced) {
    ProcessContext c = test::Context(test::Tempo120(), synced ? 0x7f : 0);
    for (int p = 0; p < ModCombs::NUM_PARAMS; ++p) {
      for (int v = 0; v < 3; ++v) {
        char text[32];
        memset(text, 0, sizeof(text));
        rig.block->Format(p, values[v], c, text, sizeof(text));
        CHECK(strlen(text) > 0);
        CHECK(strlen(text) <= 10);
        test::Note("param %d value %.1f synced %d: '%s'", p, values[v],
                   synced, text);
      }
    }
  }
}

TEST(mod_combs, synced_rate_locks_to_bar) {
  // RATE synced to 1 BAR, then 1/4: the LFO phase follows bar_phase (and
  // four times it), through a tempo change.
  Rig rig;
  CHECK(rig.ok);
  sidefx::TempoState tempo = test::Tempo120();
  tempo.bar_phase = 0.37f;
  const float one_bar = 2.0f / 19.0f;      // SyncedRateIndex 17: 1 BAR
  const float quarter = 1.0f - 11.0f / 19.0f;  // index 11: 1/4
  CHECK_NEAR(sidefx::SyncedHz(one_bar, 0.5f), 0.5, 1e-4);
  CHECK_NEAR(sidefx::SyncedHz(quarter, 0.5f), 2.0, 1e-4);
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  const float rates[] = { one_bar, one_bar, quarter };
  const float beats[] = { 0.5f, 0.4f, 0.4f };
  const float multiples[] = { 1.0f, 1.0f, 4.0f };
  for (int stage = 0; stage < 3; ++stage) {
    rig.params[ModCombs::PARAM_RATE] = rates[stage];
    tempo.beat_seconds = beats[stage];
    tempo.bar_increment = 1.0f / (4.0f * tempo.beat_seconds * kFs);
    float worst = 0.0f;
    for (int b = 0; b < 1500; ++b) {
      ProcessContext c = test::Context(tempo, 1u << ModCombs::PARAM_RATE);
      rig.Run(c, in, out);
      tempo.bar_phase += tempo.bar_increment * float(kB);
      tempo.bar_phase -= floorf(tempo.bar_phase);
      if (b > 750) {
        const float expected = tempo.bar_phase * multiples[stage];
        float error = rig.block->lfo_phase() - (expected - floorf(expected));
        error -= floorf(error + 0.5f);
        worst = fmaxf(worst, fabsf(error));
      }
    }
    test::Note("stage %d: worst phase error %.4f", stage, worst);
    CHECK(worst < 0.005f);
  }
}

namespace {

// Goertzel power of x at hz.
double PowerAt(const float* x, size_t n, double hz) {
  const double c = 2.0 * cos(2.0 * 3.14159265358979 * hz / kFs);
  double s1 = 0.0, s2 = 0.0;
  for (size_t i = 0; i < n; ++i) {
    const double s = x[i] + c * s1 - s2;
    s2 = s1;
    s1 = s;
  }
  return s1 * s1 + s2 * s2 - c * s1 * s2;
}

// The ring's fundamental: the strongest frequency within two semitones
// of the one expected, in steps of a cent. (The harmonics above it ring a
// little sharp of their multiples, as on a plucked string: the loop's
// lowpass delays them less.)
float RingHz(const float* x, size_t n, float expected_hz) {
  double best = expected_hz;
  double best_power = -1.0;
  for (int cents = -200; cents <= 200; ++cents) {
    const double hz = expected_hz * pow(2.0, cents / 1200.0);
    const double p = PowerAt(x, n, hz);
    if (p > best_power) {
      best_power = p;
      best = hz;
    }
  }
  return float(best);
}

}  // namespace

TEST(mod_combs, damp_keeps_the_pitch) {
  // Karplus-style: FEEDBACK +-99 %, no modulation, an impulse. The ring
  // must stay at FREQ whatever DAMP (the loop's lowpass delays it).
  const float hz[] = { 200.0f, 200.0f, 2000.0f, 2000.0f };
  const float damp[] = { 0.0f, 1.0f, 0.0f, 0.3f };
  const size_t n = 12000;
  static float x[12000];
  for (int t = 0; t < 4; ++t) {
    for (int sign = 0; sign < 2; ++sign) {
      Rig rig;
      ProcessContext c = test::Context(test::Tempo120(), 0);
      rig.params[ModCombs::PARAM_FREQ] = FreqValue(hz[t]);
      rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(sign ? -0.99f
                                                                : 0.99f);
      rig.params[ModCombs::PARAM_DEPTH] = 0.0f;
      rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
      rig.params[ModCombs::PARAM_SPREAD] = 0.0f;
      rig.params[ModCombs::PARAM_DAMP] = damp[t];
      Frame in[kB];
      Frame out[kB];
      for (size_t b = 0; b < n; b += kB) {
        memset(in, 0, sizeof(in));
        if (b == 0) {
          in[0].l = in[0].r = 1.0f;
        }
        rig.Run(c, in, out);
        for (size_t i = 0; i < kB; ++i) {
          x[b + i] = out[i].l;
        }
      }
      const float f = RingHz(x, n, hz[t]);
      const float cents = 1200.0f * log2f(f / hz[t]);
      test::Note("%4.0f Hz, DAMP %.1f, FEEDBACK %s99%%: rings at %.1f Hz "
                 "(%+.1f ct)", hz[t], damp[t], sign ? "-" : "+", f, cents);
      CHECK(fabsf(cents) < 4.0f);
    }
  }
}

TEST(mod_combs, voices_change_keeps_the_phases) {
  // DEPTH and SPREAD full, VOICES 4 -> 1: the voices that keep playing
  // must not jump to a new LFO phase (a backwards chirp). And the left and
  // right voice of a pair are in antiphase, at 4 voices as at 1.
  Rig rig;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  rig.params[ModCombs::PARAM_FREQ] = FreqValue(200.0f);
  rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.5f);
  rig.params[ModCombs::PARAM_DEPTH] = 1.0f;
  rig.params[ModCombs::PARAM_SPREAD] = 1.0f;
  rig.params[ModCombs::PARAM_DAMP] = 0.0f;
  rig.params[ModCombs::PARAM_VOICES] = VoicesValue(4);
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  for (int b = 0; b < 3000; ++b) {
    rig.Run(c, in, out);
  }
  // Pair 0 (no detune): log2(D / d) of the two adds up to DEPTH's 2
  // octaves when they are in antiphase.
  const float base = kFs / 200.0f;
  float worst = 0.0f;
  for (int b = 0; b < 1500; ++b) {
    rig.Run(c, in, out);
    const float sum = log2f(base / rig.block->voice_delay(0)) +
        log2f(base / rig.block->voice_delay(1));
    worst = fmaxf(worst, fabsf(sum - 2.0f));
  }
  test::Note("4 voices: pair 0 off antiphase by up to %.3f octave", worst);
  CHECK(worst < 0.02f);

  float largest = 0.0f;
  float last = rig.block->voice_delay(1);
  rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
  for (int b = 0; b < 3000; ++b) {
    rig.Run(c, in, out);
    const float d = rig.block->voice_delay(1);
    largest = fmaxf(largest, fabsf(d - last));
    last = d;
  }
  test::Note("4 -> 1 voices: voice 1 moves up to %.3f samples per block",
             largest);
  CHECK(largest < 1.0f);
  CHECK(rig.block->voices_running() == 2);
}

TEST(mod_combs, silent_voices_come_back_clean) {
  // A ringing comb at 4 voices; VOICES 1 stops the six others (they cost
  // nothing while off) and they come back silent, not with the old ring.
  // Two rigs run the same; then, with silence in, one goes back to 4
  // voices: pair 0 rings on at half the level (1 / sqrt(4)), and the
  // others must add nothing.
  Rig a;
  Rig b;
  Rig* rigs[2] = { &a, &b };
  ProcessContext c = test::Context(test::Tempo120(), 0);
  for (int r = 0; r < 2; ++r) {
    Rig& rig = *rigs[r];
    rig.params[ModCombs::PARAM_FEEDBACK] = FeedbackValue(0.99f);
    rig.params[ModCombs::PARAM_DEPTH] = 0.0f;
    rig.params[ModCombs::PARAM_SPREAD] = 1.0f;
    rig.params[ModCombs::PARAM_DAMP] = 0.0f;
    rig.params[ModCombs::PARAM_VOICES] = VoicesValue(4);
    NoiseThrough(&rig, c, 0.5f, NULL, NULL, 0);
    CHECK(rig.block->voices_running() == 8);
    rig.params[ModCombs::PARAM_VOICES] = VoicesValue(1);
    NoiseThrough(&rig, c, 0.5f, NULL, NULL, 0);
    CHECK(rig.block->voices_running() == 2);
  }
  a.params[ModCombs::PARAM_VOICES] = VoicesValue(4);
  Frame in[kB];
  Frame out[kB];
  memset(in, 0, sizeof(in));
  double energy[2] = { 0.0, 0.0 };
  for (int blocks = 0; blocks < 300; ++blocks) {
    for (int r = 0; r < 2; ++r) {
      rigs[r]->Run(c, in, out);
      for (size_t i = 0; i < kB; ++i) {
        energy[r] += out[i].l * out[i].l + out[i].r * out[i].r;
      }
    }
  }
  CHECK(a.block->voices_running() == 8);
  test::Note("ring energy back at 4 voices %.4f, at 1 voice %.4f",
             energy[0], energy[1]);
  CHECK(energy[0] < 0.4 * energy[1]);
}
