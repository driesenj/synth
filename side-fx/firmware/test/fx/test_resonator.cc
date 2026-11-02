// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the RESONATOR block.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"

#include "engine/params.h"
#include "fx/resonator.h"

using sidefx::Frame;
using sidefx::ProcessContext;
using sidefx::Resonator;

namespace {

const float kFs = 48014.32f;
const size_t kBlock = sidefx::kBlockSize;

struct Rig {
  test::TestMemory memory;
  Resonator* resonator;
  float params[Resonator::NUM_PARAMS];
  ProcessContext context;

  Rig() : memory(1u << 20, 64u << 10) {
    resonator = memory.memory()->internal->Create<Resonator>();
    CHECK(resonator != NULL);
    CHECK(resonator->Init(memory.memory()));
    resonator->Reset();
    const sidefx::BlockInfo& info = resonator->info();
    for (int i = 0; i < Resonator::NUM_PARAMS; ++i) {
      params[i] = info.params[i].default_value;
    }
    params[Resonator::PARAM_DETUNE] = 0.0f;
    context = test::Context(test::Tempo120(), 0);
  }

  void Process(const Frame* in, Frame* out) {
    resonator->Process(context, params, in, out, kBlock);
  }

  // Plays an impulse (or a sine at hz when hz > 0) for `seconds`; the left
  // output into *left, the right into *right (when not NULL).
  void Record(float seconds, float hz, float amplitude,
              std::vector<float>* left, std::vector<float>* right) {
    const int blocks = int(seconds * kFs / kBlock);
    left->clear();
    if (right) right->clear();
    float phase = 0.0f;
    for (int b = 0; b < blocks; ++b) {
      Frame in[kBlock], out[kBlock];
      for (size_t i = 0; i < kBlock; ++i) {
        float s;
        if (hz > 0.0f) {
          s = amplitude * sinf(6.2831853f * phase);
          phase += hz / kFs;
          if (phase >= 1.0f) phase -= 1.0f;
        } else {
          s = (b == 0 && i == 0) ? amplitude : 0.0f;
        }
        in[i].l = in[i].r = s;
      }
      Process(in, out);
      for (size_t i = 0; i < kBlock; ++i) {
        left->push_back(out[i].l);
        if (right) right->push_back(out[i].r);
      }
    }
  }
};

float Chord(int chord) {
  return sidefx::StepValue(chord, Resonator::NUM_CHORDS);
}

float Pitch(float semitones) {
  return 0.5f + semitones / 48.0f;
}

// |DFT| at hz of x[start .. start + n), Hann windowed.
double Magnitude(const std::vector<float>& x, size_t start, size_t n,
                 double hz) {
  double re = 0.0, im = 0.0;
  const double w = 2.0 * M_PI * hz / double(kFs);
  for (size_t i = 0; i < n; ++i) {
    const double window = 0.5 - 0.5 * cos(2.0 * M_PI * double(i) / double(n));
    const double s = window * x[start + i];
    re += s * cos(w * double(i));
    im -= s * sin(w * double(i));
  }
  return sqrt(re * re + im * im);
}

// The strongest frequency within +-30 cents of hz, in cents off hz.
double PeakCents(const std::vector<float>& x, size_t start, size_t n,
                 double hz) {
  double best = 0.0;
  int best_cents = 0;
  double m[61];
  for (int c = -30; c <= 30; ++c) {
    m[c + 30] = Magnitude(x, start, n, hz * pow(2.0, c / 1200.0));
    if (m[c + 30] > best) {
      best = m[c + 30];
      best_cents = c;
    }
  }
  if (best_cents == -30 || best_cents == 30) {
    return best_cents;
  }
  // A parabola through the log magnitudes around the peak.
  const double a = log(m[best_cents + 29]);
  const double b = log(m[best_cents + 30]);
  const double c = log(m[best_cents + 31]);
  return best_cents + 0.5 * (a - c) / (a - 2.0 * b + c);
}

// RT60 of the partial at hz, from its level in two windows.
double Rt60(const std::vector<float>& x, double hz, double t_a, double t_b) {
  const size_t n = size_t(0.1 * kFs);
  const double a = Magnitude(x, size_t(t_a * kFs), n, hz);
  const double b = Magnitude(x, size_t(t_b * kFs), n, hz);
  const double db_per_second = 20.0 * log10(a / b) / (t_b - t_a);
  return 60.0 / db_per_second;
}

}  // namespace

