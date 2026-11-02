// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: TAPE DELAY.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"
#include "fx/tape_delay.h"

namespace {

using sidefx::Frame;
using sidefx::MakeFrame;
using sidefx::ProcessContext;
using sidefx::TapeDelay;

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

struct Rig {
  Rig() : memory(4u << 20, 64u << 10), block(NULL), ok(false) {
    block = memory.memory()->internal->Create<TapeDelay>();
    ok = block && block->Init(memory.memory());
  }
  test::TestMemory memory;
  TapeDelay* block;
  bool ok;
};

void Defaults(float* p) {
  const sidefx::BlockInfo& info = TapeDelay().info();
  for (int i = 0; i < info.num_params; ++i) {
    p[i] = info.params[i].default_value;
  }
}

float HeadsValue(int mode) {
  return sidefx::StepValue(mode, TapeDelay::kNumHeadModes);
}

// A clean machine: no feedback, wobble, drive or age; heads in the middle.
void Clean(float* p, float time, int heads_mode) {
  Defaults(p);
  p[TapeDelay::TIME] = sidefx::ExpUnmap(time, 0.03f, 2.0f);
  p[TapeDelay::FEEDBACK] = 0.0f;
  p[TapeDelay::HEADS] = HeadsValue(heads_mode);
  p[TapeDelay::WOBBLE] = 0.0f;
  p[TapeDelay::DRIVE] = 0.0f;
  p[TapeDelay::AGE] = 0.0f;
  p[TapeDelay::WIDTH] = 0.0f;
}

void Run(TapeDelay* block, const ProcessContext& c, const float* p,
         const std::vector<Frame>& in, std::vector<Frame>* out) {
  out->resize(in.size());
  for (size_t i = 0; i < in.size(); i += kBlock) {
    size_t n = in.size() - i < kBlock ? in.size() - i : kBlock;
    block->Process(c, p, &in[i], &(*out)[i], n);
  }
}

std::vector<Frame> Impulse(float seconds, float amplitude) {
  std::vector<Frame> in(static_cast<size_t>(kFs * seconds),
                        MakeFrame(0.0f, 0.0f));
  in[0] = MakeFrame(amplitude, amplitude);
  return in;
}

std::vector<Frame> SineIn(float seconds, float hz, float amplitude,
                          size_t offset = 0) {
  std::vector<Frame> in(static_cast<size_t>(kFs * seconds));
  for (size_t i = 0; i < in.size(); ++i) {
    float x = amplitude * sinf(6.2831853f * hz * float(i + offset) / kFs);
    in[i] = MakeFrame(x, x);
  }
  return in;
}

size_t Peak(const std::vector<Frame>& x, bool right, size_t from, size_t to) {
  size_t best = from;
  float best_value = -1.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    float v = fabsf(right ? x[i].r : x[i].l);
    if (v > best_value) {
      best_value = v;
      best = i;
    }
  }
  return best;
}

float Energy(const std::vector<Frame>& x, bool right, size_t from,
             size_t to) {
  float e = 0.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    float v = right ? x[i].r : x[i].l;
    e += v * v;
  }
  return e;
}

float Sum(const std::vector<Frame>& x, size_t from, size_t to) {
  float s = 0.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    s += x[i].l;
  }
  return s;
}

size_t At(float seconds) {
  return static_cast<size_t>(seconds * kFs);
}

// Periods between upward zero crossings of the left channel in [from, to).
void Periods(const std::vector<Frame>& x, size_t from, size_t to,
             float* shortest, float* longest) {
  float last = -1.0f;
  *shortest = 1e9f;
  *longest = 0.0f;
  for (size_t i = from + 1; i < to && i < x.size(); ++i) {
    float a = x[i - 1].l, b = x[i].l;
    if (a < 0.0f && b >= 0.0f) {
      float t = float(i - 1) + a / (a - b);
      if (last > 0.0f) {
        *shortest = fminf(*shortest, t - last);
        *longest = fmaxf(*longest, t - last);
      }
      last = t;
    }
  }
}

}  // namespace

