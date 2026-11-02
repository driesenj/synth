// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: BEADSY (Beads' granular engine as a block).

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"
#include "fx/beadsy.h"

namespace {

using sidefx::Beadsy;
using sidefx::Frame;
using sidefx::ProcessContext;

const float kSr = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;
const float kPi = 3.14159265f;

struct Rig {
  test::TestMemory memory;
  Beadsy* block;
  sidefx::TempoState tempo;
  ProcessContext context;
  float params[Beadsy::NUM_PARAMS];
  bool ok;

  Rig() : memory(16u << 20, 64u << 10) {
    block = memory.internal().Create<Beadsy>();
    ok = block && block->Init(memory.memory());
    tempo = test::Tempo120();
    context = test::Context(tempo, 0);
    Defaults();
  }

  void Defaults() {
    const sidefx::BlockInfo& info = block->info();
    for (int i = 0; i < info.num_params; ++i) {
      params[i] = info.params[i].default_value;
    }
  }

  // A clean granular setting for measurements: regular grains, no
  // randomness, reverb or feedback.
  void Clean() {
    Defaults();
    params[Beadsy::TIME] = 0.05f;
    params[Beadsy::SIZE] = 0.6f;
    params[Beadsy::SHAPE] = 0.5f;
    params[Beadsy::PITCH] = 0.5f;
    params[Beadsy::DENSITY] = 0.15f;
    params[Beadsy::FEEDBACK] = 0.0f;
    params[Beadsy::REVERB] = 0.0f;
    params[Beadsy::QUALITY] = 1.0f;
    params[Beadsy::TIME_RANDOM] = 0.5f;
    params[Beadsy::PITCH_RANDOM] = 0.5f;
    params[Beadsy::FREEZE] = 0.0f;
  }

  void Tempo(float beat_seconds) {
    tempo.beat_seconds = beat_seconds;
    tempo.bar_increment = 1.0f / (4.0f * beat_seconds * kSr);
    context.beat_seconds = beat_seconds;
    context.bar_increment = tempo.bar_increment;
  }

  // One block; advances the bar phase like the engine.
  void Block(const Frame* in, Frame* out) {
    block->Process(context, params, in, out, kBlock);
    context.bar_phase += context.bar_increment * float(kBlock);
    context.bar_phase -= floorf(context.bar_phase);
  }
};

// Runs n samples of a sine (frequency hz, amplitude a; hz 0: silence) and
// appends the output's left + right to `out` if given.
void RunSine(Rig* rig, float hz, float a, size_t n, std::vector<float>* out,
             float* phase) {
  Frame in[kBlock], o[kBlock];
  for (size_t done = 0; done < n; done += kBlock) {
    for (size_t i = 0; i < kBlock; ++i) {
      const float s = a * sinf(*phase);
      *phase += 2.0f * kPi * hz / kSr;
      if (*phase > 2.0f * kPi) {
        *phase -= 2.0f * kPi;
      }
      in[i].l = in[i].r = s;
    }
    rig->Block(in, o);
    if (out) {
      for (size_t i = 0; i < kBlock; ++i) {
        out->push_back(0.5f * (o[i].l + o[i].r));
      }
    }
  }
}

// Power of x at hz (Goertzel), normalised by length.
double GoertzelWindow(const std::vector<float>& x, size_t begin, size_t end,
                      double hz) {
  const double w = 2.0 * 3.14159265358979 * hz / kSr;
  const double c = 2.0 * cos(w);
  double s1 = 0.0, s2 = 0.0;
  for (size_t i = begin; i < end; ++i) {
    const double s0 = x[i] + c * s1 - s2;
    s2 = s1;
    s1 = s0;
  }
  const double power = s1 * s1 + s2 * s2 - c * s1 * s2;
  const double n = double(end - begin);
  return power / (n * n);
}

// The mean of GoertzelWindow over 2048-sample windows (23 Hz wide): grains
// restart their phase, and a ratio from SemitonesToRatio is not exact, so a
// long window would miss the partial.
double Goertzel(const std::vector<float>& x, size_t begin, size_t end,
                double hz) {
  const size_t w = 2048;
  double sum = 0.0;
  int n = 0;
  for (size_t i = begin; i + w <= end; i += w) {
    sum += GoertzelWindow(x, i, i + w, hz);
    ++n;
  }
  return n ? sum / n : 0.0;
}

double Rms(const std::vector<float>& x, size_t begin, size_t end) {
  double sum = 0.0;
  for (size_t i = begin; i < end; ++i) {
    sum += double(x[i]) * double(x[i]);
  }
  return sqrt(sum / double(end - begin > 0 ? end - begin : 1));
}

}  // namespace

