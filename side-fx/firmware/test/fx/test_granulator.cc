// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: GRANULATOR.

#include <string.h>

#include "check.h"
#include "fx/granulator.h"
#include "test_support.h"

using sidefx::Frame;
using sidefx::Granulator;
using sidefx::kBlockSize;
using sidefx::kSampleRate;

namespace {

const float kPi = 3.14159265f;

struct Rig {
  test::TestMemory memory;
  Granulator* block;
  bool ok;
  float params[Granulator::NUM_PARAMS];
  sidefx::ProcessContext context;

  Rig() : memory(3u << 20, 64u << 10) {
    block = memory.internal().Create<Granulator>();
    ok = block && block->Init(memory.memory());
    for (int i = 0; i < Granulator::NUM_PARAMS; ++i) {
      params[i] = block->info().params[i].default_value;
    }
    context = test::Context(test::Tempo120(), 0);
  }

  // No pitch, no spread, no feedback, centred; the density, size and delay
  // given.
  void Neutral(float density_hz, float size_seconds, float delay_seconds) {
    params[Granulator::PITCH] = 0.5f;
    params[Granulator::SPREAD] = 0.0f;
    params[Granulator::DENSITY] = sidefx::ExpUnmap(density_hz, 0.5f, 100.0f);
    params[Granulator::SIZE] = sidefx::ExpUnmap(size_seconds, 0.02f, 0.5f);
    params[Granulator::DELAY] = sqrtf(delay_seconds / 2.0f);
    params[Granulator::FEEDBACK] = 0.0f;
    params[Granulator::WIDTH] = 0.0f;
  }

  void Semitones(float st) {
    params[Granulator::PITCH] = 0.5f + st / 48.0f;
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

float Power(const Frame* x, size_t start, size_t end, float hz) {
  const float w = 2.0f * kPi * hz / kSampleRate;
  const float c = 2.0f * cosf(w);
  float s1 = 0.0f;
  float s2 = 0.0f;
  for (size_t i = start; i < end; ++i) {
    const float s = x[i].l + c * s1 - s2;
    s2 = s1;
    s1 = s;
  }
  return s1 * s1 + s2 * s2 - c * s1 * s2;
}

// The pitch by short-time autocorrelation: the median over 10 ms frames of
// the best lag within -30 % .. +40 % of the expected period (frames with
// little signal skipped).
float Pitch(const Frame* x, size_t start, size_t end, float expected_hz) {
  const size_t frame = 480;
  const int lo = int(kSampleRate / expected_hz / 1.4f);
  const int hi = int(kSampleRate / expected_hz / 0.7f) + 1;
  float estimates[1024];
  int n = 0;
  for (size_t f = start; f + frame + hi + 1 < end && n < 1024; f += frame) {
    float best = -2.0f;
    int best_lag = lo;
    float scores[512];
    double energy = 0.0;
    for (size_t i = f; i < f + frame; ++i) {
      energy += x[i].l * x[i].l;
    }
    if (energy < 1e-4 * frame) {
      continue;
    }
    for (int lag = lo; lag <= hi && lag - lo < 512; ++lag) {
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
    if (best_lag > lo && best_lag < hi && best_lag - lo + 1 < 512) {
      const float r0 = scores[best_lag - lo - 1];
      const float r1 = scores[best_lag - lo];
      const float r2 = scores[best_lag - lo + 1];
      const float d = r0 - 2.0f * r1 + r2;
      if (d < 0.0f) {
        lag += 0.5f * (r0 - r2) / d;
      }
    }
    estimates[n++] = kSampleRate / lag;
  }
  for (int i = 1; i < n; ++i) {
    for (int j = i; j > 0 && estimates[j - 1] > estimates[j]; --j) {
      const float t = estimates[j];
      estimates[j] = estimates[j - 1];
      estimates[j - 1] = t;
    }
  }
  return n ? estimates[n / 2] : 0.0f;
}

float MaxStep(const Frame* x, size_t start, size_t end) {
  float m = 0.0f;
  for (size_t i = start + 1; i < end; ++i) {
    m = fmaxf(m, fabsf(x[i].l - x[i - 1].l));
    m = fmaxf(m, fabsf(x[i].r - x[i - 1].r));
  }
  return m;
}

// The first sample louder than threshold, or n.
size_t FirstAbove(const Frame* x, size_t n, float threshold) {
  for (size_t i = 0; i < n; ++i) {
    if (fabsf(x[i].l) > threshold || fabsf(x[i].r) > threshold) {
      return i;
    }
  }
  return n;
}

float NoteValue(const char* label) {
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, label)) {
      return sidefx::StepValue(i, sidefx::kNumNoteValues);
    }
  }
  return 0.0f;
}

// A synced rate's value for `label` (rates run the other way).
float RateValue(const char* label) {
  return 1.0f - NoteValue(label);
}

}  // namespace

