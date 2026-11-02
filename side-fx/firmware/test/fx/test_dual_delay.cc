// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: DUAL DELAY.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"
#include "fx/dual_delay.h"

namespace {

using sidefx::DualDelay;
using sidefx::Frame;
using sidefx::MakeFrame;
using sidefx::ProcessContext;

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

struct Rig {
  Rig() : memory(8u << 20, 64u << 10), block(NULL), ok(false) {
    block = memory.memory()->internal->Create<DualDelay>();
    ok = block && block->Init(memory.memory());
  }
  test::TestMemory memory;
  DualDelay* block;
  bool ok;
};

void Defaults(float* p) {
  const sidefx::BlockInfo& info = DualDelay().info();
  for (int i = 0; i < info.num_params; ++i) {
    p[i] = info.params[i].default_value;
  }
}

// A clean echo: no feedback, no modulation, flat tone, full width.
void Clean(float* p, float time_l, float time_r) {
  Defaults(p);
  p[DualDelay::TIME_L] = sidefx::ExpUnmap(time_l, 0.001f, 10.0f);
  p[DualDelay::TIME_R] = sidefx::ExpUnmap(time_r, 0.001f, 10.0f);
  p[DualDelay::FEEDBACK] = 0.0f;
  p[DualDelay::CROSS] = 0.0f;
  p[DualDelay::TONE] = 0.5f;
  p[DualDelay::MOD] = 0.0f;
  p[DualDelay::WIDTH] = 1.0f;
}

// Runs `in` through the block in kBlock pieces.
void Run(DualDelay* block, const ProcessContext& c, const float* p,
         const std::vector<Frame>& in, std::vector<Frame>* out) {
  out->resize(in.size());
  for (size_t i = 0; i < in.size(); i += kBlock) {
    size_t n = in.size() - i < kBlock ? in.size() - i : kBlock;
    block->Process(c, p, &in[i], &(*out)[i], n);
  }
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

float MaxAbs(const std::vector<Frame>& x, size_t from, size_t to) {
  float m = 0.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    m = fmaxf(m, fmaxf(fabsf(x[i].l), fabsf(x[i].r)));
  }
  return m;
}

}  // namespace

