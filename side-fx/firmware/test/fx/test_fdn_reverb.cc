// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: FDN VERB.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"
#include "fx/fdn_reverb.h"

namespace {

using sidefx::FdnReverb;
using sidefx::Frame;

const float kFs = 48014.32f;

struct Rig {
  test::TestMemory memory;
  FdnReverb* fdn;
  bool ok;
  sidefx::ProcessContext context;
  float params[sidefx::kMaxBlockParams];

  Rig() : memory(8u << 20, 64u << 10), fdn(NULL), ok(false) {
    fdn = memory.internal().Create<FdnReverb>();
    ok = fdn && fdn->Init(memory.memory());
    context = test::Context(test::Tempo120(), 0);
    const sidefx::BlockInfo& info = fdn->info();
    for (int i = 0; i < info.num_params; ++i) {
      params[i] = info.params[i].default_value;
    }
    if (ok) {
      fdn->Reset();
    }
  }

  // n: a multiple of kBlockSize.
  void Run(const Frame* in, Frame* out, size_t n) {
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      fdn->Process(context, params, in + i, out + i, sidefx::kBlockSize);
    }
  }
};

size_t Samples(float seconds) {
  return size_t(seconds * kFs) / sidefx::kBlockSize * sidefx::kBlockSize;
}

double Energy(const std::vector<Frame>& x, float from, float to) {
  double sum = 0.0;
  for (size_t i = size_t(from * kFs); i < size_t(to * kFs) && i < x.size();
       ++i) {
    sum += double(x[i].l) * x[i].l + double(x[i].r) * x[i].r;
  }
  return sum;
}

// T20 * 3 of the impulse response's Schroeder decay curve.
float MeasureRt60(const std::vector<Frame>& response) {
  std::vector<double> energy(response.size() + 1, 0.0);
  for (size_t i = response.size(); i-- > 0; ) {
    const Frame& f = response[i];
    energy[i] = energy[i + 1] + double(f.l) * f.l + double(f.r) * f.r;
  }
  size_t t5 = 0;
  size_t t25 = 0;
  for (size_t i = 0; i < response.size(); ++i) {
    const double db = 10.0 * log10(energy[i] / energy[0] + 1e-30);
    if (!t5 && db < -5.0) {
      t5 = i;
    }
    if (db < -25.0) {
      t25 = i;
      break;
    }
  }
  return t25 ? 3.0f * float(t25 - t5) / kFs : 1e9f;
}

std::vector<Frame> ImpulseResponse(Rig* rig, float seconds) {
  const size_t n = Samples(seconds);
  std::vector<Frame> in(n, sidefx::MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(n);
  in[0] = sidefx::MakeFrame(1.0f, 1.0f);
  rig->Run(in.data(), out.data(), n);
  return out;
}

TEST(fdn_reverb, init_and_silence) {
  test::TestMemory memory(8u << 20, 64u << 10);
  FdnReverb* fdn = memory.internal().Create<FdnReverb>();
  CHECK(fdn != NULL);
  CHECK(fdn->Init(memory.memory()));
  test::Note("external %u bytes, internal %u bytes",
             unsigned(memory.external().used()),
             unsigned(memory.internal().used()));
  CHECK(memory.external().used() <= (4u << 20));
  CHECK(sizeof(FdnReverb) < 8192);
  sidefx::ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[sidefx::kMaxBlockParams];
  for (int i = 0; i < fdn->info().num_params; ++i) {
    params[i] = fdn->info().params[i].default_value;
  }
  Frame in[sidefx::kBlockSize];
  Frame out[sidefx::kBlockSize];
  uint32_t seed = 1;
  for (int b = 0; b < 2000; ++b) {
    for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
      in[i] = sidefx::MakeFrame(test::Noise(&seed), test::Noise(&seed));
    }
    fdn->Process(context, params, in, out, sidefx::kBlockSize);
  }
  fdn->Reset();
  memset(in, 0, sizeof(in));
  bool silent = true;
  for (int b = 0; b < 3000; ++b) {
    fdn->Process(context, params, in, out, sidefx::kBlockSize);
    for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);

  test::TestMemory small(256u << 10, 64u << 10);
  FdnReverb* starved = small.internal().Create<FdnReverb>();
  CHECK(!starved->Init(small.memory()));
}