TEST(tape_delay, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  CHECK(rig.memory.external().used() <= (4u << 20));
  CHECK(rig.memory.internal().used() < (8u << 10));
  test::Note("external %zu bytes, internal %zu bytes",
             rig.memory.external().used(), rig.memory.internal().used());
  float p[TapeDelay::NUM_PARAMS];
  Defaults(p);
  p[TapeDelay::AGE] = 1.0f;
  p[TapeDelay::WOBBLE] = 1.0f;
  p[TapeDelay::DRIVE] = 1.0f;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in(At(2.0f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);

  uint32_t seed = 1;
  std::vector<Frame> noise(At(1.0f));
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = MakeFrame(test::Noise(&seed), test::Noise(&seed));
  }
  p[TapeDelay::FEEDBACK] = 1.0f;
  Run(rig.block, c, p, noise, &out);
  rig.block->Reset();
  Run(rig.block, c, p, in, &out);
  silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(tape_delay, stability) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  uint32_t seed = 7;
  float p[TapeDelay::NUM_PARAMS];
  Frame in[kBlock];
  Frame out[kBlock];
  bool finite = true;
  float peak = 0.0f;
  const size_t blocks = At(20.0f) / kBlock;
  for (int pass = 0; pass < 3; ++pass) {
    rig.block->Reset();
    for (size_t b = 0; b < blocks; ++b) {
      for (int i = 0; i < TapeDelay::NUM_PARAMS; ++i) {
        p[i] = pass == 0 ? 0.5f * (test::Noise(&seed) + 1.0f)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      uint16_t mask = pass == 0 && test::Noise(&seed) > 0.0f ? 1 : 0;
      ProcessContext c = test::Context(test::Tempo120(), mask);
      for (size_t i = 0; i < kBlock; ++i) {
        in[i] = MakeFrame(test::Noise(&seed), test::Noise(&seed));
      }
      rig.block->Process(c, p, in, out, kBlock);
      for (size_t i = 0; i < kBlock; ++i) {
        finite = finite && test::Finite(out[i]);
        peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
      }
    }
    test::Note("pass %d: peak so far %.3f", pass, peak);
  }
  CHECK(finite);
  CHECK(peak < 4.0f);

  // Runaway feedback with every head, then no input: bounded.
  for (int drive = 0; drive < 2; ++drive) {
    rig.block->Reset();
    for (int i = 0; i < TapeDelay::NUM_PARAMS; ++i) {
      p[i] = 1.0f;
    }
    p[TapeDelay::TIME] = 0.2f;
    p[TapeDelay::AGE] = 0.0f;
    p[TapeDelay::DRIVE] = float(drive);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    float tail = 0.0f;
    for (size_t b = 0; b < At(10.0f) / kBlock; ++b) {
      for (size_t i = 0; i < kBlock; ++i) {
        float x = b < 100 ? test::Noise(&seed) * 4.0f : 0.0f;
        in[i] = MakeFrame(x, x);
      }
      rig.block->Process(c, p, in, out, kBlock);
      for (size_t i = 0; i < kBlock; ++i) {
        if (b > 5000) {
          tail = fmaxf(tail, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
        finite = finite && test::Finite(out[i]);
      }
    }
    test::Note("self-oscillation at DRIVE %d: peak %.3f", drive, tail);
    CHECK(finite);
    CHECK(tail > 0.05f);  // it does run away
    CHECK(tail < 2.0f);
  }
}

TEST(tape_delay, three_heads) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[TapeDelay::NUM_PARAMS];
  Clean(p, 0.2f, 6);  // 1+2+3
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in = Impulse(0.8f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  const float tol = 0.001f * kFs;
  size_t h1 = Peak(out, false, 1, At(0.3f));
  size_t h2 = Peak(out, false, At(0.3f), At(0.5f));
  size_t h3 = Peak(out, false, At(0.5f), out.size());
  test::Note("heads at %.2f, %.2f, %.2f ms", h1 * 1000.0f / kFs,
             h2 * 1000.0f / kFs, h3 * 1000.0f / kFs);
  CHECK(fabsf(float(h1) - 0.2f * kFs) <= tol);
  CHECK(fabsf(float(h2) - 0.4f * kFs) <= tol);
  CHECK(fabsf(float(h3) - 0.6f * kFs) <= tol);
  CHECK(fabsf(out[h1].l) > 0.1f);
  CHECK(fabsf(out[h3].l) > 0.1f);

  // Each mode plays exactly its heads.
  for (int mode = 0; mode < TapeDelay::kNumHeadModes; ++mode) {
    Rig r;
    CHECK(r.ok);
    if (!r.ok) return;
    Clean(p, 0.2f, mode);
    Run(r.block, c, p, in, &out);
    uint8_t mask = TapeDelay::HeadMask(mode);
    for (int k = 0; k < 3; ++k) {
      size_t t = At(0.2f * float(k + 1));
      float e = Energy(out, false, t - 50, t + 50);
      CHECK(((mask >> k) & 1) ? e > 1e-3f : e < 1e-7f);
    }
  }
}

TEST(tape_delay, width_spreads_heads) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[TapeDelay::NUM_PARAMS];
  Clean(p, 0.2f, 5);  // 1+3
  p[TapeDelay::WIDTH] = 1.0f;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in = Impulse(0.8f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  size_t t1 = At(0.2f), t3 = At(0.6f);
  float l1 = Energy(out, false, t1 - 50, t1 + 50);
  float r1 = Energy(out, true, t1 - 50, t1 + 50);
  float l3 = Energy(out, false, t3 - 50, t3 + 50);
  float r3 = Energy(out, true, t3 - 50, t3 + 50);
  test::Note("head 1 L %.4f R %.6f, head 3 L %.6f R %.4f", l1, r1, l3, r3);
  CHECK(l1 > 100.0f * r1);
  CHECK(r3 > 100.0f * l3);
}

TEST(tape_delay, feedback_repeats) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[TapeDelay::NUM_PARAMS];
  Clean(p, 0.1f, 0);
  p[TapeDelay::FEEDBACK] = 0.5f;  // loop gain 0.575
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in = Impulse(0.5f, 0.1f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  size_t t = At(0.1f);
  float s1 = Sum(out, t - 20, t + 20);
  float s2 = Sum(out, 2 * t - 20, 2 * t + 20);
  float s3 = Sum(out, 3 * t - 20, 3 * t + 20);
  test::Note("repeat ratios %.3f %.3f (expected 0.575)", s2 / s1, s3 / s2);
  CHECK(fabsf(s2 / s1 - 0.575f) < 0.05f);
  CHECK(fabsf(s3 / s2 - 0.575f) < 0.05f);
}

TEST(tape_delay, age_darkens_and_thins) {
  float hf[2], lf[2];
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[TapeDelay::NUM_PARAMS];
    Clean(p, 0.05f, 0);
    p[TapeDelay::FEEDBACK] = 0.7f;
    p[TapeDelay::AGE] = float(k);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    uint32_t seed = 3;
    std::vector<Frame> in(At(0.5f), MakeFrame(0.0f, 0.0f));
    for (size_t i = 0; i < 1000; ++i) {
      float x = 0.3f * test::Noise(&seed);
      in[i] = MakeFrame(x, x);
    }
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    // The third repeat: high share in the first difference, low share in
    // a 100 Hz lowpass.
    size_t from = At(0.15f) + 100;
    size_t to = from + 1000;
    float e = 0.0f, d = 0.0f, low = 0.0f, lp = 0.0f;
    for (size_t i = from - 2000; i < to; ++i) {
      lp += 0.013f * (out[i].l - lp);
      if (i >= from) {
        e += out[i].l * out[i].l;
        float diff = out[i].l - out[i - 1].l;
        d += diff * diff;
        low += lp * lp;
      }
    }
    hf[k] = d / (e + 1e-12f);
    lf[k] = low;
  }
  // Thinner: the band under 100 Hz loses far more than the whole does.
  test::Note("HF share new %.3f aged %.3f; energy under 100 Hz new %.5f "
             "aged %.5f", hf[0], hf[1], lf[0], lf[1]);
  CHECK(hf[1] < 0.2f * hf[0]);
  CHECK(lf[1] < 0.1f * lf[0]);
}

TEST(tape_delay, wobble) {
  float spread[2];
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[TapeDelay::NUM_PARAMS];
    Clean(p, 0.5f, 0);
    p[TapeDelay::WOBBLE] = float(k);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    std::vector<Frame> in = SineIn(5.0f, 500.0f, 0.5f);
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    float lo, hi;
    Periods(out, At(0.7f), out.size(), &lo, &hi);
    spread[k] = (hi - lo) / (kFs / 500.0f);
  }
  test::Note("period spread: WOBBLE 0 %.4f, WOBBLE 1 %.4f", spread[0],
             spread[1]);
  CHECK(spread[0] < 0.002f);
  CHECK(spread[1] > 0.005f);
  CHECK(spread[1] < 0.05f);
}

TEST(tape_delay, drive_adds_harmonics) {
  float residual[2];
  const float f = 375.0f;
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[TapeDelay::NUM_PARAMS];
    Clean(p, 0.1f, 0);
    p[TapeDelay::DRIVE] = float(k);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    std::vector<Frame> in = SineIn(1.0f, f, 0.8f);
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    // Project a whole number of periods onto the fundamental.
    size_t from = At(0.3f);
    size_t n = size_t(kFs / f * 100.0f);
    double cs = 0.0, sn = 0.0, e = 0.0;
    for (size_t i = from; i < from + n; ++i) {
      double ph = 6.283185307179586 * f * double(i) / double(kFs);
      cs += out[i].l * cos(ph);
      sn += out[i].l * sin(ph);
      e += out[i].l * out[i].l;
    }
    double fundamental = 2.0 * (cs * cs + sn * sn) / double(n);
    residual[k] = float((e - fundamental) / e);
  }
  test::Note("residual (harmonics) share: DRIVE 0 %.4f, DRIVE 1 %.4f",
             residual[0], residual[1]);
  CHECK(residual[0] < 0.01f);
  CHECK(residual[1] > 0.03f);
}