TEST(resonator, silence) {
  Rig rig;
  test::Note("internal %u bytes, external %u bytes",
             unsigned(rig.memory.internal().used()),
             unsigned(rig.memory.external().used()));
  CHECK(rig.memory.internal().used() < 8192);
  Frame in[kBlock], out[kBlock];
  memset(in, 0, sizeof(in));
  bool silent = true;
  for (int b = 0; b < 2000; ++b) {
    rig.Process(in, out);
    for (size_t i = 0; i < kBlock; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);

  // Init fails cleanly when the external arena is too small.
  test::TestMemory small(16u << 10, 64u << 10);
  Resonator* r = small.memory()->internal->Create<Resonator>();
  CHECK(r != NULL);
  CHECK(!r->Init(small.memory()));
}

TEST(resonator, stability) {
  Rig rig;
  uint32_t seed = 7;
  float peak = 0.0f;
  bool finite = true;
  const int blocks = int(20.0f * kFs / kBlock);
  for (int b = 0; b < blocks; ++b) {
    for (int p = 0; p < Resonator::NUM_PARAMS; ++p) {
      rig.params[p] = 0.5f + 0.5f * test::Noise(&seed);
    }
    rig.context.sync_mask = uint16_t(test::Noise(&seed) > 0.0f ?
                                     1 << Resonator::PARAM_DECAY : 0);
    Frame in[kBlock], out[kBlock];
    for (size_t i = 0; i < kBlock; ++i) {
      in[i].l = test::Noise(&seed);
      in[i].r = test::Noise(&seed);
    }
    rig.Process(in, out);
    for (size_t i = 0; i < kBlock; ++i) {
      finite = finite && test::Finite(out[i]);
      peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
    }
  }
  rig.context.sync_mask = 0;
  for (int extreme = 0; extreme < 2; ++extreme) {
    for (int loud = 0; loud < 2; ++loud) {
      for (int p = 0; p < Resonator::NUM_PARAMS; ++p) {
        rig.params[p] = float(extreme);
      }
      for (int b = 0; b < int(5.0f * kFs / kBlock); ++b) {
        Frame in[kBlock], out[kBlock];
        for (size_t i = 0; i < kBlock; ++i) {
          in[i].l = (loud ? 4.0f : 1.0f) * test::Noise(&seed);
          in[i].r = (loud ? 4.0f : 1.0f) * test::Noise(&seed);
        }
        rig.Process(in, out);
        for (size_t i = 0; i < kBlock; ++i) {
          finite = finite && test::Finite(out[i]);
          peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
        }
      }
    }
  }
  // A loud sine right on the resonance, longest decay, full drive.
  for (int p = 0; p < Resonator::NUM_PARAMS; ++p) {
    rig.params[p] = 1.0f;
  }
  rig.params[Resonator::PARAM_DAMP] = 0.0f;
  rig.params[Resonator::PARAM_CHORD] = 0.0f;
  rig.params[Resonator::PARAM_DETUNE] = 0.0f;
  std::vector<float> left, right;
  rig.Record(5.0f, 523.25f, 4.0f, &left, &right);
  for (size_t i = 0; i < left.size(); ++i) {
    finite = finite && isfinite(left[i]) && isfinite(right[i]);
    peak = fmaxf(peak, fmaxf(fabsf(left[i]), fabsf(right[i])));
  }
  test::Note("peak %.3f", peak);
  CHECK(finite);
  CHECK(peak < 4.0f);
}

TEST(resonator, tuning) {
  // A ringing voice's fundamental within 2 cents, from 33 Hz to 1 kHz,
  // with and without damping (the loop compensates the lowpass's delay).
  struct Case {
    float semitones;  // root
    int chord;
    float damp;
    double hz;        // a voice to look for
  };
  const Case cases[] = {
    { 0.0f, Resonator::CHORD_UNISON, 0.0f, 130.8128 },
    { 0.0f, Resonator::CHORD_UNISON, 0.8f, 130.8128 },
    { -24.0f, Resonator::CHORD_UNISON, 0.5f, 32.7032 },
    { 24.0f, Resonator::CHORD_UNISON, 0.0f, 523.2511 },
    { 24.0f, Resonator::CHORD_UNISON, 0.7f, 523.2511 },
    { 7.5f, Resonator::CHORD_UNISON, 0.3f, 130.8128 * pow(2.0, 7.5 / 12.0) },
    { 24.0f, Resonator::CHORD_MAJ7, 0.0f, 987.7666 },
    { 24.0f, Resonator::CHORD_MAJ7, 0.6f, 987.7666 },
  };
  for (size_t k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(cases[k].semitones);
    rig.params[Resonator::PARAM_CHORD] = Chord(cases[k].chord);
    rig.params[Resonator::PARAM_DAMP] = cases[k].damp;
    rig.params[Resonator::PARAM_DECAY] = 1.0f;
    std::vector<float> left;
    rig.Record(1.25f, 0.0f, 1.0f, &left, NULL);
    const double cents = PeakCents(left, size_t(0.2 * kFs), size_t(kFs),
                                   cases[k].hz);
    test::Note("%.2f Hz, damp %.1f: %+.2f cents", cases[k].hz,
               cases[k].damp, cents);
    CHECK(fabs(cents) < 2.0);
  }
}

TEST(resonator, chord) {
  // MINOR on C3: C3 Eb3 G3 C4 ring, D3 F3 G#3 do not.
  Rig rig;
  rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
  rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_MINOR);
  rig.params[Resonator::PARAM_DAMP] = 0.5f;
  rig.params[Resonator::PARAM_DECAY] = 0.8f;
  std::vector<float> left, right;
  rig.Record(1.25f, 0.0f, 1.0f, &left, &right);
  for (size_t i = 0; i < left.size(); ++i) {
    left[i] += right[i];
  }
  const size_t start = size_t(0.2 * kFs), n = size_t(kFs);
  const double in_chord[] = { 130.8128, 155.5635, 195.9977, 261.6256 };
  const double off_chord[] = { 146.8324, 174.6141, 207.6523 };
  double weakest = 1e9, strongest_off = 0.0;
  for (int i = 0; i < 4; ++i) {
    weakest = fmin(weakest, Magnitude(left, start, n, in_chord[i]));
  }
  for (int i = 0; i < 3; ++i) {
    strongest_off = fmax(strongest_off,
                         Magnitude(left, start, n, off_chord[i]));
  }
  test::Note("weakest chord tone %.2f, strongest other %.4f", weakest,
             strongest_off);
  CHECK(weakest > 30.0 * strongest_off);
  for (int v = 0; v < 4; ++v) {
    CHECK(fabs(rig.resonator->voice_hz(v) / in_chord[v] - 1.0) < 1e-3);
  }
}