TEST(beadsy, init_memory_and_silence) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  const size_t external = rig.memory.external().used();
  const size_t internal = rig.memory.internal().used();
  test::Note("memory: external %zu bytes, internal %zu bytes", external,
             internal);
  // 768 kB of buffer + 64 kB of reverb + the 8.5 kB processor.
  CHECK(external >= 786432 + 65536);
  CHECK(external < 786432 + 65536 + 16384);
  CHECK(internal < 1024);

  const float qualities[] = { 1.0f, 0.0f, 1.0f / 3.0f, 2.0f / 3.0f };
  for (int q = 0; q < 4; ++q) {
    // Some noise through it first, then Reset(): silence in, silence out.
    rig.Defaults();
    rig.params[Beadsy::QUALITY] = qualities[q];
    rig.params[Beadsy::FEEDBACK] = 0.8f;
    rig.params[Beadsy::REVERB] = 0.8f;
    Frame in[kBlock], out[kBlock];
    uint32_t seed = 1;
    for (int b = 0; b < 3000; ++b) {
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = test::Noise(&seed);
        in[i].r = test::Noise(&seed);
      }
      rig.Block(in, out);
    }
    rig.block->Reset();
    CHECK(rig.block->quality() == (q == 0 ? 3 : q - 1));
    bool silent = true;
    memset(in, 0, sizeof(in));
    for (int b = 0; b < 3000; ++b) {
      rig.Block(in, out);
      for (size_t i = 0; i < kBlock; ++i) {
        silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
      }
    }
    CHECK(silent);
  }
}

