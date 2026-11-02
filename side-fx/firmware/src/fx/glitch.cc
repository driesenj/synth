// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: GLITCH (see glitch.h).

#include "fx/glitch.h"

#include <math.h>

namespace sidefx {

using dsp::Clamp;

namespace {

// 2^18 stereo frames: 5.46 s, 2 MB.
const uint32_t kBufferSize = 262144;
const uint32_t kBufferMask = kBufferSize - 1;
// The recording holds still while the playing slice is this close to being
// overwritten (see Process()).
const uint32_t kOverwriteMargin = 4096;

const float kMinSliceSeconds = 0.01f;
const float kMaxSliceSeconds = 2.0f;
// A synced slice is clamped here (one bar down to 96 BPM): the buffer must
// hold a slice, SHUFFLE's earlier ones and a while of repeats.
const float kMaxSyncedSliceSeconds = 2.5f;
// The shortest slice in samples: two crossfades.
const float kMinSliceSamples = 192.0f;

// 2 ms crossfades.
const int32_t kFadeLength = 96;

// How far back SHUFFLE reaches, in slices before the latest.
const uint32_t kMaxShuffleSlices = 7;

const int32_t kRepeatCounts[Glitch::kNumRepeatSteps] = {
  1, 2, 3, 4, 6, 8, 12, 16
};

// The longest synced slice: 1 BAR (kNoteValues[17]).
const int kLongestSyncedNote = 17;

const ParamInfo kParams[] = {
  // 83 ms free, 1/8 synced.
  { "SLICE", 0.4f, PARAM_SYNC, 0, 0 },
  { "CHANCE", 0.3f, 0, 0, 100 },
  { "REPEATS", 3.0f / 7.0f, PARAM_STEPPED, Glitch::kNumRepeatSteps, 0 },
  { "REVERSE", 0.2f, 0, 0, 100 },
  { "PITCH", 0.5f, PARAM_BIPOLAR, 0, 48 },
  { "CRUSH", 0.0f, 0, 0, 100 },
  { "SHUFFLE", 0.2f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "GLITCH", "GLTCH", Glitch::NUM_PARAMS, kParams, 1.00f, 0,
};

inline int SyncedSliceIndex(float value) {
  const int index = NoteValueIndex(value);
  return index > kLongestSyncedNote ? kLongestSyncedNote : index;
}

inline float FreeSliceSeconds(float value) {
  return ExpMap(Clamp(value, 0.0f, 1.0f), kMinSliceSeconds, kMaxSliceSeconds);
}

// sin(pi/2 t) for t in [0, 1].
inline float QuarterSine(float t) {
  return dsp::Sine(t * 0.25f);
}

}  // namespace

const BlockInfo& Glitch::info() const {
  return kInfo;
}

bool Glitch::Init(Memory* memory) {
  buffer_ = memory->external->AllocateArray<Frame>(kBufferSize);
  if (!buffer_) {
    return false;
  }
  Reset();
  return true;
}

void Glitch::Reset() {
  for (uint32_t i = 0; i < kBufferSize; ++i) {
    buffer_[i].l = buffer_[i].r = 0.0f;
  }
  write_ = 0;
  random_.Seed(0x6c697463u);
  voice_.live = true;
  voice_.start = 0;
  voice_.position = 0.0f;
  voice_.direction = 1.0f;
  previous_voice_ = voice_;
  fading_ = false;
  fade_position_ = 0;
  pending_step_ = false;
  glitching_ = false;
  repeats_left_ = 0;
  slice_length_ = kMinSliceSamples;
  elapsed_ = 0.0f;
  duration_ = 1.0f;
  chance_ = reverse_ = shuffle_ = 0.0f;
  repeats_ = 1;
  grid_synced_ = false;
  grid_fresh_ = true;
  last_phase_ = 0.0f;
  last_step_ = 0;
  countdown_ = 0;
  grid_rate_ = 1.0f;
  frozen_ = false;
  thaw_position_ = kFadeLength;
  hold_phase_ = 1.0f;
  hold_.l = hold_.r = 0.0f;
}

void Glitch::StartVoice(float direction) {
  previous_voice_ = voice_;
  voice_.live = false;
  voice_.direction = direction;
  // A reversed slice starts just inside its end: the last frames of the
  // latest slice may not be written yet.
  voice_.position = direction > 0.0f ? 0.0f : slice_length_ - 3.0f;
  fading_ = true;
  fade_position_ = 0;
}

void Glitch::StartLive() {
  previous_voice_ = voice_;
  voice_.live = true;
  fading_ = true;
  fade_position_ = 0;
}

void Glitch::StartGlitch(float slice_samples, float step_samples) {
  const uint32_t length = uint32_t(slice_samples);
  const uint32_t duration = uint32_t(repeats_) * length;
  // The latest slice, or with SHUFFLE one 1 .. 7 further back, as long as
  // it lasts the glitch out without holding the recording still.
  uint32_t back = 0;
  if (random_.Uniform() < shuffle_) {
    const uint32_t room = kBufferSize - kOverwriteMargin;
    const uint32_t needed = duration + 2 * length;
    const uint32_t limit = room > needed ? (room - needed) / length : 0;
    const uint32_t most = limit < kMaxShuffleSlices ? limit : kMaxShuffleSlices;
    if (most > 0) {
      back = 1 + random_.Next() % most;
    }
  }
  slice_length_ = float(length);
  glitching_ = true;
  repeats_left_ = repeats_;
  elapsed_ = 0.0f;
  duration_ = float(repeats_) * step_samples;
  previous_voice_ = voice_;
  voice_.live = false;
  // The slice ends with the frame just written.
  voice_.start = write_ + 1 - (back + 1) * length;
  voice_.direction = random_.Uniform() < reverse_ ? -1.0f : 1.0f;
  voice_.position = voice_.direction > 0.0f ? 0.0f : slice_length_ - 3.0f;
  fading_ = true;
  fade_position_ = 0;
}

void Glitch::OnStep(float slice_samples, float step_samples) {
  if (glitching_) {
    if (--repeats_left_ > 0) {
      StartVoice(random_.Uniform() < reverse_ ? -1.0f : 1.0f);
      return;
    }
    glitching_ = false;
  }
  if (random_.Uniform() < chance_) {
    StartGlitch(slice_samples, step_samples);
  } else if (!voice_.live) {
    StartLive();
  }
}

Frame Glitch::ReadVoice(const Voice& voice) const {
  float position = voice.position;
  // Never read frames not written yet (a slice read on past its end, or
  // sped up): hold at the newest.
  const float newest = float(int32_t(write_ - voice.start)) - 3.0f;
  position = position > newest ? newest : position;
  const float integral = floorf(position);
  const float t = position - integral;
  const uint32_t i = voice.start + uint32_t(int32_t(integral));
  const Frame xm1 = buffer_[(i - 1) & kBufferMask];
  const Frame x0 = buffer_[i & kBufferMask];
  const Frame x1 = buffer_[(i + 1) & kBufferMask];
  const Frame x2 = buffer_[(i + 2) & kBufferMask];
  const Frame c = (x1 - xm1) * 0.5f;
  const Frame v = x0 - x1;
  const Frame w = c + v;
  const Frame a = w + v + (x2 - x0) * 0.5f;
  const Frame b_neg = w + a;
  return (((a * t) - b_neg) * t + c) * t + x0;
}

void Glitch::Process(const ProcessContext& context, const float* params,
                     const Frame* in, Frame* out, size_t size) {
  chance_ = Clamp(params[PARAM_CHANCE], 0.0f, 1.0f);
  reverse_ = Clamp(params[PARAM_REVERSE], 0.0f, 1.0f);
  shuffle_ = Clamp(params[PARAM_SHUFFLE], 0.0f, 1.0f);
  repeats_ = kRepeatCounts[StepIndex(params[PARAM_REPEATS], kNumRepeatSteps)];
  const float crush = Clamp(params[PARAM_CRUSH], 0.0f, 1.0f);
  const float bend = Bipolar(Clamp(params[PARAM_PITCH], 0.0f, 1.0f), 24.0f);

  // The grid and the slice length.
  const bool synced = context.synced(PARAM_SLICE);
  if (synced != grid_synced_) {
    grid_synced_ = synced;
    grid_fresh_ = true;
  }
  float step_samples;
  float slice_seconds;
  float inverse_step_bars = 1.0f;
  if (synced) {
    const float beats = kNoteValues[SyncedSliceIndex(params[PARAM_SLICE])].beats;
    slice_seconds = beats * context.beat_seconds;
    inverse_step_bars = 4.0f / beats;
    step_samples = context.bar_increment > 0.0f
        ? beats * 0.25f / context.bar_increment : slice_seconds * kSampleRate;
    slice_seconds = slice_seconds > kMaxSyncedSliceSeconds
        ? kMaxSyncedSliceSeconds : slice_seconds;
  } else {
    slice_seconds = FreeSliceSeconds(params[PARAM_SLICE]);
    step_samples = slice_seconds * kSampleRate;
  }
  float slice_samples = slice_seconds * kSampleRate;
  slice_samples = slice_samples < kMinSliceSamples
      ? kMinSliceSamples : slice_samples;
  step_samples = step_samples < kMinSliceSamples
      ? kMinSliceSamples : step_samples;

  float phase = context.bar_phase;
  if (grid_fresh_) {
    grid_fresh_ = false;
    last_phase_ = phase;
    last_step_ = int32_t(phase * inverse_step_bars);
    countdown_ = int32_t(step_samples);
  }
  if (synced && inverse_step_bars != grid_rate_) {
    // A new note value (turned, or moved by a CV): count on from where the
    // last block ended, on the new grid, without a step of its own. The
    // old grid's index would hold a coarser grid back until the bar line,
    // or fire a finer one off the grid at once.
    last_step_ = int32_t(last_phase_ * inverse_step_bars);
  }
  grid_rate_ = inverse_step_bars;
  if (!synced && countdown_ > int32_t(step_samples)) {
    countdown_ = int32_t(step_samples);
  }

  // PITCH: the rate goes from 1 to 2^(bend / 12) over the glitch,
  // exponentially, evaluated at the block's ends and linear in between.
  float rate = 1.0f;
  float rate_step = 0.0f;
  if (glitching_ && bend != 0.0f) {
    const float k = bend * (0.6931472f / 12.0f) / duration_;
    float u0 = elapsed_;
    float u1 = elapsed_ + float(size);
    u0 = u0 > duration_ ? duration_ : u0;
    u1 = u1 > duration_ ? duration_ : u1;
    rate = expf(k * u0);
    rate_step = (expf(k * u1) - rate) / float(size ? size : 1);
  }
  if (glitching_) {
    elapsed_ += float(size);
  }

  // CRUSH: 16 bits and no hold at 0, 4 bits and 1/32 of the rate at 1.
  const float levels = crush > 0.0f ? expf((16.0f - 12.0f * crush) *
                                           0.6931472f) : 0.0f;
  const float inverse_levels = levels > 0.0f ? 1.0f / levels : 0.0f;
  const float hold_increment = 1.0f / (1.0f + 31.0f * crush * crush);

  for (size_t n = 0; n < size; ++n) {
    // Record, unless the playing slice would be overwritten: a glitch
    // longer than the buffer (16 repeats of a 1/4 at 120 BPM is 8 s) holds
    // the recording still until it lets go, so it plays out in full. The
    // recording fades out where it stops and back in where it goes on, so
    // a later slice across the join has a 2 ms gap in it, not a click.
    if (!voice_.live &&
        write_ + 1 - voice_.start > kBufferSize - kOverwriteMargin) {
      if (!frozen_) {
        frozen_ = true;
        for (int32_t j = 0; j < kFadeLength; ++j) {
          buffer_[(write_ - uint32_t(j)) & kBufferMask] *=
              float(j) * (1.0f / float(kFadeLength));
        }
      }
    } else {
      if (frozen_) {
        frozen_ = false;
        thaw_position_ = 0;
      }
      ++write_;
      Frame x = in[n];
      if (thaw_position_ < kFadeLength) {
        x = x * (float(thaw_position_) * (1.0f / float(kFadeLength)));
        ++thaw_position_;
      }
      buffer_[write_ & kBufferMask] = x;
    }

    // A grid step?
    bool step = false;
    if (synced) {
      if (n) {
        phase += context.bar_increment;
        if (phase >= 1.0f) {
          phase -= 1.0f;
        }
      }
      const bool wrapped = phase + 0.5f < last_phase_;
      const int32_t index = int32_t(phase * inverse_step_bars);
      if (wrapped || index > last_step_) {
        step = true;
        last_step_ = index;
      }
      last_phase_ = phase;
    } else if (--countdown_ <= 0) {
      step = true;
      countdown_ = int32_t(step_samples);
    }
    pending_step_ = pending_step_ || step;

    // Change source only between fades: one crossfade at a time.
    if (!fading_) {
      if (pending_step_) {
        pending_step_ = false;
        OnStep(slice_samples, step_samples);
      } else if (!voice_.live) {
        // A slice faster than its step (sped up, or clamped shorter than
        // a long synced step) loops within the step. The slack lets the
        // grid step win the race at normal speed: one restart, not two.
        const float p = voice_.position;
        const float slack = float(kFadeLength);
        if ((voice_.direction > 0.0f && p >= slice_length_ + slack) ||
            (voice_.direction < 0.0f && p <= -slack)) {
          StartVoice(voice_.direction);
        }
      }
    }

    // Read and crossfade. Only the slices are crushed.
    Frame dry = MakeFrame(0.0f, 0.0f);
    Frame wet = MakeFrame(0.0f, 0.0f);
    float gain = 1.0f;
    if (fading_) {
      const float t = float(fade_position_) * (1.0f / float(kFadeLength));
      gain = QuarterSine(t);
      const float gain_out = QuarterSine(1.0f - t);
      if (previous_voice_.live) {
        dry = in[n] * gain_out;
      } else {
        wet = ReadVoice(previous_voice_) * gain_out;
        previous_voice_.position += previous_voice_.direction * rate;
      }
      if (++fade_position_ >= kFadeLength) {
        fading_ = false;
      }
    }
    if (voice_.live) {
      dry += in[n] * gain;
    } else {
      wet += ReadVoice(voice_) * gain;
      voice_.position += voice_.direction * rate;
    }

    if (crush > 0.0f && (!voice_.live || fading_)) {
      hold_phase_ += hold_increment;
      if (hold_phase_ >= 1.0f) {
        hold_phase_ -= 1.0f;
        hold_.l = floorf(wet.l * levels + 0.5f) * inverse_levels;
        hold_.r = floorf(wet.r * levels + 0.5f) * inverse_levels;
      }
      wet = hold_;
    }

    if (!fading_ && voice_.live) {
      out[n] = in[n];  // exactly the input between glitches
    } else {
      out[n] = dry + wet;
    }
    rate += rate_step;
  }
}

void Glitch::Format(int param, float value, const ProcessContext& context,
                    char* text, size_t size) const {
  switch (param) {
    case PARAM_SLICE:
      if (context.synced(param)) {
        FormatNoteValue(text, size, SyncedSliceIndex(value));
      } else {
        FormatSeconds(text, size, FreeSliceSeconds(value));
      }
      break;
    case PARAM_REPEATS:
      FormatNumber(text, size,
                   float(kRepeatCounts[StepIndex(value, kNumRepeatSteps)]), 0,
                   false, "x");
      break;
    case PARAM_PITCH:
      FormatSemitones(text, size, Bipolar(value, 24.0f), false);
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