TEST(fdn_reverb, stability) {
  Rig rig;
  CHECK(rig.ok);
  Frame in[sidefx::kBlockSize];
  Frame out[sidefx::kBlockSize];
  uint32_t seed = 7;
  uint32_t param_seed = 99;
  const int num_params = rig.fdn->info().num_params;
  // Pass 0: random parameters every block; 1: all at 0; 2: all at 1
  // (frozen); 3: all at 1 with +-4 input; 4: just under the freeze (60 s)
  // with +-4 input.
  for (int pass = 0; pass < 5; ++pass) {
    rig.fdn->Reset();
    float peak = 0.0f;
    bool finite = true;
    const float level = pass >= 3 ? 4.0f : 1.0f;
    for (size_t b = 0; b < Samples(20.0f) / sidefx::kBlockSize; ++b) {
      for (int p = 0; p < num_params; ++p) {
        rig.params[p] = pass == 0 ? 0.5f * (test::Noise(&param_seed) + 1.0f)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      if (pass == 4) {
        rig.params[FdnReverb::PARAM_DECAY] = 0.98f;
      }
      rig.context.sync_mask = pass == 0 && (b & 64) ? 0xffff : 0;
      for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
        in[i] = sidefx::MakeFrame(level * test::Noise(&seed),
                                  level * test::Noise(&seed));
      }
      rig.fdn->Process(rig.context, rig.params, in, out, sidefx::kBlockSize);
      for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
        finite = finite && test::Finite(out[i]);
        peak = fmaxf(peak, fmaxf(fabsf(out[i].l), fabsf(out[i].r)));
      }
    }
    test::Note("pass %d peak %.3f", pass, peak);
    CHECK(finite);
    CHECK(peak < 4.0f);
  }
}

TEST(fdn_reverb, rt60_follows_decay) {
  const float values[] = { 0.2f, 0.45f, 0.65f };
  for (size_t v = 0; v < sizeof(values) / sizeof(values[0]); ++v) {
    Rig rig;
    rig.params[FdnReverb::PARAM_DECAY] = values[v];
    rig.params[FdnReverb::PARAM_DAMP] = 0.0f;
    rig.params[FdnReverb::PARAM_LOWCUT] = 0.0f;
    const float expected = FdnReverb::Rt60(values[v]);
    std::vector<Frame> response =
        ImpulseResponse(&rig, 1.5f * expected + 1.0f);
    const float measured = MeasureRt60(response);
    test::Note("DECAY %.2f: RT60 expected %.2f s, measured %.2f s",
               values[v], expected, measured);
    CHECK(measured > 0.5f * expected && measured < 2.0f * expected);
  }
}

TEST(fdn_reverb, freeze_holds_and_closes_the_input) {
  Rig rig;
  rig.params[FdnReverb::PARAM_DECAY] = 0.5f;
  rig.params[FdnReverb::PARAM_DAMP] = 0.6f;
  const size_t n = Samples(12.0f);
  std::vector<Frame> in(n), out(n);
  // A noise burst for the first second, a gap, then louder noise that
  // the frozen reverb must not take in.
  uint32_t seed = 3;
  for (size_t i = 0; i < n; ++i) {
    const float level = i < Samples(1.0f) ? 0.5f : (i < Samples(1.1f) ? 0.0f
        : 2.0f);
    in[i] = sidefx::MakeFrame(level * test::Noise(&seed),
                              level * test::Noise(&seed));
  }
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    if (i == Samples(1.0f)) {
      rig.params[FdnReverb::PARAM_DECAY] = 1.0f;
    }
    rig.fdn->Process(rig.context, rig.params, &in[i], &out[i],
                     sidefx::kBlockSize);
  }
  // Broadband, and below about 3 kHz (two one-pole lowpasses): the
  // loop is lossless (freeze_keeps_every_band checks each band).
  std::vector<Frame> low(out);
  float a = 0.0f, b = 0.0f, c = 0.0f, d = 0.0f;
  const float coefficient = 1.0f - expf(-2.0f * 3.14159265f * 3000.0f / kFs);
  for (size_t i = 0; i < n; ++i) {
    a += coefficient * (out[i].l - a);
    b += coefficient * (a - b);
    c += coefficient * (out[i].r - c);
    d += coefficient * (c - d);
    low[i] = sidefx::MakeFrame(b, d);
  }
  const double change = 10.0 * log10(Energy(out, 10.0f, 11.0f) /
                                     Energy(out, 2.0f, 3.0f));
  const double low_change = 10.0 * log10(Energy(low, 10.0f, 11.0f) /
                                         Energy(low, 2.0f, 3.0f));
  test::Note("frozen, louder input meanwhile: %.2f dB from 2-3 s to "
             "10-11 s, %.2f dB below 3 kHz", change, low_change);
  CHECK(fabs(low_change) < 1.5);
  CHECK(change > -1.5 && change < 1.5);
  CHECK(Energy(out, 2.0f, 3.0f) > 1.0);
}