TEST(beadsy, stability) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  Frame in[kBlock], out[kBlock];
  uint32_t seed = 7, pseed = 99;
  float peak = 0.0f;
  bool finite = true;
  // 20 s of noise, every parameter random every block, synced or not.
  const int blocks = int(20.0f * kSr / float(kBlock));
  for (int b = 0; b < blocks; ++b) {
    // QUALITY changes once a second (each change mutes for ~45 ms).
    const float quality = rig.params[Beadsy::QUALITY];
    for (int p = 0; p < Beadsy::NUM_PARAMS; ++p) {
      rig.params[p] = 0.5f + 0.5f * test::Noise(&pseed);
    }
    if (b % 1500) {
      rig.params[Beadsy::QUALITY] = quality;
    }
    rig.context.sync_mask = (b / 500) & 1 ? 0xffff : 0;
    rig.context.send = (b / 300) % 3 == 2 ? 0.0f : 1.0f;
    for (size_t i = 0; i < kBlock; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Block(in, out);
    for (size_t i = 0; i < kBlock; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  test::Note("random parameters: peak %.3f", peak);
  CHECK(finite);
  CHECK(peak > 0.05f);  // it did play
  CHECK(peak < 4.0f);

  // Every parameter at 0, then at 1 (feedback at maximum, delay mode, +-4
  // input), 10 s each, for every quality.
  for (int extreme = 0; extreme < 2; ++extreme) {
    for (int q = 0; q < 4; ++q) {
      for (int p = 0; p < Beadsy::NUM_PARAMS; ++p) {
        rig.params[p] = float(extreme);
      }
      rig.params[Beadsy::QUALITY] = float(q) / 3.0f;
      rig.context.sync_mask = 0;
      rig.context.send = 1.0f;
      float peak_q = 0.0f;
      const int n = int(10.0f * kSr / float(kBlock));
      for (int b = 0; b < n; ++b) {
        // FREEZE off for the first half, so the buffer fills.
        rig.params[Beadsy::FREEZE] = b < n / 2 ? 0.0f : float(extreme);
        for (size_t i = 0; i < kBlock; ++i) {
          in[i].l = 4.0f * test::Noise(&seed);
          in[i].r = 4.0f * test::Noise(&seed);
        }
        rig.Block(in, out);
        for (size_t i = 0; i < kBlock; ++i) {
          finite = finite && test::Finite(out[i]);
          peak_q = fmaxf(peak_q, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
      }
      test::Note("all at %d, quality %d: peak %.3f", extreme, q, peak_q);
      CHECK(finite);
      CHECK(peak_q < 4.0f);
    }
  }
}

TEST(beadsy, freeze_holds_when_send_drops) {
  for (int how = 0; how < 2; ++how) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) {
      return;
    }
    rig.Clean();
    rig.params[Beadsy::QUALITY] = 1.0f;
    float phase = 0.0f;
    // 3 s of 440 Hz, recorded.
    RunSine(&rig, 440.0f, 0.5f, size_t(3.0f * kSr), NULL, &phase);
    CHECK(!rig.block->frozen());
    // Then the send drops (or FREEZE goes on) and 1000 Hz arrives.
    if (how == 0) {
      rig.context.send = 0.0f;
    } else {
      rig.params[Beadsy::FREEZE] = 1.0f;
    }
    std::vector<float> out;
    RunSine(&rig, 1000.0f, 0.5f, size_t(4.0f * kSr), &out, &phase);
    CHECK(rig.block->frozen());
    const size_t a = size_t(1.0f * kSr), b = out.size();
    const double old_power = Goertzel(out, a, b, 440.0);
    const double new_power = Goertzel(out, a, b, 1000.0);
    const double rms = Rms(out, a, b);
    test::Note("%s: rms %.3f, 440 Hz %.2e, 1000 Hz %.2e",
               how == 0 ? "send 0" : "FREEZE ON", rms, old_power, new_power);
    CHECK(rms > 0.05);                       // still playing
    CHECK(old_power > 1000.0 * new_power);   // what it heard before
  }

  // Send back on: the new input is recorded again.
  Rig rig;
  rig.Clean();
  float phase = 0.0f;
  RunSine(&rig, 440.0f, 0.5f, size_t(2.0f * kSr), NULL, &phase);
  rig.context.send = 0.0f;
  RunSine(&rig, 1000.0f, 0.5f, size_t(1.0f * kSr), NULL, &phase);
  rig.context.send = 1.0f;
  std::vector<float> out;
  RunSine(&rig, 1000.0f, 0.5f, size_t(3.0f * kSr), &out, &phase);
  CHECK(!rig.block->frozen());
  const double old_power = Goertzel(out, out.size() / 2, out.size(), 440.0);
  const double new_power = Goertzel(out, out.size() / 2, out.size(), 1000.0);
  CHECK(new_power > 100.0 * old_power);
}

TEST(beadsy, pitch_shifts_grains) {
  const float semitones[] = { 0.0f, 12.0f, -12.0f, 7.0f };
  for (int k = 0; k < 4; ++k) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) {
      return;
    }
    rig.Clean();
    rig.params[Beadsy::PITCH] = 0.5f + semitones[k] / 48.0f;
    float phase = 0.0f;
    std::vector<float> out;
    RunSine(&rig, 220.0f, 0.5f, size_t(4.0f * kSr), &out, &phase);
    const double expected = 220.0 * pow(2.0, semitones[k] / 12.0);
    const size_t a = size_t(2.0f * kSr), b = out.size();
    const double at_expected = Goertzel(out, a, b, expected);
    const double at_input = semitones[k] == 0.0f
        ? Goertzel(out, a, b, 220.0 * 1.5) : Goertzel(out, a, b, 220.0);
    test::Note("%+.0f st: power at %.1f Hz %.2e, reference %.2e",
               semitones[k], expected, at_expected, at_input);
    CHECK(at_expected > 30.0 * at_input);
    char text[16];
    rig.block->Format(Beadsy::PITCH, rig.params[Beadsy::PITCH], rig.context,
                      text, sizeof(text));
    test::Note("PITCH shows %s", text);
  }
}

TEST(beadsy, every_quality_runs) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  float phase = 0.0f;
  for (int q = 0; q < 4; ++q) {
    rig.params[Beadsy::QUALITY] = float(q) / 3.0f;
    rig.params[Beadsy::REVERB] = 0.5f;
    rig.params[Beadsy::FEEDBACK] = 0.5f;
    // The switch: fade out, clear, fade in.
    std::vector<float> out;
    RunSine(&rig, 220.0f, 0.5f, kBlock, &out, &phase);
    int blocks = 1;
    while (rig.block->switching() && blocks < 400) {
      RunSine(&rig, 220.0f, 0.5f, kBlock, &out, &phase);
      ++blocks;
    }
    CHECK(rig.block->quality() == q);
    test::Note("quality %d: switch took %.1f ms", q,
               float(blocks * kBlock) / kSr * 1000.0f);
    out.clear();
    RunSine(&rig, 220.0f, 0.5f, size_t(3.0f * kSr), &out, &phase);
    bool finite = true;
    float peak = 0.0f;
    for (size_t i = 0; i < out.size(); ++i) {
      finite = finite && isfinite(out[i]);
      peak = fmaxf(peak, fabsf(out[i]));
    }
    const double rms = Rms(out, out.size() / 2, out.size());
    test::Note("quality %d: rms %.3f peak %.3f, 220 Hz %.2e", q, rms, peak,
               Goertzel(out, out.size() / 2, out.size(), 220.0));
    CHECK(finite);
    CHECK(peak < 2.0f);
    CHECK(rms > 0.05);
    CHECK(Goertzel(out, out.size() / 2, out.size(), 220.0) >
          30.0 * Goertzel(out, out.size() / 2, out.size(), 330.0));
  }
}

