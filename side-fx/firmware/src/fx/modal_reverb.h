// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: MODAL, a resonant body in the REVERB slot.
//
// Up to 32 two-pole resonators (coupled form: a damped rotation, so a mode
// keeps its amplitude when its frequency moves and pitch changes never
// click) tuned from PITCH and STRUCT. STRUCT morphs the partial ratios
// through four bodies: harmonic, stiff (stretched) string, bell and a
// rectangular plate. DECAY sets the fundamental's RT60, BRIGHT how much
// faster and quieter the high modes are, DENSITY how many modes sound,
// WIDTH how far the modes spread across the stereo field and DRIFT a slow
// random detune per mode.
//
// The coefficients are computed at control rate, a quarter of the modes
// per block (each mode every 4 blocks, 2.7 ms), and ramped across the
// block. Each mode's amplitude is limited (a mode saturates like a struck
// body pushed too hard instead of growing without bound on a sustained
// tone at its frequency): over the limit, it decays faster for the next
// block, smoothly. The output goes through a soft limiter.

#ifndef SIDEFX_FX_MODAL_REVERB_H_
#define SIDEFX_FX_MODAL_REVERB_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class ModalReverb : public Block {
 public:
  ModalReverb() { }
  ~ModalReverb() { }

  static const int kMaxModes = 32;
  static const int kNumBodies = 4;   // harmonic, string, bell, plate
  static const int kUpdateGroups = 4;

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

 private:
  // What the audio loop reads and writes per mode, kept together.
  struct Mode {
    float x, y;        // the rotating state; y is the output
    float c, s;        // r cos(w), r sin(w) now
    float c_target, s_target;
    float gain;        // input gain
    float pan_l, pan_r;
    float pan_l_target, pan_r_target;
    float drift_1, drift;   // two cascaded smoothers of drift_target
    float drift_target;
    float limiter;     // extra per-sample decay while over the limit, <= 1
    bool active;
  };

  void UpdateMode(int n, const ProcessContext& context, const float* params);

  Mode* modes_;
  // log2 of each body's partial ratios: [body * kMaxModes + mode].
  float* ratios_;
  float* mix_l_;     // kBlockSize accumulators
  float* mix_r_;
  float* excitation_;
  int group_;
  dsp::DcBlocker dc_blocker_;
  dsp::Random random_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_MODAL_REVERB_H_
