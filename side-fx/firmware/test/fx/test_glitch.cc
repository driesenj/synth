// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: GLITCH.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "fx/glitch.h"
#include "test_support.h"

using sidefx::Frame;
using sidefx::Glitch;
using sidefx::MakeFrame;
using sidefx::StepValue;

namespace {

const float kFs = 48014.32f;

// The synced SLICE value of kNoteValues[index].
float Note(int index) {
  return StepValue(index, sidefx::kNumNoteValues);
}

const int kEighth = 8;  // kNoteValues[8] = 1/8

struct Rig {
  test::TestMemory memory;
  Glitch* block;
  bool ok;
  sidefx::TempoState tempo;
  uint16_t sync;
  float params[Glitch::NUM_PARAMS];

  Rig() : memory(4u << 20, 32u << 10) {
    block = memory.internal().Create<Glitch>();
    ok = block && block->Init(memory.memory());
    tempo = test::Tempo120();
    sync = 0;
    for (int i = 0; i < Glitch::NUM_PARAMS; ++i) {
      params[i] = block->info().params[i].default_value;
    }
  }

  void SetBeat(float beat_seconds) {
    tempo.beat_seconds = beat_seconds;
    tempo.bar_increment = 1.0f / (4.0f * beat_seconds * kFs);
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

  // Always glitching on a 1/8 grid, 16 repeats, forward, latest slice,
  // normal speed, clean.
  void Plain() {
    sync = 1 << Glitch::PARAM_SLICE;
    params[Glitch::PARAM_SLICE] = Note(kEighth);
    params[Glitch::PARAM_CHANCE] = 1.0f;
    params[Glitch::PARAM_REPEATS] = 1.0f;
    params[Glitch::PARAM_REVERSE] = 0.0f;
    params[Glitch::PARAM_PITCH] = 0.5f;
    params[Glitch::PARAM_CRUSH] = 0.0f;
    params[Glitch::PARAM_SHUFFLE] = 0.0f;
  }
};

float PeakIn(const std::vector<Frame>& x, size_t from, size_t to) {
  float peak = 0.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    const float a = fabsf(x[i].l);
    peak = a > peak ? a : peak;
  }
  return peak;
}

size_t PeakIndex(const std::vector<Frame>& x, size_t from, size_t to) {
  size_t best = from;
  float peak = -1.0f;
  for (size_t i = from; i < to && i < x.size(); ++i) {
    if (fabsf(x[i].l) > peak) {
      peak = fabsf(x[i].l);
      best = i;
    }
  }
  return best;
}

// Rising zero crossings per second of the left channel.
float Frequency(const std::vector<Frame>& x, size_t from, size_t to) {
  int crossings = 0;
  for (size_t i = from + 1; i < to; ++i) {
    crossings += x[i - 1].l < 0.0f && x[i].l >= 0.0f ? 1 : 0;
  }
  return float(crossings) * kFs / float(to - from);
}

}  // namespace

TEST(glitch, init_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  CHECK(rig.memory.external().used() <= (2u << 20) + 64);
  CHECK(rig.memory.internal().used() < 8192);
  test::Note("external %zu bytes, internal %zu bytes",
             rig.memory.external().used(), rig.memory.internal().used());
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_CRUSH] = 1.0f;
  rig.params[Glitch::PARAM_SHUFFLE] = 1.0f;
  rig.params[Glitch::PARAM_REVERSE] = 0.5f;
  std::vector<Frame> in(size_t(kFs * 5), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  rig.Run(&in[0], &out[0], in.size());
  bool silent = true;
  for (size_t i = 0; i < out.size(); ++i) {
    silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
  }
  CHECK(silent);
}

