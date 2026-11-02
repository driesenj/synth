// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: DUAL SHIFT.

#include <string.h>

#include "check.h"
#include "fx/dual_shift.h"
#include "test_support.h"

using sidefx::DualShift;
using sidefx::Frame;
using sidefx::kBlockSize;
using sidefx::kSampleRate;

namespace {

const float kPi = 3.14159265f;

struct Rig {
  test::TestMemory memory;
  DualShift* block;
  bool ok;
  float params[DualShift::NUM_PARAMS];
  sidefx::ProcessContext context;

  Rig() : memory(4u << 20, 64u << 10) {
    block = memory.internal().Create<DualShift>();
    ok = block && block->Init(memory.memory());
    for (int i = 0; i < DualShift::NUM_PARAMS; ++i) {
      params[i] = block->info().params[i].default_value;
    }
    context = test::Context(test::Tempo120(), 0);
  }

  // Unison, no delay, no feedback, no detune, both voices in the middle.
  void Neutral() {
    params[DualShift::PITCH_A] = 0.5f;
    params[DualShift::PITCH_B] = 0.5f;
    params[DualShift::DETUNE] = 0.5f;
    params[DualShift::DELAY] = 0.0f;
    params[DualShift::FEEDBACK] = 0.0f;
    params[DualShift::WINDOW] = 0.5f;
    params[DualShift::WIDTH] = 0.0f;
  }

