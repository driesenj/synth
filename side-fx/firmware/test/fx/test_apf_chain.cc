// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: APF CHAIN (src/fx/apf_chain.cc).

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "fx/apf_chain.h"
#include "test_support.h"

using sidefx::ApfChain;
using sidefx::Frame;
using sidefx::ProcessContext;
using sidefx::kBlockSize;

namespace {

const float kFs = 48014.32f;
const int kNumParams = 7;
enum { LENGTH, STAGES, DIFFUSE, FEEDBACK, DAMP, MOD, WIDTH };

// The first stage ratios of each chain, as in apf_chain.cc.
const float kLeftRatios[] = { 1.01f, 0.73f, 1.31f, 0.89f };

struct Fixture {
  test::TestMemory memory;
  ApfChain* block;
  Fixture() : memory(4u << 20, 64u << 10) {
    block = memory.internal().Create<ApfChain>();
    if (!block->Init(memory.memory())) {
      block = NULL;
    }
  }
};

void Defaults(float* params) {
  ApfChain block;
  const sidefx::BlockInfo& info = block.info();
  for (int i = 0; i < info.num_params; ++i) {
    params[i] = info.params[i].default_value;
  }
}

// A plain delay: no diffusion, no feedback, no modulation, chains apart.
void PlainDelay(float* params) {
  Defaults(params);
  params[DIFFUSE] = 0.0f;
  params[FEEDBACK] = 0.0f;
  params[DAMP] = 0.0f;
  params[MOD] = 0.0f;
  params[WIDTH] = 1.0f;
}

// in: the left input (the right one is silent unless both is set).
void Run(ApfChain* block, const ProcessContext& context, const float* params,
         const std::vector<float>& in, std::vector<Frame>* out,
         bool both = false) {
  out->resize(in.size());
  Frame input[kBlockSize];
  for (size_t start = 0; start < in.size(); start += kBlockSize) {
    const size_t n = in.size() - start < kBlockSize ? in.size() - start
                                                     : kBlockSize;
    for (size_t i = 0; i < n; ++i) {
      input[i].l = in[start + i];
      input[i].r = both ? in[start + i] : 0.0f;
    }
    block->Process(context, params, input, &(*out)[start], n);
  }
}

std::vector<float> Impulse(size_t samples) {
  std::vector<float> x(samples, 0.0f);
  x[0] = 1.0f;
  return x;
}

// The sample with the largest |left| in [from, to).
size_t Peak(const std::vector<Frame>& x, size_t from, size_t to) {
  size_t best = from;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    if (fabsf(x[i].l) > fabsf(x[best].l)) {
      best = i;
    }
  }
  return best;
}

float MaxStep(const std::vector<Frame>& x, size_t from) {
  float m = 0.0f;
  for (size_t i = from + 1; i < x.size(); ++i) {
    m = fmaxf(m, fabsf(x[i].l - x[i - 1].l));
    m = fmaxf(m, fabsf(x[i].r - x[i - 1].r));
  }
  return m;
}

int NoteIndex(const char* label) {
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, label)) {
      return i;
    }
  }
  return -1;
}

}  // namespace