TEST(beadsy, delay_mode_echo) {
  // SIZE at the top: Beads' delay mode. DENSITY sets the repeat time,
  // 4.0 s * 2 ^ (-18 * |DENSITY - 0.5|) in the 16-bit medium: 0.2778 gives
  // 1/16 of the buffer, 12000 samples (250 ms).
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  rig.params[Beadsy::SIZE] = 1.0f;
  rig.params[Beadsy::TIME] = 0.0f;
  rig.params[Beadsy::SHAPE] = 0.0f;
  rig.params[Beadsy::DENSITY] = 0.5f - 4.0f / 18.0f;
  rig.params[Beadsy::FEEDBACK] = 0.0f;
  float phase = 0.0f;
  RunSine(&rig, 0.0f, 0.0f, size_t(4.0f * kSr), NULL, &phase);

  // A click every second; the echo's peak after each.
  const size_t period = size_t(kSr);
  std::vector<float> out;
  Frame in[kBlock], o[kBlock];
  for (size_t n = 0; n < 4 * period; n += kBlock) {
    for (size_t i = 0; i < kBlock; ++i) {
      const bool click = (n + i) % period == 0;
      in[i].l = in[i].r = click ? 1.0f : 0.0f;
    }
    rig.Block(in, o);
    for (size_t i = 0; i < kBlock; ++i) {
      out.push_back(0.5f * (o[i].l + o[i].r));
    }
  }
  // Beads filters DENSITY with a hysteresis of 0.0025 (approached from 0
  // here): 0.2753 is what it uses, 11632 samples.
  const double expected = 192000.0 *
      pow(2.0, -18.0 * (0.5 - (0.5 - 4.0 / 18.0 - 0.0025)));
  int good = 0;
  for (int k = 1; k < 4; ++k) {
    size_t best = 0;
    float best_value = 0.0f;
    for (size_t i = 0; i < period - 1000; ++i) {
      const float v = fabsf(out[k * period + i]);
      if (v > best_value) {
        best_value = v;
        best = i;
      }
    }
    test::Note("click %d: echo after %zu samples (%.2f ms), peak %.3f", k,
               best, float(best) / kSr * 1000.0f, best_value);
    if (fabs(double(best) - expected) < 0.001 * kSr && best_value > 0.1f) {
      ++good;
    }
  }
  CHECK(good == 3);
  char text[16];
  rig.block->Format(Beadsy::SIZE, 1.0f, rig.context, text, sizeof(text));
  CHECK(strcmp(text, "DELAY") == 0);
  rig.block->Format(Beadsy::DENSITY, rig.params[Beadsy::DENSITY],
                    rig.context, text, sizeof(text));
  test::Note("DENSITY shows %s in delay mode", text);
}

TEST(beadsy, no_clicks) {
  // A sine through it while PITCH, TIME and SIZE jump: the grains take the
  // new values when they start, under their envelopes. The largest step
  // stays within a few times that of the steady texture at the highest
  // pitch used.
  for (int which = 0; which < 3; ++which) {
    float steady_step = 0.0f, jump_step = 0.0f;
    for (int jumping = 0; jumping < 2; ++jumping) {
      Rig rig;
      rig.Clean();
      rig.params[Beadsy::PITCH] = 0.5f + 12.0f / 48.0f;
      float phase = 0.0f;
      RunSine(&rig, 220.0f, 0.5f, size_t(2.0f * kSr), NULL, &phase);
      std::vector<float> out;
      for (int k = 0; k < 40; ++k) {
        if (jumping) {
          const bool up = k & 1;
          if (which == 0) {
            rig.params[Beadsy::PITCH] = up ? 0.5f + 12.0f / 48.0f : 0.25f;
          } else if (which == 1) {
            rig.params[Beadsy::TIME] = up ? 0.6f : 0.02f;
          } else {
            rig.params[Beadsy::SIZE] = up ? 0.9f : 0.45f;
          }
        }
        RunSine(&rig, 220.0f, 0.5f, size_t(0.1f * kSr), &out, &phase);
      }
      float step = 0.0f;
      for (size_t i = 1; i < out.size(); ++i) {
        step = fmaxf(step, fabsf(out[i] - out[i - 1]));
      }
      (jumping ? jump_step : steady_step) = step;
    }
    test::Note("%s jumps: largest step %.4f, steady %.4f",
               which == 0 ? "PITCH" : (which == 1 ? "TIME" : "SIZE"),
               jump_step, steady_step);
    CHECK(jump_step < 3.0f * steady_step);
  }

  // A quality change fades out and in: no step larger than the music's.
  Rig rig;
  rig.Clean();
  float phase = 0.0f;
  RunSine(&rig, 220.0f, 0.5f, size_t(2.0f * kSr), NULL, &phase);
  std::vector<float> out;
  RunSine(&rig, 220.0f, 0.5f, size_t(0.5f * kSr), &out, &phase);
  float steady = 0.0f;
  for (size_t i = 1; i < out.size(); ++i) {
    steady = fmaxf(steady, fabsf(out[i] - out[i - 1]));
  }
  out.clear();
  rig.params[Beadsy::QUALITY] = 2.0f / 3.0f;
  RunSine(&rig, 220.0f, 0.5f, size_t(0.5f * kSr), &out, &phase);
  float step = 0.0f;
  for (size_t i = 1; i < out.size(); ++i) {
    step = fmaxf(step, fabsf(out[i] - out[i - 1]));
  }
  test::Note("quality change: largest step %.4f, steady %.4f", step, steady);
  CHECK(step < 3.0f * steady);
}

