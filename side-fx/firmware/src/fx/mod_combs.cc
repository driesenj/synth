// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: MOD COMBS (see mod_combs.h).

#include "fx/mod_combs.h"

#include <math.h>

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  // 80 detents over 20 Hz..2 kHz (6.6 octaves): a semitone each.
  { "FREQ", 0.50f, 0, 0, 80 },
  // 99 detents of 2 % across -99..+99 %.
  { "FEEDBACK", 0.80f, PARAM_BIPOLAR, 0, 99 },
  { "RATE", 0.30f, PARAM_SYNC, 0, 0 },
  { "DEPTH", 0.30f, 0, 0, 100 },
  { "VOICES", 0.333333f, PARAM_STEPPED, 4, 0 },
  { "SPREAD", 0.70f, 0, 0, 100 },
  { "DAMP", 0.30f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "MOD COMBS", "COMBS", ModCombs::NUM_PARAMS, kParams, 0.50f, 0,
};

const char* const kVoiceLabels[] = {
  "1 VOICE", "2 VOICES", "3 VOICES", "4 VOICES" };

const float kMinFrequency = 20.0f;
const float kMaxFrequency = 2000.0f;
const float kMaxFeedback = 0.99f;
const float kMinRate = 0.02f;
const float kMaxRate = 10.0f;
const float kMaxDepthOctaves = 2.0f;
// DAMP: the loop lowpass from 16 kHz (open) down to 600 Hz.
const float kOpenDamp = 16000.0f;
const float kClosedDamp = 600.0f;
// Below -15 % feedback the line is half as long (see mod_combs.h).
const float kNegativeFeedbackKnee = 0.15f;

// ReadHermite() needs 1 .. size - 3 and reads before the write: D - 1.
const float kMinDelay = 2.0f;
const float kMaxDelay = float(ModCombs::kLineSize - 4);

// The base delay moves at most 0.4 samples per sample (the comb's pitch
// glides, the signal through it bends by at most 0.6..1.4) after a one-pole
// of about 7 ms.
const float kBaseSlewPerSample = 0.4f;

// The voices' LFO phase offsets glide at most a quarter of a cycle per
// second, so a VOICES or SPREAD change re-spaces them smoothly: a jump
// would move a voice's delay by up to all of DEPTH within one block and
// play it backwards, a chirp.
const float kOffsetSlewPerSample = 0.25f / kSampleRate;

// A stopped voice's line is cleared this much per block (16 blocks).
const size_t kClearPerBlock = 256;

// Voice v = 2 * k + c: c the channel (0 left, 1 right), k the pair.
// Detune at full SPREAD, cents (the pairs fan out, L and R mirrored).
const float kDetuneCents[ModCombs::kNumVoices] = {
  0.0f, 0.0f, 7.0f, -7.0f, -11.0f, 11.0f, 17.0f, -17.0f };
// Pan width at full SPREAD, the first pair widest.
const float kPanWidth[ModCombs::kMaxVoicesPerChannel] = {
  1.0f, 0.75f, 0.5f, 0.85f };

// Bars the synced LFO phase repeats over: every note value's cycles per
// bar times 48 is a whole number (16 bars for 4 BAR, 3 for the dotted).
const uint32_t kSyncBars = 48;

inline float OutputLimit(float x) {
  return 3.0f * dsp::SoftSaturate(x * (1.0f / 3.0f));
}

inline float Fraction(float x) {
  return x - floorf(x);
}

}  // namespace

const BlockInfo& ModCombs::info() const {
  return kInfo;
}

bool ModCombs::Init(Memory* memory) {
  for (int v = 0; v < kNumVoices; ++v) {
    float* buffer = memory->external->AllocateArray<float>(kLineSize);
    if (!buffer) {
      return false;
    }
    voice_[v].line.Init(buffer, kLineSize);
  }
  Reset();
  return true;
}

void ModCombs::Reset() {
  for (int v = 0; v < kNumVoices; ++v) {
    Voice& voice = voice_[v];
    voice.line.Clear();
    voice.damp.Reset();
    voice.delay = kMinDelay;
    voice.gain_l = voice.gain_r = 0.0f;
    voice.level = 0.0f;
    voice.offset = 0.0f;
    voice.running = false;
    voice.cleared = kLineSize;
  }
  dc_blocker_[0].Reset();
  dc_blocker_[1].Reset();
  phase_ = 0.0f;
  base_delay_ = kMinDelay;
  depth_ = 0.0f;
  spread_ = 0.0f;
  feedback_ = 0.0f;
  input_gain_ = 0.0f;
  last_bar_phase_ = 0.0f;
  bar_count_ = 0;
  num_running_ = 0;
  snap_ = true;
}

