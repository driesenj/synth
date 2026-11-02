// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the four slots, their sends and mixes, and the algorithms that
// connect them.
//
// Per slot, with u its input, w = block(send * u) its wet signal, m its MIX
// and g its send (0..1, ramped over ~1.3 ms when toggled):
//
//   a = cos(m * pi/2), b = sin(m * pi/2)     equal-power dry/wet
//   dry = a + (1 - a) * (1 - g)              send off: the dry passes whole
//   y = dry * u + b * w                      ... and the wet keeps its trails
//
// So a send button engages its block: on, the slot mixes as its MIX says;
// off, the block hears nothing new, the signal passes, and whatever the
// block still holds (echoes, reverb tail, frozen grains) rings out on top.
//
// Branches in parallel would each pass the dry, so a stage subtracts each
// branch's own unprocessed part (the product of its slots' dry gains, A)
// and adds the input back once at the branches' mean A. The engine tracks
// that unprocessed part through the whole chain, which lets the global DRY
// and the preset's WET level it separately from everything processed:
//
//   out = DRY * A * x + WET * (chain(x) - A * x)
//
// DRY 100 % suits an insert; DRY 0 % makes a pure return for a mixer's send.
//
// Structural changes never happen inside the audio interrupt's work on a
// block: a slot whose type changes fades out (8 ms), is detached (passes
// its input), gets its new type and Reset() in the main loop (Poll()), and
// fades back in. Loading a preset mutes the output (10 ms), swaps the whole
// state and resets every slot in Poll(), then unmutes. An algorithm change
// dips the output for 5 ms each way; the blocks keep running through it.
//
// Threads: Process() runs in the audio interrupt. Init(), LoadPreset(),
// ApplyPresetNow(), SetBlockType() and Poll() run in the main loop.
// ToggleSend() and SetSend() may run anywhere (the control interrupt
// toggles sends directly). The UI edits values, mods, WET and the
// algorithm in mutable_preset() directly; every field is read once per
// audio block and 16-bit writes are atomic, so no lock is needed.

#ifndef SIDEFX_ENGINE_ENGINE_H_
#define SIDEFX_ENGINE_ENGINE_H_

#include <stddef.h>
#include <stdint.h>

#include "engine/algorithm.h"
#include "engine/block.h"
#include "engine/config.h"
#include "engine/frame.h"
#include "engine/memory.h"
#include "engine/modulation.h"
#include "engine/preset.h"
#include "engine/tempo_state.h"

namespace sidefx {

class Engine {
 public:
  Engine() { }
  ~Engine() { }

  // Creates and Init()s every block (InitBlocks), then applies InitPreset.
  // False when the arenas ran out.
  bool Init(Memory* memory);

  // Audio interrupt. in: IN 1 / IN 2 as l / r, out: OUT 1 / OUT 2. Any
  // size; works in kBlockSize pieces.
  void Process(const ModValues& mods, const TempoState& tempo,
               const Frame* in, Frame* out, size_t size);

  // Main loop: completes type changes, preset loads and fault resets.
  void Poll();

  Preset* mutable_preset() { return &preset_; }
  const Preset& preset() const { return preset_; }

  // Main loop: fades, swaps in `preset` (sanitized) and resets every slot.
  void LoadPreset(const Preset& preset);
  // Main loop, before the audio starts: the same, at once.
  void ApplyPresetNow(const Preset& preset);
  bool loading() const { return load_request_ != 0; }

  // Main loop: change a slot's block type; its values go to the type's
  // defaults (InitSlot). Shown at once by block_type() / block().
  void SetBlockType(int slot, int type);
  int block_type(int slot) const;
  Block* block(int slot) const;
  bool changing(int slot) const { return slot_[slot].request != REQUEST_NONE; }

  void ToggleSend(int slot);
  void SetSend(int slot, bool on);
  // The send as heard: the button's state, inverted while its gate is open.
  bool send_active(int slot) const { return slot_[slot].send_active; }