TEST(tape_delay, varispeed_bends_pitch) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[TapeDelay::NUM_PARAMS];
  Clean(p, 0.3f, 0);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  const float f = 500.0f;
  std::vector<Frame> in = SineIn(1.0f, f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  // Longer time: the tape slows, the repeats drop in pitch for a while.
  p[TapeDelay::TIME] = sidefx::ExpUnmap(0.4f, 0.03f, 2.0f);
  in = SineIn(3.0f, f, 0.5f, At(1.0f));
  Run(rig.block, c, p, in, &out);
  float lo, hi;
  Periods(out, 0, At(0.5f), &lo, &hi);
  const float period = kFs / f;
  test::Note("while slewing: periods %.2f .. %.2f samples (%.2f)", lo, hi,
             period);
  CHECK(hi > 1.05f * period);
  CHECK(hi < 3.0f * period);
  Periods(out, At(2.0f), out.size(), &lo, &hi);
  test::Note("settled: periods %.3f .. %.3f", lo, hi);
  CHECK(fabsf(lo - period) < 0.01f * period);
  CHECK(fabsf(hi - period) < 0.01f * period);

  // And the echo now comes at the new time.
  Rig fresh;
  CHECK(fresh.ok);
  if (!fresh.ok) return;
  Clean(p, 0.3f, 0);
  in = Impulse(0.1f, 0.0f);
  Run(fresh.block, c, p, in, &out);
  p[TapeDelay::TIME] = sidefx::ExpUnmap(0.4f, 0.03f, 2.0f);
  in = Impulse(3.0f, 0.0f);
  Run(fresh.block, c, p, in, &out);
  in = Impulse(1.0f, 0.5f);
  Run(fresh.block, c, p, in, &out);
  size_t t = Peak(out, false, 1, out.size());
  test::Note("echo 3 s after the change at %.2f ms", t * 1000.0f / kFs);
  CHECK(fabsf(float(t) - 0.4f * kFs) <= 0.001f * kFs);
}