TEST(dual_delay, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  CHECK(rig.memory.external().used() <= (4u << 20));
  CHECK(rig.memory.internal().used() < (8u << 10));
  test::Note("external %zu bytes, internal %zu bytes",
             rig.memory.external().used(), rig.memory.internal().used());
  float p[DualDelay::NUM_PARAMS];
  Defaults(p);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in(size_t(kFs * 2.0f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);

  // After noise and a Reset(), silence again at once.
  uint32_t seed = 1;
  std::vector<Frame> noise(static_cast<size_t>(kFs));
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = MakeFrame(test::Noise(&seed), test::Noise(&seed));
  }
  p[DualDelay::FEEDBACK] = 1.0f;
  Run(rig.block, c, p, noise, &out);
  rig.block->Reset();
  Run(rig.block, c, p, in, &out);
  silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(dual_delay, stability) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  uint32_t seed = 7;
  float p[DualDelay::NUM_PARAMS];
  Frame in[kBlock];
  Frame out[kBlock];
  bool finite = true;
  float peak = 0.0f;
  const size_t blocks = size_t(20.0f * kFs) / kBlock;
  for (int pass = 0; pass < 3; ++pass) {
    rig.block->Reset();
    for (size_t b = 0; b < blocks; ++b) {
      for (int i = 0; i < DualDelay::NUM_PARAMS; ++i) {
        p[i] = pass == 0 ? 0.5f * (test::Noise(&seed) + 1.0f)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      uint16_t mask = pass == 0 ? uint16_t(test::Noise(&seed) > 0.0f ? 3 : 0)
          : 0;
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

  // Self-oscillation at the top stays bounded once the input stops.
  rig.block->Reset();
  for (int i = 0; i < DualDelay::NUM_PARAMS; ++i) {
    p[i] = 1.0f;
  }
  p[DualDelay::TIME_L] = p[DualDelay::TIME_R] = 0.3f;
  p[DualDelay::TONE] = 0.5f;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  float tail = 0.0f;
  for (size_t b = 0; b < size_t(10.0f * kFs) / kBlock; ++b) {
    for (size_t i = 0; i < kBlock; ++i) {
      float x = b < 100 ? test::Noise(&seed) * 4.0f : 0.0f;
      in[i] = MakeFrame(x, 0.5f * x);
    }
    rig.block->Process(c, p, in, out, kBlock);
    for (size_t i = 0; i < kBlock; ++i) {
      if (b > 5000) tail = fmaxf(tail, fmaxf(fabsf(out[i].l),
                                            fabsf(out[i].r)));
      CHECK(test::Finite(out[i]));
    }
  }
  test::Note("self-oscillation peak %.3f", tail);
  CHECK(tail < 2.0f);
}

TEST(dual_delay, echo_times) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[DualDelay::NUM_PARAMS];
  Clean(p, 0.25f, 0.4f);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in(size_t(kFs * 1.0f), MakeFrame(0.0f, 0.0f));
  in[0] = MakeFrame(0.5f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  const float tol = 0.001f * kFs;
  size_t pl = Peak(out, false, 1, out.size());
  size_t pr = Peak(out, true, 1, out.size());
  test::Note("L echo at %.2f ms, R at %.2f ms", pl * 1000.0f / kFs,
             pr * 1000.0f / kFs);
  CHECK(fabsf(float(pl) - 0.25f * kFs) <= tol);
  CHECK(fabsf(float(pr) - 0.4f * kFs) <= tol);
  CHECK(fabsf(out[pl].l) > 0.3f);
  CHECK(fabsf(out[pr].r) > 0.3f);
  // No feedback: nothing after the first echo.
  CHECK(MaxAbs(out, size_t(0.45f * kFs), out.size()) < 1e-3f);
}

TEST(dual_delay, feedback_repeats) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[DualDelay::NUM_PARAMS];
  Clean(p, 0.1f, 0.1f);
  p[DualDelay::FEEDBACK] = 0.5f;  // loop gain 0.575
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in(size_t(kFs * 0.5f), MakeFrame(0.0f, 0.0f));
  in[0] = MakeFrame(0.1f, 0.1f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  const size_t t = size_t(0.1f * kFs);
  // Window sums: the interpolator keeps DC exactly, an impulse's energy
  // not quite.
  float e1 = Sum(out, t - 10, t + 10);
  float e2 = Sum(out, 2 * t - 10, 2 * t + 10);
  float e3 = Sum(out, 3 * t - 10, 3 * t + 10);
  float r1 = e2 / e1;
  float r2 = e3 / e2;
  test::Note("repeat ratios %.3f %.3f (expected 0.575)", r1, r2);
  CHECK(fabsf(r1 - 0.575f) < 0.05f);
  CHECK(fabsf(r2 - 0.575f) < 0.05f);
}

TEST(dual_delay, ping_pong) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[DualDelay::NUM_PARAMS];
  Clean(p, 0.2f, 0.3f);
  p[DualDelay::CROSS] = 1.0f;
  p[DualDelay::FEEDBACK] = 0.6f;
  ProcessContext c = test::Context(test::Tempo120(), 0);
  std::vector<Frame> in(size_t(kFs * 1.2f), MakeFrame(0.0f, 0.0f));
  in[0] = MakeFrame(0.5f, 0.5f);
  std::vector<Frame> out;
  Run(rig.block, c, p, in, &out);
  const float tol = 0.001f * kFs;
  size_t l1 = Peak(out, false, 1, size_t(0.45f * kFs));
  size_t r1 = Peak(out, true, 1, size_t(0.65f * kFs));
  size_t l2 = Peak(out, false, size_t(0.45f * kFs), out.size());
  test::Note("L %.1f ms, R %.1f ms, L again %.1f ms", l1 * 1000.0f / kFs,
             r1 * 1000.0f / kFs, l2 * 1000.0f / kFs);
  CHECK(fabsf(float(l1) - 0.2f * kFs) <= tol);
  CHECK(fabsf(float(r1) - 0.5f * kFs) <= tol);
  CHECK(fabsf(float(l2) - 0.7f * kFs) <= tol);
  // The right line hears nothing of its own at 300 ms.
  CHECK(Energy(out, true, size_t(0.29f * kFs), size_t(0.31f * kFs)) < 1e-6f);
}

TEST(dual_delay, tone_in_the_loop) {
  float hf[3];
  const float tones[3] = { 0.0f, 0.5f, 1.0f };
  for (int k = 0; k < 3; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[DualDelay::NUM_PARAMS];
    Clean(p, 0.05f, 0.05f);
    p[DualDelay::FEEDBACK] = 0.7f;
    p[DualDelay::TONE] = tones[k];
    ProcessContext c = test::Context(test::Tempo120(), 0);
    uint32_t seed = 3;
    std::vector<Frame> in(size_t(kFs * 0.5f), MakeFrame(0.0f, 0.0f));
    for (size_t i = 0; i < 1000; ++i) {
      float x = 0.3f * test::Noise(&seed);
      in[i] = MakeFrame(x, x);
    }
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    // The fourth repeat: share of energy in the first difference.
    size_t from = size_t(0.2f * kFs);
    size_t to = from + 1000;
    float e = 0.0f, d = 0.0f;
    for (size_t i = from; i < to; ++i) {
      e += out[i].l * out[i].l;
      float diff = out[i].l - out[i - 1].l;
      d += diff * diff;
    }
    hf[k] = d / (e + 1e-12f);
  }
  test::Note("HF share dark %.3f flat %.3f thin %.3f", hf[0], hf[1], hf[2]);
  CHECK(hf[0] < 0.25f * hf[1]);
  CHECK(hf[2] > 1.1f * hf[1]);
}

TEST(dual_delay, modulation_chorus) {
  float spread[2];
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) return;
    float p[DualDelay::NUM_PARAMS];
    Clean(p, 0.3f, 0.3f);
    p[DualDelay::MOD] = k ? 1.0f : 0.0f;
    ProcessContext c = test::Context(test::Tempo120(), 0);
    std::vector<Frame> in(size_t(kFs * 4.0f));
    for (size_t i = 0; i < in.size(); ++i) {
      float x = 0.5f * sinf(6.2831853f * 500.0f * float(i) / kFs);
      in[i] = MakeFrame(x, x);
    }
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    // Spread of the period between upward zero crossings.
    float last = -1.0f, lo = 1e9f, hi = 0.0f;
    for (size_t i = size_t(0.5f * kFs); i < out.size(); ++i) {
      float a = out[i - 1].l, b = out[i].l;
      if (a < 0.0f && b >= 0.0f) {
        float t = float(i - 1) + a / (a - b);
        if (last > 0.0f) {
          lo = fminf(lo, t - last);
          hi = fmaxf(hi, t - last);
        }
        last = t;
      }
    }
    spread[k] = (hi - lo) / (kFs / 500.0f);
  }
  test::Note("period spread: MOD 0 %.4f, MOD 1 %.4f", spread[0], spread[1]);
  CHECK(spread[0] < 0.002f);
  CHECK(spread[1] > 0.01f);
  CHECK(spread[1] < 0.2f);
}

