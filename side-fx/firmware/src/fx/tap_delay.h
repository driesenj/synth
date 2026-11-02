// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAP DELAY, eight taps placed by a rhythm PATTERN inside a span
// TIME (50 ms .. 4 s, or a note value up to 5.4 s; a longer one plays
// 5.4 s and shows it). Tap 1 of every pattern sits at the end of the span
// and feeds back, so TAPS = 1 is a plain delay and the pattern repeats
// every span with FEEDBACK: a bar-long pattern stays on the grid however
// many times it comes round. DECAY makes later taps quieter,
// TONE darker (or brighter) and SPREAD throws them alternately left and
// right. The feedback is taken after the last tap's tone filter, so dark
// repeats keep getting darker, as on a dub delay.
//
// Time changes crossfade (21 ms) between the old and the new tap times
// instead of gliding: eight taps gliding at eight different speeds would
// smear into a pitch cluster. Changes within an external clock's jitter
// (16 samples + 0.3 %) are left alone, so a synced TIME does not
// crossfade at every clock pulse.

#ifndef SIDEFX_FX_TAP_DELAY_H_
#define SIDEFX_FX_TAP_DELAY_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class TapDelay : public Block {
 public:
  enum {
    PARAM_TIME,
    PARAM_PATTERN,
    PARAM_TAPS,
    PARAM_DECAY,
    PARAM_FEEDBACK,
    PARAM_SPREAD,
    PARAM_TONE,
    NUM_PARAMS
  };

  static const int kNumTaps = 8;
  static const int kNumPatterns = 8;

  TapDelay() { }
  ~TapDelay() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The delay of tap `tap` in samples at these settings (tests).
  static float TapDelaySamples(int pattern, int tap, float span_seconds);

 private:
  void UpdateTargets(int pattern, int num_taps, float span_seconds);
  void UpdateMix(int pattern, int num_taps);
  void UpdateTimes(int pattern, float span_seconds);

  dsp::RingBuffer<Frame> line_;

  // Tap times in samples: the ones playing and, during a crossfade, the
  // ones faded in.
  int32_t delay_[kNumTaps];
  int32_t next_delay_[kNumTaps];
  bool crossfading_;
  int32_t crossfade_position_;
  bool snap_;  // the first block after Reset() takes the times at once

  // Per tap: the stereo matrix (gain, decay, pan and spread folded in),
  // the smoothed target and the value reached at the end of the last
  // block (interpolated per sample in between).
  float target_[kNumTaps][4];
  float smoothed_[kNumTaps][4];
  float matrix_[kNumTaps][4];

  // Tone: a lowpass then a highpass per tap and channel.
  float lp_coefficient_[kNumTaps];
  float hp_coefficient_[kNumTaps];
  // Their targets, reached at the end of each block.
  float lp_target_[kNumTaps];
  float hp_target_[kNumTaps];
  float lp_[kNumTaps][2];
  float hp_[kNumTaps][2];

  float decay_;
  float spread_;
  float tone_;
  float feedback_;      // smoothed knob
  float feedback_gain_;  // reached at the end of the last block

  // What target_ and the filter targets were last computed from.
  int mix_pattern_;
  int mix_taps_;
  float mix_decay_;
  float mix_tone_;
  float mix_spread_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_TAP_DELAY_H_