  // n a multiple of kBlockSize.
  void Run(const Frame* in, Frame* out, size_t n) {
    for (size_t i = 0; i < n; i += kBlockSize) {
      block->Process(context, params, in + i, out + i, kBlockSize);
      context.bar_phase += context.bar_increment * float(kBlockSize);
      if (context.bar_phase >= 1.0f) {
        context.bar_phase -= 1.0f;
      }
    }
  }
};

size_t Blocks(float seconds) {
  return size_t(seconds * kSampleRate) / kBlockSize * kBlockSize;
}

void Sine(Frame* x, size_t n, float hz, float amplitude) {
  for (size_t i = 0; i < n; ++i) {
    x[i].l = x[i].r = amplitude * sinf(2.0f * kPi * hz * float(i) /
                                       kSampleRate);
  }
}

// Goertzel power of one channel of x[start, end) at hz.
float Power(const Frame* x, size_t start, size_t end, float hz, bool right) {
  const float w = 2.0f * kPi * hz / kSampleRate;
  const float c = 2.0f * cosf(w);
  float s1 = 0.0f;
  float s2 = 0.0f;
  for (size_t i = start; i < end; ++i) {
    const float s = (right ? x[i].r : x[i].l) + c * s1 - s2;
    s2 = s1;
    s1 = s;
  }
  return s1 * s1 + s2 * s2 - c * s1 * s2;
}

// The strongest frequency in lo..hi, in 0.5 Hz steps.
float Peak(const Frame* x, size_t start, size_t end, float lo, float hi,
           bool right) {
  float best = lo;
  float best_power = -1.0f;
  for (float f = lo; f <= hi; f += 0.5f) {
    const float p = Power(x, start, end, f, right);
    if (p > best_power) {
      best_power = p;
      best = f;
    }
  }
  return best;
}

// The pitch by short-time autocorrelation: the median over 10 ms frames of
// the best lag within -40 % .. +40 % of the expected period. A delay-line
// shifter's output is the shifted tone with the phase stepping from one
// grain to the next, which can move a long FFT's peak by the grain rate;
// within a frame the period is the shifted one.
float Pitch(const Frame* x, size_t start, size_t end, float expected_hz) {
  const size_t frame = 480;
  const int lo = int(kSampleRate / expected_hz / 1.4f);
  const int hi = int(kSampleRate / expected_hz / 0.7f) + 1;
  float estimates[512];
  int n = 0;
  for (size_t f = start; f + frame + hi + 1 < end && n < 512; f += frame) {
    float best = -2.0f;
    int best_lag = lo;
    float r[3] = { 0.0f, 0.0f, 0.0f };
    float scores[256];
    for (int lag = lo; lag <= hi && lag - lo < 256; ++lag) {
      double xy = 0.0, xx = 0.0, yy = 0.0;
      for (size_t i = f; i < f + frame; ++i) {
        xy += x[i].l * x[i + lag].l;
        xx += x[i].l * x[i].l;
        yy += x[i + lag].l * x[i + lag].l;
      }
      const float score = xx > 0.0 && yy > 0.0
          ? float(xy / sqrt(xx * yy)) : 0.0f;
      scores[lag - lo] = score;
      if (score > best) {
        best = score;
        best_lag = lag;
      }
    }
    float lag = float(best_lag);
    if (best_lag > lo && best_lag < hi && best_lag - lo + 1 < 256) {
      r[0] = scores[best_lag - lo - 1];
      r[1] = scores[best_lag - lo];
      r[2] = scores[best_lag - lo + 1];
      const float d = r[0] - 2.0f * r[1] + r[2];
      if (d < 0.0f) {
        lag += 0.5f * (r[0] - r[2]) / d;
      }
    }
    estimates[n++] = kSampleRate / lag;
  }
  // Median.
  for (int i = 1; i < n; ++i) {
    for (int j = i; j > 0 && estimates[j - 1] > estimates[j]; --j) {
      const float t = estimates[j];
      estimates[j] = estimates[j - 1];
      estimates[j - 1] = t;
    }
  }
  return n ? estimates[n / 2] : 0.0f;
}

float Energy(const Frame* x, size_t start, size_t end) {
  float e = 0.0f;
  for (size_t i = start; i < end; ++i) {
    e += x[i].l * x[i].l + x[i].r * x[i].r;
  }
  return e;
}

float MaxStep(const Frame* x, size_t start, size_t end) {
  float m = 0.0f;
  for (size_t i = start + 1; i < end; ++i) {
    m = fmaxf(m, fabsf(x[i].l - x[i - 1].l));
    m = fmaxf(m, fabsf(x[i].r - x[i - 1].r));
  }
  return m;
}

size_t ArgMaxAbs(const Frame* x, size_t n) {
  size_t best = 0;
  float m = -1.0f;
  for (size_t i = 0; i < n; ++i) {
    const float a = fabsf(x[i].l) + fabsf(x[i].r);
    if (a > m) {
      m = a;
      best = i;
    }
  }
  return best;
}

// The value of a synced time parameter that shows `label`.
float NoteValue(const char* label) {
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, label)) {
      return sidefx::StepValue(i, sidefx::kNumNoteValues);
    }
  }
  return 0.0f;
}

}  // namespace

