// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: GLITCH, a beat repeater. It records its input all the time
// (5.4 s; a glitch longer than that holds the recording still until it
// ends, so its slice is never overwritten). On every step of the SLICE grid (a note value locked to the
// bar, or 10 ms .. 2 s free) it rolls CHANCE: on a hit it takes the slice
// that has just gone by (or, with SHUFFLE, one further back on the grid)
// and plays it REPEATS steps long, restarting it on every step, each
// restart reversed with probability REVERSE. PITCH bends the repeats
// continuously from normal speed to +-24 semitones at the glitch's end (a
// tape stop below the centre, a riser above), CRUSH reduces their bits and
// sample rate. Between glitches the output is the input itself, so at the
// default MIX of 100 % it sits in the chain as an insert stutter.
//
// Every change of source (into a glitch, each restart, a loop of a sped-up
// slice, back to the input) is a 2 ms equal-power crossfade, the old source
// reading on past its end meanwhile.

#ifndef SIDEFX_FX_GLITCH_H_
#define SIDEFX_FX_GLITCH_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class Glitch : public Block {
 public:
  enum {
    PARAM_SLICE,
    PARAM_CHANCE,
    PARAM_REPEATS,
    PARAM_REVERSE,
    PARAM_PITCH,
    PARAM_CRUSH,
    PARAM_SHUFFLE,
    NUM_PARAMS
  };

  static const int kNumRepeatSteps = 8;

  Glitch() { }
  ~Glitch() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  bool glitching() const { return glitching_; }

 private:
  // Where a crossfade's two sides read: the input, or a slice from
  // `start` (absolute write index), `position` samples in, moving by
  // `direction` * rate per sample.
  struct Voice {
    bool live;
    uint32_t start;
    float position;
    float direction;
  };

  void OnStep(float slice_samples, float step_samples);
  void StartGlitch(float slice_samples, float step_samples);
  void StartVoice(float direction);
  void StartLive();
  Frame ReadVoice(const Voice& voice) const;

  Frame* buffer_;
  uint32_t write_;  // absolute index of the last frame written

  dsp::Random random_;

  Voice voice_;           // the one faded in
  Voice previous_voice_;  // the one fading out
  bool fading_;
  int32_t fade_position_;
  bool pending_step_;     // a grid step that came during a fade

  bool glitching_;
  int32_t repeats_left_;
  float slice_length_;    // samples, as captured
  float elapsed_;         // samples since the glitch started
  float duration_;        // its expected length in samples (pitch bend)

  // The parameters read at each step.
  float chance_;
  float reverse_;
  float shuffle_;
  int32_t repeats_;

  // Grid.
  bool grid_synced_;
  bool grid_fresh_;       // the first block after Reset() or a mode change
  float last_phase_;
  int32_t last_step_;
  int32_t countdown_;
  float grid_rate_;       // the steps per bar the last block counted

  // Recording held still for a glitch longer than the buffer, and the
  // fade back in when it goes on (samples into kFadeLength).
  bool frozen_;
  int32_t thaw_position_;

  // Crush: sample-and-hold phase and value.
  float hold_phase_;
  Frame hold_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_GLITCH_H_
