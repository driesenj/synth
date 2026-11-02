// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: BAND DELAY, four delays in four frequency bands.
//
// The input is split by four resonant bandpasses (stmlib Svf, normalised
// to unity peak gain) at FREQ * 2^{-1.8, -0.6, +0.6, +1.8} octaves. Every
// band has its own delay line, its own time (TIME scaled by a SPREAD
// ratio of 1/2..2) and its own feedback loop that runs back through its
// bandpass, so each repeat is narrower than the last and the bands drift
// apart in time: a dub echo that smears into pitched, filtered ghosts.
//
//   in -> [BP k] -> line k --+--> out (band k panned by WIDTH)
//           ^                |
//           +---- FB k ------+
//
// Delay-time changes glide (a slew-limited one-pole, pitch within 0.7..1.3
// of the input, the bend of a tape delay being turned) while they are
// small, and crossfade between two read heads over 40 ms when they are
// large, so a jump from 4 s to 10 ms never clicks or chirps.

#ifndef SIDEFX_FX_BAND_DELAY_H_
#define SIDEFX_FX_BAND_DELAY_H_

#include "engine/block.h"
#include "fx/dsp_util.h"
#include "stmlib/dsp/filter.h"

namespace sidefx {

class BandDelay : public Block {
 public:
  enum Params {
    PARAM_TIME,
    PARAM_SPREAD,
    PARAM_FEEDBACK,
    PARAM_FREQ,
    PARAM_Q,
    PARAM_TILT,
    PARAM_WIDTH,
    NUM_PARAMS
  };

  static const int kNumBands = 4;
  // 2^19 floats per band (2 MB, 8 MB in all): 10.9 s, room for the 4 s
  // TIME stretched 2x by SPREAD, 8 s.
  static const size_t kLineSize = 1u << 19;

  BandDelay() { }
  ~BandDelay() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // For the tests: band k's delay target in samples and centre in Hz, as
  // the last Process() computed them.
  float band_delay_target(int band) const { return band_[band].target; }
  float band_frequency(int band) const { return band_[band].frequency; }

 private:
  struct Band {
    dsp::RingBuffer<float> line;
    stmlib::Svf filter;
    float target;     // delay in samples (TIME * ratio * fs)
    float delay_a;    // the playing head, gliding toward target
    float delay_b;    // the head being faded in
    float fade;       // 0..1 while crossfading, < 0 when not
    float frequency;  // centre, Hz
    // Ramped across a block: input gain, feedback, output pan gains.
    float input_gain;
    float feedback;
    float gain_l;
    float gain_r;
  };

  // Band k's TIME ratio for spread -1..+1, quantised to rhythmic ratios
  // (1/2, 2/3, 3/4, 1, 4/3, 3/2, 2) when TIME follows the tempo.
  static float SpreadRatio(int band, float spread, bool synced);

  Band band_[kNumBands];
  float log_frequency_;  // smoothed log2(FREQ)
  float q_;              // smoothed Q
  float side_amount_;    // ramped WIDTH for the input split
  bool snap_;            // first block after Reset(): no glides
};

}  // namespace sidefx

#endif  // SIDEFX_FX_BAND_DELAY_H_