TEST(dual_shift, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(rig.memory.internal().used() < 8192);
  CHECK(rig.memory.external().used() <= (2u << 20));
  test::Note("internal %u B, external %u B",
             unsigned(rig.memory.internal().used()),
             unsigned(rig.memory.external().used()));
  rig.block->Reset();
  rig.params[DualShift::FEEDBACK] = 1.0f;
  const size_t n = Blocks(3.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  rig.Run(in, out, n);
  bool silent = true;
  for (size_t i = 0; i < n; ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
  delete[] in;
  delete[] out;
}

TEST(dual_shift, stability) {
  Rig rig;
  CHECK(rig.ok);
  uint32_t seed = 1;
  uint32_t param_seed = 7;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  // 20 s of noise with every parameter randomised every block, then 5 s
  // each with every parameter at 0 and at 1 (feedback at maximum), then
  // 5 s at 1 with +-4 noise.
  const size_t blocks = Blocks(20.0f) / kBlockSize;
  const size_t blocks_5s = Blocks(5.0f) / kBlockSize;
  bool finite = true;
  float peak = 0.0f;
  float peak_hot = 0.0f;
  for (int phase = 0; phase < 4; ++phase) {
    const size_t count = phase == 0 ? blocks : blocks_5s;
    const float amplitude = phase == 3 ? 4.0f : 1.0f;
    for (size_t b = 0; b < count; ++b) {
      for (int p = 0; p < DualShift::NUM_PARAMS; ++p) {
        rig.params[p] = phase == 0
            ? 0.5f + 0.5f * test::Noise(&param_seed)
            : (phase == 1 ? 0.0f : 1.0f);
      }
      rig.context.sync_mask = phase == 0 && (b & 256) ? 0xffff : 0;
      for (size_t i = 0; i < kBlockSize; ++i) {
        in[i].l = amplitude * test::Noise(&seed);
        in[i].r = amplitude * test::Noise(&seed);
      }
      rig.Run(in, out, kBlockSize);
      for (size_t i = 0; i < kBlockSize; ++i) {
        finite = finite && test::Finite(out[i]);
        const float a = fmaxf(fabsf(out[i].l), fabsf(out[i].r));
        if (phase == 3) {
          peak_hot = fmaxf(peak_hot, a);
        } else {
          peak = fmaxf(peak, a);
        }
      }
    }
  }
  CHECK(finite);
  CHECK(peak < 4.0f);
  CHECK(peak_hot < 12.0f);
  test::Note("peak %.2f at +-1 in, %.2f at +-4 in", peak, peak_hot);
}

TEST(dual_shift, shifts_pitch) {
  struct Case { float semitones; float hz; };
  const Case cases[] = { { 12.0f, 880.0f }, { -12.0f, 220.0f },
                         { 7.0f, 659.26f }, { -5.0f, 329.63f },
                         { 24.0f, 1760.0f }, { -24.0f, 110.0f } };
  const size_t n = Blocks(1.5f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 440.0f, 0.5f);
  for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); ++c) {
    for (int window = 0; window < 3; ++window) {
      Rig rig;
      rig.Neutral();
      rig.params[DualShift::WINDOW] = 0.5f * float(window);
      const float v = 0.5f + cases[c].semitones / 48.0f;
      rig.params[DualShift::PITCH_A] = v;
      rig.params[DualShift::PITCH_B] = v;
      rig.Run(in, out, n);
      const size_t start = Blocks(0.5f);
      const float f = Pitch(out, start, n, cases[c].hz);
      const float peak = Peak(out, start, n, cases[c].hz * 0.8f,
                              cases[c].hz * 1.2f, false);
      test::Note("%+.0f st window %d: %.1f Hz (want %.1f), FFT peak %.1f",
                 cases[c].semitones, window, f, cases[c].hz, peak);
      // A delay-line shifter's tone drifts in phase from one splice to the
      // next, by up to half the grain rate: exact with the 150 ms window,
      // within 4 % at the default 39 ms, and the 10 ms window is the grainy,
      // metallic end by design (only its energy is checked).
      if (window == 2) {
        CHECK(fabsf(f / cases[c].hz - 1.0f) < 0.005f);
      } else if (window == 1) {
        CHECK(fabsf(f / cases[c].hz - 1.0f) < 0.04f);
      }
      // The energy is around the shifted tone (its grain-rate sidebands
      // included), not at the original.
      float near = 0.0f;
      for (float g = -0.06f; g <= 0.06f; g += 0.01f) {
        near += Power(out, start, n, cases[c].hz * (1.0f + g), false);
      }
      CHECK(near > 10.0f * Power(out, start, n, 440.0f, false));
    }
  }
  delete[] in;
  delete[] out;
}