TEST(fdn_reverb, onset_at_predelay_and_width) {
  Rig rig;
  rig.params[FdnReverb::PARAM_PREDELAY] = 0.8f;
  rig.params[FdnReverb::PARAM_SIZE] = 0.5f;  // SIZE 1
  rig.params[FdnReverb::PARAM_MOD] = 0.0f;
  const float predelay = FdnReverb::PredelaySeconds(0.8f, rig.context);
  std::vector<Frame> response = ImpulseResponse(&rig, 2.0f);
  size_t onset_l = 0;
  size_t onset_r = 0;
  for (size_t i = 0; i < response.size(); ++i) {
    if (!onset_l && fabsf(response[i].l) > 1e-6f) onset_l = i;
    if (!onset_r && fabsf(response[i].r) > 1e-6f) onset_r = i;
  }
  // The shortest left line is 1693 samples, the shortest right 2063, but
  // with WIDTH 100 % each side hears both: the left line comes first.
  const float expected = predelay + 1693.0f / kFs;
  test::Note("predelay %.1f ms: onset L %.2f ms R %.2f ms (expected %.2f)",
             predelay * 1000.0f, onset_l / kFs * 1000.0f,
             onset_r / kFs * 1000.0f, expected * 1000.0f);
  CHECK(fabsf(onset_l / kFs - expected) < 0.001f);

  double ll = 0.0, rr = 0.0, lr = 0.0;
  for (size_t i = size_t(0.2f * kFs); i < response.size(); ++i) {
    ll += response[i].l * response[i].l;
    rr += response[i].r * response[i].r;
    lr += response[i].l * response[i].r;
  }
  const double correlation = lr / sqrt(ll * rr);
  test::Note("WIDTH 100%%: L/R correlation of the tail %.3f", correlation);
  CHECK(fabs(correlation) < 0.5);

  Rig mono;
  mono.params[FdnReverb::PARAM_WIDTH] = 0.0f;
  response = ImpulseResponse(&mono, 1.0f);
  bool same = true;
  for (size_t i = 0; i < response.size(); ++i) {
    same = same && response[i].l == response[i].r;
  }
  CHECK(same);
}

int ZeroCrossings(const std::vector<Frame>& x, float from, float to) {
  int n = 0;
  for (size_t i = size_t(from * kFs) + 1; i < size_t(to * kFs) &&
       i < x.size(); ++i) {
    n += (x[i].l >= 0.0f) != (x[i - 1].l >= 0.0f);
  }
  return n;
}