TEST(glitch, stability) {
  Rig rig;
  rig.block->Reset();
  uint32_t seed = 7;
  const size_t n = size_t(kFs * 20);
  std::vector<Frame> in(sidefx::kBlockSize), out(sidefx::kBlockSize);
  float peak = 0.0f;
  bool finite = true;
  int glitching_blocks = 0;
  for (int pass = 0; pass < 3; ++pass) {
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      for (int p = 0; p < Glitch::NUM_PARAMS; ++p) {
        rig.params[p] = pass == 0 ? 0.5f + 0.5f * test::Noise(&seed)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      rig.sync = (pass == 0 && (i & 8192)) || pass == 2 ? 1 : 0;
      for (size_t j = 0; j < in.size(); ++j) {
        in[j] = MakeFrame(test::Noise(&seed), test::Noise(&seed));
      }
      rig.Run(&in[0], &out[0], in.size());
      glitching_blocks += rig.block->glitching() ? 1 : 0;
      for (size_t j = 0; j < out.size(); ++j) {
        finite = finite && test::Finite(out[j]);
        peak = fabsf(out[j].l) > peak ? fabsf(out[j].l) : peak;
        peak = fabsf(out[j].r) > peak ? fabsf(out[j].r) : peak;
      }
    }
    test::Note("pass %d: peak %.3f, %d blocks glitching so far", pass, peak,
               glitching_blocks);
  }
  CHECK(finite);
  CHECK(peak < 4.0f);
  CHECK(glitching_blocks > 1000);
}

TEST(glitch, insert_when_not_glitching) {
  // CHANCE 0: the output is the input, bit for bit, whatever else is set.
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_CHANCE] = 0.0f;
  rig.params[Glitch::PARAM_CRUSH] = 1.0f;
  rig.params[Glitch::PARAM_PITCH] = 0.0f;
  uint32_t seed = 3;
  std::vector<Frame> in(size_t(kFs * 3)), out(in.size());
  for (size_t i = 0; i < in.size(); ++i) {
    in[i] = MakeFrame(4.0f * test::Noise(&seed), test::Noise(&seed));
  }
  rig.Run(&in[0], &out[0], in.size());
  bool same = true;
  for (size_t i = 0; i < in.size(); ++i) {
    same = same && out[i].l == in[i].l && out[i].r == in[i].r;
  }
  CHECK(same);
}

namespace {

// An impulse at 3000 samples, then silence, through a 1/8 grid at 120 BPM.
// The first step (12004) captures the slice holding it and repeats it.
std::vector<Frame> RepeatImpulse(Rig* rig, float beat_seconds) {
  rig->SetBeat(beat_seconds);
  std::vector<Frame> in(size_t(kFs * 2.2f), MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(in.size());
  in[3000] = MakeFrame(1.0f, 1.0f);
  rig->Run(&in[0], &out[0], in.size());
  return out;
}

}  // namespace

TEST(glitch, repeats_the_slice) {
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  std::vector<Frame> out = RepeatImpulse(&rig, 0.5f);
  const float step = 0.25f * kFs;
  // The live impulse first, then once per step, 2998 samples into it.
  CHECK(PeakIn(out, 2990, 3010) > 0.99f);
  int found = 0;
  for (int k = 1; k <= 7; ++k) {
    const float expected = float(k) * step + 2998.0f;
    const size_t at = PeakIndex(out, size_t(expected) - 200,
                                size_t(expected) + 200);
    const float error = float(at) - expected;
    test::Note("repeat %d at %zu (%+.1f), %.3f", k, at, error, out[at].l);
    found += fabsf(error) < 48.0f && out[at].l > 0.9f ? 1 : 0;
  }
  CHECK(found == 7);
  // Nothing else: away from the impulses it is silent.
  CHECK(PeakIn(out, size_t(step) + 4000, size_t(step) + 10000) < 1e-4f);
}

TEST(glitch, reverse) {
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_REVERSE] = 1.0f;
  std::vector<Frame> out = RepeatImpulse(&rig, 0.5f);
  // Reversed, the impulse 2998 into a 12003-sample slice comes 9002 in.
  const float step = 0.25f * kFs;
  int found = 0;
  for (int k = 1; k <= 6; ++k) {
    const float expected = float(k) * step + 9002.0f;
    const size_t at = PeakIndex(out, size_t(expected) - 200,
                                size_t(expected) + 200);
    test::Note("reversed repeat %d at %zu (%+.1f)", k, at,
               float(at) - expected);
    found += fabsf(float(at) - expected) < 48.0f && out[at].l > 0.9f ? 1 : 0;
  }
  CHECK(found == 6);
}

