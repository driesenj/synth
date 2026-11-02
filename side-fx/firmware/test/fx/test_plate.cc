// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: PLATE.

#include <math.h>
#include <string.h>

#include <vector>

#include "check.h"
#include "test_support.h"
#include "fx/plate.h"

namespace {

using sidefx::Frame;
using sidefx::Plate;

const float kFs = 48014.32f;
const float kLengthScale = 48014.32f / 29761.0f;

struct Rig {
  test::TestMemory memory;
  Plate* plate;
  bool ok;
  sidefx::ProcessContext context;
  float params[sidefx::kMaxBlockParams];

  Rig() : memory(8u << 20, 64u << 10), plate(NULL), ok(false) {
    plate = memory.internal().Create<Plate>();
    ok = plate && plate->Init(memory.memory());
    context = test::Context(test::Tempo120(), 0);
    const sidefx::BlockInfo& info = plate->info();
    for (int i = 0; i < info.num_params; ++i) {
      params[i] = info.params[i].default_value;
    }
    if (ok) {
      plate->Reset();
    }
  }

  // n: a multiple of kBlockSize.
  void Run(const Frame* in, Frame* out, size_t n) {
    for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
      plate->Process(context, params, in + i, out + i, sidefx::kBlockSize);
    }
  }
};

size_t Blocks(float seconds) {
  return size_t(seconds * kFs) / sidefx::kBlockSize;
}

// T20 * 3 of the impulse response's Schroeder decay curve (l^2 + r^2).
float MeasureRt60(const std::vector<Frame>& response) {
  std::vector<double> energy(response.size() + 1, 0.0);
  for (size_t i = response.size(); i-- > 0; ) {
    const Frame& f = response[i];
    energy[i] = energy[i + 1] + double(f.l) * f.l + double(f.r) * f.r;
  }
  const double total = energy[0];
  size_t t5 = 0;
  size_t t25 = 0;
  for (size_t i = 0; i < response.size(); ++i) {
    const double db = 10.0 * log10(energy[i] / total + 1e-30);
    if (!t5 && db < -5.0) {
      t5 = i;
    }
    if (!t25 && db < -25.0) {
      t25 = i;
      break;
    }
  }
  if (!t25) {
    return 1e9f;
  }
  return 3.0f * float(t25 - t5) / kFs;
}

std::vector<Frame> ImpulseResponse(Rig* rig, float seconds) {
  const size_t n = Blocks(seconds) * sidefx::kBlockSize;
  std::vector<Frame> in(n, sidefx::MakeFrame(0.0f, 0.0f));
  std::vector<Frame> out(n);
  in[0] = sidefx::MakeFrame(1.0f, 1.0f);
  rig->Run(in.data(), out.data(), n);
  return out;
}

TEST(plate, init_and_silence) {
  test::TestMemory memory(8u << 20, 64u << 10);
  Plate* plate = memory.internal().Create<Plate>();
  CHECK(plate != NULL);
  CHECK(plate->Init(memory.memory()));
  test::Note("external %u bytes, internal %u bytes",
             unsigned(memory.external().used()),
             unsigned(memory.internal().used()));
  CHECK(memory.external().used() <= (2u << 20));
  CHECK(sizeof(Plate) < 8192);
  // Fill it with noise, Reset, then silence must come out as exact zeros.
  sidefx::ProcessContext context = test::Context(test::Tempo120(), 0);
  float params[sidefx::kMaxBlockParams];
  for (int i = 0; i < plate->info().num_params; ++i) {
    params[i] = plate->info().params[i].default_value;
  }
  Frame in[sidefx::kBlockSize];
  Frame out[sidefx::kBlockSize];
  uint32_t seed = 1;
  for (int b = 0; b < 2000; ++b) {
    for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
      in[i] = sidefx::MakeFrame(test::Noise(&seed), test::Noise(&seed));
    }
    plate->Process(context, params, in, out, sidefx::kBlockSize);
  }
  plate->Reset();
  memset(in, 0, sizeof(in));
  bool silent = true;
  for (int b = 0; b < 3000; ++b) {
    plate->Process(context, params, in, out, sidefx::kBlockSize);
    for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
      silent = silent && out[i].l == 0.0f && out[i].r == 0.0f;
    }
  }
  CHECK(silent);

  // Too little memory: Init says so.
  test::TestMemory small(256u << 10, 64u << 10);
  Plate* starved = small.internal().Create<Plate>();
  CHECK(!starved->Init(small.memory()));
}

