// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: WAVESHAPER, a TEXTURE block. Drive into one of six shapers
// (SOFT, HARD, FOLD, RECTIFY, FUZZ, SINE) at twice the sample rate, with a
// bias for asymmetry (even harmonics) whose DC is taken out again, then a
// bit and sample-rate crusher that aliases on purpose, a dark..bright tone
// filter and an output trim. DRIVE is level compensated: turning it up
// changes the colour, not the loudness of a typical signal.
//
//   in -> gain -> 2x up -> + bias -> shaper -> - DC -> 2x down -> DC block
//      -> BITS -> RATE -> TONE -> LEVEL -> out

#ifndef SIDEFX_FX_WAVE_SHAPER_H_
#define SIDEFX_FX_WAVE_SHAPER_H_

#include "engine/block.h"
#include "fx/wave_shaper_dsp.h"

namespace sidefx {

class WaveShaper : public Block {
 public:
  enum Mode {
    MODE_SOFT,
    MODE_HARD,
    MODE_FOLD,
    MODE_RECTIFY,
    MODE_FUZZ,
    MODE_SINE,
    MODE_LAST
  };

  enum Param {
    PARAM_MODE,
    PARAM_DRIVE,
    PARAM_BIAS,
    PARAM_TONE,
    PARAM_BITS,
    PARAM_RATE,
    PARAM_LEVEL,
    PARAM_LAST
  };

  WaveShaper() { }
  ~WaveShaper() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The bare transfer curve of a mode, for the tests and the DC estimate.
  static float Shape(int mode, float x);

 private:
  struct Channel {
    dsp::Halfband2x up;
    dsp::Halfband2x down;
    dsp::DcBlocker dc;
    dsp::Svf bright;  // TONE's high shelf
    dsp::Svf dark;    // TONE's lowpass
    float held;  // RATE's sample and hold
  };

  Channel channel_[2];

  int mode_;
  int previous_mode_;
  float fade_;  // 0: previous_mode_ only .. 1: mode_ only
  bool first_block_;
  float hold_phase_;

  // Parameters smoothed at block rate (one-pole), in their own units.
  float drive_db_;
  float bias_;
  float tone_;
  float level_db_;

  // Per-sample ramps: the values reached at the end of the last block.
  float gain_;
  float offset_;
  float dc_new_;
  float dc_old_;
  float out_gain_;
  float dark_mix_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_WAVE_SHAPER_H_