TEST(dual_shift, detune_and_width) {
  // Both pitches 0 and DETUNE +50 ct: A (left) 50 cents up, B (right) down.
  const size_t n = Blocks(2.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 440.0f, 0.5f);
  Rig rig;
  rig.Neutral();
  rig.params[DualShift::DETUNE] = 1.0f;
  rig.params[DualShift::WIDTH] = 1.0f;
  rig.Run(in, out, n);
  const size_t start = Blocks(0.5f);
  const float up = 440.0f * powf(2.0f, 50.0f / 1200.0f);
  const float down = 440.0f * powf(2.0f, -50.0f / 1200.0f);
  const float fl = Peak(out, start, n, 400.0f, 480.0f, false);
  const float fr = Peak(out, start, n, 400.0f, 480.0f, true);
  test::Note("left %.1f Hz (want %.1f), right %.1f Hz (want %.1f)",
             fl, up, fr, down);
  CHECK(fabsf(fl - up) < 1.0f);
  CHECK(fabsf(fr - down) < 1.0f);
  delete[] in;
  delete[] out;
}

TEST(dual_shift, echo_time) {
  const float delays[] = { 0.05f, 0.25f, 1.0f, 2.0f };
  const size_t n = Blocks(2.5f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  in[0].l = in[0].r = 1.0f;
  for (size_t d = 0; d < 4; ++d) {
    Rig rig;
    rig.Neutral();
    rig.params[DualShift::DELAY] = sqrtf(delays[d] / 2.0f);
    rig.Run(in, out, n);
    const size_t at = ArgMaxAbs(out, n);
    const float seconds = float(at) / kSampleRate;
    test::Note("DELAY %.3f s: echo at %.4f s", delays[d], seconds);
    CHECK(fabsf(seconds - delays[d]) < 0.001f);
  }
  delete[] in;
  delete[] out;
}

TEST(dual_shift, unison_after_a_shift_is_a_clean_delay) {
  // After +7 st the taps stop wherever they were; back at unison the block
  // fades to one centred tap: a single echo, no comb.
  const size_t n = Blocks(1.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Rig rig;
  rig.Neutral();
  rig.params[DualShift::DELAY] = sqrtf(0.1f / 2.0f);
  rig.params[DualShift::PITCH_A] = 0.5f + 7.0f / 48.0f;
  rig.params[DualShift::PITCH_B] = 0.5f + 7.0f / 48.0f;
  uint32_t seed = 3;
  for (size_t i = 0; i < n; ++i) {
    in[i].l = in[i].r = 0.5f * test::Noise(&seed);
  }
  rig.Run(in, out, Blocks(0.123f));
  rig.params[DualShift::PITCH_A] = 0.5f;
  rig.params[DualShift::PITCH_B] = 0.5f;
  rig.Run(in, out, n);
  // Half a second of silence flushes the noise, then the impulse.
  memset(in, 0, sizeof(Frame) * n);
  const size_t impulse = Blocks(0.5f);
  in[impulse].l = in[impulse].r = 1.0f;
  rig.Run(in, out, n);
  const size_t at = ArgMaxAbs(out + impulse, n - impulse) + impulse;
  for (size_t i = 0; i < impulse; ++i) {
    out[i].l = 0.0f;
  }
  float rest = 0.0f;
  for (size_t i = 0; i < n; ++i) {
    if (i + 4 < at || i > at + 4) {
      rest = fmaxf(rest, fabsf(out[i].l));
    }
  }
  test::Note("echo at %.4f s, %.3f; largest elsewhere %.4f",
             float(at - impulse) / kSampleRate, out[at].l, rest);
  CHECK(fabsf(float(at - impulse) / kSampleRate - 0.1f) < 0.001f);
  CHECK(rest < 0.05f * fabsf(out[at].l));
  delete[] in;
  delete[] out;
}

TEST(dual_shift, spirals) {
  // A 300 Hz burst, 200 ms delay, +12 st on both voices, high feedback:
  // the first repeat is at 600 Hz, the second at 1200 Hz.
  const size_t n = Blocks(1.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  Sine(in, Blocks(0.05f), 300.0f, 0.5f);
  Rig rig;
  rig.Neutral();
  rig.params[DualShift::PITCH_A] = 0.75f;
  rig.params[DualShift::PITCH_B] = 0.75f;
  rig.params[DualShift::DELAY] = sqrtf(0.2f / 2.0f);
  rig.params[DualShift::FEEDBACK] = 0.9f;
  rig.Run(in, out, n);
  // The repeats spread a little around n * DELAY: the taps sweep.
  const size_t r1 = Blocks(0.19f);
  const size_t r2 = Blocks(0.39f);
  const size_t w = Blocks(0.05f);
  const float p1_600 = Power(out, r1, r1 + w, 600.0f, false);
  const float p1_1200 = Power(out, r1, r1 + w, 1200.0f, false);
  const float p2_600 = Power(out, r2, r2 + w, 600.0f, false);
  const float p2_1200 = Power(out, r2, r2 + w, 1200.0f, false);
  test::Note("repeat 1: 600 Hz %.3g, 1200 Hz %.3g; repeat 2: %.3g, %.3g",
             p1_600, p1_1200, p2_600, p2_1200);
  CHECK(p1_600 > 10.0f * p1_1200);
  CHECK(p2_1200 > 10.0f * p2_600);
  // And it is about as loud: feedback 90 %, a little lost to the windows.
  const float e1 = Energy(out, r1, r1 + w);
  const float e2 = Energy(out, r2, r2 + w);
  test::Note("repeat energies %.3g, %.3g", e1, e2);
  CHECK(e2 > 0.5f * e1);
  CHECK(e2 < 1.0f * e1);
  delete[] in;
  delete[] out;
}

TEST(dual_shift, no_clicks) {
  const size_t n = Blocks(3.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 200.0f, 0.5f);
  const size_t start = Blocks(0.5f);

  // Reference: the largest step at the extremes it jumps between.
  float reference = 0.0f;
  for (int top = 0; top < 2; ++top) {
    Rig rig;
    rig.Neutral();
    rig.params[DualShift::PITCH_A] = top ? 1.0f : 0.5f;
    rig.params[DualShift::PITCH_B] = top ? 1.0f : 0.5f;
    rig.Run(in, out, n);
    reference = fmaxf(reference, MaxStep(out, start, n));
  }
  // Pitch jumping between unison and +24 every 100 ms.
  {
    Rig rig;
    rig.Neutral();
    size_t at = 0;
    while (at < n) {
      const bool up = (at / Blocks(0.1f)) & 1;
      rig.params[DualShift::PITCH_A] = up ? 1.0f : 0.5f;
      rig.params[DualShift::PITCH_B] = up ? 0.0f : 0.5f;
      rig.Run(in + at, out + at, kBlockSize);
      at += kBlockSize;
    }
    const float step = MaxStep(out, start, n);
    test::Note("pitch jumps: step %.4f, reference %.4f", step, reference);
    CHECK(step < 3.0f * reference);
  }

  // DELAY and WINDOW jumping every 150 ms at unison, with feedback.
  float unison_reference;
  {
    Rig rig;
    rig.Neutral();
    rig.Run(in, out, n);
    unison_reference = MaxStep(out, start, n);
  }
  {
    Rig rig;
    rig.Neutral();
    rig.params[DualShift::FEEDBACK] = 0.5f;
    size_t at = 0;
    while (at < n) {
      const size_t k = at / Blocks(0.15f);
      rig.params[DualShift::DELAY] = (k & 1) ? 0.8f : 0.2f;
      rig.params[DualShift::WINDOW] = (k & 2) ? 1.0f : 0.0f;
      rig.Run(in + at, out + at, kBlockSize);
      at += kBlockSize;
    }
    const float step = MaxStep(out, start, n);
    test::Note("delay jumps: step %.4f, unison reference %.4f", step,
               unison_reference);
    CHECK(step < 3.0f * unison_reference);
  }
  delete[] in;
  delete[] out;
}

TEST(dual_shift, format) {
  Rig rig;
  for (int synced = 0; synced < 2; ++synced) {
    rig.context.sync_mask = synced ? 0xffff : 0;
    for (int p = 0; p < DualShift::NUM_PARAMS; ++p) {
      const float values[] = { 0.0f, 0.5f, 1.0f, 0.51f };
      for (int v = 0; v < 4; ++v) {
        char text[32];
        memset(text, 0, sizeof(text));
        rig.block->Format(p, values[v], rig.context, text, sizeof(text));
        test::Note("%-8s %.2f %s: \"%s\"", rig.block->info().params[p].name,
                   values[v], synced ? "synced" : "free", text);
        CHECK(strlen(text) > 0);
        CHECK(strlen(text) <= 10);
      }
    }
  }
  char text[16];
  rig.context.sync_mask = 0;
  rig.block->Format(DualShift::PITCH_A, 0.5f + 7.0f / 48.0f, rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "+7st"));
  rig.block->Format(DualShift::PITCH_A, 0.5f + 7.25f / 48.0f, rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "+7.25"));
  rig.block->Format(DualShift::DELAY, sqrtf(0.25f / 2.0f), rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "250ms"));
  rig.context.sync_mask = 1 << DualShift::DELAY;
  rig.block->Format(DualShift::DELAY, NoteValue("1/8."), rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "1/8."));
  // Names and info within the screen's limits.
  CHECK(strlen(rig.block->info().name) <= 10);
  CHECK(strlen(rig.block->info().short_name) <= 5);
  CHECK(rig.block->info().num_params <= 7);
  for (int p = 0; p < rig.block->info().num_params; ++p) {
    CHECK(strlen(rig.block->info().params[p].name) <= 8);
  }
}