void ModCombs::Process(const ProcessContext& context, const float* params,
                       const Frame* in, Frame* out, size_t size) {
  if (size == 0) {
    return;
  }
  const float sample_rate = kSampleRate;
  const float inv_size = 1.0f / float(size);

  // --- control rate -------------------------------------------------------
  const float frequency = ExpMap(dsp::Clamp(params[PARAM_FREQ], 0.0f, 1.0f),
                                 kMinFrequency, kMaxFrequency);
  const float feedback = Bipolar(dsp::Clamp(params[PARAM_FEEDBACK], 0.0f,
                                            1.0f), kMaxFeedback);
  const bool rate_synced = context.synced(PARAM_RATE);
  const float rate = RateParam(dsp::Clamp(params[PARAM_RATE], 0.0f, 1.0f),
                               rate_synced, context.beat_seconds, kMinRate,
                               kMaxRate);
  const float depth_value = dsp::Clamp(params[PARAM_DEPTH], 0.0f, 1.0f);
  const float target_depth = kMaxDepthOctaves * depth_value * depth_value;
  const int num_voices = StepIndex(dsp::Clamp(params[PARAM_VOICES], 0.0f,
                                              1.0f), kMaxVoicesPerChannel) + 1;
  const float target_spread = dsp::Clamp(params[PARAM_SPREAD], 0.0f, 1.0f);
  const float damp = dsp::Clamp(params[PARAM_DAMP], 0.0f, 1.0f);
  const float damp_coefficient = dsp::OnePoleCoefficient(
      ExpMap(damp, kOpenDamp, kClosedDamp), sample_rate);

  // Negative feedback halves the line, so f stays the fundamental.
  const float negative = dsp::Clamp(-feedback * (1.0f /
                                    kNegativeFeedbackKnee), 0.0f, 1.0f);
  const float target_base = dsp::Clamp(
      sample_rate / frequency * (1.0f - 0.5f * negative), kMinDelay,
      kMaxDelay);
  // Unity gain for broadband input whatever the feedback: the comb's power
  // gain on noise is 1 / (1 - fb^2).
  const float input_gain = sqrtf(1.0f - feedback * feedback);

  // The bar position, for a synced LFO.
  if (context.bar_phase < last_bar_phase_ - 0.5f) {
    bar_count_ = (bar_count_ + 1) % kSyncBars;
  }
  last_bar_phase_ = context.bar_phase;

  if (snap_) {
    base_delay_ = target_base;
    depth_ = target_depth;
    spread_ = target_spread;
    feedback_ = feedback;
    input_gain_ = input_gain;
  } else {
    const float max_step = kBaseSlewPerSample * float(size);
    base_delay_ += dsp::Clamp(0.1f * (target_base - base_delay_), -max_step,
                              max_step);
    depth_ += 0.1f * (target_depth - depth_);
    spread_ += 0.05f * (target_spread - spread_);
  }

  const float increment = rate / sample_rate;
  if (rate_synced) {
    // Lock to the bar: a gentle phase-locked loop rather than a jump, so
    // syncing or a tempo change never steps the delays.
    const float cycles_per_bar = rate * 4.0f * context.beat_seconds;
    const float target = Fraction((float(bar_count_) + context.bar_phase) *
                                  cycles_per_bar);
    float error = target - phase_;
    error -= floorf(error + 0.5f);  // -0.5..0.5
    phase_ = Fraction(phase_ + (snap_ ? error : 0.05f * error));
  }
  const float phase_end = Fraction(phase_ + increment * float(size));

  const float feedback_increment = (feedback - feedback_) * inv_size;
  const float input_gain_increment = (input_gain - input_gain_) * inv_size;

  // The loop's lowpass delays the ring by its phase delay at the ring's
  // fundamental ((1 - c) / c samples at low frequencies, 12 at full DAMP):
  // the line is that much shorter, so the comb rings at FREQ whatever
  // DAMP. The fundamental is fs / D, or half that with negative feedback.
  const float pole = 1.0f - damp_coefficient;
  const float w = dsp::kTwoPi * (1.0f - 0.5f * negative) / base_delay_;
  const float damp_delay = atan2f(pole * sinf(w), 1.0f - pole * cosf(w)) / w;

  const float max_offset_step = kOffsetSlewPerSample * float(size);
  float delay_increment[kNumVoices];
  float gain_l_increment[kNumVoices];
  float gain_r_increment[kNumVoices];
  float gain_l_end[kNumVoices];
  float gain_r_end[kNumVoices];
  int running[kNumVoices];
  int num_running = 0;
  const float voice_norm = 1.0f / sqrtf(float(num_voices));
  for (int v = 0; v < kNumVoices; ++v) {
    Voice& voice = voice_[v];
    const int channel = v & 1;
    const int pair = v >> 1;
    const bool active = pair < num_voices;
    const float target_level = active ? 1.0f : 0.0f;
    voice.level = snap_ ? target_level
        : voice.level + 0.1f * (target_level - voice.level);
    if (voice.level < 1e-4f && !active) {
      voice.level = 0.0f;
    }

    // LFO phases: the left voices evenly spaced over half a cycle, each
    // right voice in antiphase to its left one, so all 2 N are evenly
    // spaced. They glide to a new spacing (a voice coming back from
    // silence takes its place at once); the inactive ones keep theirs
    // while they fade out.
    if (active) {
      const float target = spread_ * (float(pair) / float(2 * num_voices) +
                                      0.5f * float(channel));
      voice.offset = snap_ || !voice.running ? target
          : voice.offset + dsp::Clamp(target - voice.offset,
                                      -max_offset_step, max_offset_step);
    }
    const float lfo = dsp::Sine(Fraction(phase_end + voice.offset));
    const float octaves = depth_ * 0.5f * (1.0f + lfo) -
        spread_ * kDetuneCents[v] * (1.0f / 1200.0f);
    const float delay_end = dsp::Clamp(
        base_delay_ * exp2f(-octaves) - damp_delay, kMinDelay, kMaxDelay);
    if (snap_) {
      voice.delay = delay_end;
    }

    float pan_l, pan_r;
    const float side = channel ? 1.0f : -1.0f;
    dsp::PanGains(side * spread_ * kPanWidth[pair], &pan_l, &pan_r);
    const float g = voice.level * voice_norm * 0.7071f;
    gain_l_end[v] = pan_l * g;
    gain_r_end[v] = pan_r * g;
    if (snap_) {
      voice.gain_l = gain_l_end[v];
      voice.gain_r = gain_r_end[v];
    }
    gain_l_increment[v] = (gain_l_end[v] - voice.gain_l) * inv_size;
    gain_r_increment[v] = (gain_r_end[v] - voice.gain_r) * inv_size;

    // A voice faded out to nothing stops (no SDRAM reads or writes), its
    // line cleared a piece per block; one coming back finishes the clear
    // at once, so it starts silent rather than with its old ring.
    const bool run = active || voice.level > 0.0f ||
        voice.gain_l != 0.0f || voice.gain_r != 0.0f;
    if (run) {
      if (!voice.running && voice.cleared < kLineSize) {
        voice.line.ClearPart(voice.cleared, kLineSize - voice.cleared);
      }
      voice.cleared = 0;
      delay_increment[v] = (delay_end - voice.delay) * inv_size;
      running[num_running++] = v;
    } else {
      if (voice.running) {
        voice.damp.Reset();
      }
      if (voice.cleared < kLineSize) {
        voice.line.ClearPart(voice.cleared, kClearPerBlock);
        voice.cleared += kClearPerBlock;
      }
      voice.delay = delay_end;
    }
    voice.running = run;
  }
  snap_ = false;
  num_running_ = num_running;

  // --- audio rate ---------------------------------------------------------
  for (size_t i = 0; i < size; ++i) {
    feedback_ += feedback_increment;
    input_gain_ += input_gain_increment;
    const float x_l = dc_blocker_[0].Process(in[i].l) * input_gain_;
    const float x_r = dc_blocker_[1].Process(in[i].r) * input_gain_;
    float l = 0.0f;
    float r = 0.0f;
    for (int k = 0; k < num_running; ++k) {
      const int v = running[k];
      Voice& voice = voice_[v];
      voice.delay += delay_increment[v];
      voice.gain_l += gain_l_increment[v];
      voice.gain_r += gain_r_increment[v];
      const float y = voice.line.ReadHermite(voice.delay - 1.0f);
      const float w = (v & 1 ? x_r : x_l) +
          feedback_ * voice.damp.Lowpass(y, damp_coefficient);
      // Soft limit to +-2: the loop may ring forever at 99 % but no louder.
      voice.line.Write(2.0f * dsp::SoftSaturate(0.5f * w));
      l += y * voice.gain_l;
      r += y * voice.gain_r;
    }
    out[i].l = OutputLimit(l);
    out[i].r = OutputLimit(r);
  }
  // Exact end gains: a voice fading out ends on 0, and stops next block.
  for (int k = 0; k < num_running; ++k) {
    voice_[running[k]].gain_l = gain_l_end[running[k]];
    voice_[running[k]].gain_r = gain_r_end[running[k]];
  }
  // Free-running phase advance (a synced one is corrected next block).
  phase_ = phase_end;
}

void ModCombs::Format(int param, float value, const ProcessContext& context,
                      char* text, size_t size) const {
  value = dsp::Clamp(value, 0.0f, 1.0f);
  switch (param) {
    case PARAM_FREQ:
      FormatHz(text, size, ExpMap(value, kMinFrequency, kMaxFrequency));
      break;
    case PARAM_FEEDBACK:
      FormatNumber(text, size, Bipolar(value, kMaxFeedback * 100.0f), 0,
                   true, "%");
      break;
    case PARAM_RATE:
      if (context.synced(param)) {
        FormatNoteValue(text, size, SyncedRateIndex(value));
      } else {
        FormatHz(text, size, ExpMap(value, kMinRate, kMaxRate));
      }
      break;
    case PARAM_VOICES:
      FormatLabel(text, size, kVoiceLabels,
                  StepIndex(value, kMaxVoicesPerChannel));
      break;
    default:
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