TEST(resonator, decay_and_damp) {
  // DECAY is the fundamental's RT60.
  const float decays[] = { 0.25f, 1.0f, 4.0f };
  for (int k = 0; k < 3; ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
    rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_UNISON);
    rig.params[Resonator::PARAM_DAMP] = 0.3f;
    rig.params[Resonator::PARAM_DECAY] = sidefx::ExpUnmap(decays[k], 0.05f,
                                                          10.0f);
    std::vector<float> left;
    const double t_b = 0.1 + 0.5 * decays[k];
    rig.Record(float(t_b) + 0.2f, 0.0f, 1.0f, &left, NULL);
    const double rt60 = Rt60(left, 130.8128, 0.1, t_b);
    test::Note("DECAY %.2f s: RT60 %.3f s", decays[k], rt60);
    CHECK(rt60 > 0.5 * decays[k] && rt60 < 2.0 * decays[k]);
    CHECK(fabs(rt60 / decays[k] - 1.0) < 0.2);
  }

  // More DAMP: the 5th harmonic dies sooner relative to the fundamental.
  double ratio[2];
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
    rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_UNISON);
    rig.params[Resonator::PARAM_DECAY] = 0.8f;
    rig.params[Resonator::PARAM_DAMP] = k ? 0.8f : 0.2f;
    std::vector<float> left;
    rig.Record(0.6f, 0.0f, 1.0f, &left, NULL);
    const size_t start = size_t(0.2 * kFs), n = size_t(0.3 * kFs);
    ratio[k] = Magnitude(left, start, n, 5.0 * 130.8128) /
        Magnitude(left, start, n, 130.8128);
  }
  test::Note("5th harmonic / fundamental: DAMP 0.2 %.3f, DAMP 0.8 %.5f",
             ratio[0], ratio[1]);
  CHECK(ratio[1] < 0.1 * ratio[0]);
}

