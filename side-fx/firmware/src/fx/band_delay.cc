// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: BAND DELAY (see band_delay.h).

#include "fx/band_delay.h"

#include <math.h>

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "TIME", 0.45f, PARAM_SYNC, 0, 0 },
  { "SPREAD", 0.70f, PARAM_BIPOLAR, 0, 100 },
  { "FEEDBACK", 0.45f, 0, 0, 100 },
  // 76 detents over 100 Hz..8 kHz (6.3 octaves): a semitone each.
  { "FREQ", 0.50f, 0, 0, 76 },
  { "Q", 0.35f, 0, 0, 100 },
  { "TILT", 0.40f, PARAM_BIPOLAR, 0, 100 },
  { "WIDTH", 0.80f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "BAND DELAY", "BAND", BandDelay::NUM_PARAMS, kParams, 0.35f, 0,
};

const float kMinTime = 0.01f;
const float kMaxTime = 4.0f;
const float kMinFrequency = 100.0f;
const float kMaxFrequency = 8000.0f;
const float kMinQ = 0.6f;
const float kMaxQ = 15.0f;
// A hair above unity: at 100 % the loops bloom into their soft limit and
// hold, an infinite smeared repeat to play over.
const float kMaxFeedback = 1.02f;

// Where the bands sit, low to high: octaves from FREQ, the SPREAD/TILT
// weight (-1..+1) and the side WIDTH pans them to.
const float kBandOctave[BandDelay::kNumBands] = { -1.8f, -0.6f, 0.6f, 1.8f };
const float kBandPosition[BandDelay::kNumBands] = {
  -1.0f, -1.0f / 3.0f, 1.0f / 3.0f, 1.0f };
const float kBandSide[BandDelay::kNumBands] = { -1.0f, 1.0f, -1.0f, 1.0f };

// Delay limits in samples. ReadHermite() needs 1 .. size - 3, and the read
// happens before the write, so a delay of D reads at D - 1.
const float kMinDelay = 2.0f;
const float kMaxDelay = float(BandDelay::kLineSize - 4);

// Glide: a one-pole of about 80 ms, its rate limited to 0.3 samples per
// sample (the repeats bend by at most -6..+5 semitones while it moves).
const float kGlideCoefficient = 1.0f / (0.08f * kSampleRate);
const float kGlideSlew = 0.3f;
// A jump beyond 20 % + 10 ms crossfades to a second head instead.
const float kFadeRelative = 0.2f;
const float kFadeAbsolute = 0.01f * kSampleRate;
const float kFadeIncrement = 1.0f / (0.04f * kSampleRate);

// Rhythmic SPREAD ratios for a synced TIME, as log2.
const float kRhythmicLog2[] = {
  -1.0f,          // 1/2
  -0.5849625f,    // 2/3
  -0.4150375f,    // 3/4
  0.0f,           // 1
  0.4150375f,     // 4/3
  0.5849625f,     // 3/2
  1.0f,           // 2
};
const int kNumRhythmic = sizeof(kRhythmicLog2) / sizeof(kRhythmicLog2[0]);

// The wet sum's soft limit: +-3, slope 1 at 0 (2 % down at 1.0).
inline float OutputLimit(float x) {
  return 3.0f * dsp::SoftSaturate(x * (1.0f / 3.0f));
}

}  // namespace

const BlockInfo& BandDelay::info() const {
  return kInfo;
}

bool BandDelay::Init(Memory* memory) {
  for (int k = 0; k < kNumBands; ++k) {
    float* buffer = memory->external->AllocateArray<float>(kLineSize);
    if (!buffer) {
      return false;
    }
    band_[k].line.Init(buffer, kLineSize);
    band_[k].filter.Init();
  }
  Reset();
  return true;
}

void BandDelay::Reset() {
  for (int k = 0; k < kNumBands; ++k) {
    Band& b = band_[k];
    b.line.Clear();
    b.filter.Reset();
    b.target = b.delay_a = b.delay_b = kMinDelay;
    b.fade = -1.0f;
    b.frequency = kMinFrequency;
    b.input_gain = b.feedback = b.gain_l = b.gain_r = 0.0f;
  }
  log_frequency_ = 0.0f;
  q_ = kMinQ;
  side_amount_ = 0.0f;
  snap_ = true;
}