TEST(tape_delay, no_clicks) {
  const float f = 220.0f;
  const float amplitude = 0.5f;
  const float normal = 6.2831853f * f / kFs * amplitude;
  float worst[2] = { 0.0f, 0.0f };
  for (int test_case = 0; test_case < 2; ++test_case) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[TapeDelay::NUM_PARAMS];
    Clean(p, 0.3f, 0);
    ProcessContext c = test::Context(test::Tempo120(), 0);
    // Case 0: time jumps on head 1. Case 1: every head mode and width.
    const float times[] = { 0.3f, 0.32f, 0.6f, 0.05f, 2.0f, 0.03f, 0.3f };
    const int steps = test_case ? 2 * TapeDelay::kNumHeadModes : 7;
    size_t phase = 0;
    float previous = 0.0f;
    std::vector<Frame> out;
    for (int k = 0; k < steps; ++k) {
      if (test_case == 0) {
        p[TapeDelay::TIME] = sidefx::ExpUnmap(times[k], 0.03f, 2.0f);
      } else {
        p[TapeDelay::HEADS] = HeadsValue((k * 3) % TapeDelay::kNumHeadModes);
        p[TapeDelay::WIDTH] = (k & 1) ? 1.0f : 0.0f;
      }
      std::vector<Frame> in = SineIn(test_case ? 1.0f : 2.5f, f, amplitude,
                                     phase);
      phase += in.size();
      Run(rig.block, c, p, in, &out);
      for (size_t i = 0; i < out.size(); ++i) {
        if (k > 0 || i > At(0.95f)) {
          worst[test_case] = fmaxf(worst[test_case],
                                   fmaxf(fabsf(out[i].l - previous), 0.0f));
        }
        previous = out[i].l;
      }
    }
  }
  test::Note("largest steps: time %.4f, heads %.4f; a clean sine's %.4f",
             worst[0], worst[1], normal);
  CHECK(worst[0] < 3.0f * normal);
  CHECK(worst[1] < 3.0f * normal);
}