TEST(beadsy, format) {
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  const float values[] = { 0.0f, 0.25f, 0.5f, 0.75f, 1.0f };
  for (int mode = 0; mode < 2; ++mode) {
    // Granular, then delay mode (Format follows the block's mode).
    rig.Clean();
    rig.params[Beadsy::SIZE] = mode ? 1.0f : 0.5f;
    float phase = 0.0f;
    RunSine(&rig, 220.0f, 0.3f, kBlock * 4, NULL, &phase);
    for (int synced = 0; synced < 2; ++synced) {
      ProcessContext c = rig.context;
      c.sync_mask = synced ? 0xffff : 0;
      for (int p = 0; p < Beadsy::NUM_PARAMS; ++p) {
        for (int v = 0; v < 5; ++v) {
          char text[32];
          memset(text, 'X', sizeof(text));
          rig.block->Format(p, values[v], c, text, 11);
          const size_t n = strnlen(text, sizeof(text));
          if (v == 2 || n == 0 || n > 10) {
            test::Note("mode %d synced %d %s %.2f: \"%s\"", mode, synced,
                       rig.block->info().params[p].name, values[v], text);
          }
          CHECK(n > 0 && n <= 10);
        }
      }
    }
  }
  const sidefx::BlockInfo& info = rig.block->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params <= sidefx::kMaxBlockParams);
  for (int p = 0; p < info.num_params; ++p) {
    CHECK(strlen(info.params[p].name) <= 8);
  }
}

TEST(beadsy, synced_density_follows_tempo) {
  // DENSITY synced, left of centre at the 1/4 divider: short grains start
  // on every quarter note. Their onsets' spacing is the beat.
  const float beats[] = { 0.5f, 0.6f };
  for (int t = 0; t < 2; ++t) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) {
      return;
    }
    rig.Clean();
    rig.Tempo(beats[t]);
    rig.context.sync_mask = 1 << Beadsy::DENSITY;
    rig.params[Beadsy::DENSITY] = 0.2f;  // index 3 of 1, 2, 3, 4, 6..: 1/4
    rig.params[Beadsy::SIZE] = 0.49f;    // ~30 ms grains
    char text[16];
    rig.block->Format(Beadsy::DENSITY, 0.2f, rig.context, text, sizeof(text));
    CHECK(strcmp(text, "1/4") == 0);
    float phase = 0.0f;
    std::vector<float> out;
    RunSine(&rig, 440.0f, 0.5f, size_t(8.0f * kSr), &out, &phase);
    // Envelope in 1 ms windows; onsets where it rises past half its peak.
    const size_t w = 48;
    std::vector<float> env;
    float peak = 0.0f;
    for (size_t i = 0; i + w <= out.size(); i += w) {
      float m = 0.0f;
      for (size_t j = 0; j < w; ++j) {
        m = fmaxf(m, fabsf(out[i + j]));
      }
      env.push_back(m);
      peak = fmaxf(peak, m);
    }
    std::vector<size_t> onsets;
    bool high = true;
    for (size_t i = 0; i < env.size(); ++i) {
      if (!high && env[i] > 0.5f * peak) {
        onsets.push_back(i * w);
        high = true;
      } else if (high && env[i] < 0.1f * peak) {
        high = false;
      }
    }
    CHECK(onsets.size() >= 8);
    if (onsets.size() < 3) {
      continue;
    }
    // Skip the first onsets (the divider locks after the first pulses).
    double sum = 0.0;
    int count = 0;
    double worst = 0.0;
    for (size_t i = 3; i < onsets.size(); ++i) {
      const double d = double(onsets[i] - onsets[i - 1]) / kSr;
      sum += d;
      ++count;
      worst = fmax(worst, fabs(d - beats[t]));
    }
    const double mean = count ? sum / count : 0.0;
    test::Note("beat %.2f s: %zu onsets, mean spacing %.4f s, worst %.4f",
               beats[t], onsets.size(), mean, worst);
    CHECK(fabs(mean - beats[t]) < 0.002);
    CHECK(worst < 0.004);
  }
}

