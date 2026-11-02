// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: MOD COMBS, one to four modulated feedback combs per channel.
//
// Each voice is a short delay line read with 4-point Hermite interpolation,
// fed back through a one-pole lowpass (DAMP) and a soft limit:
//
//   in -> (+) -> line -> Hermite read at D -> out
//          ^                    |
//          +-- FB * LP(DAMP) ---+
//
// FREQ sets the comb's fundamental, 20 Hz..2 kHz exponentially:
// f = 20 * 100^FREQ (6.6 octaves, 80 detents of a semitone; 0.5 is 200 Hz),
// D = fs / f, less the DAMP lowpass's delay at f (up to 12 samples), so the
// pitch does not sag as DAMP rises. With positive feedback the comb rings at f and every
// harmonic. Negative feedback rings at the odd multiples of 1 / (2 D): the
// line is halved below -15 % (smoothly, from 0 to -15 %), so the
// fundamental stays at f and the even harmonics drop out, the hollow,
// square-ish tone.
//
// A sine LFO (RATE, 0.02..10 Hz or a note value locked to the bar) shortens
// each line by up to 2 * DEPTH^2 octaves: with little feedback and several
// voices that is a chorus, with one voice and more feedback a flanger
// sweeping up to two octaves. SPREAD gives the voices evenly spaced LFO
// phases (the left voices over half a cycle, each right voice in antiphase
// to its left one; they glide to a new spacing when VOICES changes), a few
// cents of detune and their pan positions; at 0 every voice moves together
// in the centre. Voices that VOICES leaves out fade, then stop: they cost
// nothing.

#ifndef SIDEFX_FX_MOD_COMBS_H_
#define SIDEFX_FX_MOD_COMBS_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class ModCombs : public Block {
 public:
  enum Params {
    PARAM_FREQ,
    PARAM_FEEDBACK,
    PARAM_RATE,
    PARAM_DEPTH,
    PARAM_VOICES,
    PARAM_SPREAD,
    PARAM_DAMP,
    NUM_PARAMS
  };

  static const int kMaxVoicesPerChannel = 4;
  static const int kNumVoices = 2 * kMaxVoicesPerChannel;
  // 4096 floats (16 kB) per voice: 85 ms, the 50 ms of 20 Hz plus detune.
  static const size_t kLineSize = 4096;

  ModCombs() { }
  ~ModCombs() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // For the tests: the LFO phase at the start of the next block, and voice
  // v's delay (samples) at the end of the last one.
  float lfo_phase() const { return phase_; }
  float voice_delay(int v) const { return voice_[v].delay; }
  // The voices the last block ran (the others are silent and cost nothing).
  int voices_running() const { return num_running_; }

 private:
  struct Voice {
    dsp::RingBuffer<float> line;
    dsp::OnePole damp;
    float delay;   // samples, interpolated across the block
    float gain_l;  // output gains, ramped across the block
    float gain_r;
    float level;   // smoothed on/off for VOICES
    float offset;  // LFO phase offset, gliding to its place
    bool running;  // processed in the last block
    size_t cleared;  // entries of the line cleared since it stopped
  };

  Voice voice_[kNumVoices];
  dsp::DcBlocker dc_blocker_[2];
  float phase_;          // LFO, 0..1
  float base_delay_;     // smoothed, slew-limited D
  float depth_;          // smoothed DEPTH in octaves
  float spread_;         // smoothed SPREAD
  float feedback_;       // ramped feedback
  float input_gain_;     // ramped
  float last_bar_phase_;
  uint32_t bar_count_;
  int num_running_;
  bool snap_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_MOD_COMBS_H_