TEST(tape_delay, format) {
  TapeDelay block;
  const sidefx::BlockInfo& info = block.info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params <= 7);
  const float values[] = { 0.0f, 0.25f, 0.5f, 0.75f, 1.0f };
  for (int synced = 0; synced < 2; ++synced) {
    ProcessContext c = test::Context(test::Tempo120(), synced ? 0xffff : 0);
    for (int i = 0; i < info.num_params; ++i) {
      CHECK(strlen(info.params[i].name) <= 8);
      for (size_t v = 0; v < sizeof(values) / sizeof(values[0]); ++v) {
        char text[32];
        memset(text, 'x', sizeof(text));
        block.Format(i, values[v], c, text, sizeof(text));
        test::Note("%s %.2f %s: \"%s\"", info.params[i].name, values[v],
                   synced ? "synced" : "free", text);
        CHECK(strlen(text) > 0);
        CHECK(strlen(text) <= 10);
      }
    }
  }
}

TEST(tape_delay, synced_time_follows_tempo) {
  float quarter = -1.0f;
  for (int i = 0; i <= 1000 && quarter < 0.0f; ++i) {
    float v = float(i) / 1000.0f;
    if (sidefx::kNoteValues[sidefx::NoteValueIndex(v)].beats == 1.0f) {
      quarter = v;
    }
  }
  CHECK(quarter >= 0.0f);
  const float beats[] = { 0.5f, 0.3f, 0.8f };
  for (int k = 0; k < 3; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[TapeDelay::NUM_PARAMS];
    Clean(p, 0.1f, 0);
    p[TapeDelay::TIME] = quarter;
    sidefx::TempoState tempo = test::Tempo120();
    tempo.beat_seconds = beats[k];
    ProcessContext c = test::Context(tempo, 1 << TapeDelay::TIME);
    std::vector<Frame> in = Impulse(1.0f, 0.5f);
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    size_t t = Peak(out, false, 1, out.size());
    test::Note("beat %.2f s: echo at %.2f ms", beats[k], t * 1000.0f / kFs);
    CHECK(fabsf(float(t) - beats[k] * kFs) <= 0.001f * kFs);
  }
}

TEST(tape_delay, long_synced_times) {
  // 1 BAR at 100 BPM is 2.4 s: past the free range's 2 s, but the tape
  // holds head 3 at three times 3.6 s, so it plays on the grid. 2 BAR
  // (4.8 s) does not fit: the screen shows the 3.6 s it plays.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[TapeDelay::NUM_PARAMS];
  Clean(p, 0.1f, 0);
  p[TapeDelay::TIME] = sidefx::StepValue(17, sidefx::kNumNoteValues);  // 1 BAR
  sidefx::TempoState tempo = test::Tempo120();
  tempo.beat_seconds = 0.6f;
  ProcessContext c = test::Context(tempo, 1 << TapeDelay::TIME);
  std::vector<Frame> in = Impulse(3.0f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  const size_t t = Peak(out, false, 1, out.size());
  test::Note("1 BAR at 100 BPM: echo at %.3f s", float(t) / kFs);
  CHECK(fabsf(float(t) - 2.4f * kFs) <= 0.001f * kFs);
  char text[16];
  rig.block->Format(TapeDelay::TIME, p[TapeDelay::TIME], c, text,
                    sizeof(text));
  CHECK(!strcmp(text, "1 BAR"));
  rig.block->Format(TapeDelay::TIME,
                    sidefx::StepValue(18, sidefx::kNumNoteValues), c, text,
                    sizeof(text));
  test::Note("2 BAR at 100 BPM shows \"%s\"", text);
  CHECK(!strcmp(text, "3.60s"));
}