TEST(glitch, pitch_bends_the_repeats) {
  const float pitches[] = { 0.5f, 1.0f, 0.0f };
  float ratio[3];
  for (int p = 0; p < 3; ++p) {
    Rig rig;
    rig.block->Reset();
    rig.Plain();
    rig.params[Glitch::PARAM_PITCH] = pitches[p];
    const size_t step = size_t(0.25f * kFs);
    std::vector<Frame> in(18 * step), out(in.size());
    for (size_t i = 0; i < in.size(); ++i) {
      const float s = 0.5f * sinf(6.2831853f * 500.0f * float(i) / kFs);
      in[i] = MakeFrame(s, s);
    }
    rig.Run(&in[0], &out[0], in.size());
    const float first = Frequency(out, step + 200, 2 * step - 200);
    const float last = Frequency(out, 16 * step + 200, 17 * step - 200);
    ratio[p] = last / first;
    test::Note("pitch %.1f: %.0f Hz in the first repeat, %.0f Hz in the last",
               pitches[p], first, last);
  }
  CHECK(fabsf(ratio[0] - 1.0f) < 0.02f);
  CHECK(ratio[1] > 2.5f);   // towards +24 st
  CHECK(ratio[2] < 0.4f);   // towards -24 st: a tape stop
}

TEST(glitch, crush) {
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_CRUSH] = 1.0f;
  const size_t step = size_t(0.25f * kFs);
  std::vector<Frame> in(4 * step), out(in.size());
  for (size_t i = 0; i < in.size(); ++i) {
    const float s = 0.5f * sinf(6.2831853f * 300.0f * float(i) / kFs);
    in[i] = MakeFrame(s, s);
  }
  rig.Run(&in[0], &out[0], in.size());
  // Held samples and few levels on the repeats; the live part untouched.
  int held = 0;
  for (size_t i = step + 200; i < 3 * step; ++i) {
    held += out[i].l == out[i - 1].l ? 1 : 0;
  }
  const float fraction = float(held) / float(2 * step - 200);
  int levels_off_grid = 0;
  for (size_t i = step + 200; i < 3 * step; ++i) {
    const float q = out[i].l * 16.0f;
    levels_off_grid += fabsf(q - floorf(q + 0.5f)) > 1e-4f ? 1 : 0;
  }
  test::Note("crush: %.0f %% held, %d samples off the 4-bit grid",
             100.0f * fraction, levels_off_grid);
  CHECK(fraction > 0.9f);
  CHECK(levels_off_grid == 0);
  bool live = true;
  for (size_t i = 0; i < step - 10; ++i) {
    live = live && out[i].l == in[i].l;
  }
  CHECK(live);
}

TEST(glitch, shuffle_takes_an_earlier_slice) {
  // Each step of the input holds its own level (0.05 per step); one repeat
  // per glitch and a glitch on every step, so step s plays slice s - 1, or
  // with SHUFFLE an earlier one.
  const float step = 0.25f * kFs;
  for (int shuffle = 0; shuffle < 2; ++shuffle) {
    Rig rig;
    rig.block->Reset();
    rig.Plain();
    rig.params[Glitch::PARAM_REPEATS] = 0.0f;
    rig.params[Glitch::PARAM_SHUFFLE] = float(shuffle);
    std::vector<Frame> in(size_t(14 * step)), out(in.size());
    for (size_t i = 0; i < in.size(); ++i) {
      const float level = 0.05f * float(int(float(i) / step) + 1);
      in[i] = MakeFrame(level, level);
    }
    rig.Run(&in[0], &out[0], in.size());
    int latest = 0;
    int earlier = 0;
    float seen[16];
    int distinct = 0;
    for (int s = 2; s < 14; ++s) {
      const float level = out[size_t((float(s) + 0.5f) * step)].l;
      const float expected = 0.05f * float(s);  // slice s - 1
      latest += fabsf(level - expected) < 1e-4f ? 1 : 0;
      earlier += level < expected - 0.04f ? 1 : 0;
      bool is_new = true;
      for (int k = 0; k < distinct; ++k) {
        is_new = is_new && fabsf(seen[k] - (expected - level)) > 1e-3f;
      }
      if (is_new) {
        seen[distinct++] = expected - level;
      }
    }
    test::Note("shuffle %d: %d latest, %d earlier, %d distinct distances",
               shuffle, latest, earlier, distinct);
    if (shuffle) {
      CHECK(earlier == 12);
      CHECK(distinct >= 3);
    } else {
      CHECK(latest == 12);
    }
  }
}