TEST(plate, stability) {
  Rig rig;
  CHECK(rig.ok);
  Frame in[sidefx::kBlockSize];
  Frame out[sidefx::kBlockSize];
  uint32_t seed = 7;
  uint32_t param_seed = 99;
  const int num_params = rig.plate->info().num_params;
  // Pass 0: random parameters every block; 1: all at 0; 2: all at 1
  // (maximum decay); 3: all at 1 with +-4 input.
  for (int pass = 0; pass < 4; ++pass) {
    rig.plate->Reset();
    float peak = 0.0f;
    bool finite = true;
    const float level = pass == 3 ? 4.0f : 1.0f;
    for (size_t b = 0; b < Blocks(20.0f); ++b) {
      for (int p = 0; p < num_params; ++p) {
        rig.params[p] = pass == 0 ? 0.5f * (test::Noise(&param_seed) + 1.0f)
            : (pass == 1 ? 0.0f : 1.0f);
      }
      rig.context.sync_mask = pass == 0 && (b & 64) ? 0xffff : 0;
      for (size_t i = 0; i < sidefx::kBlockSize; ++i) {
        in[i] = sidefx::MakeFrame(level * test::Noise(&seed),
                                  level * test::Noise(&seed));
      }
      rig.plate->Process(rig.context, rig.params, in, out,
                         sidefx::kBlockSize);
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

TEST(plate, rt60_follows_decay) {
  const float values[] = { 0.25f, 0.5f, 0.7f };
  for (size_t v = 0; v < sizeof(values) / sizeof(values[0]); ++v) {
    Rig rig;
    rig.params[Plate::PARAM_DECAY] = values[v];
    rig.params[Plate::PARAM_DAMP] = 0.0f;
    rig.params[Plate::PARAM_LOWCUT] = 0.0f;
    rig.params[Plate::PARAM_SIZE] = 0.5f;
    const float expected = Plate::Rt60(values[v]);
    std::vector<Frame> response = ImpulseResponse(&rig, 2.0f * expected + 1.0f);
    const float measured = MeasureRt60(response);
    test::Note("DECAY %.2f: RT60 expected %.2f s, measured %.2f s",
               values[v], expected, measured);
    CHECK(measured > 0.5f * expected && measured < 2.0f * expected);
  }
}

TEST(plate, top_of_decay_holds) {
  Rig rig;
  rig.params[Plate::PARAM_DECAY] = 1.0f;
  rig.params[Plate::PARAM_DAMP] = 0.0f;
  rig.params[Plate::PARAM_LOWCUT] = 0.0f;
  std::vector<Frame> response = ImpulseResponse(&rig, 10.0f);
  double early = 0.0;
  double late = 0.0;
  for (size_t i = size_t(1.0f * kFs); i < size_t(2.0f * kFs); ++i) {
    early += response[i].l * response[i].l + response[i].r * response[i].r;
  }
  for (size_t i = size_t(8.0f * kFs); i < size_t(9.0f * kFs); ++i) {
    late += response[i].l * response[i].l + response[i].r * response[i].r;
  }
  const double drop = 10.0 * log10(late / early);
  test::Note("DECAY 1: %.2f dB from 1-2 s to 8-9 s", drop);
  CHECK(drop > -6.0);
}

TEST(plate, onset_at_predelay_and_stereo) {
  Rig rig;
  rig.params[Plate::PARAM_PREDELAY] = 0.8f;
  rig.params[Plate::PARAM_SIZE] = 0.5f;  // SIZE 1
  const float predelay = Plate::PredelaySeconds(0.8f, rig.context);
  std::vector<Frame> response = ImpulseResponse(&rig, 2.0f);
  size_t onset_l = 0;
  size_t onset_r = 0;
  for (size_t i = 0; i < response.size(); ++i) {
    if (!onset_l && fabsf(response[i].l) > 1e-7f) onset_l = i;
    if (!onset_r && fabsf(response[i].r) > 1e-7f) onset_r = i;
  }
  // The earliest output taps: 266 (left) and 353 (right) samples at
  // 29761 Hz after the tank's first delay.
  const float expected_l = predelay + 266.0f * kLengthScale / kFs;
  const float expected_r = predelay + 353.0f * kLengthScale / kFs;
  test::Note("predelay %.1f ms: onset L %.2f ms (%.2f), R %.2f ms (%.2f)",
             predelay * 1000.0f, onset_l / kFs * 1000.0f,
             expected_l * 1000.0f, onset_r / kFs * 1000.0f,
             expected_r * 1000.0f);
  CHECK(fabsf(onset_l / kFs - expected_l) < 0.001f);
  CHECK(fabsf(onset_r / kFs - expected_r) < 0.001f);

  // The two sides are different mixes of the tank: decorrelated.
  double ll = 0.0, rr = 0.0, lr = 0.0;
  for (size_t i = size_t(0.2f * kFs); i < response.size(); ++i) {
    ll += response[i].l * response[i].l;
    rr += response[i].r * response[i].r;
    lr += response[i].l * response[i].r;
  }
  const double correlation = lr / sqrt(ll * rr);
  test::Note("L/R correlation of the tail %.3f", correlation);
  CHECK(fabs(correlation) < 0.5);
}

int ZeroCrossings(const std::vector<Frame>& x, size_t from, size_t to) {
  int n = 0;
  for (size_t i = from + 1; i < to; ++i) {
    n += (x[i].l >= 0.0f) != (x[i - 1].l >= 0.0f);
  }
  return n;
}

TEST(plate, damp_darkens_and_lowcut_thins) {
  int crossings[2];
  for (int d = 0; d < 2; ++d) {
    Rig rig;
    rig.params[Plate::PARAM_DECAY] = 0.6f;
    rig.params[Plate::PARAM_DAMP] = d ? 1.0f : 0.0f;
    std::vector<Frame> response = ImpulseResponse(&rig, 1.6f);
    crossings[d] = ZeroCrossings(response, size_t(0.5f * kFs),
                                 size_t(1.5f * kFs));
  }
  test::Note("zero crossings per second: DAMP 0 %d, DAMP 1 %d",
             crossings[0], crossings[1]);
  CHECK(crossings[1] < crossings[0] / 2);

  // A 60 Hz sine: LOWCUT at the top takes most of it away.
  float rms[2];
  for (int c = 0; c < 2; ++c) {
    Rig rig;
    rig.params[Plate::PARAM_LOWCUT] = c ? 1.0f : 0.0f;
    const size_t n = Blocks(3.0f) * sidefx::kBlockSize;
    std::vector<Frame> in(n), out(n);
    for (size_t i = 0; i < n; ++i) {
      const float s = 0.5f * sinf(2.0f * 3.14159265f * 60.0f * i / kFs);
      in[i] = sidefx::MakeFrame(s, s);
    }
    rig.Run(in.data(), out.data(), n);
    double sum = 0.0;
    for (size_t i = n / 2; i < n; ++i) {
      sum += out[i].l * out[i].l;
    }
    rms[c] = float(sqrt(sum / (n / 2)));
  }
  test::Note("60 Hz wet rms: LOWCUT 0 %.4f, LOWCUT 1 %.4f", rms[0], rms[1]);
  CHECK(rms[1] < 0.1f * rms[0]);
}

TEST(plate, no_clicks_when_size_and_predelay_jump) {
  Rig rig;
  rig.params[Plate::PARAM_DECAY] = 0.5f;
  rig.params[Plate::PARAM_SIZE] = 0.2f;
  rig.params[Plate::PARAM_PREDELAY] = 0.2f;
  const size_t n = Blocks(8.0f) * sidefx::kBlockSize;
  std::vector<Frame> in(n), out(n);
  for (size_t i = 0; i < n; ++i) {
    const float s = 0.5f * sinf(2.0f * 3.14159265f * 330.0f * i / kFs);
    in[i] = sidefx::MakeFrame(s, s);
  }
  float normal = 0.0f;
  float jumped = 0.0f;
  const size_t settle = Blocks(3.0f) * sidefx::kBlockSize;
  const size_t jump = Blocks(5.0f) * sidefx::kBlockSize;
  for (size_t i = 0; i < n; i += sidefx::kBlockSize) {
    if (i == jump) {
      rig.params[Plate::PARAM_SIZE] = 0.9f;
      rig.params[Plate::PARAM_PREDELAY] = 0.9f;
    }
    rig.plate->Process(rig.context, rig.params, &in[i], &out[i],
                       sidefx::kBlockSize);
    for (size_t j = i; j < i + sidefx::kBlockSize; ++j) {
      if (j < settle) continue;
      const float step = fmaxf(fabsf(out[j].l - out[j - 1].l),
                               fabsf(out[j].r - out[j - 1].r));
      if (j < jump) {
        normal = fmaxf(normal, step);
      } else {
        jumped = fmaxf(jumped, step);
      }
    }
  }
  test::Note("largest step: steady %.4f, after the jump %.4f", normal, jumped);
  CHECK(normal > 0.0f);
  CHECK(jumped < 3.0f * normal);
}

TEST(plate, format) {
  Rig rig;
  const sidefx::BlockInfo& info = rig.plate->info();
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
        rig.plate->Format(p, values[v], rig.context, text, 11);
        test::Note("%s %.1f%s: '%s'", info.params[p].name, values[v],
                   synced ? " synced" : "", text);
        CHECK(strlen(text) > 0 && strlen(text) <= 10);
      }
    }
  }
}