TEST(apf_chain, init_and_silence) {
  Fixture f;
  CHECK(f.block != NULL);
  if (!f.block) {
    return;
  }
  test::Note("internal arena use: %u bytes (object %u), external %u bytes",
             unsigned(f.memory.internal().used()),
             unsigned(sizeof(ApfChain)),
             unsigned(f.memory.external().used()));
  CHECK(f.memory.internal().used() < 8192);
  CHECK(f.memory.external().used() <= (2u << 20) + 64);
  CHECK(f.block->info().num_params == kNumParams);

  float params[kNumParams];
  Defaults(params);
  ProcessContext context = test::Context(test::Tempo120(), 0);
  std::vector<float> noise(48000);
  uint32_t seed = 1;
  for (size_t i = 0; i < noise.size(); ++i) {
    noise[i] = test::Noise(&seed);
  }
  std::vector<Frame> out;
  Run(f.block, context, params, noise, &out, true);
  f.block->Reset();
  Run(f.block, context, params, std::vector<float>(48000, 0.0f), &out);
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);

  // A fresh block (garbage in the arenas) is silent at once too.
  Fixture g;
  Run(g.block, context, params, std::vector<float>(4800, 0.0f), &out);
  silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(apf_chain, stability) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  uint32_t seed = 7;
  float peak = 0.0f;
  bool finite = true;
  Frame in[kBlockSize], out[kBlockSize];
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
  // Every parameter at 0, at 1 (feedback 0.98, darkest damping), and at 1
  // with no damping, with noise at +-1 and then +-4.
  context.sync_mask = 0;
  for (int setting = 0; setting < 6; ++setting) {
    for (int p = 0; p < kNumParams; ++p) {
      params[p] = (setting % 3) ? 1.0f : 0.0f;
    }
    if (setting % 3 == 2) {
      params[DAMP] = 0.0f;
    }
    const float level = setting < 3 ? 1.0f : 4.0f;
    for (int block = 0; block < int(5.0f * kFs / kBlockSize); ++block) {
      for (size_t i = 0; i < kBlockSize; ++i) {
        in[i].l = level * test::Noise(&seed);
        in[i].r = level * test::Noise(&seed);
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

TEST(apf_chain, plain_delay_time) {
  // DIFFUSE 0 makes every stage a plain delay: the impulse comes out after
  // the sum of the first STAGES stage delays.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  PlainDelay(params);
  params[STAGES] = sidefx::StepValue(1, 8);  // 4 stages
  const float lengths[] = { 0.0f, 0.5f, 1.0f };
  for (int k = 0; k < 3; ++k) {
    params[LENGTH] = lengths[k];
    const float stage = sidefx::ExpMap(lengths[k], 0.001f, 0.1f) * kFs;
    float expected = 0.0f;
    for (int s = 0; s < 4; ++s) {
      expected += floorf(stage * kLeftRatios[s] + 0.5f);  // whole samples
    }
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(expected) + 4800), &out);
    const size_t peak = Peak(out, 0, out.size());
    test::Note("LENGTH %.1f: impulse at %u, expected %.1f (peak %.3f)",
               lengths[k], unsigned(peak), expected, out[peak].l);
    CHECK(fabsf(float(peak) - expected) < 0.001f * kFs);
    CHECK(float(peak) == expected);
    CHECK(out[peak].l == 1.0f);
  }
}

TEST(apf_chain, diffusion_is_allpass) {
  // High DIFFUSE, no feedback: the impulse's energy comes out whole (an
  // allpass chain is lossless) but smeared: no sample near the impulse's
  // height, and many samples carry it.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  PlainDelay(params);
  params[DIFFUSE] = 1.0f;
  params[STAGES] = 1.0f;  // 16
  params[LENGTH] = sidefx::ExpUnmap(0.005f, 0.001f, 0.1f);
  std::vector<Frame> out;
  Run(f.block, context, params, Impulse(size_t(3.0f * kFs)), &out);
  double energy = 0.0;
  float peak = 0.0f;
  int busy = 0;
  for (size_t i = 0; i < out.size(); ++i) {
    energy += double(out[i].l) * out[i].l;
    peak = fmaxf(peak, fabsf(out[i].l));
    busy += fabsf(out[i].l) > 1e-3f;
  }
  test::Note("energy %.4f, peak %.3f, %d samples over -60 dB", energy, peak,
             busy);
  CHECK(fabs(energy - 1.0) < 0.02);
  CHECK(peak < 0.5f);
  CHECK(busy > 2000);
}

TEST(apf_chain, feedback_sustains_and_damp_darkens) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[MOD] = 0.0f;
  double tail[3], brightness[3];
  const float feedback[] = { 0.0f, 1.0f, 1.0f };
  const float damp[] = { 0.0f, 0.0f, 0.8f };
  for (int k = 0; k < 3; ++k) {
    params[FEEDBACK] = feedback[k];
    params[DAMP] = damp[k];
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(4.0f * kFs)), &out, true);
    double e = 1e-30, d = 0.0;
    for (size_t i = size_t(2.0f * kFs); i < out.size(); ++i) {
      e += double(out[i].l) * out[i].l;
      const double step = out[i].l - out[i - 1].l;
      d += step * step;
    }
    tail[k] = e;
    brightness[k] = d / e;
    test::Note("FEEDBACK %.0f DAMP %.1f: tail energy (2..4 s) %.2e, "
               "brightness %.4f", feedback[k], damp[k], e, brightness[k]);
  }
  CHECK(tail[0] < 1e-12);
  CHECK(tail[1] > 1e-3);
  CHECK(brightness[2] < 0.3 * brightness[1]);
}

TEST(apf_chain, width) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  for (int k = 0; k < 2; ++k) {
    params[WIDTH] = float(k);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(48000), &out, true);
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
      CHECK(fabs(correlation) < 0.5);
    }
  }
}

