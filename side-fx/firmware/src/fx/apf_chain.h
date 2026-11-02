// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: APF CHAIN, a series chain of Schroeder allpasses in the REVERB
// slot, with a feedback loop around it.
//
// Two chains (left and right) of 16 allpass stages each; STAGES picks where
// the output (and the feedback) is tapped: 2..16 stages. LENGTH scales the
// stage delays (1..100 ms per stage on average, prime-ish ratios, the right
// chain's different from the left's); synced, it sets the whole loop's
// period to a note value instead, so the smear repeats in time (up to what
// the tapped stages' buffers hold: about 0.58 s at 2 stages, 1.95 s at 8,
// 3.56 s at 16; a longer note value runs, and shows, that time). DIFFUSE is
// the allpass coefficient: 0 makes the chain a plain delay, high values
// with short LENGTH give metallic, dispersive, spring-like chirps.
// FEEDBACK (up to 0.98) runs the tapped output back to the chain's input
// through DAMP (a lowpass), a DC blocker and a soft saturator, for long
// dense smears and pads. MOD sways every fourth stage's delay with its own
// slow LFO; WIDTH cross-mixes the two chains (0: mono, 1: separate, with a
// rotation in the feedback that blends them less as WIDTH rises).
//
// Every stage of both chains always runs, even past the tap: a change of
// STAGES then crossfades between two live taps instead of switching to a
// stage with a stale buffer. Stages are processed a whole block at a time
// (each stage's delay is longer than one sample, so it only reads its own
// past), which keeps every stage's state in registers; the feedback
// therefore comes from the previous block, adding kBlockSize samples to
// the loop (accounted for when synced).
//
// LENGTH changes glide like tape: each stage's delay follows a one-pole
// with a slew limit chosen so the Doppler shift of all 16 stages together
// stays within an octave. At rest the delays are whole samples, so the
// unmodulated stages are exact allpasses; MOD sways every fourth stage,
// read with Hermite interpolation.

#ifndef SIDEFX_FX_APF_CHAIN_H_
#define SIDEFX_FX_APF_CHAIN_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class ApfChain : public Block {
 public:
  ApfChain() { }
  ~ApfChain() { }

  static const int kNumStages = 16;
  static const int kNumChains = 2;
  // Per stage: 16384 samples = 341 ms (the longest stage at LENGTH max is
  // 157 ms plus modulation; synced loops use the rest). 32 stages: 2 MB.
  static const size_t kStageBufferSize = 16384;

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

 private:
  void ProcessBlock(const ProcessContext& context, const float* params,
                    const Frame* in, Frame* out, size_t size);

  float* buffers_;     // kNumChains * kNumStages * kStageBufferSize
  float* delays_;      // each stage's gliding delay, in samples
  float* reads_;       // the delay each stage read at last (with MOD)
  float* phases_;      // each stage's LFO phase
  float* work_;        // kNumChains * kBlockSize: the signal through a chain
  float* tap_;         // kNumChains * kBlockSize: output at the current tap
  float* previous_tap_;  // kNumChains * kBlockSize: output at the old tap
  float* feedback_;    // kNumChains * kBlockSize: next block's feedback

  uint32_t write_;
  float diffusion_;
  float feedback_gain_;
  float mod_depth_;
  float width_;
  int stages_;
  int previous_stages_;
  float fade_;                // 0 (old tap) .. 1 (current tap)
  bool first_;

  dsp::OnePole damp_[kNumChains];
  dsp::DcBlocker dc_blocker_[kNumChains];
};

}  // namespace sidefx

#endif  // SIDEFX_FX_APF_CHAIN_H_