namespace {

// The energy of n samples of the output, a sine going in.
double Energy(Rig* rig, float hz, size_t n, float* phase) {
  std::vector<float> out;
  RunSine(rig, hz, 0.5f, n, &out, phase);
  double e = 0.0;
  for (size_t i = 0; i < out.size(); ++i) {
    e += double(out[i]) * double(out[i]);
  }
  return e;
}

}  // namespace

TEST(beadsy, quality_and_freeze_hysteresis) {
  // A frozen texture survives QUALITY excursions under modulation: a value
  // within the hysteresis does nothing, one past it that comes back before
  // the output has faded out cancels the change. Both used to wipe the
  // buffer.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  rig.params[Beadsy::TIME] = 0.3f;
  float phase = 0.0f;
  RunSine(&rig, 330.0f, 0.5f, size_t(3.0f * kSr), NULL, &phase);
  rig.context.send = 0.0f;
  RunSine(&rig, 330.0f, 0.5f, size_t(0.2f * kSr), NULL, &phase);
  const double before = Energy(&rig, 0.0f, size_t(1.0f * kSr), &phase);

  const float excursions[] = { 0.80f, 0.60f };
  for (int k = 0; k < 2; ++k) {
    rig.params[Beadsy::QUALITY] = excursions[k];
    RunSine(&rig, 0.0f, 0.0f, kBlock, NULL, &phase);
    const bool switched = rig.block->switching();
    rig.params[Beadsy::QUALITY] = 1.0f;
    RunSine(&rig, 0.0f, 0.0f, size_t(0.5f * kSr), NULL, &phase);
    const double after = Energy(&rig, 0.0f, size_t(1.0f * kSr), &phase);
    test::Note("QUALITY %.2f for one block: switching %d, frozen energy "
               "%.1f before, %.1f after", excursions[k], int(switched),
               before, after);
    CHECK(switched == (k == 1));
    CHECK(rig.block->quality() == Beadsy::QUALITY_DIGITAL_16_BIT);
    CHECK(!rig.block->switching());
    CHECK(after > 0.5 * before);
  }

  // CV noise around the boundary at 0.8333: no switch at all.
  uint32_t seed = 3;
  bool switched = false;
  for (int b = 0; b < 1500; ++b) {
    rig.params[Beadsy::QUALITY] = 0.8333f + 0.03f * test::Noise(&seed);
    RunSine(&rig, 0.0f, 0.0f, kBlock, NULL, &phase);
    switched = switched || rig.block->switching();
  }
  CHECK(!switched);
  CHECK(rig.block->quality() == Beadsy::QUALITY_DIGITAL_16_BIT);

  // FREEZE: on above 0.55, off below 0.45.
  rig.params[Beadsy::QUALITY] = 1.0f;
  rig.context.send = 1.0f;
  const float freeze[] = { 0.0f, 0.54f, 0.56f, 0.46f, 0.44f };
  const bool expected[] = { false, false, true, true, false };
  for (int k = 0; k < 5; ++k) {
    rig.params[Beadsy::FREEZE] = freeze[k];
    RunSine(&rig, 330.0f, 0.5f, kBlock, NULL, &phase);
    CHECK(rig.block->frozen() == expected[k]);
  }
}

