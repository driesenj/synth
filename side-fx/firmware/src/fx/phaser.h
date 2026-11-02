// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: PHASER, a TEXTURE block. 2..12 first-order allpasses per
// channel, all on one swept corner frequency, with bipolar feedback around
// the chain. The block outputs the allpass chain only; the slot's MIX (50 %
// by default) adds the dry signal back, which is what digs the notches.
//
// The sweep is exponential: an LFO (sine, triangle or a smooth random walk)
// moves the corner +-2 octaves * DEPTH around CENTER. The coefficients are
// computed every kUpdatePeriod samples (a pitch-ratio table and a Pade tan,
// no expf) and interpolated linearly in between. When RATE is synced, the
// LFO is a phase-locked loop on the bar: it starts where the bar says and
// stays there through tempo changes.

#ifndef SIDEFX_FX_PHASER_H_
#define SIDEFX_FX_PHASER_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class Phaser : public Block {
 public:
  enum Param {
    PARAM_RATE,
    PARAM_DEPTH,
    PARAM_CENTER,
    PARAM_FEEDBACK,
    PARAM_STAGES,
    PARAM_SPREAD,
    PARAM_SHAPE,
    NUM_PARAMS
  };

  enum Shape {
    SHAPE_SINE,
    SHAPE_TRIANGLE,
    SHAPE_RANDOM,
    NUM_SHAPES
  };

  static const int kMaxStages = 12;
  static const int kNumStageSettings = 6;  // 2, 4 .. 12
  static const size_t kUpdatePeriod = 8;   // samples per coefficient update

  Phaser() { }
  ~Phaser() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // For the tests: the LFO's phase [0, 1) and the left channel's current
  // corner frequency in Hz.
  float lfo_phase() const { return phase_; }
  float corner_hz(int channel) const { return corner_hz_[channel]; }

 private:
  struct Channel {
    float stage[kMaxStages];  // allpass states
    float feedback;           // the last output, fed back
    dsp::DcBlocker dc;        // keeps DC out of the feedback
    float coefficient;        // the allpass coefficient now
  };

  float LfoValue(float phase, int shape, int channel) const;
  void AdvancePhase(float increment);
  float Coefficient(float hz) const;

  Channel channel_[2];

  float phase_;            // the LFO, [0, 1)
  int bar_count_;          // bars seen, modulo kBarCycle (synced locking)
  float last_bar_phase_;
  dsp::Random random_;
  float random_from_[2];   // the random walk's segment, per channel
  float random_to_[2];

  // Smoothed controls.
  float center_;           // the CENTER knob, 0..1
  float depth_;            // octaves, +- around center
  float feedback_;
  float spread_;           // 0..0.5 of a cycle
  float corner_hz_[2];

  int stages_;             // the stage count playing
  int stages_from_;        // the one it crossfades from
  float crossfade_;        // 0..1, 1 = all stages_

  bool primed_;            // false until the first Process() after Reset()
};

}  // namespace sidefx

#endif  // SIDEFX_FX_PHASER_H_
