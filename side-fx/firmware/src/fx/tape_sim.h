// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: TAPE SIM, a TEXTURE block: a tape machine without the echo.
//
//   in -> transport (WOW, FLUTTER: a short modulated delay, the same for
//   both channels as both tracks share the tape) -> record emphasis ->
//   saturation with memory (DRIVE) -> de-emphasis -> head bump (BUMP) ->
//   + hiss (HISS) -> head and tape losses (AGE, DROPOUT) -> out
//
// AGE also raises the record emphasis, so an old tape squashes its highs
// before it loses them. The hiss follows the input's envelope (a slow
// release), so a slot fed silence goes quiet instead of hissing forever.

#ifndef SIDEFX_FX_TAPE_SIM_H_
#define SIDEFX_FX_TAPE_SIM_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "fx/wave_shaper_dsp.h"

namespace sidefx {

class TapeSim : public Block {
 public:
  enum Param {
    PARAM_DRIVE,
    PARAM_WOW,
    PARAM_FLUTTER,
    PARAM_AGE,
    PARAM_HISS,
    PARAM_DROPOUT,
    PARAM_BUMP,
    PARAM_LAST
  };

  // The transport's delay line: the deepest wow needs ~30 samples of swing.
  enum { kDelaySize = 256 };

  TapeSim() { }
  ~TapeSim() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // Peak pitch deviation (a fraction: 0.005 = 0.5 %) of WOW and FLUTTER.
  static float WowDepth(float value);
  static float FlutterDepth(float value);
  // BUMP's peak gain and frequency.
  static float BumpDecibels(float value);
  static float BumpHz(float value);

 private:
  struct Channel {
    float emphasis;      // the record emphasis' lowpass state
    float last_pre;      // the emphasised input one sample ago
    float magnet;        // the saturator's memory
    float de_emphasis;   // the playback de-emphasis' lowpass state
    dsp::Svf bump;
    dsp::OnePole low_cut;
    dsp::OnePole hiss_low_cut;
    dsp::Svf loss;
  };

  // Smoothed random wander, redrawn every `period` blocks.
  struct Wander {
    float value;
    float target;
    int countdown;
  };
  float UpdateWander(Wander* w, int period, float smoothing);

  dsp::RingBuffer<Frame> delay_;
  Frame* delay_buffer_;
  Channel channel_[2];
  dsp::Random random_;

  bool first_block_;
  float wow_phase_;
  float flutter_phase_;
  Wander wow_rate_;
  Wander wow_depth_;
  Wander flutter_rate_;
  Wander flutter_depth_;
  float wow_amplitude_;      // samples, smoothed
  float flutter_amplitude_;  // samples, smoothed
  float delay_samples_;      // the read delay at the end of the last block

  float drive_db_;
  float age_;
  float bump_;
  float hiss_level_;
  float drive_gain_;         // ramp state
  float out_gain_;           // ramp state
  float hiss_gain_;          // ramp state
  float bump_gain_;          // ramp state

  float envelope_;           // input level, for the hiss gate
  int dropout_remaining_;    // samples left in the current dropout
  float dropout_target_;
  float dropout_;            // 0 .. 0.9, the current dip
};

}  // namespace sidefx

#endif  // SIDEFX_FX_TAPE_SIM_H_