TEST(beadsy, synced_divider_on_the_bar) {
  // Synced DENSITY's divisions count from the bar, wherever the bar was
  // when sync started: "1 BAR" lands on the downbeat, "1/2." on the 16th
  // grid, and the first grain after sync-on is on the grid too.
  struct Case {
    float density;
    const char* label;
    float start_phase;
  };
  const Case cases[] = {
    { 0.46f, "1 BAR", 0.0f },
    { 0.46f, "1 BAR", 0.3225f },
    { 0.46f, "1 BAR", 0.53f },
    { 0.38f, "1/2.", 0.29f },
    { 0.03f, "1/16", 0.3225f },
  };
  for (int c = 0; c < 5; ++c) {
    Rig rig;
    CHECK(rig.ok);
    if (!rig.ok) {
      return;
    }
    rig.Clean();
    rig.params[Beadsy::SIZE] = 0.49f;  // ~30 ms grains
    // A second of recording without grains, then sync and DENSITY on at
    // start_phase (so a first grain off the grid would be heard).
    rig.params[Beadsy::DENSITY] = 0.5f;
    float phase = 0.0f;
    RunSine(&rig, 440.0f, 0.5f, size_t(1.0f * kSr), NULL, &phase);
    rig.params[Beadsy::DENSITY] = cases[c].density;
    rig.context.sync_mask = 1 << Beadsy::DENSITY;
    rig.context.bar_phase = cases[c].start_phase;
    char text[16];
    rig.block->Format(Beadsy::DENSITY, cases[c].density, rig.context, text,
                      sizeof(text));
    CHECK(strcmp(text, cases[c].label) == 0);
    Frame in[kBlock], out[kBlock];
    bool high = false;
    int onsets = 0;
    float worst = 0.0f;      // distance from the 16th grid, in 16ths
    float worst_bar = 0.0f;  // "1 BAR": distance from the downbeat, in bars
    for (int b = 0; b < int(10.0f * kSr / float(kBlock)); ++b) {
      const float block_phase = rig.context.bar_phase;
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = in[i].r = 0.5f * sinf(phase);
        phase += 2.0f * kPi * 440.0f / kSr;
        phase -= phase > 2.0f * kPi ? 2.0f * kPi : 0.0f;
      }
      rig.Block(in, out);
      float m = 0.0f;
      for (size_t i = 0; i < kBlock; ++i) {
        m = fmaxf(m, fabsf(out[i].l + out[i].r));
      }
      if (!high && m > 0.1f) {
        high = true;
        ++onsets;
        const float x = block_phase * 16.0f;
        worst = fmaxf(worst, fabsf(x - floorf(x + 0.5f)));
        if (c < 3) {
          worst_bar = fmaxf(worst_bar,
                            fminf(block_phase, 1.0f - block_phase));
        }
      } else if (high && m < 0.01f) {
        high = false;
      }
    }
    test::Note("%s from bar phase %.4f: %d onsets, worst %.3f 16ths off the "
               "grid, %.4f bars off the downbeat", cases[c].label,
               cases[c].start_phase, onsets, worst, worst_bar);
    CHECK(onsets >= 4);
    CHECK(worst < 0.05f);
    CHECK(worst_bar < 0.02f);
  }
}

TEST(beadsy, random_amount_law) {
  // T RAND and P RAND follow Beads' attenuverter law: nothing within 3 % of
  // the centre, then quadratic.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  const float values[] = { 0.5f, 0.51f, 0.53f, 0.75f, 1.0f, 0.25f, 0.0f };
  const char* expected[] = {
    "0%", "0%", "0%", "SPRD 23%", "SPRD 100%", "JUMP 23%", "JUMP 100%",
  };
  for (int k = 0; k < 7; ++k) {
    for (int p = Beadsy::TIME_RANDOM; p <= Beadsy::PITCH_RANDOM; ++p) {
      char text[16];
      rig.block->Format(p, values[k], rig.context, text, sizeof(text));
      if (strcmp(text, expected[k]) != 0) {
        test::Note("%.2f shows \"%s\", expected \"%s\"", values[k], text,
                   expected[k]);
      }
      CHECK(strcmp(text, expected[k]) == 0);
    }
  }

  // Three detents clockwise on P RAND: the grains stay at PITCH, as at the
  // centre (the linear law scattered them by +-1.4 semitones there).
  double power[2];
  for (int k = 0; k < 2; ++k) {
    Rig r;
    r.Clean();
    r.params[Beadsy::PITCH] = 0.75f;
    r.params[Beadsy::PITCH_RANDOM] = k ? 0.53f : 0.5f;
    float phase = 0.0f;
    std::vector<float> out;
    RunSine(&r, 220.0f, 0.5f, size_t(4.0f * kSr), &out, &phase);
    power[k] = Goertzel(out, size_t(2.0f * kSr), out.size(), 440.0);
  }
  test::Note("an octave up: 440 Hz %.2e with P RAND at 0.5, %.2e at 0.53",
             power[0], power[1]);
  CHECK(power[1] > 0.7 * power[0]);
}

