// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: TAP DELAY.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "fx/tap_delay.h"
#include "test_support.h"

using sidefx::Frame;
using sidefx::MakeFrame;
using sidefx::StepValue;
using sidefx::TapDelay;

namespace {

const float kFs = 48014.32f;

struct Rig {
  test::TestMemory memory;
  TapDelay* block;
  bool ok;
  sidefx::TempoState tempo;
  uint16_t sync;
  float params[TapDelay::NUM_PARAMS];

  Rig() : memory(4u << 20, 32u << 10) {
    block = memory.internal().Create<TapDelay>();
    ok = block && block->Init(memory.memory());
    tempo = test::Tempo120();
    sync = 0;
    for (int i = 0; i < TapDelay::NUM_PARAMS; ++i) {
      params[i] = block->info().params[i].default_value;
    }
  }

  void Run(const Frame* in, Frame* out, size_t n) {
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      size_t len = n - i < sidefx::kBlockSize ? n - i : sidefx::kBlockSize;
      sidefx::ProcessContext c = test::Context(tempo, sync);
      block->Process(c, params, in + i, out + i, len);
      tempo.bar_phase += tempo.bar_increment * float(len);
      tempo.bar_phase -= floorf(tempo.bar_phase);
    }
  }

  // A plain single echo: one tap, no feedback, no colour, centred.
  void Plain(float seconds) {
    params[TapDelay::PARAM_TIME] = sidefx::ExpUnmap(seconds, 0.05f, 4.0f);
    params[TapDelay::PARAM_PATTERN] = 0.0f;
    params[TapDelay::PARAM_TAPS] = 0.0f;
    params[TapDelay::PARAM_DECAY] = 0.0f;
    params[TapDelay::PARAM_FEEDBACK] = 0.0f;
    params[TapDelay::PARAM_SPREAD] = 0.0f;
    params[TapDelay::PARAM_TONE] = 0.5f;
  }
};

size_t PeakIndex(const std::vector<Frame>& x, size_t from, size_t to) {
  size_t best = from;
  float peak = -1.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    const float a = fabsf(x[i].l) + fabsf(x[i].r);
    if (a > peak) {
      peak = a;
      best = i;
    }
  }
  return best;
}

float PeakIn(const std::vector<Frame>& x, size_t from, size_t to, bool right) {
  float peak = 0.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    const float a = fabsf(right ? x[i].r : x[i].l);
    peak = a > peak ? a : peak;
  }
  return peak;
}

// Energy of the first difference over the energy: high for bright.
float Brightness(const std::vector<Frame>& x, size_t from, size_t to) {
  double e = 0.0, d = 0.0;
  for (size_t i = from + 1; i < to; ++i) {
    e += double(x[i].l) * x[i].l;
    const double v = double(x[i].l) - x[i - 1].l;
    d += v * v;
  }
  return e > 0.0 ? float(d / e) : 0.0f;
}

}  // namespace