TEST(fdn_reverb, damp_darkens_and_lowcut_thins) {
  int crossings[2];
  for (int d = 0; d < 2; ++d) {
    Rig rig;
    rig.params[FdnReverb::PARAM_DECAY] = 0.6f;
    rig.params[FdnReverb::PARAM_DAMP] = d ? 1.0f : 0.0f;
    std::vector<Frame> response = ImpulseResponse(&rig, 1.6f);
    crossings[d] = ZeroCrossings(response, 0.5f, 1.5f);
  }
  test::Note("zero crossings per second: DAMP 0 %d, DAMP 1 %d",
             crossings[0], crossings[1]);
  CHECK(crossings[1] < crossings[0] / 2);

  float rms[2];
  double input_energy = 0.0;
  for (int c = 0; c < 2; ++c) {
    Rig rig;
    rig.params[FdnReverb::PARAM_LOWCUT] = c ? 1.0f : 0.0f;
    const size_t n = Samples(3.0f);
    std::vector<Frame> in(n), out(n);
    for (size_t i = 0; i < n; ++i) {
      const float s = 0.5f * sinf(2.0f * 3.14159265f * 60.0f * i / kFs);
      in[i] = sidefx::MakeFrame(s, s);
    }
    rig.Run(in.data(), out.data(), n);
    double sum = 0.0;
    input_energy = 0.0;
    for (size_t i = n / 2; i < n; ++i) {
      sum += out[i].l * out[i].l;
      input_energy += in[i].l * in[i].l;
    }
    rms[c] = float(sqrt(sum / (n / 2)));
  }
  test::Note("60 Hz wet rms (input %.3f): LOWCUT 0 %.4f, LOWCUT 1 %.4f",
             sqrt(input_energy / (Samples(3.0f) / 2)), rms[0], rms[1]);
  CHECK(rms[1] < 0.1f * rms[0]);
}

// The largest sample-to-sample step after `jump` against before it, with a
// sine in and `change` applied at the jump.
void StepsAroundJump(Rig* rig, void (*change)(float* params), float* normal,
                     float* jumped) {
  const size_t n = Samples(8.0f);
  std::vector<Frame> in(n), out(n);
  for (size_t i = 0; i < n; ++i) {
    const float s = 0.5f * sinf(2.0f * 3.14159265f * 330.0f * i / kFs);
    in[i] = sidefx::MakeFrame(s, s);
  }
  *normal = 0.0f;
  *jumped = 0.0f;
  const size_t settle = Samples(3.0f);
  const size_t jump = Samples(5.0f);
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    if (i == jump) {
      change(rig->params);
    }
    rig->fdn->Process(rig->context, rig->params, &in[i], &out[i],
                      sidefx::kBlockSize);
    for (size_t j = i; j < i + sidefx::kBlockSize; ++j) {
      if (j < settle) continue;
      const float step = fmaxf(fabsf(out[j].l - out[j - 1].l),
                               fabsf(out[j].r - out[j - 1].r));
      if (j < jump) {
        *normal = fmaxf(*normal, step);
      } else {
        *jumped = fmaxf(*jumped, step);
      }
    }
  }
}

void JumpSizeAndPredelay(float* params) {
  params[FdnReverb::PARAM_SIZE] = 0.95f;
  params[FdnReverb::PARAM_PREDELAY] = 0.9f;
}

void JumpToFreeze(float* params) {
  params[FdnReverb::PARAM_DECAY] = 1.0f;
}

TEST(fdn_reverb, no_clicks) {
  {
    Rig rig;
    rig.params[FdnReverb::PARAM_SIZE] = 0.1f;
    rig.params[FdnReverb::PARAM_PREDELAY] = 0.2f;
    float normal, jumped;
    StepsAroundJump(&rig, JumpSizeAndPredelay, &normal, &jumped);
    test::Note("SIZE + PREDELAY jump: steady %.4f, after %.4f", normal,
               jumped);
    CHECK(normal > 0.0f);
    CHECK(jumped < 3.0f * normal);
  }
  {
    Rig rig;
    rig.params[FdnReverb::PARAM_DECAY] = 0.5f;
    float normal, jumped;
    StepsAroundJump(&rig, JumpToFreeze, &normal, &jumped);
    test::Note("into FREEZE: steady %.4f, after %.4f", normal, jumped);
    CHECK(jumped < 3.0f * normal);
  }
}

TEST(fdn_reverb, format) {
  Rig rig;
  const sidefx::BlockInfo& info = rig.fdn->info();
  CHECK(strlen(info.name) <= 10);
  CHECK(strlen(info.short_name) <= 5);
  CHECK(info.num_params <= 7);
  const float values[] = { 0.0f, 0.5f, 1.0f };
  for (int p = 0; p < info.num_params; ++p) {
    CHECK(strlen(info.params[p].name) <= 8);
    for (int synced = 0; synced < 2; ++synced) {
      rig.context.sync_mask = synced ? 0xffff : 0;
      for (int v = 0; v < 3; ++v) {
        char text[32];
        memset(text, 'x', sizeof(text));
        rig.fdn->Format(p, values[v], rig.context, text, 11);
        test::Note("%s %.1f%s: '%s'", info.params[p].name, values[v],
                   synced ? " synced" : "", text);
        CHECK(strlen(text) > 0 && strlen(text) <= 10);
      }
    }
  }
}

