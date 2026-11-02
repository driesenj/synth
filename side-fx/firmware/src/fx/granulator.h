// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: GRANULATOR, a pitch-crowd granulator: one sound becomes a
// crowd of voices around a pitch.
//
// The mono sum of the input is recorded into a 5.4 s line. Grains start at
// DENSITY per second (randomly jittered, or on the tempo grid when DENSITY
// is synced), each reading from DELAY plus a random spread behind the write
// head, lasting SIZE with a smooth (4 t (1 - t))^2 envelope, at PITCH plus
// a random offset within SPREAD, panned at random within WIDTH. Up to 24
// grains sound at once; a 25th makes the oldest fade out in 64 samples and
// takes its place. FEEDBACK writes the grains back into the line (DC
// blocked, darkened, soft-saturated): grains of grains, a cloud that keeps
// climbing or falling by the grain pitch.
//
// The output is scaled by 1 / sqrt(overlap) so a dense crowd is about as
// loud as a single grain. The scale follows a rising overlap over a few
// tens of ms, as the new grains fade in, so the grains already sounding
// are never ducked at once.

#ifndef SIDEFX_FX_GRANULATOR_H_
#define SIDEFX_FX_GRANULATOR_H_

#include "engine/block.h"
#include "fx/dsp_util.h"

namespace sidefx {

class Granulator : public Block {
 public:
  enum Param {
    PITCH,
    SPREAD,
    DENSITY,
    SIZE,
    DELAY,
    FEEDBACK,
    WIDTH,
    NUM_PARAMS
  };

  static const int kMaxGrains = 24;

  Granulator() { }
  ~Granulator() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // The parameter mappings, shared with the tests.
  static float PitchSemitones(float value);
  static float SpreadSemitones(float value);
  static float DensityHz(float value, bool synced, float beat_seconds);
  static float SizeSeconds(float value, bool synced, float beat_seconds);
  static float DelaySeconds(float value, bool synced, float beat_seconds);

  int num_active_grains() const;
  // Grains started since Reset() (tests).
  uint32_t grains_triggered() const { return serial_; }

 private:
  struct Grain {
    bool active;
    bool releasing;
    uint32_t position;  // absolute line index of the next read
    float fraction;     // and the fraction past it
    float ratio;
    float phase;        // envelope, 0..1
    float increment;
    float release;      // 1, falling to 0 once stolen
    float gain_l;
    float gain_r;
    uint32_t serial;    // start order: the smallest is the oldest
  };

  void Trigger();
  void Place(int index, const Grain& grain);
  float ReadLine(uint32_t position, float fraction) const;

  float* line_;
  uint32_t write_;

  Grain grains_[kMaxGrains];
  Grain pending_;     // waits for a stolen grain's fade
  bool has_pending_;
  uint32_t serial_;

  // This block's mapped parameters, read by Trigger().
  float pitch_;
  float spread_;
  float size_samples_;
  float delay_samples_;
  float width_;

  // Free-running scheduler.
  float countdown_;
  // Tempo grid scheduler: the last grid line (in the 16-bar cycle; -1
  // before the first), the grid lines per bar it counted, and where in the
  // cycle the last sample was (bars).
  int32_t grid_index_;
  float grid_rate_;
  float last_bars_;
  uint32_t bar_count_;
  float last_bar_phase_;

  float overlap_;  // grains sounding at once, smoothed
  float normalization_;
  float feedback_;
  float feedback_sample_;
  float loop_lowpass_;
  dsp::OnePole lowpass_;
  dsp::DcBlocker dc_blocker_;
  dsp::Random random_;
  bool primed_;
};

}  // namespace sidefx

#endif  // SIDEFX_FX_GRANULATOR_H_