TEST(tap_delay, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(rig.memory.external().used() <= (2u << 20) + 64);
  CHECK(rig.memory.internal().used() < 8192);
  test::Note("external %zu bytes, internal %zu bytes",
             rig.memory.external().used(), rig.memory.internal().used());
  rig.block->Reset();
  std::vector<Frame> in(size_t(kFs * 5), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  rig.params[TapDelay::PARAM_TIME] = 1.0f;
  rig.params[TapDelay::PARAM_FEEDBACK] = 1.0f;
  rig.Run(&in[0], &out[0], in.size());
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(tap_delay, stability) {
  Rig rig;
  rig.block->Reset();
  uint32_t seed = 1;
  const size_t n = size_t(kFs * 20);
  std::vector<Frame> in(sidefx::kBlockSize), out(sidefx::kBlockSize);
  float peak = 0.0f;
  bool finite = true;
  for (int pass = 0; pass < 3; ++pass) {
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      for (int p = 0; p < TapDelay::NUM_PARAMS; ++p) {
        rig.params[p] = pass == 0 ? 0.5f + 0.5f * test::Noise(&seed)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      rig.sync = pass == 0 && (i & 4096) ? 1 : 0;
      for (size_t j = 0; j < in.size(); ++j) {
        // Pass 2: everything at 1 with a hot input.
        const float g = pass == 2 ? 4.0f : 1.0f;
        in[j] = MakeFrame(g * test::Noise(&seed), g * test::Noise(&seed));
      }
      rig.Run(&in[0], &out[0], in.size());
      for (size_t j = 0; j < out.size(); ++j) {
        finite = finite && test::Finite(out[j]);
        peak = fabsf(out[j].l) > peak ? fabsf(out[j].l) : peak;
        peak = fabsf(out[j].r) > peak ? fabsf(out[j].r) : peak;
      }
    }
    test::Note("pass %d: peak %.3f", pass, peak);
  }
  CHECK(finite);
  CHECK(peak < 4.0f);
}

TEST(tap_delay, echo_at_time) {
  const float times[] = { 0.05f, 0.35f, 1.25f, 4.0f };
  for (int t = 0; t < 4; ++t) {
    Rig rig;
    rig.block->Reset();
    rig.Plain(times[t]);
    std::vector<Frame> in(size_t(kFs * (times[t] + 0.5f)),
                          MakeFrame(0.0f, 0.0f));
    std::vector<Frame> out(in.size());
    in[100] = MakeFrame(1.0f, 1.0f);
    rig.Run(&in[0], &out[0], in.size());
    const float expected = 100.0f + times[t] * kFs;
    const size_t peak = PeakIndex(out, 0, out.size());
    test::Note("%.2f s: echo at %zu, expected %.1f, level %.3f", times[t], peak,
               expected, out[peak].l);
    CHECK(fabsf(float(peak) - expected) < 0.001f * kFs);
    CHECK(out[peak].l > 0.9f && out[peak].l < 1.1f);
  }
}

TEST(tap_delay, pattern_taps) {
  // EVEN, eight taps, no decay: an echo every eighth of the span.
  Rig rig;
  rig.block->Reset();
  rig.Plain(1.6f);
  rig.params[TapDelay::PARAM_TAPS] = 1.0f;
  std::vector<Frame> in(size_t(kFs * 2.0f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  in[0] = MakeFrame(1.0f, 1.0f);
  rig.Run(&in[0], &out[0], in.size());
  const float span = 1.6f * kFs;
  for (int k = 1; k <= 8; ++k) {
    const size_t at = size_t(span * float(k) / 8.0f + 0.5f);
    const float level = PeakIn(out, at - 48, at + 48, false);
    // Between the taps: nothing.
    const float between = PeakIn(out, at - size_t(span / 16.0f) - 200,
                                 at - size_t(span / 16.0f) + 200, false);
    CHECK(level > 0.3f);
    CHECK(between < 1.0e-3f);
  }
  // Every pattern's taps land where the table puts them.
  for (int p = 0; p < TapDelay::kNumPatterns; ++p) {
    Rig r;
    r.block->Reset();
    r.Plain(1.0f);
    r.params[TapDelay::PARAM_PATTERN] = StepValue(p, TapDelay::kNumPatterns);
    r.params[TapDelay::PARAM_TAPS] = 1.0f;
    std::vector<Frame> o(in.size());
    r.Run(&in[0], &o[0], in.size());
    for (int k = 0; k < TapDelay::kNumTaps; ++k) {
      const size_t at = size_t(TapDelay::TapDelaySamples(p, k, 1.0f) + 0.5f);
      CHECK(PeakIn(o, at > 48 ? at - 48 : 0, at + 48, false) > 0.2f);
    }
  }
}

TEST(tap_delay, feedback_decay_tone_spread) {
  std::vector<Frame> in(size_t(kFs * 1.2f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  in[0] = MakeFrame(1.0f, 1.0f);
  const size_t span = size_t(0.5f * kFs + 0.5f);
  {
    // FEEDBACK at about 50 %: the second echo about half the first.
    Rig rig;
    rig.block->Reset();
    rig.Plain(0.5f);
    rig.params[TapDelay::PARAM_FEEDBACK] = 0.5f / 1.05f;
    rig.Run(&in[0], &out[0], in.size());
    const float first = PeakIn(out, span - 48, span + 48, false);
    const float second = PeakIn(out, 2 * span - 48, 2 * span + 48, false);
    test::Note("feedback: %.3f then %.3f", first, second);
    CHECK(second / first > 0.4f && second / first < 0.55f);
  }
  {
    // DECAY at 1: the span's end 24 dB under the earliest tap.
    Rig rig;
    rig.block->Reset();
    rig.Plain(0.5f);
    rig.params[TapDelay::PARAM_TAPS] = 1.0f;
    rig.params[TapDelay::PARAM_DECAY] = 1.0f;
    rig.Run(&in[0], &out[0], in.size());
    const float first = PeakIn(out, span / 8 - 48, span / 8 + 48, false);
    const float last = PeakIn(out, span - 48, span + 48, false);
    test::Note("decay: %.3f .. %.3f", first, last);
    CHECK(last / first > 0.04f && last / first < 0.1f);
  }
  {
    // TONE fully dark: the later tap is much duller than the earlier.
    Rig rig;
    rig.block->Reset();
    rig.Plain(0.5f);
    rig.params[TapDelay::PARAM_TAPS] = StepValue(1, TapDelay::kNumTaps);
    rig.params[TapDelay::PARAM_TONE] = 0.0f;
    rig.Run(&in[0], &out[0], in.size());
    const float early = Brightness(out, span / 2 - 10, span / 2 + 2000);
    const float late = Brightness(out, span - 10, span + 2000);
    test::Note("dark: brightness %.4f then %.4f", early, late);
    CHECK(late < 0.3f * early);
    // Bright: a 60 Hz sine loses more on the later tap.
    Rig b;
    b.block->Reset();
    b.Plain(0.5f);
    b.params[TapDelay::PARAM_TAPS] = StepValue(1, TapDelay::kNumTaps);
    b.params[TapDelay::PARAM_TONE] = 1.0f;
    std::vector<Frame> sine(size_t(kFs * 0.15f));
    for (size_t i = 0; i < sine.size(); ++i) {
      const float s = sinf(6.2831853f * 60.0f * float(i) / kFs);
      sine[i] = MakeFrame(s, s);
    }
    std::vector<Frame> burst(in.size(), MakeFrame(0.0f, 0.0f));
    for (size_t i = 0; i < sine.size(); ++i) {
      burst[i] = sine[i];
    }
    b.Run(&burst[0], &out[0], burst.size());
    const float at_half = PeakIn(out, span / 2 + 2000, span / 2 + 6000, false);
    const float at_end = PeakIn(out, span + 2000, span + 6000, false);
    test::Note("bright: 60 Hz at %.3f then %.3f", at_half, at_end);
    CHECK(at_end < 0.3f * at_half);
  }
  {
    // SPREAD at 1: two taps, hard left then hard right, from a mono input.
    Rig rig;
    rig.block->Reset();
    rig.Plain(0.5f);
    rig.params[TapDelay::PARAM_TAPS] = StepValue(1, TapDelay::kNumTaps);
    rig.params[TapDelay::PARAM_SPREAD] = 1.0f;
    rig.Run(&in[0], &out[0], in.size());
    const size_t half = span / 2;
    const float hl = PeakIn(out, half - 48, half + 48, false);
    const float hr = PeakIn(out, half - 48, half + 48, true);
    const float el = PeakIn(out, span - 48, span + 48, false);
    const float er = PeakIn(out, span - 48, span + 48, true);
    test::Note("spread: half %.3f/%.3f, end %.3f/%.3f", hl, hr, el, er);
    CHECK(hl > 0.5f && hr < 0.01f);
    CHECK(er > 0.5f && el < 0.01f);
  }
}

TEST(tap_delay, no_clicks) {
  Rig rig;
  rig.block->Reset();
  rig.Plain(0.3f);
  const size_t n = size_t(kFs * 9.0f);
  std::vector<Frame> in(n), out(n);
  for (size_t i = 0; i < n; ++i) {
    const float s = 0.5f * sinf(6.2831853f * 220.0f * float(i) / kFs);
    in[i] = MakeFrame(s, s);
  }
  const float normal = 0.5f * 6.2831853f * 220.0f / kFs;
  // 0..3 s: one tap, TIME jumping. 3..5 s: eight taps, steady, for the
  // normal step of their sum. 5..9 s: TIME, PATTERN, TAPS and TONE jumping.
  const float times[] = { 0.3f, 0.9f, 0.12f, 2.0f, 0.5f, 0.07f };
  const size_t steady = size_t(kFs * 3.0f);
  const size_t jumping = size_t(kFs * 5.0f);
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    const int section = int(i / size_t(kFs * 0.25f));
    if (i < steady) {
      rig.params[TapDelay::PARAM_TIME] =
          sidefx::ExpUnmap(times[section % 6], 0.05f, 4.0f);
    } else if (i < jumping) {
      rig.params[TapDelay::PARAM_TIME] = sidefx::ExpUnmap(0.4f, 0.05f, 4.0f);
      rig.params[TapDelay::PARAM_TAPS] = 1.0f;
      rig.params[TapDelay::PARAM_DECAY] = 0.3f;
    } else {
      rig.params[TapDelay::PARAM_TIME] =
          sidefx::ExpUnmap(times[section % 6], 0.05f, 4.0f);
      rig.params[TapDelay::PARAM_PATTERN] =
          StepValue(section % 8, TapDelay::kNumPatterns);
      rig.params[TapDelay::PARAM_TAPS] = StepValue((section * 3) % 8, 8);
      rig.params[TapDelay::PARAM_TONE] = (section & 1) ? 0.1f : 0.9f;
    }
    rig.Run(&in[i], &out[i], sidefx::kBlockSize < n - i
            ? sidefx::kBlockSize : n - i);
  }
  float worst[3] = { 0.0f, 0.0f, 0.0f };
  float curvature[3] = { 0.0f, 0.0f, 0.0f };
  for (size_t i = size_t(kFs * 0.5f); i < n; ++i) {
    const int part = i < steady ? 0 : (i < jumping ? 1 : 2);
    if (part == 1 && i < steady + size_t(kFs)) {
      continue;  // let the eight taps fill up
    }
    const float d = fabsf(out[i].l - out[i - 1].l);
    const float c = fabsf(out[i].l - 2.0f * out[i - 1].l + out[i - 2].l);
    worst[part] = d > worst[part] ? d : worst[part];
    curvature[part] = c > curvature[part] ? c : curvature[part];
  }
  test::Note("one tap: largest step %.4f, a 220 Hz sine's %.4f", worst[0],
             normal);
  test::Note("eight taps: steady step %.4f / curvature %.5f, jumping "
             "%.4f / %.5f", worst[1], curvature[1], worst[2], curvature[2]);
  CHECK(worst[0] < 4.0f * normal);
  CHECK(worst[2] < 4.0f * worst[1]);
  CHECK(curvature[2] < 4.0f * curvature[1]);
}

TEST(tap_delay, format) {
  Rig rig;
  sidefx::TempoState tempo = test::Tempo120();
  const float values[] = { 0.0f, 0.5f, 1.0f };
  for (int s = 0; s < 2; ++s) {
    sidefx::ProcessContext c = test::Context(tempo, s ? 0xffff : 0);
    for (int p = 0; p < TapDelay::NUM_PARAMS; ++p) {
      for (int v = 0; v < 3; ++v) {
        char text[32];
        memset(text, 0, sizeof(text));
        rig.block->Format(p, values[v], c, text, 11);
        test::Note("%s %.1f %s: %s", rig.block->info().params[p].name,
                   values[v], s ? "synced" : "free", text);
        CHECK(strlen(text) > 0 && strlen(text) <= 10);
      }
    }
  }
  const sidefx::BlockInfo& info = rig.block->info();
  CHECK(strlen(info.name) <= 10 && strlen(info.short_name) <= 5);
  for (int p = 0; p < info.num_params; ++p) {
    CHECK(strlen(info.params[p].name) <= 8);
  }
}

TEST(tap_delay, synced_time_follows_tempo) {
  const float beats[] = { 0.5f, 0.375f, 0.75f };
  for (int b = 0; b < 3; ++b) {
    Rig rig;
    rig.block->Reset();
    rig.Plain(0.3f);
    rig.sync = 1 << TapDelay::PARAM_TIME;
    rig.params[TapDelay::PARAM_TIME] =
        StepValue(11, sidefx::kNumNoteValues);  // 1/4
    rig.tempo.beat_seconds = beats[b];
    rig.tempo.bar_increment = 1.0f / (4.0f * beats[b] * kFs);
    std::vector<Frame> in(size_t(kFs * 1.0f), MakeFrame(0.0f, 0.0f));
    std::vector<Frame> out(in.size());
    in[10] = MakeFrame(1.0f, 1.0f);
    rig.Run(&in[0], &out[0], in.size());
    const size_t peak = PeakIndex(out, 0, out.size());
    const float expected = 10.0f + beats[b] * kFs;
    test::Note("beat %.3f s: echo at %zu, expected %.1f", beats[b], peak,
               expected);
    CHECK(fabsf(float(peak) - expected) < 0.001f * kFs);
  }
}

TEST(tap_delay, clock_jitter_does_not_crossfade) {
  // TIME synced to 1 BAR on a 4 PPQN external clock: every pulse moves the
  // beat by up to +-0.05 % (the 250 us timestamp grid through the tempo
  // glide), tens of samples on a 96000-sample span. The repeats of a
  // steady sine must not dip and swell with crossfades at every pulse.
  Rig rig;
  rig.Plain(1.0f);
  rig.sync = 1 << TapDelay::PARAM_TIME;
  rig.params[TapDelay::PARAM_TIME] = StepValue(17, sidefx::kNumNoteValues);
  const size_t n = size_t(kFs * 6.0f) / sidefx::kBlockSize *
      sidefx::kBlockSize;
  std::vector<Frame> in(n);
  std::vector<Frame> out(n);
  for (size_t i = 0; i < n; ++i) {
    const float s = 0.5f * sinf(2.0f * 3.14159265f * 1000.0f * float(i) / kFs);
    in[i] = MakeFrame(s, s);
  }
  uint32_t seed = 5;
  const size_t pulse = size_t(0.125f * kFs) / sidefx::kBlockSize *
      sidefx::kBlockSize;
  for (size_t i = 0; i < n; i += pulse) {
    rig.tempo.beat_seconds = 0.5f * (1.0f + 0.0005f * test::Noise(&seed));
    rig.Run(&in[i], &out[i], n - i < pulse ? n - i : pulse);
  }
  // RMS of the repeats in 10 ms windows, once the first has arrived.
  float lo = 1e30f;
  float hi = 0.0f;
  for (size_t start = size_t(2.1f * kFs); start + 480 <= n; start += 480) {
    double e = 0.0;
    for (size_t i = start; i < start + 480; ++i) {
      e += double(out[i].l) * out[i].l;
    }
    lo = fminf(lo, float(e));
    hi = fmaxf(hi, float(e));
  }
  const float swing_db = 10.0f * log10f(hi / lo);
  test::Note("repeat level swings %.2f dB", swing_db);
  CHECK(swing_db < 1.0f);
}

TEST(tap_delay, long_synced_span) {
  // 1 BAR at 50 BPM is 4.8 s: past the free range's 4 s, but the line
  // holds 5.4 s, so the pattern stays on the grid. At 40 BPM (6 s) it
  // does not fit: the screen shows the 5.4 s it plays.
  Rig rig;
  rig.block->Reset();
  rig.Plain(1.0f);
  rig.sync = 1 << TapDelay::PARAM_TIME;
  rig.params[TapDelay::PARAM_TIME] = StepValue(17, sidefx::kNumNoteValues);
  rig.tempo.beat_seconds = 1.2f;
  rig.tempo.bar_increment = 1.0f / (4.0f * 1.2f * kFs);
  std::vector<Frame> in(size_t(kFs * 5.0f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  in[10] = MakeFrame(1.0f, 1.0f);
  rig.Run(&in[0], &out[0], in.size());
  const size_t peak = PeakIndex(out, 0, out.size());
  test::Note("1 BAR at 50 BPM: echo at %.3f s", float(peak - 10) / kFs);
  CHECK(fabsf(float(peak) - (10.0f + 4.8f * kFs)) < 0.001f * kFs);
  char text[16];
  sidefx::ProcessContext c = test::Context(rig.tempo, rig.sync);
  rig.block->Format(TapDelay::PARAM_TIME, rig.params[TapDelay::PARAM_TIME],
                    c, text, sizeof(text));
  CHECK(!strcmp(text, "1 BAR"));
  c.beat_seconds = 1.5f;
  rig.block->Format(TapDelay::PARAM_TIME, rig.params[TapDelay::PARAM_TIME],
                    c, text, sizeof(text));
  test::Note("1 BAR at 40 BPM shows \"%s\"", text);
  CHECK(!strcmp(text, "5.40s"));
}