TEST(resonator, drive_and_spread) {
  // DRIVE saturates the loop: a sine at the root gains a 3rd harmonic.
  // Short decay and some damping, measured late: what rings is the
  // sine's own resonance, not the onset's overtones. A quiet sine, so the
  // loop stays below DRIVE 0's soft ceiling.
  double h3[2];
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
    rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_UNISON);
    rig.params[Resonator::PARAM_DECAY] = sidefx::ExpUnmap(0.3f, 0.05f, 10.0f);
    rig.params[Resonator::PARAM_DAMP] = 0.3f;
    rig.params[Resonator::PARAM_DRIVE] = float(k);
    std::vector<float> left;
    rig.Record(2.0f, 130.8128f, 0.05f, &left, NULL);
    const size_t start = size_t(1.5 * kFs), n = size_t(0.4 * kFs);
    h3[k] = Magnitude(left, start, n, 3.0 * 130.8128) /
        Magnitude(left, start, n, 130.8128);
  }
  test::Note("3rd harmonic / fundamental: DRIVE 0 %.5f, DRIVE 1 %.4f",
             h3[0], h3[1]);
  CHECK(h3[1] > 10.0 * h3[0]);
  CHECK(h3[1] > 0.01);

  // SPREAD 0: mono in, mono out. SPREAD 1: the root (voice 0) far left,
  // the fifth (voice 1) far right.
  for (int k = 0; k < 2; ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
    rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_FIFTHS);
    rig.params[Resonator::PARAM_SPREAD] = float(k);
    std::vector<float> left, right;
    rig.Record(0.6f, 0.0f, 1.0f, &left, &right);
    double diff = 0.0;
    for (size_t i = 0; i < left.size(); ++i) {
      diff = fmax(diff, fabs(left[i] - right[i]));
    }
    const size_t start = size_t(0.1 * kFs), n = size_t(0.4 * kFs);
    const double root = Magnitude(left, start, n, 130.8128) /
        Magnitude(right, start, n, 130.8128);
    const double fifth = Magnitude(right, start, n, 195.9977) /
        Magnitude(left, start, n, 195.9977);
    test::Note("SPREAD %d: root L/R %.2f, fifth R/L %.2f", k, root, fifth);
    if (k) {
      CHECK(root > 10.0 && fifth > 10.0);
    } else {
      CHECK(diff == 0.0);
    }
  }
}

TEST(resonator, no_clicks) {
  // A 220 Hz sine while PITCH jumps two octaves and CHORD changes every
  // 100 ms: no step much above the steady ones.
  Rig rig;
  rig.params[Resonator::PARAM_DECAY] = 0.3f;
  rig.params[Resonator::PARAM_DAMP] = 0.4f;
  float steady = 0.0f, jumping = 0.0f;
  for (int pass = 0; pass < 3; ++pass) {
    rig.resonator->Reset();
    float phase = 0.0f, last = 0.0f;
    for (int b = 0; b < int(3.0f * kFs / kBlock); ++b) {
      const int setting = (b / 150) & 1;
      const int use = pass == 2 ? setting : pass;
      rig.params[Resonator::PARAM_PITCH] = use ? Pitch(12.0f) : Pitch(-12.0f);
      rig.params[Resonator::PARAM_CHORD] = use ?
          Chord(Resonator::CHORD_CLUSTER) : Chord(Resonator::CHORD_FIFTHS);
      Frame in[kBlock], out[kBlock];
      for (size_t i = 0; i < kBlock; ++i) {
        in[i].l = in[i].r = 0.3f * sinf(6.2831853f * phase);
        phase += 220.0f / kFs;
        if (phase >= 1.0f) phase -= 1.0f;
      }
      rig.Process(in, out);
      for (size_t i = 0; i < kBlock; ++i) {
        const float step = fabsf(out[i].l - last);
        last = out[i].l;
        if (b > 300) {
          if (pass < 2) {
            steady = fmaxf(steady, step);
          } else {
            jumping = fmaxf(jumping, step);
          }
        }
      }
    }
  }
  test::Note("largest step: steady %.4f, jumping %.4f", steady, jumping);
  // Not 1: sliding the loop up two octaves plays what rings in it faster
  // (up to the 4:1 of the slide, as a retuned string would), so its slope
  // rises for the few tens of ms of the slide. A click (a jump in the
  // loop's read position) would be tens of times the steady step.
  CHECK(jumping < 4.0f * steady);
}

