// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: GRANULATOR (see granulator.h).

#include "fx/granulator.h"

#include "stmlib/dsp/units.h"

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },  // +-24st, one per detent
  { "SPREAD", 0.200000f, 0, 0, 100 },            // 0.5st: a choir's spread
  { "DENSITY", 0.600000f, PARAM_SYNC, 0, 0 },    // 12/s
  { "SIZE", 0.600000f, PARAM_SYNC, 0, 0 },       // 138ms
  { "DELAY", 0.200000f, PARAM_SYNC, 0, 0 },      // 80ms
  { "FEEDBACK", 0.000000f, 0, 0, 100 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "GRANULATOR", "GRAIN", Granulator::NUM_PARAMS, kParams, 0.50f, 0,
};

// 2^18 samples = 5.46 s: 2 s of delay, the spread and a 500 ms grain at
// +36 st (which has to start 3.5 s back so it never overtakes the write
// head) all fit.
const uint32_t kLineSize = 262144;
const uint32_t kLineMask = kLineSize - 1;

const float kMinDensity = 0.5f;
const float kMaxDensity = 100.0f;
const float kMinSize = 0.020f;
const float kMaxSize = 0.500f;
const float kMaxDelay = 2.0f;
const float kSemitoneRange = 24.0f;
const float kMaxSpread = 12.0f;
const float kMaxGrainSemitones = 36.0f;

// The closest a grain reads to the write head: Hermite's newer neighbours.
const float kMinGrainDelay = 8.0f;

// A stolen grain fades out over 64 samples (1.3 ms) instead of stopping.
const float kReleaseIncrement = 1.0f / 64.0f;

// Free-running grain intervals vary between 0.3 and 1.7 times the mean:
// the crowd never locks into a buzz.
const float kJitterMin = 0.3f;
const float kJitterRange = 1.4f;

const float kLoopLowpassHz = 5000.0f;

// The grains' power is 0.41 of the line's (the mean of the envelope's
// square, (4 t (1 - t))^4 integrated, times overlap, over the
// 1 / sqrt(overlap) normalisation squared), and the mono sum of an
// equal-power pan is 0.71 of a centred grain. Making up for both puts the
// loop's gain at FEEDBACK: at 100 % the cloud sustains, held by the
// saturator.
const float kFeedbackMakeup = 1.1f;

// The normalisation follows the grains actually sounding (they outlive a
// SIZE or DENSITY turned down) with a 7 ms time constant per block.
const float kNormalizationSmoothing = 0.1f;
// A rising overlap is followed at most 6 % per block (the gain falls by
// 0.25 dB per block, 14 dB in 37 ms): the new grains fade in over their
// envelope, so the crowd takes that long to build up, and a jump would
// duck the grains already sounding (a thump when DENSITY or SIZE jumps).
const float kNormalizationRise = 1.06f;

}  // namespace

const BlockInfo& Granulator::info() const {
  return kInfo;
}

float Granulator::PitchSemitones(float value) {
  return Bipolar(value, kSemitoneRange);
}

float Granulator::SpreadSemitones(float value) {
  // Quadratic: the first third of the knob is the sub-semitone chorus and
  // choir range, the rest opens up to an octave either way.
  const float v = dsp::Clamp(value, 0.0f, 1.0f);
  return kMaxSpread * v * v;
}

float Granulator::DensityHz(float value, bool synced, float beat_seconds) {
  if (synced) {
    return dsp::Clamp(SyncedHz(value, beat_seconds), 0.05f, kMaxDensity);
  }
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), kMinDensity, kMaxDensity);
}

float Granulator::SizeSeconds(float value, bool synced, float beat_seconds) {
  if (synced) {
    return dsp::Clamp(SyncedSeconds(value, beat_seconds), kMinSize, kMaxSize);
  }
  return ExpMap(dsp::Clamp(value, 0.0f, 1.0f), kMinSize, kMaxSize);
}

