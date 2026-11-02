// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/registry.h"

#include <string.h>

#include "fx/dual_shift.h"
#include "fx/granulator.h"
#include "fx/dual_delay.h"
#include "fx/band_delay.h"
#include "fx/tap_delay.h"
#include "fx/tape_delay.h"
#include "fx/glitch.h"
#include "fx/mod_combs.h"
#include "fx/phaser.h"
#include "fx/resonator.h"
#include "fx/wave_shaper.h"
#include "fx/tape_sim.h"
#include "fx/beadsy.h"
#include "fx/plate.h"
#include "fx/fdn_reverb.h"
#include "fx/modal_reverb.h"
#include "fx/apf_chain.h"

namespace sidefx {

const char* const kSlotNames[NUM_SLOTS] = {
  "PITCH", "DELAY", "TEXTURE", "REVERB",
};

namespace {

const int kMaxTypes = 8;

Block* blocks_[NUM_SLOTS][kMaxTypes];
int num_types_[NUM_SLOTS];

template<typename T>
bool Add(int slot, Memory* memory) {
  T* block = memory->internal->Create<T>();
  if (!block || num_types_[slot] >= kMaxTypes) {
    return false;
  }
  blocks_[slot][num_types_[slot]++] = block;
  return block->Init(memory);
}

}  // namespace

bool InitBlocks(Memory* memory) {
  memset(blocks_, 0, sizeof(blocks_));
  memset(num_types_, 0, sizeof(num_types_));
  bool ok = true;
  // The order is the preset format's: append, never reorder.
  ok = Add<DualShift>(SLOT_PITCH, memory) && ok;
  ok = Add<Granulator>(SLOT_PITCH, memory) && ok;
  ok = Add<DualDelay>(SLOT_DELAY, memory) && ok;
  ok = Add<BandDelay>(SLOT_DELAY, memory) && ok;
  ok = Add<TapDelay>(SLOT_DELAY, memory) && ok;
  ok = Add<TapeDelay>(SLOT_DELAY, memory) && ok;
  ok = Add<Glitch>(SLOT_DELAY, memory) && ok;
  ok = Add<ModCombs>(SLOT_DELAY, memory) && ok;
  ok = Add<Phaser>(SLOT_TEXTURE, memory) && ok;
  ok = Add<Resonator>(SLOT_TEXTURE, memory) && ok;
  ok = Add<WaveShaper>(SLOT_TEXTURE, memory) && ok;
  ok = Add<TapeSim>(SLOT_TEXTURE, memory) && ok;
  ok = Add<Beadsy>(SLOT_TEXTURE, memory) && ok;
  ok = Add<Plate>(SLOT_REVERB, memory) && ok;
  ok = Add<FdnReverb>(SLOT_REVERB, memory) && ok;
  ok = Add<ModalReverb>(SLOT_REVERB, memory) && ok;
  ok = Add<ApfChain>(SLOT_REVERB, memory) && ok;
  return ok;
}

int NumBlockTypes(int slot) {
  return slot >= 0 && slot < NUM_SLOTS ? num_types_[slot] : 0;
}

Block* GetBlock(int slot, int type) {
  if (slot < 0 || slot >= NUM_SLOTS || type < 0 || type >= num_types_[slot]) {
    return NULL;
  }
  return blocks_[slot][type];
}

}  // namespace sidefx