TEST(fdn_reverb, synced_predelay_follows_tempo) {
  float eighth = -1.0f;
  for (int i = 0; i <= 1000; ++i) {
    const float v = i / 1000.0f;
    if (sidefx::kNoteValues[sidefx::NoteValueIndex(v)].beats == 0.5f) {
      eighth = v;
      break;
    }
  }
  CHECK(eighth >= 0.0f);
  const float beats[] = { 0.5f, 0.3f };
  for (int b = 0; b < 2; ++b) {
    Rig rig;
    rig.context.sync_mask = 1 << FdnReverb::PARAM_PREDELAY;
    rig.context.beat_seconds = beats[b];
    rig.params[FdnReverb::PARAM_PREDELAY] = eighth;
    rig.params[FdnReverb::PARAM_SIZE] = 0.5f;
    rig.params[FdnReverb::PARAM_MOD] = 0.0f;
    std::vector<Frame> response = ImpulseResponse(&rig, 1.0f);
    size_t onset = 0;
    for (size_t i = 0; i < response.size() && !onset; ++i) {
      if (fabsf(response[i].l) > 1e-6f) onset = i;
    }
    const float expected = 0.5f * beats[b] + 1693.0f / kFs;
    test::Note("beat %.2f s: onset %.2f ms, expected %.2f ms", beats[b],
               onset / kFs * 1000.0f, expected * 1000.0f);
    CHECK(fabsf(onset / kFs - expected) < 0.001f);
  }
}

}  // namespace

namespace {

// In place, radix 2, n a power of two.
void Fft(std::vector<double>* re, std::vector<double>* im) {
  const size_t n = re->size();
  for (size_t i = 1, j = 0; i < n; ++i) {
    size_t bit = n >> 1;
    for (; j & bit; bit >>= 1) {
      j ^= bit;
    }
    j ^= bit;
    if (i < j) {
      std::swap((*re)[i], (*re)[j]);
      std::swap((*im)[i], (*im)[j]);
    }
  }
  for (size_t length = 2; length <= n; length <<= 1) {
    const double angle = -2.0 * M_PI / double(length);
    for (size_t i = 0; i < n; i += length) {
      for (size_t k = 0; k < length / 2; ++k) {
        const double wr = cos(angle * double(k));
        const double wi = sin(angle * double(k));
        const size_t a = i + k;
        const size_t b = a + length / 2;
        const double tr = (*re)[b] * wr - (*im)[b] * wi;
        const double ti = (*re)[b] * wi + (*im)[b] * wr;
        (*re)[b] = (*re)[a] - tr;
        (*im)[b] = (*im)[a] - ti;
        (*re)[a] += tr;
        (*im)[a] += ti;
      }
    }
  }
}

// The energy of both channels between lo and hi Hz over one second from
// `from` (Hann windows of 4096, hopped by half).
double BandEnergy(const std::vector<Frame>& x, float from, float lo,
                  float hi) {
  const size_t n = 4096;
  double sum = 0.0;
  for (size_t start = size_t(from * kFs);
       start + n <= size_t((from + 1.0f) * kFs) && start + n <= x.size();
       start += n / 2) {
    for (int side = 0; side < 2; ++side) {
      std::vector<double> re(n), im(n, 0.0);
      for (size_t i = 0; i < n; ++i) {
        const double w = 0.5 - 0.5 * cos(2.0 * M_PI * double(i) / double(n));
        re[i] = w * (side ? x[start + i].r : x[start + i].l);
      }
      Fft(&re, &im);
      for (size_t k = size_t(lo * n / kFs); k <= size_t(hi * n / kFs); ++k) {
        sum += re[k] * re[k] + im[k] * im[k];
      }
    }
  }
  return sum + 1e-30;
}

}  // namespace