float Granulator::DelaySeconds(float value, bool synced, float beat_seconds) {
  if (synced) {
    const float t = SyncedSeconds(value, beat_seconds);
    return t > kMaxDelay ? kMaxDelay : t;
  }
  const float v = dsp::Clamp(value, 0.0f, 1.0f);
  return kMaxDelay * v * v;
}

bool Granulator::Init(Memory* memory) {
  line_ = memory->external->AllocateArray<float>(kLineSize);
  if (!line_) {
    return false;
  }
  loop_lowpass_ = dsp::OnePoleCoefficient(kLoopLowpassHz, kSampleRate);
  Reset();
  return true;
}

void Granulator::Reset() {
  memset(line_, 0, sizeof(float) * kLineSize);
  write_ = 0;
  for (int g = 0; g < kMaxGrains; ++g) {
    grains_[g].active = false;
    grains_[g].releasing = false;
  }
  has_pending_ = false;
  pending_.active = false;
  serial_ = 0;
  pitch_ = 0.0f;
  spread_ = 0.0f;
  size_samples_ = kMinSize * kSampleRate;
  delay_samples_ = 0.0f;
  width_ = 0.0f;
  countdown_ = 0.0f;
  grid_index_ = -1;
  grid_rate_ = 0.0f;
  last_bars_ = 0.0f;
  bar_count_ = 0;
  last_bar_phase_ = 0.0f;
  normalization_ = 1.0f;
  overlap_ = 1.0f;
  feedback_ = 0.0f;
  feedback_sample_ = 0.0f;
  lowpass_.Reset();
  dc_blocker_.Reset();
  random_.Seed(0x6a09e667u);
  primed_ = false;
}

int Granulator::num_active_grains() const {
  int n = 0;
  for (int g = 0; g < kMaxGrains; ++g) {
    n += grains_[g].active ? 1 : 0;
  }
  return n;
}

float Granulator::ReadLine(uint32_t position, float fraction) const {
  const float xm1 = line_[(position - 1) & kLineMask];
  const float x0 = line_[position & kLineMask];
  const float x1 = line_[(position + 1) & kLineMask];
  const float x2 = line_[(position + 2) & kLineMask];
  const float c = (x1 - xm1) * 0.5f;
  const float v = x0 - x1;
  const float w = c + v;
  const float a = w + v + (x2 - x0) * 0.5f;
  const float b_neg = w + a;
  return (((a * fraction) - b_neg) * fraction + c) * fraction + x0;
}

void Granulator::Place(int index, const Grain& grain) {
  grains_[index] = grain;
  grains_[index].active = true;
}

void Granulator::Trigger() {
  Grain grain;
  const float semitones = dsp::Clamp(
      pitch_ + spread_ * random_.Bipolar(),
      -kMaxGrainSemitones, kMaxGrainSemitones);
  grain.ratio = stmlib::SemitonesToRatio(semitones);
  const float length = size_samples_;

  // DELAY plus up to half a grain of spread, so overlapping grains never
  // read the same moment; then far enough back that a grain playing faster
  // than real time ends before it reaches the write head, and close enough
  // that a slow one ends before the line wraps.
  float delay = delay_samples_ + random_.Uniform() * 0.5f * length;
  const float min_delay = kMinGrainDelay +
      (grain.ratio > 1.0f ? (grain.ratio - 1.0f) * length : 0.0f);
  const float max_delay = float(kLineSize) - kMinGrainDelay - length;
  delay = delay < min_delay ? min_delay : delay;
  delay = delay > max_delay ? max_delay : delay;

  grain.active = true;
  grain.releasing = false;
  grain.position = write_ - uint32_t(delay);
  grain.fraction = 0.0f;
  grain.phase = 0.0f;
  grain.increment = 1.0f / length;
  grain.release = 1.0f;
  dsp::PanGains(width_ * random_.Bipolar(), &grain.gain_l, &grain.gain_r);
  grain.serial = serial_++;

  int oldest = -1;
  uint32_t oldest_age = 0;
  for (int g = 0; g < kMaxGrains; ++g) {
    if (!grains_[g].active) {
      Place(g, grain);
      return;
    }
    const uint32_t age = serial_ - grains_[g].serial;
    if (!grains_[g].releasing && age >= oldest_age) {
      oldest_age = age;
      oldest = g;
    }
  }
  // Full: the oldest fades out and this grain takes its slot when it is
  // gone. One grain waits at most; a trigger during the fade is dropped.
  if (!has_pending_ && oldest >= 0) {
    grains_[oldest].releasing = true;
    pending_ = grain;
    has_pending_ = true;
  }
}

