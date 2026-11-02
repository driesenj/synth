// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the tempo as the audio code sees it, once per block
// (produced by app/tempo.h).

#ifndef SIDEFX_ENGINE_TEMPO_STATE_H_
#define SIDEFX_ENGINE_TEMPO_STATE_H_

namespace sidefx {

struct TempoState {
  float beat_seconds;   // one quarter note
  float bar_phase;      // position in a 4/4 bar at the block's first sample, [0, 1)
  float bar_increment;  // bar_phase advance per sample
  bool external;        // the CLOCK jack or MIDI clock sets the tempo
  // The bar started over in this block (MIDI START, or the first pulse
  // after a pause): bar_phase jumped to the downbeat, no wrap. Cycles
  // longer than a bar count their bars from here.
  bool downbeat;
};

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_TEMPO_STATE_H_