TEST(fdn_reverb, freeze_keeps_every_band) {
  // Frozen at DAMP 0 the loop is lossless: the highs of a frozen wash stay
  // as long as the mids, with and without MOD (each line's fractional,
  // gliding length must not filter the loop).
  const float mods[] = { 0.0f, 0.4f, 1.0f };
  for (size_t m = 0; m < sizeof(mods) / sizeof(mods[0]); ++m) {
    Rig rig;
    rig.params[FdnReverb::PARAM_DECAY] = 0.97f;
    rig.params[FdnReverb::PARAM_DAMP] = 0.0f;
    rig.params[FdnReverb::PARAM_LOWCUT] = 0.0f;
    rig.params[FdnReverb::PARAM_MOD] = mods[m];
    const size_t n = Samples(19.0f);
    std::vector<Frame> in(n, sidefx::MakeFrame(0.0f, 0.0f)), out(n);
    uint32_t seed = 5;
    for (size_t i = 0; i < Samples(1.0f); ++i) {
      in[i] = sidefx::MakeFrame(0.2f * test::Noise(&seed),
                                0.2f * test::Noise(&seed));
    }
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      if (i == Samples(1.0f)) {
        rig.params[FdnReverb::PARAM_DECAY] = 1.0f;
      }
      rig.fdn->Process(rig.context, rig.params, &in[i], &out[i],
                       sidefx::kBlockSize);
    }
    const float bands[][2] = {
      { 20.0f, 60.0f }, { 200.0f, 1000.0f }, { 4000.0f, 8000.0f },
      { 8000.0f, 12000.0f }, { 12000.0f, 18000.0f },
    };
    for (size_t b = 0; b < sizeof(bands) / sizeof(bands[0]); ++b) {
      const double change = 10.0 * log10(
          BandEnergy(out, 17.0f, bands[b][0], bands[b][1]) /
          BandEnergy(out, 2.0f, bands[b][0], bands[b][1]));
      test::Note("MOD %.1f, %5.0f-%5.0f Hz: %+.2f dB from 2 s to 17 s",
                 mods[m], bands[b][0], bands[b][1], change);
      // Full MOD moves the read heads fast enough that the interpolator's
      // integer steps trade a little of the very top for the mids.
      CHECK(fabs(change) < (mods[m] < 0.5f ? 1.0 : 2.0));
    }
  }
}

TEST(fdn_reverb, damp_0_decays_every_band_alike) {
  // Below the freeze, DAMP 0 gives every band the RT60 DECAY shows.
  Rig rig;
  rig.params[FdnReverb::PARAM_DECAY] = 0.6f;
  rig.params[FdnReverb::PARAM_DAMP] = 0.0f;
  rig.params[FdnReverb::PARAM_LOWCUT] = 0.0f;
  rig.params[FdnReverb::PARAM_MOD] = 0.4f;
  const float rt60 = FdnReverb::Rt60(0.6f);
  const size_t n = Samples(6.0f);
  std::vector<Frame> in(n, sidefx::MakeFrame(0.0f, 0.0f)), out(n);
  uint32_t seed = 9;
  for (size_t i = 0; i < Samples(0.5f); ++i) {
    in[i] = sidefx::MakeFrame(0.2f * test::Noise(&seed),
                              0.2f * test::Noise(&seed));
  }
  rig.Run(in.data(), out.data(), n);
  const float expected = -60.0f * 3.0f / rt60;
  const float bands[][2] = {
    { 200.0f, 1000.0f }, { 4000.0f, 8000.0f }, { 8000.0f, 12000.0f },
    { 12000.0f, 18000.0f },
  };
  for (size_t b = 0; b < sizeof(bands) / sizeof(bands[0]); ++b) {
    const double change = 10.0 * log10(
        BandEnergy(out, 4.5f, bands[b][0], bands[b][1]) /
        BandEnergy(out, 1.5f, bands[b][0], bands[b][1]));
    test::Note("RT60 %.1f s, %5.0f-%5.0f Hz: %+.1f dB in 3 s (expected "
               "%+.1f)", rt60, bands[b][0], bands[b][1], change, expected);
    CHECK(fabs(change - expected) < 3.0);
  }
}