TEST(plate, synced_predelay_follows_tempo) {
  // The value whose note is 1/8.
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
    rig.context.sync_mask = 1 << Plate::PARAM_PREDELAY;
    rig.context.beat_seconds = beats[b];
    rig.params[Plate::PARAM_PREDELAY] = eighth;
    rig.params[Plate::PARAM_SIZE] = 0.5f;
    std::vector<Frame> response = ImpulseResponse(&rig, 1.0f);
    size_t onset = 0;
    for (size_t i = 0; i < response.size() && !onset; ++i) {
      if (fabsf(response[i].l) > 1e-7f) onset = i;
    }
    const float expected = 0.5f * beats[b] + 266.0f * kLengthScale / kFs;
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

TEST(plate, top_of_decay_keeps_every_band) {
  // DECAY 1 at DAMP 0, LOWCUT 0: the tank only loses what the 1000 s RT60
  // takes (0.9 dB in 15 s), the highs no faster than the mids: DAMP 0 has
  // no lowpass in the tank and the fractional tank delays (SIZE, MOD) read
  // without loss.
  const float mods[] = { 0.0f, 0.35f };
  for (size_t m = 0; m < 2; ++m) {
    Rig rig;
    rig.params[Plate::PARAM_DECAY] = 1.0f;
    rig.params[Plate::PARAM_DAMP] = 0.0f;
    rig.params[Plate::PARAM_LOWCUT] = 0.0f;
    rig.params[Plate::PARAM_MOD] = mods[m];
    const size_t n = Blocks(19.0f) * sidefx::kBlockSize;
    std::vector<Frame> in(n, sidefx::MakeFrame(0.0f, 0.0f)), out(n);
    uint32_t seed = 5;
    for (size_t i = 0; i < size_t(kFs); ++i) {
      in[i] = sidefx::MakeFrame(0.2f * test::Noise(&seed),
                                0.2f * test::Noise(&seed));
    }
    rig.Run(in.data(), out.data(), n);
    const double expected = -60.0 * 15.0 / Plate::Rt60(1.0f);
    const float bands[][2] = {
      { 200.0f, 1000.0f }, { 4000.0f, 8000.0f }, { 8000.0f, 12000.0f },
      { 12000.0f, 18000.0f },
    };
    for (size_t b = 0; b < sizeof(bands) / sizeof(bands[0]); ++b) {
      const double change = 10.0 * log10(
          BandEnergy(out, 17.0f, bands[b][0], bands[b][1]) /
          BandEnergy(out, 2.0f, bands[b][0], bands[b][1]));
      test::Note("MOD %.2f, %5.0f-%5.0f Hz: %+.2f dB from 2 s to 17 s "
                 "(RT60 %+.2f)", mods[m], bands[b][0], bands[b][1], change,
                 expected);
      CHECK(fabs(change - expected) < 1.5);
    }
  }
  // The screen shows the RT60 the tank makes, not an endless hold.
  Rig rig;
  char text[16];
  rig.plate->Format(Plate::PARAM_DECAY, 1.0f, rig.context, text, 11);
  test::Note("DECAY 1: '%s'", text);
  CHECK(strcmp(text, "1000s") == 0);
  rig.plate->Format(Plate::PARAM_DECAY, 0.95f, rig.context, text, 11);
  test::Note("DECAY 0.95: '%s'", text);
  CHECK(strcmp(text, "173s") == 0);
}