TEST(resonator, format) {
  Rig rig;
  for (int sync = 0; sync < 2; ++sync) {
    rig.context.sync_mask = sync ? 0xffff : 0;
    for (int p = 0; p < Resonator::NUM_PARAMS; ++p) {
      for (int v = 0; v <= 2; ++v) {
        char text[32];
        memset(text, 'x', sizeof(text));
        rig.resonator->Format(p, 0.5f * float(v), rig.context, text, 11);
        const size_t n = strlen(text);
        test::Note("%d %.1f %s: %s", p, 0.5f * float(v),
                   sync ? "synced" : "free", text);
        CHECK(n > 0 && n <= 10);
      }
    }
  }
  char text[16];
  rig.context.sync_mask = 0;
  rig.resonator->Format(Resonator::PARAM_PITCH, Pitch(7.0f), rig.context,
                        text, 16);
  CHECK(strcmp(text, "G3 +7st") == 0);
  rig.resonator->Format(Resonator::PARAM_PITCH, Pitch(-23.0f), rig.context,
                        text, 16);
  CHECK(strcmp(text, "C#1 -23st") == 0);
  rig.resonator->Format(Resonator::PARAM_CHORD, 1.0f, rig.context, text, 16);
  CHECK(strcmp(text, "CLUSTER") == 0);
  // A 4-byte buffer still ends in a zero.
  rig.resonator->Format(Resonator::PARAM_PITCH, Pitch(-23.0f), rig.context,
                        text, 4);
  CHECK(strlen(text) <= 3);
}

TEST(resonator, synced_decay) {
  // DECAY synced to 1/4: RT60 = one beat, so it halves at double tempo.
  const float quarter = sidefx::StepValue(11, sidefx::kNumNoteValues);
  double rt60[2];
  for (int t = 0; t < 2; ++t) {
    Rig rig;
    const float beat = t ? 0.25f : 0.5f;
    rig.context.beat_seconds = beat;
    rig.context.sync_mask = 1 << Resonator::PARAM_DECAY;
    rig.params[Resonator::PARAM_DECAY] = quarter;
    rig.params[Resonator::PARAM_PITCH] = Pitch(0.0f);
    rig.params[Resonator::PARAM_CHORD] = Chord(Resonator::CHORD_UNISON);
    rig.params[Resonator::PARAM_DAMP] = 0.3f;
    std::vector<float> left;
    const double t_b = 0.1 + 0.5 * beat;
    rig.Record(float(t_b) + 0.2f, 0.0f, 1.0f, &left, NULL);
    rt60[t] = Rt60(left, 130.8128, 0.1, t_b);
    test::Note("beat %.2f s: RT60 %.3f s", beat, rt60[t]);
    CHECK(fabs(rt60[t] / beat - 1.0) < 0.25);
  }
  CHECK(rt60[0] / rt60[1] > 1.6 && rt60[0] / rt60[1] < 2.5);
  char text[16];
  ProcessContext c = test::Context(test::Tempo120(),
                                   1 << Resonator::PARAM_DECAY);
  Rig rig;
  rig.resonator->Format(Resonator::PARAM_DECAY, quarter, c, text, 16);
  CHECK(strcmp(text, "1/4") == 0);
}

