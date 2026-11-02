// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAPE DELAY. A Space Echo style tape loop: one record head
// (mono, (L+R)/2) and three playback heads at 1x, 2x and 3x the head-1
// time.
//
// Parameters:
//   TIME      head 1's time, 30 ms .. 2 s, or a note value when synced
//             (up to 3.6 s, all the tape holds for head 3; a longer one
//             plays 3.6 s and shows it).
//             Changes slew like a varispeed motor (0.3 s, in the log
//             domain so every head moves in proportion): the repeats bend
//             in pitch, down when the time grows.
//   FEEDBACK  0 .. 115 %: the active heads' sum (each 1/n of it) back to
//             the record head through the loop saturator; over ~90 % the
//             loop runs away into a held, saturated oscillation.
//   HEADS     1, 2, 3, 1+2, 2+3, 1+3, 1+2+3: the heads heard and fed back.
//   WOBBLE    wow (about 0.4 .. 1.9 Hz) plus flutter (6 .. 12 Hz), their
//             rates and depth drifting at random; up to 0.6 % of pitch.
//   DRIVE     tape saturation of the input (with a little asymmetry) and
//             a harder knee in the loop.
//   AGE       the record path loses highs (15 kHz .. 2.2 kHz, 12 dB/oct)
//             and lows (25 .. 280 Hz) on every pass, plus modulation noise
//             that follows the signal (so silence stays silent).
//   WIDTH     the active heads spread from the centre (0) to the full
//             stereo field (1): left to right in head order.

#ifndef SIDEFX_FX_TAPE_DELAY_H_
#define SIDEFX_FX_TAPE_DELAY_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "fx/dual_delay_line.h"

namespace sidefx {

class TapeDelay : public Block {
 public:
  TapeDelay() { }
  ~TapeDelay() { }

  enum Param {
    TIME,
    FEEDBACK,
    HEADS,
    WOBBLE,
    DRIVE,
    AGE,
    WIDTH,
    NUM_PARAMS
  };

  static const int kNumHeads = 3;
  static const int kNumHeadModes = 7;

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // Bit k set: head k + 1 plays in HEADS mode `mode`.
  static uint8_t HeadMask(int mode);
  static float FeedbackGain(float value);

 private:
  // Block-rate values ramped across each block.
  enum Ramp {
    RAMP_FEEDBACK,
    RAMP_DRIVE_GAIN,
    RAMP_DRIVE_BIAS,
    RAMP_DRIVE_MAKEUP,   // makeup / drive gain
    RAMP_LOOP_GAIN,
    RAMP_LOOP_INVERSE,
    RAMP_LOWPASS,
    RAMP_HIGHPASS,
    RAMP_NOISE,
    RAMP_WOW_1,          // wow depth in samples, per head
    RAMP_WOW_2,
    RAMP_WOW_3,
    RAMP_FLUTTER_1,      // flutter depth in samples, per head
    RAMP_FLUTTER_2,
    RAMP_FLUTTER_3,
    NUM_RAMPS
  };

  dsp::DelayLine16 line_;
  bool primed_;

  float head_delay_[kNumHeads];  // samples
  float head_slope_[kNumHeads];  // change per sample in this block

  float out_l_[kNumHeads];       // smoothed per sample
  float out_r_[kNumHeads];
  float fb_gain_[kNumHeads];

  float ramp_[NUM_RAMPS];        // values at the end of the last block

  float wow_phase_;
  float flutter_phase_;
  float wow_drift_;
  float wow_drift_target_;
  float flutter_drift_;
  float flutter_drift_target_;
  int drift_counter_;

  dsp::OnePole lowpass_[2];
  dsp::OnePole highpass_;
  float envelope_;
  dsp::Random random_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_TAPE_DELAY_H_