TEST(dual_shift, synced_delay_follows_tempo) {
  const size_t n = Blocks(1.5f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  in[0].l = in[0].r = 1.0f;
  const float beats[] = { 0.5f, 0.25f, 0.4f };
  for (int b = 0; b < 3; ++b) {
    Rig rig;
    rig.Neutral();
    rig.context.beat_seconds = beats[b];
    rig.context.sync_mask = 1 << DualShift::DELAY;
    rig.params[DualShift::DELAY] = NoteValue("1/4");
    rig.Run(in, out, n);
    const float seconds = float(ArgMaxAbs(out, n)) / kSampleRate;
    test::Note("1/4 at %.2f s per beat: echo at %.4f s", beats[b], seconds);
    CHECK(fabsf(seconds - beats[b]) < 0.001f);
  }
  delete[] in;
  delete[] out;
}

TEST(dual_shift, clock_jitter_does_not_crossfade) {
  // A synced DELAY on an external clock: the 250 us timestamp grid makes
  // beat_seconds wander by a few hundredths of a percent from pulse to
  // pulse. At unison the echo of a steady sine must stay steady, not
  // crossfade between taps a few samples apart (a warbling comb).
  const size_t n = Blocks(3.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 3000.0f, 0.5f);
  Rig rig;
  rig.Neutral();
  rig.context.sync_mask = 1 << DualShift::DELAY;
  rig.params[DualShift::DELAY] = NoteValue("1/4");
  uint32_t seed = 11;
  // One pulse every 125 ms (4 PPQN at 120 BPM), each moving the beat by
  // up to +-0.08 % around 0.5 s.
  const size_t pulse = Blocks(0.125f);
  for (size_t i = 0; i < n; i += pulse) {
    rig.context.beat_seconds = 0.5f * (1.0f + 0.0008f * test::Noise(&seed));
    rig.Run(in + i, out + i, n - i < pulse ? n - i : pulse);
  }
  // Power of the echo in 10 ms windows, after the first echo has arrived.
  float lo = 1e30f;
  float hi = 0.0f;
  for (size_t start = Blocks(0.6f); start + 480 <= n; start += 480) {
    const float p = Power(out, start, start + 480, 3000.0f, false);
    lo = fminf(lo, p);
    hi = fmaxf(hi, p);
  }
  const float swing_db = 10.0f * log10f(hi / lo);
  test::Note("echo power swings %.2f dB", swing_db);
  CHECK(swing_db < 1.0f);
  delete[] in;
  delete[] out;
}