float BandDelay::SpreadRatio(int band, float spread, bool synced) {
  float l = spread * kBandPosition[band];  // log2 of the ratio, -1..+1
  if (synced) {
    int best = 0;
    float best_distance = 1e9f;
    for (int i = 0; i < kNumRhythmic; ++i) {
      const float d = fabsf(kRhythmicLog2[i] - l);
      if (d < best_distance) {
        best_distance = d;
        best = i;
      }
    }
    l = kRhythmicLog2[best];
  }
  return exp2f(l);
}

void BandDelay::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  if (size == 0) {
    return;
  }
  const float sample_rate = kSampleRate;

  // --- control rate -------------------------------------------------------
  const bool time_synced = context.synced(PARAM_TIME);
  const float time = TimeParam(dsp::Clamp(params[PARAM_TIME], 0.0f, 1.0f),
                               time_synced, context.beat_seconds, kMinTime,
                               kMaxTime);
  const float spread = Bipolar(dsp::Clamp(params[PARAM_SPREAD], 0.0f, 1.0f),
                               1.0f);
  const float feedback = dsp::Clamp(params[PARAM_FEEDBACK], 0.0f, 1.0f) *
      kMaxFeedback;
  const float target_log_frequency = log2f(ExpMap(
      dsp::Clamp(params[PARAM_FREQ], 0.0f, 1.0f), kMinFrequency,
      kMaxFrequency));
  const float target_q = ExpMap(dsp::Clamp(params[PARAM_Q], 0.0f, 1.0f),
                                kMinQ, kMaxQ);
  const float tilt = Bipolar(dsp::Clamp(params[PARAM_TILT], 0.0f, 1.0f), 1.0f);
  const float width = dsp::Clamp(params[PARAM_WIDTH], 0.0f, 1.0f);

  if (snap_) {
    log_frequency_ = target_log_frequency;
    q_ = target_q;
    side_amount_ = width;
  } else {
    // About 4 ms: fast enough to play, slow enough not to zip at high Q.
    log_frequency_ += 0.15f * (target_log_frequency - log_frequency_);
    q_ += 0.15f * (target_q - q_);
  }

  // A narrow band passes less of a broad input: give some of it back
  // (+7 dB at Q 15), the soft limit on each line catches what is left.
  const float q_compensation = sqrtf(sqrtf(q_ * (1.0f / kMinQ)));

  // TILT: up to +-4.5 dB per band position, normalised to the loudest band
  // so that it only ever cuts. The cut bands also lose some feedback, so a
  // dark tilt makes the high repeats die first, as on a dub echo.
  float tilt_gain[kNumBands];
  float max_tilt_gain = 0.0f;
  for (int k = 0; k < kNumBands; ++k) {
    tilt_gain[k] = exp2f(1.5f * tilt * kBandPosition[k]);
    if (tilt_gain[k] > max_tilt_gain) {
      max_tilt_gain = tilt_gain[k];
    }
  }

  const float inv_size = 1.0f / float(size);
  float input_gain_increment[kNumBands];
  float feedback_increment[kNumBands];
  float gain_l_increment[kNumBands];
  float gain_r_increment[kNumBands];

  for (int k = 0; k < kNumBands; ++k) {
    Band& b = band_[k];
    const float g = tilt_gain[k] / max_tilt_gain;
    const float band_feedback = feedback * (1.0f - 0.2f * (1.0f - g));

    b.target = dsp::Clamp(time * SpreadRatio(k, spread, time_synced) *
                          sample_rate, kMinDelay, kMaxDelay);

    float f = exp2f(log_frequency_ + kBandOctave[k]);
    f = dsp::Clamp(f, 20.0f, 0.35f * sample_rate);
    b.frequency = f;
    b.filter.set_f_q<stmlib::FREQUENCY_ACCURATE>(f / sample_rate, q_);

    float pan_l, pan_r;
    dsp::PanGains(kBandSide[k] * width, &pan_l, &pan_r);
    // 0.707: four bands at the centre sum to about unity.
    pan_l *= 0.7071f;
    pan_r *= 0.7071f;
    const float input_gain = g * q_compensation;

    if (snap_) {
      b.delay_a = b.delay_b = b.target;
      b.fade = -1.0f;
      b.input_gain = input_gain;
      b.feedback = band_feedback;
      b.gain_l = pan_l;
      b.gain_r = pan_r;
    } else if (b.fade < 0.0f) {
      const float distance = fabsf(b.target - b.delay_a);
      if (distance > kFadeRelative * b.delay_a + kFadeAbsolute) {
        b.delay_b = b.target;
        b.fade = 0.0f;
      }
    }
    input_gain_increment[k] = (input_gain - b.input_gain) * inv_size;
    feedback_increment[k] = (band_feedback - b.feedback) * inv_size;
    gain_l_increment[k] = (pan_l - b.gain_l) * inv_size;
    gain_r_increment[k] = (pan_r - b.gain_r) * inv_size;
  }
  const float side_increment = (width - side_amount_) * inv_size;
  snap_ = false;

  // --- audio rate ---------------------------------------------------------
  for (size_t i = 0; i < size; ++i) {
    const float mid = 0.5f * (in[i].l + in[i].r);
    const float side = 0.5f * (in[i].l - in[i].r);
    side_amount_ += side_increment;
    const float side_scaled = side * side_amount_;
    float l = 0.0f;
    float r = 0.0f;

    for (int k = 0; k < kNumBands; ++k) {
      Band& b = band_[k];
      b.input_gain += input_gain_increment[k];
      b.feedback += feedback_increment[k];
      b.gain_l += gain_l_increment[k];
      b.gain_r += gain_r_increment[k];

      // WIDTH also picks the input side: a left band hears the left input.
      const float x = (mid + kBandSide[k] * side_scaled) * b.input_gain;

      float y;
      if (b.fade >= 0.0f) {
        b.fade += kFadeIncrement;
        if (b.fade >= 1.0f) {
          b.delay_a = b.delay_b;
          b.fade = -1.0f;
          y = b.line.ReadHermite(b.delay_a - 1.0f);
        } else {
          // 1 - t^2 and 1 - (1 - t)^2: within 0.5 dB of equal power for
          // the two uncorrelated heads.
          const float t = b.fade;
          const float u = 1.0f - t;
          y = (1.0f - t * t) * b.line.ReadHermite(b.delay_a - 1.0f) +
              (1.0f - u * u) * b.line.ReadHermite(b.delay_b - 1.0f);
        }
      } else {
        const float step = dsp::Clamp((b.target - b.delay_a) *
                                      kGlideCoefficient,
                                      -kGlideSlew, kGlideSlew);
        b.delay_a += step;
        y = b.line.ReadHermite(b.delay_a - 1.0f);
      }

      const float v = b.filter.Process<stmlib::FILTER_MODE_BAND_PASS_NORMALIZED>(
          x + b.feedback * y);
      // Soft limit to +-2 on the way in: the loop holds at 100 % and more.
      b.line.Write(2.0f * dsp::SoftSaturate(0.5f * v));

      l += y * b.gain_l;
      r += y * b.gain_r;
    }
    out[i].l = OutputLimit(l);
    out[i].r = OutputLimit(r);
  }
}

void BandDelay::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  value = dsp::Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_TIME:
      if (context.synced(param) &&
          SyncedSeconds(value, context.beat_seconds) <= kMaxTime) {
        FormatNoteValue(text, size, NoteValueIndex(value));
      } else {
        // Free, or a note value longer than 4 s: the time it plays, so the
        // screen does not claim the grid.
        FormatSeconds(text, size, TimeParam(value, context.synced(param),
                                            context.beat_seconds, kMinTime,
                                            kMaxTime));
      }
      break;
    case PARAM_SPREAD:
    case PARAM_TILT:
      FormatBipolarPercent(text, size, value);
      break;
    case PARAM_FREQ:
      FormatHz(text, size, ExpMap(value, kMinFrequency, kMaxFrequency));
      break;
    case PARAM_Q: {
        const float q = ExpMap(value, kMinQ, kMaxQ);
        FormatNumber(text, size, q, q < 9.95f ? 1 : 0, false, "");
      }
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
