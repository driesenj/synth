// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: what an effect block is.
//
// A block type (TAPE DELAY, PLATE, ...) is one class. The engine creates
// one object of each type at boot; a slot runs whichever type its preset
// names. A block produces only its wet signal: the engine sends it the
// slot's input (scaled by the slot's send), mixes its output with the dry
// signal by the slot's MIX, and keeps the send's trails (see engine.h).
//
// Threads:
//   Init(), Reset(), Format()  main loop
//   Process()                  audio interrupt, every kBlockSize samples
// Reset() is only called while the engine keeps the slot detached, so it
// may take a while (clearing megabytes of SDRAM is fine there).
//
// Rules for Process():
//   - no allocation, no blocking, no printf, no division by a parameter
//     that can be 0;
//   - finite output whatever the parameters and input (including +-4.0
//     input and 100 % feedback): soft-limit feedback paths;
//   - smooth what would click or zip when a parameter jumps: the engine
//     hands over new values once per block;
//   - stay within the block's CPU budget (see the block list in
//     side-fx/firmware/README.md).
// A non-finite output makes the engine bypass the slot and Reset() it.

#ifndef SIDEFX_ENGINE_BLOCK_H_
#define SIDEFX_ENGINE_BLOCK_H_

#include <stddef.h>
#include <stdint.h>

#include "engine/config.h"
#include "engine/frame.h"
#include "engine/memory.h"
#include "engine/params.h"

namespace sidefx {

enum BlockFlags {
  // The engine does not scale the block's input by the send; the block
  // reads ProcessContext::send itself (Beadsy freezes its buffer instead of
  // starving it, so the grains keep playing the last thing it heard).
  BLOCK_HANDLES_SEND = 1,
};

struct BlockInfo {
  const char* name;        // the block page's title, at most 10 characters ("TAPE DELAY")
  const char* short_name;  // the algorithm diagram's box, at most 5 characters ("TAPE")
  int num_params;          // <= kMaxBlockParams
  const ParamInfo* params;
  float default_mix;       // the slot's MIX when the type is chosen
  uint8_t flags;           // BlockFlags
};

struct ProcessContext {
  float sample_rate;       // kSampleRate
  float beat_seconds;      // one quarter note at the current tempo
  float bar_phase;         // position in a 4/4 bar at the block's first sample, [0, 1)
  float bar_increment;     // bar_phase advance per sample
  bool external_clock;     // the CLOCK jack or MIDI clock sets the tempo
  uint16_t sync_mask;      // bit n set: parameter n follows the tempo
  float send;              // the slot's send, 0..1 (smoothed); see BLOCK_HANDLES_SEND

  bool synced(int param) const { return (sync_mask >> param) & 1; }
};

class Block {
 public:
  Block() { }
  virtual ~Block() { }

  virtual const BlockInfo& info() const = 0;

  // Takes buffers from the arenas. False when they ran out.
  virtual bool Init(Memory* memory) = 0;

  // Clears every buffer and state: silence in gives silence out at once.
  virtual void Reset() = 0;

  // params[i], i < info().num_params: the modulated values, 0..1.
  // in and out never alias. out is the wet signal only.
  virtual void Process(const ProcessContext& context, const float* params,
                       const Frame* in, Frame* out, size_t size) = 0;

  // The text for parameter `param` at `value` ("350ms", "1/8.", "+7st",
  // "TRIANGLE"), at most 10 characters, using context's tempo and sync bits.
  virtual void Format(int param, float value, const ProcessContext& context,
                      char* text, size_t size) const = 0;
};

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_BLOCK_H_
