// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the block types each slot can run.
//
//   PITCH    DUAL SHIFT, GRANULATOR
//   DELAY    DUAL DELAY, BAND DELAY, TAP DELAY, TAPE DELAY, GLITCH, MOD COMBS
//   TEXTURE  PHASER, RESONATOR, WAVESHAPER, TAPE SIM, BEADSY
//   REVERB   PLATE, FDN VERB, MODAL, APF CHAIN
//
// The order is the order of SlotPreset::type, so it is part of the preset
// format: append new types, never reorder. registry.cc creates the real
// blocks; the host tests link test/fake_registry.cc instead.

#ifndef SIDEFX_ENGINE_REGISTRY_H_
#define SIDEFX_ENGINE_REGISTRY_H_

#include "engine/block.h"
#include "engine/memory.h"

namespace sidefx {

// Creates every block type in memory->internal and Init()s it. Once, at
// boot, before anything else here. False if an arena ran out.
bool InitBlocks(Memory* memory);

int NumBlockTypes(int slot);
Block* GetBlock(int slot, int type);  // NULL before InitBlocks or out of range

extern const char* const kSlotNames[NUM_SLOTS];  // "PITCH", "DELAY", "TEXTURE", "REVERB"

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_REGISTRY_H_