TEST(glitch, no_clicks) {
  const size_t n = size_t(kFs * 8.0f);
  std::vector<Frame> in(n), out(n);
  for (size_t i = 0; i < n; ++i) {
    const float s = 0.5f * sinf(6.2831853f * 220.0f * float(i) / kFs);
    in[i] = MakeFrame(s, s);
  }
  const float normal = 0.5f * 6.2831853f * 220.0f / kFs;
  for (int mode = 0; mode < 3; ++mode) {
    Rig rig;
    rig.block->Reset();
    rig.Plain();
    rig.params[Glitch::PARAM_REVERSE] = 0.5f;
    rig.params[Glitch::PARAM_SHUFFLE] = 0.5f;
    rig.params[Glitch::PARAM_CHANCE] = 0.7f;
    rig.sync = mode == 1 ? 0 : 1;
    uint32_t seed = 11;
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      if (i % size_t(kFs * 0.3f) < sidefx::kBlockSize) {
        rig.params[Glitch::PARAM_SLICE] = 0.5f + 0.5f * test::Noise(&seed);
        rig.params[Glitch::PARAM_REPEATS] = 0.5f + 0.5f * test::Noise(&seed);
        if (mode == 2) {
          rig.params[Glitch::PARAM_PITCH] = 0.5f + 0.5f * test::Noise(&seed);
        }
      }
      rig.Run(&in[i], &out[i], n - i < sidefx::kBlockSize
              ? n - i : sidefx::kBlockSize);
    }
    float worst = 0.0f;
    for (size_t i = 1; i < n; ++i) {
      const float d = fabsf(out[i].l - out[i - 1].l);
      worst = d > worst ? d : worst;
    }
    // With PITCH the sine itself plays up to 4 times faster.
    const float limit = (mode == 2 ? 4.0f : 1.0f) * 4.0f * normal;
    test::Note("mode %d: largest step %.4f, limit %.4f", mode, worst, limit);
    CHECK(worst < limit);
  }
}