TEST(beadsy, mode_follows_the_processor) {
  // Beads leaves delay mode 1.5 s after SIZE leaves the top: the readouts
  // (and the seed clock's rate) follow the processor, not the knob.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  rig.params[Beadsy::SIZE] = 1.0f;
  float phase = 0.0f;
  RunSine(&rig, 220.0f, 0.5f, size_t(2.0f * kSr), NULL, &phase);
  char text[16];
  rig.block->Format(Beadsy::TIME, 0.3f, rig.context, text, sizeof(text));
  CHECK(text[0] == 'x');
  rig.params[Beadsy::SIZE] = 0.5f;
  RunSine(&rig, 220.0f, 0.5f, size_t(0.5f * kSr), NULL, &phase);
  rig.block->Format(Beadsy::TIME, 0.3f, rig.context, text, sizeof(text));
  test::Note("0.5 s after SIZE left the top, TIME shows %s", text);
  CHECK(text[0] == 'x');
  RunSine(&rig, 220.0f, 0.5f, size_t(1.5f * kSr), NULL, &phase);
  rig.block->Format(Beadsy::TIME, 0.3f, rig.context, text, sizeof(text));
  test::Note("2 s after, TIME shows %s", text);
  CHECK(text[0] != 'x');
}

TEST(beadsy, delay_mode_send_throw) {
  // In delay mode the send works as on a delay: off, the echoes ring out by
  // FEEDBACK (Beads' freeze there loops a slice for ever). FREEZE is the
  // slice looper, and TIME then shows where the loop starts.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  rig.params[Beadsy::SIZE] = 1.0f;
  rig.params[Beadsy::TIME] = 0.0f;
  rig.params[Beadsy::DENSITY] = 0.5f - 4.0f / 18.0f;  // 250 ms
  rig.params[Beadsy::FEEDBACK] = 0.5f;
  float phase = 0.0f;
  std::vector<float> out;
  RunSine(&rig, 440.0f, 0.5f, size_t(3.0f * kSr), &out, &phase);
  const double before = Rms(out, out.size() / 2, out.size());
  rig.context.send = 0.0f;
  out.clear();
  RunSine(&rig, 440.0f, 0.5f, size_t(4.0f * kSr), &out, &phase);
  CHECK(!rig.block->frozen());
  const double after = Rms(out, size_t(3.0f * kSr), out.size());
  test::Note("send off in delay mode: rms %.4f before, %.6f 3 s after",
             before, after);
  CHECK(before > 0.05);
  CHECK(after < 0.01 * before);

  rig.context.send = 1.0f;
  rig.params[Beadsy::FREEZE] = 1.0f;
  RunSine(&rig, 440.0f, 0.5f, size_t(1.0f * kSr), NULL, &phase);
  CHECK(rig.block->frozen());
  char text[16];
  rig.block->Format(Beadsy::TIME, 0.25f, rig.context, text, sizeof(text));
  test::Note("frozen delay mode: TIME 0.25 shows %s", text);
  CHECK(strncmp(text, "LOOP ", 5) == 0);
  CHECK(strlen(text) <= 10);
}

TEST(beadsy, reset_takes_the_new_quality) {
  // A preset load (Reset, then the new values): the new QUALITY is set up
  // at once instead of with a fade-out, a clear and a fade-in; DIRTY TAPE,
  // whose silence differs, only needs the clear.
  Rig rig;
  CHECK(rig.ok);
  if (!rig.ok) {
    return;
  }
  rig.Clean();
  float phase = 0.0f;
  RunSine(&rig, 220.0f, 0.5f, size_t(1.0f * kSr), NULL, &phase);
  rig.block->Reset();
  rig.params[Beadsy::QUALITY] = 1.0f / 3.0f;
  RunSine(&rig, 220.0f, 0.5f, kBlock, NULL, &phase);
  CHECK(rig.block->quality() == Beadsy::QUALITY_CLEAN_TAPE);
  CHECK(!rig.block->switching());

  rig.block->Reset();
  rig.params[Beadsy::QUALITY] = 0.0f;
  int blocks = 0;
  do {
    RunSine(&rig, 220.0f, 0.5f, kBlock, NULL, &phase);
    ++blocks;
  } while (rig.block->switching() && blocks < 400);
  test::Note("Reset to DIRTY TAPE: %.1f ms",
             float(blocks * kBlock) / kSr * 1000.0f);
  CHECK(rig.block->quality() == Beadsy::QUALITY_DIRTY_TAPE);
  CHECK(blocks < 70);  // 48 blocks of clearing and a 5 ms fade-in

  // And silence in, silence out, at once.
  rig.block->Reset();
  rig.params[Beadsy::QUALITY] = 2.0f / 3.0f;
  bool silent = true;
  Frame in[kBlock], o[kBlock];
  memset(in, 0, sizeof(in));
  for (int b = 0; b < 500; ++b) {
    rig.Block(in, o);
    for (size_t i = 0; i < kBlock; ++i) {
      silent = silent && o[i].l == 0.0f && o[i].r == 0.0f;
    }
  }
  CHECK(silent);
}
