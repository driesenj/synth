// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: PLATE, a Dattorro / Griesinger figure-eight plate reverb.
//
// Mono sum in -> crossfading predelay -> bandwidth lowpass and LOWCUT
// highpass -> four input allpass diffusers -> a tank of two halves, each a
// modulated allpass, a delay, damping, a second allpass and a second
// delay, each half feeding the other. The stereo output sums seven taps
// from both halves per side (Dattorro 1997, table 2). Every length scales
// with SIZE (0.5 .. 2x), which glides under a slew cap: a jump bends the
// pitch of the tail briefly instead of clicking. The tank's lines are read
// through allpass interpolators, which lose nothing at any fraction, so at
// DAMP 0 (no tank lowpass) a long tail keeps its highs; DECAY's top is an
// RT60 of 1000 s.

#ifndef SIDEFX_FX_PLATE_H_
#define SIDEFX_FX_PLATE_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "fx/plate_parts.h"

namespace sidefx {

class Plate : public Block {
 public:
  enum {
    PARAM_DECAY,
    PARAM_SIZE,
    PARAM_PREDELAY,
    PARAM_DAMP,
    PARAM_DIFFUSE,
    PARAM_MOD,
    PARAM_LOWCUT,
    NUM_PARAMS
  };

  Plate() { }
  ~Plate() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The mappings, public for the tests.
  static float Rt60(float value);       // seconds
  static float SizeRatio(float value);  // 0.5 .. 2
  static float PredelaySeconds(float value, const ProcessContext& context);
  static float LowcutHz(float value);

 private:
  struct Half {
    dsp::RingBuffer<float> ap1;     // modulated decay diffuser
    dsp::RingBuffer<float> delay1;
    dsp::RingBuffer<float> ap2;     // second decay diffuser
    dsp::RingBuffer<float> delay2;
    // The four lines' fractional reads (lossless; see Plate::Process).
    dsp::AllpassReader ap1_reader;
    dsp::AllpassReader delay1_reader;
    dsp::AllpassReader ap2_reader;
    dsp::AllpassReader delay2_reader;
    dsp::OnePole damp;
    dsp::OnePole lowcut;
  };

  struct Smoothed {
    float size;
    float decay;           // gain per decay multiplier
    float damp;            // tank lowpass coefficient
    float bandwidth;       // input lowpass coefficient
    float lowcut;          // input highpass coefficient
    float tank_lowcut;     // tank highpass coefficient
    float input_diffusion[2];
    float decay_diffusion[2];
    float mod_depth;       // samples
  };

  void Targets(const ProcessContext& context, const float* params,
               Smoothed* target) const;

  reverb::CrossfadeDelay<float> predelay_;
  dsp::RingBuffer<float> diffuser_[4];
  Half half_[2];
  dsp::OnePole bandwidth_;
  dsp::OnePole input_lowcut_[2];

  Smoothed state_;
  float lfo_phase_;
  bool first_block_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_PLATE_H_