TEST(resonator, decay_holds_with_damp_and_high_voices) {
  // DECAY is the fundamental's RT60 whatever DAMP does to the overtones,
  // and for the highest voices too (10 s: the top of the knob). The 2 kHz
  // voice is measured late: OCTAVES' lower voices have overtones on it
  // too, which die sooner.
  struct Case {
    float semitones;
    int chord;
    float damp;
    double hz;
    double from;
  };
  const Case cases[] = {
    { 0.0f, Resonator::CHORD_UNISON, 0.0f, 130.8128, 0.2 },
    { 0.0f, Resonator::CHORD_UNISON, 0.8f, 130.8128, 0.2 },
    { 0.0f, Resonator::CHORD_UNISON, 1.0f, 130.8128, 0.2 },
    { 24.0f, Resonator::CHORD_UNISON, 1.0f, 523.2511, 0.2 },
    { 24.0f, Resonator::CHORD_OCTAVES, 0.0f, 2093.0045, 3.0 },
    { 24.0f, Resonator::CHORD_OCTAVES, 0.5f, 2093.0045, 3.0 },
  };
  for (size_t k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
    Rig rig;
    rig.params[Resonator::PARAM_PITCH] = Pitch(cases[k].semitones);
    rig.params[Resonator::PARAM_CHORD] = Chord(cases[k].chord);
    rig.params[Resonator::PARAM_DAMP] = cases[k].damp;
    rig.params[Resonator::PARAM_DECAY] = 1.0f;
    rig.params[Resonator::PARAM_DRIVE] = 0.0f;
    std::vector<float> left, right;
    rig.Record(float(cases[k].from) + 2.3f, 0.0f, 1.0f, &left, &right);
    for (size_t i = 0; i < left.size(); ++i) {
      left[i] += right[i];
    }
    const double rt60 = Rt60(left, cases[k].hz, cases[k].from,
                             cases[k].from + 2.0);
    test::Note("%.1f Hz, DAMP %.1f: RT60 %.2f s (DECAY 10 s)", cases[k].hz,
               cases[k].damp, rt60);
    CHECK(fabs(rt60 / 10.0 - 1.0) < 0.2);
  }
}

TEST(resonator, synced_decay_shows_the_clamped_time) {
  // A note value DECAY cannot ring (over 10 s, under 50 ms) shows the time
  // it rings instead.
  Rig rig;
  char text[16];
  int bars4 = -1, sixtyfourth = -1;
  for (int i = 0; i < sidefx::kNumNoteValues; ++i) {
    if (!strcmp(sidefx::kNoteValues[i].label, "4 BAR")) bars4 = i;
    if (!strcmp(sidefx::kNoteValues[i].label, "1/64")) sixtyfourth = i;
  }
  CHECK(bars4 >= 0 && sixtyfourth >= 0);
  ProcessContext c = test::Context(test::Tempo120(),
                                   1 << Resonator::PARAM_DECAY);
  const float four_bars = sidefx::StepValue(bars4, sidefx::kNumNoteValues);
  const float short_note = sidefx::StepValue(sixtyfourth,
                                             sidefx::kNumNoteValues);
  c.beat_seconds = 0.5f;  // 120 BPM: 4 bars = 8 s, fits
  rig.resonator->Format(Resonator::PARAM_DECAY, four_bars, c, text, 16);
  CHECK(strcmp(text, "4 BAR") == 0);
  c.beat_seconds = 60.0f / 90.0f;  // 90 BPM: 10.7 s, rings 10 s
  rig.resonator->Format(Resonator::PARAM_DECAY, four_bars, c, text, 16);
  test::Note("4 BAR at 90 BPM: \"%s\"", text);
  CHECK(strcmp(text, "10.0s") == 0);
  c.beat_seconds = 0.25f;  // 240 BPM: 1/64 = 15.6 ms, rings 50 ms
  rig.resonator->Format(Resonator::PARAM_DECAY, short_note, c, text, 16);
  test::Note("1/64 at 240 BPM: \"%s\"", text);
  CHECK(strcmp(text, "50ms") == 0);
}
