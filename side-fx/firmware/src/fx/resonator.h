// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: RESONATOR, a TEXTURE block. Four tuned comb resonators
// (Karplus-Strong loops) playing a chord on a root note: each loop is a
// delay line read through an allpass fractional delay (lossless, so a
// 2 kHz voice can ring as long as a low one), a one-pole damping lowpass
// and a saturator, fed by the input. PITCH sets the root (C3 in the
// middle, +-24 semitones, so 1 V/oct CV into it tracks), CHORD the four
// voices' intervals, DECAY the fundamental's RT60, DAMP how much faster the
// overtones die (as far as a one-pole can while the fundamental still
// rings for DECAY: a long DECAY opens a dark DAMP up a little), DETUNE a cents spread, SPREAD the voices across the stereo
// field and DRIVE the saturation inside the loops.
//
// Tuning: the loop length is the period minus the damping filter's phase
// delay at the fundamental (computed per block), so the fundamental stays
// within a cent or so from 16 Hz to 4 kHz. Pitch and chord changes slide
// the loop length at a limited speed instead of jumping, which is what
// keeps them from clicking: CV steps of a few semitones land within a
// millisecond or two, big jumps become a short portamento, like a string
// being retuned.

#ifndef SIDEFX_FX_RESONATOR_H_
#define SIDEFX_FX_RESONATOR_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class Resonator : public Block {
 public:
  enum Param {
    PARAM_PITCH,
    PARAM_CHORD,
    PARAM_DECAY,
    PARAM_DAMP,
    PARAM_DETUNE,
    PARAM_SPREAD,
    PARAM_DRIVE,
    NUM_PARAMS
  };

  enum Chord {
    CHORD_UNISON,
    CHORD_OCTAVES,
    CHORD_FIFTHS,
    CHORD_MAJOR,
    CHORD_MINOR,
    CHORD_SUS4,
    CHORD_MAJ7,
    CHORD_MIN7,
    CHORD_ADD9,
    CHORD_CLUSTER,
    NUM_CHORDS
  };

  static const int kNumVoices = 4;
  // 4096 samples: 11.7 Hz, below the lowest voice (C3 - 24 - 12 = 16.35 Hz).
  static const size_t kDelaySize = 4096;

  Resonator() { }
  ~Resonator() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // For the tests: the voice's target fundamental in Hz.
  float voice_hz(int voice) const { return voice_hz_[voice]; }

 private:
  struct Voice {
    float delay;         // Hermite read delay, samples
    float feedback;      // loop gain
    float damp;          // one-pole lowpass coefficient
    float input_gain;
    float pan_l;
    float pan_r;
    float lowpass;       // the lowpass state
  };

  dsp::RingBuffer<float> line_[kNumVoices];
  dsp::AllpassReader reader_[kNumVoices];  // the loop's fractional read
  Voice voice_[kNumVoices];
  float voice_hz_[kNumVoices];
  dsp::DcBlocker dc_[2];
  float drive_;          // smoothed DRIVE, 0..1
  bool primed_;          // false until the first Process() after Reset()
};

}  // namespace sidefx

#endif  // SIDEFX_FX_RESONATOR_H_