void Granulator::Process(const ProcessContext& context, const float* params,
                         const Frame* in, Frame* out, size_t size) {
  // --- control rate --------------------------------------------------------
  const bool synced_density = context.synced(DENSITY);
  const float density = DensityHz(params[DENSITY], synced_density,
                                  context.beat_seconds);
  const float size_seconds = SizeSeconds(params[SIZE], context.synced(SIZE),
                                         context.beat_seconds);
  pitch_ = PitchSemitones(params[PITCH]);
  spread_ = SpreadSemitones(params[SPREAD]);
  size_samples_ = size_seconds * kSampleRate;
  delay_samples_ = DelaySeconds(params[DELAY], context.synced(DELAY),
                                context.beat_seconds) * kSampleRate;
  width_ = dsp::Clamp(params[WIDTH], 0.0f, 1.0f);

  // Expected overlap from the parameters, or the grains sounding when more
  // (a long SIZE just turned short): never louder than the crowd allows.
  float overlap = dsp::Clamp(density * size_seconds, 1.0f,
                             float(kMaxGrains));
  const float active = float(num_active_grains());
  overlap = active > overlap ? active : overlap;
  if (overlap > overlap_) {
    const float limit = overlap_ * kNormalizationRise;
    overlap_ = overlap < limit ? overlap : limit;
  } else {
    overlap_ += kNormalizationSmoothing * (overlap - overlap_);
  }
  const float normalization_target = 1.0f / sqrtf(overlap_);
  const float feedback_target = dsp::Clamp(params[FEEDBACK], 0.0f, 1.0f);
  const float interval = kSampleRate / density;

  if (!primed_) {
    normalization_ = normalization_target;
    overlap_ = overlap;
    feedback_ = feedback_target;
    last_bar_phase_ = context.bar_phase;
    primed_ = true;
  }
  // A density turned up should not wait out a long interval drawn earlier.
  const float max_countdown = interval * (kJitterMin + kJitterRange);
  if (countdown_ > max_countdown) {
    countdown_ = max_countdown;
  }
  // The tempo grid counts 16 bars, so grids longer than a bar (2 BAR,
  // 4 BAR) still land on bar lines.
  if (context.bar_phase + 0.5f < last_bar_phase_) {
    bar_count_ = (bar_count_ + 1) & 15;
  }
  last_bar_phase_ = context.bar_phase;
  const float grids_per_bar = density * 4.0f * context.beat_seconds;
  // Grid lines in the 16-bar cycle (a dotted value's last one falls short
  // of the cycle's end, so round up).
  const int32_t grid_cycle = int32_t(ceilf(16.0f * grids_per_bar - 1.0e-3f));
  if (!synced_density) {
    grid_index_ = -1;  // a grain at once when the grid comes back
  } else if (grid_index_ >= 0 &&
             fabsf(grids_per_bar - grid_rate_) > 1.0e-4f * grids_per_bar) {
    // A new note value: count on from where the last block ended, on the
    // new grid, without a grain of its own.
    grid_index_ = int32_t(last_bars_ * grids_per_bar);
  }
  grid_rate_ = grids_per_bar;

  const float step = 1.0f / float(size ? size : 1);
  const float normalization_step =
      (normalization_target - normalization_) * step;
  const float feedback_step = (feedback_target - feedback_) * step;

  // --- audio rate ----------------------------------------------------------
  for (size_t i = 0; i < size; ++i) {
    write_ = (write_ + 1) & kLineMask;
    line_[write_] = 0.5f * (in[i].l + in[i].r) + feedback_sample_;

    if (synced_density) {
      // The bar position extrapolated across the block, into the next bar
      // (and the 16-bar count) when it gets there.
      float phase = context.bar_phase + float(i) * context.bar_increment;
      uint32_t bar = bar_count_;
      if (phase >= 1.0f) {
        phase -= 1.0f;
        bar = (bar + 1) & 15;
      }
      const float bars = float(bar) + phase;
      const int32_t index = int32_t(bars * grids_per_bar);
      // Forward only, round the cycle: a block that starts a little
      // behind where the last one's extrapolation ended (an external
      // clock pulled back) does not count the same grid line twice.
      int32_t ahead = index - grid_index_;
      if (ahead < 0) {
        ahead += grid_cycle;
      }
      if (grid_index_ < 0 || (ahead > 0 && 2 * ahead < grid_cycle)) {
        grid_index_ = index;
        Trigger();
      }
      last_bars_ = bars;
    } else {
      countdown_ -= 1.0f;
      if (countdown_ <= 0.0f) {
        Trigger();
        countdown_ += interval * (kJitterMin + kJitterRange *
                                  random_.Uniform());
        if (countdown_ < 1.0f) {
          countdown_ = 1.0f;
        }
      }
    }

    float l = 0.0f;
    float r = 0.0f;
    for (int g = 0; g < kMaxGrains; ++g) {
      Grain& grain = grains_[g];
      if (!grain.active) {
        continue;
      }
      const float p = grain.phase;
      float envelope = 4.0f * p * (1.0f - p);
      envelope *= envelope;
      if (grain.releasing) {
        grain.release -= kReleaseIncrement;
        envelope *= grain.release;
      }
      const float s = ReadLine(grain.position, grain.fraction) * envelope;
      l += s * grain.gain_l;
      r += s * grain.gain_r;

      grain.fraction += grain.ratio;
      const int32_t whole = int32_t(grain.fraction);
      grain.position += uint32_t(whole);
      grain.fraction -= float(whole);
      grain.phase += grain.increment;
      if (grain.phase >= 1.0f || grain.release <= 0.0f) {
        grain.active = false;
        if (has_pending_) {
          Place(g, pending_);
          has_pending_ = false;
        }
      }
    }

    l *= normalization_;
    r *= normalization_;
    out[i].l = l;
    out[i].r = r;

    const float loop = lowpass_.Lowpass(
        dc_blocker_.Process(kFeedbackMakeup * (l + r)), loop_lowpass_);
    feedback_sample_ = dsp::SoftSaturate(feedback_ * loop);
    normalization_ += normalization_step;
    feedback_ += feedback_step;
  }
}