TEST(granulator, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(rig.memory.internal().used() < 8192);
  CHECK(rig.memory.external().used() <= (2u << 20));
  test::Note("internal %u B, external %u B",
             unsigned(rig.memory.internal().used()),
             unsigned(rig.memory.external().used()));
  rig.block->Reset();
  rig.params[Granulator::FEEDBACK] = 1.0f;
  rig.params[Granulator::DENSITY] = 1.0f;
  const size_t n = Blocks(6.0f);
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

TEST(granulator, stability) {
  Rig rig;
  CHECK(rig.ok);
  uint32_t seed = 1;
  uint32_t param_seed = 7;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  const size_t blocks = Blocks(20.0f) / kBlockSize;
  const size_t blocks_5s = Blocks(5.0f) / kBlockSize;
  bool finite = true;
  float peak = 0.0f;
  float peak_hot = 0.0f;
  int most_grains = 0;
  for (int phase = 0; phase < 4; ++phase) {
    const size_t count = phase == 0 ? blocks : blocks_5s;
    const float amplitude = phase == 3 ? 4.0f : 1.0f;
    for (size_t b = 0; b < count; ++b) {
      for (int p = 0; p < Granulator::NUM_PARAMS; ++p) {
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
      const int grains = rig.block->num_active_grains();
      most_grains = grains > most_grains ? grains : most_grains;
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
  CHECK(most_grains == Granulator::kMaxGrains);
  test::Note("peak %.2f at +-1 in, %.2f at +-4 in, %d grains at most",
             peak, peak_hot, most_grains);
}

TEST(granulator, shifts_pitch) {
  struct Case { float semitones; float hz; };
  const Case cases[] = { { 12.0f, 880.0f }, { -12.0f, 220.0f },
                         { 7.0f, 659.26f }, { 24.0f, 1760.0f },
                         { -24.0f, 110.0f } };
  const size_t n = Blocks(2.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 440.0f, 0.5f);
  for (size_t c = 0; c < sizeof(cases) / sizeof(cases[0]); ++c) {
    Rig rig;
    rig.Neutral(30.0f, 0.1f, 0.05f);
    rig.Semitones(cases[c].semitones);
    rig.Run(in, out, n);
    const size_t start = Blocks(0.6f);
    const float f = Pitch(out, start, n, cases[c].hz);
    test::Note("%+.0f st: %.1f Hz (want %.1f)", cases[c].semitones, f,
               cases[c].hz);
    CHECK(fabsf(f / cases[c].hz - 1.0f) < 0.01f);
    CHECK(Power(out, start, n, cases[c].hz) >
          10.0f * Power(out, start, n, 440.0f));
  }
  delete[] in;
  delete[] out;
}

TEST(granulator, spread_makes_a_crowd) {
  // SPREAD 0: the energy sits at the shifted tone. Full SPREAD: grains land
  // anywhere within an octave either way, so the tone's share is small.
  const size_t n = Blocks(3.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 440.0f, 0.5f);
  float share[2];
  for (int s = 0; s < 2; ++s) {
    Rig rig;
    rig.Neutral(40.0f, 0.1f, 0.05f);
    rig.params[Granulator::SPREAD] = s ? 1.0f : 0.0f;
    rig.Run(in, out, n);
    // Goertzel power at 440 Hz in 20 ms frames, as a fraction of a pure
    // tone's: N^2 A^2 / 4 against an energy of N A^2 / 2. (The grains'
    // phases wander, so a long window would miss even a steady tone.)
    const size_t frame = 960;
    float tone = 0.0f;
    float total = 0.0f;
    for (size_t f = Blocks(0.6f); f + frame <= n; f += frame) {
      tone += Power(out, f, f + frame, 440.0f);
      for (size_t i = f; i < f + frame; ++i) {
        total += out[i].l * out[i].l;
      }
    }
    share[s] = tone / (0.5f * float(frame) * total);
    test::Note("SPREAD %d: 440 Hz share %.3f", s, share[s]);
  }
  CHECK(share[0] > 0.5f);
  CHECK(share[1] < 0.2f * share[0]);
  delete[] in;
  delete[] out;
}

TEST(granulator, delay_and_width) {
  // A 10 ms burst; DELAY 500 ms, 20 ms grains: nothing before the delay,
  // then the burst, within the delay plus the spread (half a grain) and
  // the grain itself.
  const size_t n = Blocks(1.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  Sine(in, Blocks(0.01f), 1000.0f, 0.8f);
  const float delays[] = { 0.1f, 0.5f };
  for (int d = 0; d < 2; ++d) {
    Rig rig;
    rig.Neutral(100.0f, 0.02f, delays[d]);
    rig.Run(in, out, n);
    const float first = float(FirstAbove(out, n, 0.01f)) / kSampleRate;
    test::Note("DELAY %.2f s: first output at %.4f s", delays[d], first);
    CHECK(first > delays[d] - 0.001f);
    CHECK(first < delays[d] + 0.03f);
  }
  // WIDTH 0: both sides the same. WIDTH 1: grains panned apart.
  uint32_t seed = 5;
  for (size_t i = 0; i < n; ++i) {
    in[i].l = in[i].r = 0.5f * test::Noise(&seed);
  }
  for (int w = 0; w < 2; ++w) {
    Rig rig;
    rig.Neutral(20.0f, 0.1f, 0.05f);
    rig.params[Granulator::WIDTH] = float(w);
    rig.Run(in, out, n);
    double lr = 0.0, ll = 0.0, rr = 0.0;
    for (size_t i = Blocks(0.2f); i < n; ++i) {
      lr += out[i].l * out[i].r;
      ll += out[i].l * out[i].l;
      rr += out[i].r * out[i].r;
    }
    const float correlation = float(lr / sqrt(ll * rr + 1e-20));
    test::Note("WIDTH %d: L/R correlation %.3f", w, correlation);
    CHECK(w ? correlation < 0.8f : correlation > 0.999f);
  }
  delete[] in;
  delete[] out;
}

TEST(granulator, density) {
  // Free running: 10 grains a second on average, jittered.
  const size_t n = Blocks(20.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 300.0f, 0.5f);
  {
    Rig rig;
    rig.Neutral(10.0f, 0.02f, 0.05f);
    int starts = 0;
    int last = 0;
    for (size_t at = 0; at < n; at += kBlockSize) {
      rig.Run(in + at, out + at, kBlockSize);
      const int now = rig.block->num_active_grains();
      starts += now > last ? now - last : 0;
      last = now;
    }
    test::Note("10/s for 20 s: %d grains", starts);
    CHECK(starts > 170 && starts < 230);
  }
  // Synced at 1/4 and 120 BPM: one grain on every beat, the first at once.
  {
    Rig rig;
    rig.Neutral(10.0f, 0.02f, 0.05f);
    rig.context.sync_mask = 1 << Granulator::DENSITY;
    rig.params[Granulator::DENSITY] = RateValue("1/4");
    int starts = 0;
    int last = 0;
    bool on_beat = true;
    for (size_t at = 0; at < Blocks(4.0f); at += kBlockSize) {
      rig.Run(in + at, out + at, kBlockSize);
      const int now = rig.block->num_active_grains();
      if (now > last) {
        starts += now - last;
        const float beats = float(at) / kSampleRate / 0.5f;
        on_beat = on_beat && fabsf(beats - floorf(beats + 0.5f)) < 0.002f;
      }
      last = now;
    }
    test::Note("1/4 synced for 4 s: %d grains", starts);
    CHECK(starts == 8);
    CHECK(on_beat);
  }
  // Dense and long: never more than 24 at once.
  {
    Rig rig;
    rig.Neutral(100.0f, 0.5f, 0.05f);
    int most = 0;
    for (size_t at = 0; at < Blocks(3.0f); at += kBlockSize) {
      rig.Run(in + at, out + at, kBlockSize);
      const int now = rig.block->num_active_grains();
      most = now > most ? now : most;
    }
    CHECK(most == Granulator::kMaxGrains);
  }
  delete[] in;
  delete[] out;
}

TEST(granulator, feedback_keeps_the_cloud) {
  // A burst into the line, then silence: without feedback the grains have
  // nothing left to read after DELAY + spread + SIZE; with feedback the
  // cloud goes on.
  const size_t n = Blocks(3.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  uint32_t seed = 9;
  for (size_t i = 0; i < Blocks(0.3f); ++i) {
    in[i].l = in[i].r = 0.5f * test::Noise(&seed);
  }
  float late[2];
  for (int f = 0; f < 2; ++f) {
    Rig rig;
    rig.Neutral(30.0f, 0.1f, 0.1f);
    rig.params[Granulator::FEEDBACK] = f ? 0.9f : 0.0f;
    rig.Run(in, out, n);
    late[f] = 0.0f;
    for (size_t i = Blocks(2.0f); i < n; ++i) {
      late[f] = fmaxf(late[f], fabsf(out[i].l));
    }
    test::Note("FEEDBACK %d: peak after 2 s %.4f", f, late[f]);
  }
  CHECK(late[0] == 0.0f);
  CHECK(late[1] > 0.01f);
  delete[] in;
  delete[] out;
}

TEST(granulator, no_clicks) {
  const size_t n = Blocks(4.0f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 200.0f, 0.5f);
  const size_t start = Blocks(1.0f);
  float reference = 0.0f;
  for (int top = 0; top < 2; ++top) {
    Rig rig;
    rig.Neutral(40.0f, 0.1f, 0.05f);
    rig.Semitones(top ? 24.0f : 0.0f);
    rig.Run(in, out, n);
    reference = fmaxf(reference, MaxStep(out, start, n));
  }
  // PITCH, DELAY and SIZE jumping every 100 ms; the pool full and stealing.
  for (int dense = 0; dense < 2; ++dense) {
    Rig rig;
    rig.Neutral(dense ? 100.0f : 40.0f, 0.1f, 0.05f);
    for (size_t at = 0; at < n; at += kBlockSize) {
      const size_t k = at / Blocks(0.1f);
      rig.Semitones((k & 1) ? 24.0f : 0.0f);
      rig.params[Granulator::DELAY] = (k & 2) ? 0.9f : 0.1f;
      rig.params[Granulator::SIZE] = (k & 4) ? 1.0f : 0.4f;
      rig.Run(in + at, out + at, kBlockSize);
    }
    const float step = MaxStep(out, start, n);
    test::Note("jumps (dense %d): step %.4f, reference %.4f", dense, step,
               reference);
    CHECK(step < 3.0f * reference);
  }
  delete[] in;
  delete[] out;
}

TEST(granulator, format) {
  Rig rig;
  for (int synced = 0; synced < 2; ++synced) {
    rig.context.sync_mask = synced ? 0xffff : 0;
    for (int p = 0; p < Granulator::NUM_PARAMS; ++p) {
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
  rig.block->Format(Granulator::PITCH, 0.5f - 12.0f / 48.0f, rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "-12st"));
  rig.block->Format(Granulator::SPREAD, 1.0f, rig.context, text,
                    sizeof(text));
  CHECK(!strcmp(text, "12st"));
  rig.block->Format(Granulator::DENSITY, 1.0f, rig.context, text,
                    sizeof(text));
  CHECK(!strcmp(text, "100Hz"));
  rig.context.sync_mask = 1 << Granulator::DENSITY;
  rig.block->Format(Granulator::DENSITY, RateValue("1/16"), rig.context,
                    text, sizeof(text));
  CHECK(!strcmp(text, "1/16"));
  CHECK(strlen(rig.block->info().name) <= 10);
  CHECK(strlen(rig.block->info().short_name) <= 5);
  CHECK(rig.block->info().num_params <= 7);
  for (int p = 0; p < rig.block->info().num_params; ++p) {
    CHECK(strlen(rig.block->info().params[p].name) <= 8);
  }
}

TEST(granulator, synced_delay_follows_tempo) {
  const size_t n = Blocks(1.5f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  memset(in, 0, sizeof(Frame) * n);
  Sine(in, Blocks(0.01f), 1000.0f, 0.8f);
  const float beats[] = { 0.5f, 0.25f, 0.4f };
  for (int b = 0; b < 3; ++b) {
    Rig rig;
    rig.Neutral(100.0f, 0.02f, 0.0f);
    rig.context.beat_seconds = beats[b];
    rig.context.sync_mask = 1 << Granulator::DELAY;
    rig.params[Granulator::DELAY] = NoteValue("1/4");
    rig.Run(in, out, n);
    const float first = float(FirstAbove(out, n, 0.01f)) / kSampleRate;
    test::Note("1/4 at %.2f s per beat: first output at %.4f s", beats[b],
               first);
    CHECK(first > beats[b] - 0.001f);
    CHECK(first < beats[b] + 0.03f);
  }
  delete[] in;
  delete[] out;
}

TEST(granulator, synced_grid_triggers_once) {
  // DENSITY synced 1/4 at 120 BPM: one grain per beat over 34 bars, the
  // first at once (beat 0), nothing extra where the 16-bar count wraps.
  {
    Rig rig;
    rig.Neutral(10.0f, 0.02f, 0.05f);
    rig.context.sync_mask = 1 << Granulator::DENSITY;
    rig.params[Granulator::DENSITY] = RateValue("1/4");
    const size_t block = 1024 * kBlockSize;
    Frame* in = new Frame[block];
    Frame* out = new Frame[block];
    memset(in, 0, sizeof(Frame) * block);
    const size_t n = Blocks(68.0f) - kBlockSize;
    for (size_t at = 0; at < n; at += block) {
      rig.Run(in, out, n - at < block ? n - at : block);
    }
    test::Note("34 bars of 1/4: %u grains", rig.block->grains_triggered());
    CHECK(rig.block->grains_triggered() == 34 * 4);
    delete[] in;
    delete[] out;
  }
  // An external clock: the bar position advances by less than nominal
  // while it is pulled back, so a block can start a little behind where
  // the last one's extrapolation ended. A grid line there is one grain.
  {
    Rig rig;
    rig.Neutral(10.0f, 0.02f, 0.05f);
    rig.context.sync_mask = 1 << Granulator::DENSITY;
    rig.params[Granulator::DENSITY] = RateValue("1/4");
    Frame in[kBlockSize];
    Frame out[kBlockSize];
    memset(in, 0, sizeof(in));
    const size_t blocks = Blocks(8.0f) / kBlockSize - 1;
    for (size_t b = 0; b < blocks; ++b) {
      rig.block->Process(rig.context, rig.params, in, out, kBlockSize);
      const float advance = (b & 1) ? 1.5f : 0.5f;
      rig.context.bar_phase += advance * rig.context.bar_increment *
          float(kBlockSize);
      if (rig.context.bar_phase >= 1.0f) {
        rig.context.bar_phase -= 1.0f;
      }
    }
    test::Note("4 bars, pulled back every other block: %u grains",
               rig.block->grains_triggered());
    CHECK(rig.block->grains_triggered() == 4 * 4);
  }
}

TEST(granulator, density_jump_does_not_duck) {
  // One long grain sounding (1 Hz, 500 ms) when DENSITY jumps to 100 Hz:
  // the expected overlap goes to 24, but the new grains fade in over
  // their envelope; the grain already sounding must not drop at once.
  const size_t n = Blocks(0.5f);
  Frame* in = new Frame[n];
  Frame* out = new Frame[n];
  Sine(in, n, 300.0f, 0.5f);
  Rig rig;
  rig.Neutral(1.0f, 0.5f, 0.05f);
  const size_t jump = Blocks(0.25f);
  rig.Run(in, out, jump);
  rig.params[Granulator::DENSITY] = 1.0f;  // 100 Hz
  rig.Run(in + jump, out + jump, n - jump);
  float before = 0.0f;
  float after = 0.0f;
  for (size_t i = jump - 160; i < jump; ++i) {
    before += out[i].l * out[i].l;
  }
  for (size_t i = jump + 32; i < jump + 192; ++i) {
    after += out[i].l * out[i].l;
  }
  const float drop_db = 10.0f * log10f(before / after);
  test::Note("level 0.7 .. 4 ms after the jump: %.2f dB down", drop_db);
  CHECK(drop_db < 1.0f);
  delete[] in;
  delete[] out;
}