  // What the audio last used, for the screen.
  float value(int slot, int index) const { return slot_[slot].values[index]; }
  float wet_value() const { return wet_value_; }
  float slot_level(int slot) const { return slot_[slot].level; }
  float input_level() const { return input_level_; }
  float output_level() const { return output_level_; }
  // Share of the audio period the slot's block took, smoothed (needs a
  // cycle counter, see set_cycle_counter).
  float slot_load(int slot) const { return slot_[slot].load; }
  int faults(int slot) const { return slot_[slot].faults; }

  // The context a block's Format() needs, for the screen.
  ProcessContext MakeContext(int slot, const TempoState& tempo) const;

  // Settings: the global DRY level and the input / output gains (linear;
  // a negative output gain flips OUT 1 / OUT 2's polarity). The gains
  // glide (+1 to -1 takes 5 ms), so turning them or flipping the polarity
  // never steps the signal.
  void set_dry(float dry) { dry_target_ = dry; }
  void set_gains(float input, float output) {
    input_gain_target_ = input;
    output_gain_target_ = output;
  }
  // A free-running cycle counter (DWT->CYCCNT on the Seed) for slot_load().
  void set_cycle_counter(uint32_t (*counter)(), float cycles_per_second) {
    cycle_counter_ = counter;
    cycles_per_second_ = cycles_per_second;
  }

 private:
  enum SlotState {
    SLOT_ATTACHED,
    SLOT_FADING_OUT,
    SLOT_DETACHED,
    SLOT_FADING_IN,
  };

  enum SlotRequest {
    REQUEST_NONE,
    REQUEST_TYPE,   // fade out, then Poll() sets pending_type
    REQUEST_RESET,  // the block faulted: Poll() resets it
  };

  enum MasterState {
    MASTER_RUNNING,
    MASTER_ALGORITHM_OUT,  // fading out for an algorithm change
    MASTER_ALGORITHM_IN,
    MASTER_MUTING,         // fading out for a preset load
    MASTER_MUTED,          // Poll() swaps the preset
    MASTER_UNMUTING,
  };

  struct Slot {
    Block* block;               // what Process() runs
    int type;
    volatile uint8_t state;     // SlotState
    volatile uint8_t request;   // SlotRequest
    volatile int8_t pending_type;
    bool send_active;
    bool gate_open;
    float send;                 // ramped send gain g
    float dry;                  // a, from MIX
    float wet;                  // b, from MIX
    float fade;                 // 1 attached, 0 detached
    float values[kNumSlotValues];
    float level;
    float load;
    int faults;
  };

  void ApplyPreset();
  void ComputeSlot(int slot, const ModValues& mods);
  void RunSlot(int slot, const TempoState& tempo, const Frame* in, Frame* out,
               float* unprocessed, size_t size);
  void RunBranch(const Branch& branch, const TempoState& tempo,
                 const Frame* in, Frame* out, float* unprocessed, size_t size);
  void RunChunk(const ModValues& mods, const TempoState& tempo,
                const Frame* in, Frame* out, size_t size);

  Preset preset_;
  Preset pending_preset_;
  volatile uint8_t load_request_;
  volatile uint8_t master_state_;
  float master_gain_;
  int algorithm_;

  Slot slot_[NUM_SLOTS];

  float wet_value_;
  float wet_gain_;
  float dry_target_;
  float dry_gain_;
  float input_gain_;   // as used at the end of the last chunk
  float output_gain_;
  float input_gain_target_;
  float output_gain_target_;
  float input_level_;
  float output_level_;

  uint32_t (*cycle_counter_)();
  float cycles_per_second_;

  // Scratch for one kBlockSize chunk.
  Frame x_[kBlockSize];
  Frame stage_in_[kBlockSize];
  Frame branch_out_[4][kBlockSize];
  float branch_unprocessed_[4][kBlockSize];
  float total_unprocessed_[kBlockSize];
  Frame mono_in_[2][kBlockSize];
  Frame link_[kBlockSize];
  float link_unprocessed_[kBlockSize];
  Frame block_in_[kBlockSize];
  Frame block_out_[kBlockSize];
};

// The output stage's soft limiter: linear to 0.75, then a smooth knee that
// never passes +-1.
float SoftLimit(float x);

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_ENGINE_H_
