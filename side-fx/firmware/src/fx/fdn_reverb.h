// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: FDN VERB, an eight-line feedback delay network.
//
// Stereo in -> crossfading predelay -> bandwidth lowpass and LOWCUT
// highpass -> four allpass diffusers per side (a smooth onset instead of
// eight separate first echoes) -> eight delay lines of prime lengths, each
// with a slowly drifting length (MOD, against metallic ringing; read
// through an allpass interpolator, which has no loss at any fraction) and an
// absorptive one-pole set from DECAY and DAMP (Jot: every line loses the
// same dB per second, highs faster), mixed by an 8x8 Hadamard matrix.
// Left feeds and taps the even lines, right the odd ones; WIDTH scales the
// side signal. DECAY at the very top freezes: the loop turns lossless (but
// for a 0.5 Hz highpass against DC) and the input closes. SIZE (0.5 .. 2x) glides under a slew cap.

#ifndef SIDEFX_FX_FDN_REVERB_H_
#define SIDEFX_FX_FDN_REVERB_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "fx/plate_parts.h"

namespace sidefx {

class FdnReverb : public Block {
 public:
  enum {
    PARAM_DECAY,
    PARAM_SIZE,
    PARAM_PREDELAY,
    PARAM_DAMP,
    PARAM_WIDTH,
    PARAM_MOD,
    PARAM_LOWCUT,
    NUM_PARAMS
  };

  enum { kNumLines = 8, kNumDiffusers = 4 };

  FdnReverb() { }
  ~FdnReverb() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The mappings, public for the tests.
  static bool Frozen(float decay_value);
  static float Rt60(float value);       // seconds, below the freeze
  static float SizeRatio(float value);  // 0.5 .. 2
  static float PredelaySeconds(float value, const ProcessContext& context);
  static float LowcutHz(float value);

 private:
  reverb::CrossfadeDelay<Frame> predelay_;
  dsp::RingBuffer<float> diffuser_[2][kNumDiffusers];
  dsp::RingBuffer<float> line_[kNumLines];
  dsp::AllpassReader reader_[kNumLines];  // lossless fractional reads
  dsp::OnePole bandwidth_[2];
  dsp::OnePole input_lowcut_[2][2];
  dsp::OnePole loop_lowcut_[kNumLines];
  float damp_state_[kNumLines];
  float lfo_phase_[kNumLines];
  float modulation_[kNumLines];  // samples, the value at the last sample

  // Smoothed once per block.
  float size_;
  float decay_value_;
  float damp_value_;
  float freeze_;
  float input_gain_;
  float lowcut_;       // input highpass coefficient
  float loop_lowcut_coefficient_;
  float bandwidth_coefficient_;
  float width_;
  float mod_depth_;    // samples
  bool first_block_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_FDN_REVERB_H_