TEST(dual_delay, no_clicks) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) return;
  float p[DualDelay::NUM_PARAMS];
  Clean(p, 0.3f, 0.3f);
  ProcessContext c = test::Context(test::Tempo120(), 0);
  const float f = 220.0f;
  const float amplitude = 0.5f;
  const float normal = 6.2831853f * f / kFs * amplitude;
  // Times in seconds, 0.5 s each: glides (small steps), crossfades
  // (jumps), a slow sweep.
  const float times[] = { 0.3f, 0.31f, 0.33f, 0.6f, 0.05f, 2.0f, 0.3f,
                          0.29f, 9.0f, 0.001f, 0.3f };
  const int num_times = sizeof(times) / sizeof(times[0]);
  std::vector<Frame> in(size_t(kFs * 0.5f));
  std::vector<Frame> out;
  float worst = 0.0f;
  size_t phase = 0;
  float previous = 0.0f;
  for (int k = 0; k < num_times + 1; ++k) {
    if (k < num_times) {
      p[DualDelay::TIME_L] = sidefx::ExpUnmap(times[k], 0.001f, 10.0f);
    }
    for (size_t i = 0; i < in.size(); ++i, ++phase) {
      float x = amplitude * sinf(6.2831853f * f * float(phase) / kFs);
      in[i] = MakeFrame(x, x);
    }
    if (k == num_times) {
      // A sweep across the range at a fast knob turn.
      for (size_t i = 0; i < in.size(); i += kBlock) {
        p[DualDelay::TIME_L] = 0.4f + 0.3f * float(i) / float(in.size());
        size_t n = in.size() - i < kBlock ? in.size() - i : kBlock;
        rig.block->Process(c, p, &in[i], &out[i], n);
      }
    } else {
      Run(rig.block, c, p, in, &out);
    }
    for (size_t i = 0; i < out.size(); ++i) {
      if (k > 0 || i > size_t(0.31f * kFs)) {
        worst = fmaxf(worst, fabsf(out[i].l - previous));
      }
      previous = out[i].l;
    }
  }
  test::Note("largest step %.4f, a clean sine's %.4f", worst, normal);
  CHECK(worst < 3.0f * normal);
}

TEST(dual_delay, format) {
  DualDelay block;
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
        char small[11];
        block.Format(i, values[v], c, small, sizeof(small));
        CHECK(strcmp(small, text) == 0);
      }
    }
  }
}

TEST(dual_delay, synced_time_follows_tempo) {
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
    float p[DualDelay::NUM_PARAMS];
    Clean(p, 0.1f, 0.1f);
    p[DualDelay::TIME_L] = quarter;
    sidefx::TempoState tempo = test::Tempo120();
    tempo.beat_seconds = beats[k];
    ProcessContext c = test::Context(tempo, 1 << DualDelay::TIME_L);
    std::vector<Frame> in(size_t(kFs * 1.0f), MakeFrame(0.0f, 0.0f));
    in[0] = MakeFrame(0.5f, 0.5f);
    std::vector<Frame> out;
    Run(rig.block, c, p, in, &out);
    size_t pl = Peak(out, false, 1, out.size());
    test::Note("beat %.2f s: echo at %.2f ms", beats[k], pl * 1000.0f / kFs);
    CHECK(fabsf(float(pl) - beats[k] * kFs) <= 0.001f * kFs);
  }
}