TEST(apf_chain, mod_moves_the_stages) {
  // MOD sways the delays: a steady sine through the chain picks up a
  // slowly changing phase, so the output differs from the unmodulated one.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  Defaults(params);
  params[FEEDBACK] = 0.0f;
  std::vector<float> sine(size_t(2.0f * kFs));
  for (size_t i = 0; i < sine.size(); ++i) {
    sine[i] = 0.5f * sinf(2.0f * float(M_PI) * 1000.0f * float(i) / kFs);
  }
  std::vector<Frame> out[2];
  for (int k = 0; k < 2; ++k) {
    params[MOD] = float(k);
    f.block->Reset();
    Run(f.block, context, params, sine, &out[k], true);
  }
  double difference = 0.0, energy = 1e-30;
  for (size_t i = size_t(kFs); i < sine.size(); ++i) {
    const double d = out[1][i].l - out[0][i].l;
    difference += d * d;
    energy += double(out[0][i].l) * out[0][i].l;
  }
  test::Note("MOD 1 vs 0: difference %.1f dB", 10.0 * log10(difference /
                                                            energy));
  CHECK(difference > 0.01 * energy);
}

TEST(apf_chain, no_clicks) {
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  const size_t settle = size_t(kFs);
  const size_t length = 4500 * kBlockSize;  // 3 s
  std::vector<float> sine(length);
  for (size_t i = 0; i < length; ++i) {
    sine[i] = 0.5f * sinf(2.0f * float(M_PI) * 220.0f * float(i) / kFs);
  }
  struct Jump { int param; float low, high; };
  const Jump kJumps[] = {
    { LENGTH, 0.3f, 0.7f },
    { STAGES, 0.0f, 1.0f },
    { DIFFUSE, 0.0f, 1.0f },
    { FEEDBACK, 0.0f, 1.0f },
    { DAMP, 0.0f, 1.0f },
    { MOD, 0.0f, 1.0f },
    { WIDTH, 0.0f, 1.0f },
  };
  for (size_t j = 0; j < sizeof(kJumps) / sizeof(kJumps[0]); ++j) {
    const Jump& jump = kJumps[j];
    float reference = 0.0f;
    std::vector<Frame> out;
    for (int k = 0; k < 2; ++k) {
      Defaults(params);
      params[jump.param] = k ? jump.high : jump.low;
      f.block->Reset();
      Run(f.block, context, params, sine, &out, true);
      reference = fmaxf(reference, MaxStep(out, settle));
    }
    Defaults(params);
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

TEST(apf_chain, format) {
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

TEST(apf_chain, synced_loop_follows_tempo) {
  // Synced, LENGTH sets the loop's period: with no diffusion, the repeats
  // of an impulse are a note value apart (and the first one a note value,
  // less one block, after it).
  Fixture f;
  float params[kNumParams];
  PlainDelay(params);
  params[FEEDBACK] = 0.7f;
  params[STAGES] = sidefx::StepValue(1, 8);  // 4 stages
  const int eighth = NoteIndex("1/8");
  CHECK(eighth >= 0);
  params[LENGTH] = sidefx::StepValue(eighth, sidefx::kNumNoteValues);
  const float beats[] = { 0.5f, 0.25f };
  for (int k = 0; k < 2; ++k) {
    sidefx::TempoState tempo = test::Tempo120();
    tempo.beat_seconds = beats[k];
    ProcessContext context = test::Context(tempo, 1 << LENGTH);
    const float period = 0.5f * beats[k] * kFs;
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(3.5f * period)), &out);
    const size_t first = Peak(out, 0, size_t(1.5f * period));
    const size_t second = Peak(out, size_t(1.5f * period),
                               size_t(2.5f * period));
    test::Note("1/8 at %.0f BPM: repeats at %u and %u, period %.1f",
               60.0f / beats[k], unsigned(first), unsigned(second), period);
    CHECK(fabsf(float(first) - period) < 0.001f * kFs);
    CHECK(fabsf(float(second - first) - period) < 0.001f * kFs);
  }
}

TEST(apf_chain, stages_jitter_does_not_click) {
  // A STAGES value that jitters at a step boundary (CV noise) toggles the
  // tap every block or two: each change must fade, never snap.
  Fixture f;
  ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[kNumParams];
  const size_t settle = size_t(kFs);
  const size_t length = 3000 * kBlockSize;  // 2 s
  std::vector<float> sine(length);
  for (size_t i = 0; i < length; ++i) {
    sine[i] = 0.3f * sinf(2.0f * float(M_PI) * 220.0f * float(i) / kFs);
  }
  float reference = 0.0f;
  std::vector<Frame> out;
  for (int k = 3; k <= 4; ++k) {
    Defaults(params);
    params[STAGES] = sidefx::StepValue(k, 8);
    f.block->Reset();
    Run(f.block, context, params, sine, &out, true);
    reference = fmaxf(reference, MaxStep(out, settle));
  }
  const int kPeriods[] = { 1, 2, 3, 100 };
  for (size_t p = 0; p < sizeof(kPeriods) / sizeof(kPeriods[0]); ++p) {
    Defaults(params);
    f.block->Reset();
    out.resize(length);
    Frame input[kBlockSize];
    for (size_t start = 0; start < length; start += kBlockSize) {
      const size_t block = start / kBlockSize;
      params[STAGES] = sidefx::StepValue(
          ((block / kPeriods[p]) & 1) ? 4 : 3, 8);
      for (size_t i = 0; i < kBlockSize; ++i) {
        input[i].l = input[i].r = sine[start + i];
      }
      f.block->Process(context, params, input, &out[start], kBlockSize);
    }
    const float jumping = MaxStep(out, settle);
    test::Note("STAGES 8<->10 every %d blocks: max step %.4f, held %.4f",
               kPeriods[p], jumping, reference);
    CHECK(jumping < 1.5f * reference);
  }
}

TEST(apf_chain, synced_length_too_long_for_the_stages) {
  // A note value longer than the tapped stages can hold sets the longest
  // loop they can: the same period on both sides, and the screen shows that
  // time instead of the note value. One that fits is kept exactly.
  Fixture f;
  float params[kNumParams];
  PlainDelay(params);
  params[FEEDBACK] = 0.7f;
  struct Case { int stages_step; const char* note; float min_s, max_s; };
  const Case kCases[] = {
    { 0, "1/4", 0.5f, 0.5f },     // 2 stages: 0.5 s fits
    { 0, "4 BAR", 0.55f, 0.62f },  // 2 stages: about 0.58 s at most
    { 3, "4 BAR", 1.8f, 2.2f },    // 8 stages: about 1.95 s
    { 7, "4 BAR", 3.4f, 3.8f },    // 16 stages: about 3.56 s
  };
  for (size_t k = 0; k < sizeof(kCases) / sizeof(kCases[0]); ++k) {
    const Case& c = kCases[k];
    const int note = NoteIndex(c.note);
    CHECK(note >= 0);
    params[STAGES] = sidefx::StepValue(c.stages_step, 8);
    params[LENGTH] = sidefx::StepValue(note, sidefx::kNumNoteValues);
    ProcessContext context = test::Context(test::Tempo120(), 1 << LENGTH);
    f.block->Reset();
    std::vector<Frame> out;
    Run(f.block, context, params, Impulse(size_t(3.2f * c.max_s * kFs)),
        &out, true);
    // The first two arrivals on each side.
    size_t first[2], second[2];
    for (int side = 0; side < 2; ++side) {
      std::vector<Frame> x(out);
      if (side) {
        for (size_t i = 0; i < x.size(); ++i) {
          x[i].l = x[i].r;
        }
      }
      first[side] = Peak(x, 0, size_t(1.5f * c.max_s * kFs));
      second[side] = Peak(x, first[side] + size_t(0.5f * c.min_s * kFs),
                          first[side] + size_t(1.5f * c.max_s * kFs));
    }
    const float period_l = float(second[0] - first[0]) / kFs;
    const float period_r = float(second[1] - first[1]) / kFs;
    char text[16];
    f.block->Format(LENGTH, params[LENGTH], context, text, 11);
    char expected[16];
    if (c.min_s == c.max_s) {
      snprintf(expected, sizeof(expected), "%s", c.note);
    } else {
      sidefx::FormatSeconds(expected, sizeof(expected), period_l);
    }
    test::Note("%d stages, %s: loop %.4f s left, %.4f s right, shows \"%s\"",
               2 * (c.stages_step + 1), c.note, period_l, period_r, text);
    CHECK(period_l >= c.min_s - 0.002f && period_l <= c.max_s + 0.002f);
    CHECK(fabsf(period_l - period_r) < 0.002f);
    if (c.min_s == c.max_s) {
      CHECK(!strcmp(text, expected));
    } else {
      // The displayed time is the loop's, to its rounding.
      CHECK(strcmp(text, c.note) != 0);
      const float shown = float(atof(text)) * (strstr(text, "ms") ? 0.001f
                                                                   : 1.0f);
      CHECK(fabsf(shown - period_l) < 0.01f * period_l);
    }
  }
}
