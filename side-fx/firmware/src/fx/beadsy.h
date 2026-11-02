// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: BEADSY, a granular texture: Mutable Instruments Beads' granular
// engine (beads::Processor, src/beads/dsp and vendor/beads), driven by the
// block's parameters instead of Beads' panel.
//
// The block records its input into Beads' 768 kB buffer and plays grains
// (up to 10) from it; SIZE at the top turns it into Beads' delay mode.
// Beads' own reverb follows. When the slot's send is off, or FREEZE is on,
// the buffer stops recording (Beads' freeze): the grains keep playing what
// it heard last, so a send button freezes a texture instead of starving it.
// In delay mode the send works as on any delay: off, the input fades out
// and the echoes ring out by FEEDBACK; only FREEZE freezes there, and that
// is Beads' slice looper (see TIME).
//
// Parameters (Beads' knobs; Beads' own smoothing and envelopes keep them
// click-free: grains take TIME, SIZE, SHAPE and PITCH when they start):
//   TIME      where grains start in the buffer, 0 .. its whole length (4 s
//             16-bit, 5.3 s 12-bit, 10.7 s clean tape, 16 s dirty tape).
//             Delay mode: the repeat time's multiplier, x1 .. x16; frozen
//             (FREEZE on), how far back the looped slice starts ("LOOP").
//   SIZE      grain length: 0 long and reversed, 1/3 shortest (8 ms), then
//             longer forwards up to 4 s; at the top Beads' delay mode.
//             With only 10 grains, a grain lasts at most about 7 grain
//             intervals (Beads' scheduler fades the 4 grains nearest their
//             end at every new one), so dense long clouds play shorter
//             grains than the readout says: at 20 Hz about 0.37 s.
//   SHAPE     grain envelope, from a hard gate through a bell to a reversed
//             ramp. Delay mode: the repeats' envelope.
//   PITCH     +-24 semitones, one per detent (continuous under modulation).
//   DENSITY   off in the middle; left of it regular grains (0.6 .. 130 Hz
//             towards the end), right random ones. Synced: Beads' SEED
//             input clocked by the tempo grid, 16ths divided by 1 .. 16 on
//             the left (counted from the bar, dotted values from every
//             third bar, so "1 BAR" lands on the downbeat), 16ths dropped
//             at random on the right. Delay mode: the repeat time (synced:
//             a fraction of the quarter note).
//   FEEDBACK  Beads' feedback, soft-limited (squared response).
//   REVERB    Beads' reverb; at 0 for 5 s it stops costing CPU.
//   QUALITY   DIRTY TAPE (8-bit mu-law, 24 kHz, wow and flutter), CLEAN
//             TAPE (12-bit, 24 kHz), LOFI 12BIT, HIFI 16BIT (48 kHz).
//   T RAND, P RAND  Beads' TIME and PITCH attenuverters with nothing
//             patched, with their law (a dead zone of 3 % either side of
//             the centre, then quadratic): clockwise scatters every grain
//             evenly by the amount ("SPRD"), anticlockwise pulls grains
//             towards a random value by a random amount, so some jump far
//             ("JUMP"). In delay mode both are random walks (fast
//             clockwise, slow anticlockwise).
//   FREEZE    OFF / ON: stop recording, as the send button does.
//
// QUALITY picks Beads' four media. Each stores the buffer in its own format,
// so a change fades the output out, clears the buffer a slice per audio
// block (~45 ms in all; clearing it at once would stall the interrupt) and
// fades back in. Frozen material does not survive a quality change. Under
// modulation QUALITY and FREEZE have a hysteresis of 0.05 past each step's
// boundary, and a QUALITY that comes back before the output has faded out
// keeps the buffer.
//
// Beads runs VINTAGE DIGITAL (LOFI 12BIT) with its codec at 32 kHz; the
// Seed's codec stays at 48 kHz, so here it runs at 48 kHz (less aliasing,
// 5.3 s of buffer instead of 8 s). The tape media decimate by 2 inside
// Beads' processor (its ENABLE_HARDWARE_24K is not defined), so DIRTY
// TAPE's wow and flutter are half as deep as Beads', and the DIRTY TAPE and
// LOFI 12BIT reverbs are smaller and brighter (see beads/dsp/processor.h).

#ifndef SIDEFX_FX_BEADSY_H_
#define SIDEFX_FX_BEADSY_H_

#include "engine/block.h"
#include "stmlib/stmlib.h"
#include "stmlib/dsp/hysteresis_quantizer.h"
#include "stmlib/utils/gate_flags.h"

namespace beads {
class Processor;
}  // namespace beads

namespace sidefx {

class Beadsy : public Block {
 public:
  enum Param {
    TIME,
    SIZE,
    SHAPE,
    PITCH,
    DENSITY,
    FEEDBACK,
    REVERB,
    QUALITY,
    TIME_RANDOM,
    PITCH_RANDOM,
    FREEZE,
    NUM_PARAMS
  };

  // QUALITY's values, in Beads' order (beads::Processor::Media).
  enum Quality {
    QUALITY_DIRTY_TAPE,
    QUALITY_CLEAN_TAPE,
    QUALITY_VINTAGE_12_BIT,
    QUALITY_DIGITAL_16_BIT,
    NUM_QUALITIES
  };

  Beadsy() { }
  ~Beadsy() { }

  const BlockInfo& info() const;
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  // For the tests: the medium the buffer holds now, whether the last block
  // was frozen, and whether a quality change is under way.
  int quality() const { return quality_; }
  bool frozen() const { return frozen_; }
  bool switching() const { return state_ != STATE_RUNNING; }

 private:
  enum State {
    STATE_RUNNING,
    STATE_FADING_OUT,
    STATE_CLEARING,
    STATE_FADING_IN
  };

  void ClearBuffer(int quality, size_t begin, size_t end);
  void ProcessChunk(const ProcessContext& context, const float* params,
                    const Frame* in, Frame* out, size_t size);
  void MakeSeedClock(const ProcessContext& context, size_t offset,
                     int unit, int division, stmlib::GateFlags* flags,
                     size_t size);

  beads::Processor* processor_;
  uint8_t* delay_buffer_[3];
  uint16_t* reverb_buffer_;

  State state_;
  int quality_;          // the medium the processor is configured for
  int target_quality_;   // the medium QUALITY asks for
  size_t clear_offset_;  // STATE_CLEARING: bytes of the buffer cleared
  float gain_;           // output fade around a quality change
  float input_gain_;     // recording fade after a quality change
  bool fresh_;           // nothing processed since Reset()
  bool freeze_on_;       // FREEZE (with hysteresis)
  bool frozen_;
  bool delay_mode_;      // the processor's mode (after Beads' transition)
  float send_;           // context.send at the end of the last chunk

  // The seed clock (synced DENSITY): 16ths counted over kSeedBars bars.
  stmlib::HysteresisQuantizer2 divider_quantizer_;
  stmlib::GateFlags previous_seed_;
  bool seed_running_;    // the last chunk made the seed clock
  bool pulse_on_;        // the current pulse of the clock is let through
  int seed_unit_;        // 16ths per pulse of the clock (1, or 4 in delay mode)
  int last_step_;        // the last 16th seen, 0 .. 16 * kSeedBars - 1
  int bar_count_;        // bars since Reset, modulo kSeedBars
  float last_bar_phase_;
  size_t sample_offset_;  // of the chunk within the block, for the seed clock

  DISALLOW_COPY_AND_ASSIGN(Beadsy);
};

}  // namespace sidefx

#endif  // SIDEFX_FX_BEADSY_H_