TEST(glitch, format) {
  Rig rig;
  sidefx::TempoState tempo = test::Tempo120();
  const float values[] = { 0.0f, 0.5f, 1.0f };
  for (int s = 0; s < 2; ++s) {
    sidefx::ProcessContext c = test::Context(tempo, s ? 0xffff : 0);
    for (int p = 0; p < Glitch::NUM_PARAMS; ++p) {
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

TEST(glitch, synced_slice_follows_tempo) {
  const float beats[] = { 0.5f, 0.4f, 0.3f };
  for (int b = 0; b < 3; ++b) {
    Rig rig;
    rig.block->Reset();
    rig.Plain();
    std::vector<Frame> out = RepeatImpulse(&rig, beats[b]);
    // 1/8: half a beat per step.
    const float step = 0.5f * beats[b] * kFs;
    const size_t first = PeakIndex(out, size_t(step) + 100,
                                   size_t(2 * step) + 100);
    const size_t second = PeakIndex(out, first + 200, first + size_t(step) +
                                    200);
    test::Note("beat %.2f s: repeats %zu apart, step %.1f", beats[b],
               second - first, step);
    CHECK(fabsf(float(second - first) - step) < 0.001f * kFs);
  }
  // Free: 10 ms .. 2 s.
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.sync = 0;
  rig.params[Glitch::PARAM_SLICE] = sidefx::ExpUnmap(0.2f, 0.01f, 2.0f);
  std::vector<Frame> in(size_t(kFs), MakeFrame(0.0f, 0.0f)), out(in.size());
  in[2000] = MakeFrame(1.0f, 1.0f);
  rig.Run(&in[0], &out[0], in.size());
  const size_t first = PeakIndex(out, 5000, 5000 + size_t(0.2f * kFs));
  const size_t second = PeakIndex(out, first + 200, first + size_t(0.2f * kFs) +
                                  200);
  test::Note("free 200 ms: repeats %zu apart", second - first);
  CHECK(fabsf(float(second - first) - 0.2f * kFs) < 0.001f * kFs);
}

TEST(glitch, long_glitch_plays_out) {
  // SLICE 1/4 at 120 BPM, 16 repeats: an 8 s glitch, longer than the 5.4 s
  // recording. It must play all its repeats of the first slice (440 Hz),
  // not let go to the input (1 kHz) when the recording catches up, and
  // its PITCH riser must reach the top.
  for (int bend = 0; bend < 2; ++bend) {
    Rig rig;
    rig.block->Reset();
    rig.Plain();
    rig.params[Glitch::PARAM_SLICE] = Note(11);  // 1/4
    rig.params[Glitch::PARAM_REPEATS] = 1.0f;    // 16
    rig.params[Glitch::PARAM_PITCH] = bend ? 1.0f : 0.5f;  // +24 st
    const size_t step = size_t(0.5f * kFs);
    const size_t n = 20 * step / sidefx::kBlockSize * sidefx::kBlockSize;
    std::vector<Frame> in(n), out(n);
    for (size_t i = 0; i < n; ++i) {
      const float hz = i < step ? 440.0f : 1000.0f;
      const float s = 0.5f * sinf(6.2831853f * hz * float(i) / kFs);
      in[i] = MakeFrame(s, s);
    }
    size_t started = 0;
    size_t ended = 0;
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      rig.Run(&in[i], &out[i], sidefx::kBlockSize);
      if (!started && rig.block->glitching()) {
        started = i;
        rig.params[Glitch::PARAM_CHANCE] = 0.0f;
      } else if (started && !ended && !rig.block->glitching()) {
        ended = i;
      }
    }
    const float seconds = float(ended - started) / kFs;
    test::Note("pitch %d: glitch of %.3f s", bend, seconds);
    CHECK(fabsf(seconds - 8.0f) < 0.01f);
    // The last repeat, 7.5 .. 8 s in.
    const size_t last = started + 15 * step;
    const float f = Frequency(out, last + 200, last + step - 200);
    test::Note("pitch %d: %.0f Hz in the last repeat", bend, f);
    if (bend) {
      CHECK(f > 440.0f * 3.6f);  // +22.5 st or more at the end
    } else {
      CHECK(fabsf(f - 440.0f) < 10.0f);
    }
  }
}

TEST(glitch, slice_change_keeps_the_grid) {
  // A glitch on a 1/16 grid; at bar phase 0.2 SLICE turns to 1/4. The next
  // steps must come on the 1/4 grid (0.25, 0.5), not wait for the bar.
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_SLICE] = Note(5);         // 1/16
  rig.params[Glitch::PARAM_REPEATS] = StepValue(3, 8);  // 4
  const size_t n = size_t(3.0f * kFs) / sidefx::kBlockSize *
      sidefx::kBlockSize;
  std::vector<Frame> in(n, MakeFrame(0.0f, 0.0f)), out(n);
  float ended = -1.0f;
  bool changed = false;
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    if (!changed && rig.tempo.bar_phase >= 0.2f) {
      rig.params[Glitch::PARAM_SLICE] = Note(11);    // 1/4
      changed = true;
    }
    rig.Run(&in[i], &out[i], sidefx::kBlockSize);
    if (rig.block->glitching()) {
      rig.params[Glitch::PARAM_CHANCE] = 0.0f;
    } else if (rig.params[Glitch::PARAM_CHANCE] == 0.0f && ended < 0.0f) {
      ended = float(i) / kFs;
    }
  }
  // Steps at 0.0625 (start), 0.125, 0.1875, then 0.25 and 0.5 of the bar:
  // the glitch ends at 0.5 bar, 1 s.
  test::Note("glitch ended at %.3f s", ended);
  CHECK(fabsf(ended - 1.0f) < 0.01f);
}

TEST(glitch, slice_change_to_finer_stays_on_grid) {
  // From 1/4 to 1/16 at bar phase 0.3: no step at once (0.3 is no grid
  // line of either); the next at 0.3125.
  Rig rig;
  rig.block->Reset();
  rig.Plain();
  rig.params[Glitch::PARAM_SLICE] = Note(11);         // 1/4
  rig.params[Glitch::PARAM_REPEATS] = StepValue(1, 8);  // 2
  const size_t n = size_t(1.0f * kFs) / sidefx::kBlockSize *
      sidefx::kBlockSize;
  std::vector<Frame> in(n, MakeFrame(0.0f, 0.0f)), out(n);
  float ended = -1.0f;
  bool changed = false;
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    if (!changed && rig.tempo.bar_phase >= 0.3f) {
      rig.params[Glitch::PARAM_SLICE] = Note(5);       // 1/16
      changed = true;
    }
    rig.Run(&in[i], &out[i], sidefx::kBlockSize);
    if (rig.block->glitching()) {
      rig.params[Glitch::PARAM_CHANCE] = 0.0f;
    } else if (rig.params[Glitch::PARAM_CHANCE] == 0.0f && ended < 0.0f) {
      ended = float(i) / kFs;
    }
  }
  // Start at 0.25, restart at 0.3125 (not at 0.3), end at 0.375 bar: 0.75 s.
  test::Note("glitch ended at %.3f s", ended);
  CHECK(fabsf(ended - 0.75f) < 0.01f);
}
