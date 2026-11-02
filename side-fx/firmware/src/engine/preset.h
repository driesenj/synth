// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: a preset, exactly as it sits in flash (512 bytes, little
// endian, no pointers). The live state the knobs edit is a Preset too
// (Engine::mutable_preset()); saving copies it into a bank slot.
//
// Values are 0..65535 for 0..1. A slot's values belong to its current
// type: choosing another type loads that type's defaults (InitSlot).
// Fields marked "reserved" are 0; a later version may use them, so keep
// them when copying.

#ifndef SIDEFX_ENGINE_PRESET_H_
#define SIDEFX_ENGINE_PRESET_H_

#include <stddef.h>
#include <stdint.h>

#include "engine/config.h"
#include "engine/modulation.h"

namespace sidefx {

const uint32_t kPresetMagic = 0x31584653;  // "SFX1"
const uint16_t kPresetVersion = 1;
const size_t kPresetSize = 512;
const size_t kPresetNameLength = 15;  // + terminating zero

struct SlotPreset {
  uint8_t type;        // index into the slot's block types (registry.h)
  uint8_t send;        // the send button's state: 1 = on
  uint8_t send_gate;   // ModSource the send follows as a gate (MOD_OFF: none)
  uint8_t reserved0;
  uint16_t sync_mask;  // bit n: value n follows the tempo (PARAM_SYNC only)
  uint16_t reserved1;
  uint16_t value[kNumSlotValues];  // [kMixValue] is the slot's MIX
  ModAssign mod[kNumSlotValues];
};

struct LfoPreset {
  uint16_t rate;   // 0..65535: 0.02..20 Hz, or a note value when synced
  uint8_t shape;   // LfoShape
  uint8_t sync;    // 1: rate follows the tempo
};

struct RandomPreset {
  uint16_t rate;    // like LfoPreset::rate
  uint16_t smooth;  // 0: steps, 65535: smooth glide between values
  uint8_t sync;
  uint8_t reserved[3];
};

struct EnvelopePreset {
  uint16_t attack;   // 0..65535: 1 ms..500 ms
  uint16_t release;  // 0..65535: 10 ms..5 s
  uint16_t gain;     // 0..65535: 0..+24 dB before the 0..1 output
  uint16_t reserved;
};

struct Preset {
  uint32_t magic;
  uint16_t version;
  uint8_t algorithm;  // Algorithm (engine.h)
  uint8_t reserved0;
  char name[kPresetNameLength + 1];
  uint16_t wet;       // the HOME page's WET: level of the processed signal
  ModAssign wet_mod;
  uint16_t tempo;     // internal tempo, BPM * 10 (300..3000)
  uint16_t reserved1;
  SlotPreset slot[NUM_SLOTS];
  LfoPreset lfo[2];
  RandomPreset random;
  EnvelopePreset envelope;
  uint8_t reserved[228];
  uint32_t crc;       // Crc32 of every byte before it
};

// The defaults: "INIT", serial, each slot on its first type with every send
// off. Needs the blocks (InitBlocks() in registry.h) for their defaults.
void InitPreset(Preset* preset);

// Sets slot `slot` to block type `type` with that type's defaults: values,
// MIX, sync bits on for every PARAM_SYNC parameter, no modulation. Keeps
// the send and its gate.
void InitSlot(Preset* preset, int slot, int type);

// Clamps every field into range, so a corrupt or older record cannot index
// out of a table: types, algorithm, sources, depths, shapes, tempo, name.
void SanitizePreset(Preset* preset);

// Sets magic, version and crc, ready to store.
void SealPreset(Preset* preset);

// Magic, version and crc all match.
bool PresetValid(const Preset& preset);

void SetPresetName(Preset* preset, const char* name);

inline float PresetValue(uint16_t raw) { return float(raw) * (1.0f / 65535.0f); }
inline uint16_t PresetRaw(float value) {
  return value <= 0.0f ? 0 : (value >= 1.0f ? 65535 : uint16_t(value * 65535.0f + 0.5f));
}

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_PRESET_H_