void Granulator::Format(int param, float value, const ProcessContext& context,
                        char* text, size_t size) const {
  const float beat = context.beat_seconds;
  const bool synced = context.synced(param);
  switch (param) {
    case PITCH:
      {
        const float st = PitchSemitones(value);
        const float rounded = floorf(st + 0.5f);
        const bool on_grid = fabsf(st - rounded) < 0.01f;
        FormatSemitones(text, size, on_grid ? rounded : st, !on_grid);
      }
      break;
    case SPREAD:
      {
        const float st = SpreadSemitones(value);
        FormatNumber(text, size, st, st < 9.95f ? 1 : 0, false, "st");
      }
      break;
    case DENSITY:
      if (synced) {
        FormatNoteValue(text, size, SyncedRateIndex(value));
      } else {
        FormatHz(text, size, DensityHz(value, false, beat));
      }
      break;
    case SIZE:
    case DELAY:
      {
        const float played = param == SIZE
            ? SizeSeconds(value, synced, beat)
            : DelaySeconds(value, synced, beat);
        const float note = SyncedSeconds(value, beat);
        if (synced && fabsf(played - note) <= 0.001f * note) {
          FormatNoteValue(text, size, NoteValueIndex(value));
        } else {
          // Free, or a note value outside the range: the time it plays,
          // so the screen does not claim the grid.
          FormatSeconds(text, size, played);
        }
      }
      break;
    case FEEDBACK:
    case WIDTH:
      FormatPercent(text, size, value);
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
