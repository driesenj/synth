// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/preset.h"

#include <string.h>

#include "engine/algorithm.h"
#include "engine/crc32.h"
#include "engine/params.h"
#include "engine/registry.h"

namespace sidefx {

static_assert(sizeof(Preset) == kPresetSize, "the flash format is 512 bytes");
static_assert(sizeof(SlotPreset) == 56, "SlotPreset layout");

void InitSlot(Preset* preset, int slot, int type) {
  SlotPreset* s = &preset->slot[slot];
  s->type = uint8_t(type);
  s->sync_mask = 0;
  s->reserved0 = 0;
  s->reserved1 = 0;
  for (int i = 0; i < kNumSlotValues; ++i) {
    s->value[i] = 0;
    s->mod[i].source = MOD_OFF;
    s->mod[i].depth = 0;
  }
  const Block* block = GetBlock(slot, type);
  if (!block) {
    s->value[kMixValue] = PresetRaw(0.5f);
    return;
  }
  const BlockInfo& info = block->info();
  for (int i = 0; i < info.num_params && i < kMaxBlockParams; ++i) {
    s->value[i] = PresetRaw(info.params[i].default_value);
    if (info.params[i].flags & PARAM_SYNC) {
      s->sync_mask |= uint16_t(1u << i);
    }
  }
  s->value[kMixValue] = PresetRaw(info.default_mix);
}

void InitPreset(Preset* preset) {
  memset(preset, 0, sizeof(Preset));
  SetPresetName(preset, "INIT");
  preset->algorithm = ALGORITHM_SERIAL;
  preset->wet = 65535;
  preset->wet_mod.source = MOD_OFF;
  preset->tempo = 1200;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    preset->slot[s].send = 0;
    preset->slot[s].send_gate = MOD_OFF;
    InitSlot(preset, s, 0);
  }
  for (int i = 0; i < 2; ++i) {
    preset->lfo[i].rate = PresetRaw(0.4f);
    preset->lfo[i].shape = i == 0 ? LFO_SINE : LFO_TRIANGLE;
    preset->lfo[i].sync = 0;
  }
  preset->random.rate = PresetRaw(0.4f);
  preset->random.smooth = PresetRaw(0.5f);
  preset->random.sync = 0;
  preset->envelope.attack = PresetRaw(0.2f);
  preset->envelope.release = PresetRaw(0.4f);
  preset->envelope.gain = PresetRaw(0.25f);
  SealPreset(preset);
}

namespace {

void SanitizeAssign(ModAssign* m) {
  if (m->source >= NUM_MOD_SOURCES) {
    m->source = MOD_OFF;
  }
  if (m->depth > 100) {
    m->depth = 100;
  } else if (m->depth < -100) {
    m->depth = -100;
  }
}

}  // namespace

void SanitizePreset(Preset* preset) {
  if (preset->algorithm >= NUM_ALGORITHMS) {
    preset->algorithm = ALGORITHM_SERIAL;
  }
  preset->name[kPresetNameLength] = '\0';
  for (size_t i = 0; i < kPresetNameLength && preset->name[i]; ++i) {
    char c = preset->name[i];
    if (c < ' ' || c > '~') {
      preset->name[i] = ' ';
    }
  }
  if (preset->tempo < 300) {
    preset->tempo = 300;
  } else if (preset->tempo > 3000) {
    preset->tempo = 3000;
  }
  SanitizeAssign(&preset->wet_mod);
  for (int s = 0; s < NUM_SLOTS; ++s) {
    SlotPreset* slot = &preset->slot[s];
    if (slot->type >= NumBlockTypes(s)) {
      InitSlot(preset, s, 0);
    }
    slot->send = slot->send ? 1 : 0;
    if (slot->send_gate >= NUM_MOD_SOURCES) {
      slot->send_gate = MOD_OFF;
    }
    for (int i = 0; i < kNumSlotValues; ++i) {
      SanitizeAssign(&slot->mod[i]);
    }
  }
  for (int i = 0; i < 2; ++i) {
    if (preset->lfo[i].shape >= NUM_LFO_SHAPES) {
      preset->lfo[i].shape = LFO_SINE;
    }
    preset->lfo[i].sync = preset->lfo[i].sync ? 1 : 0;
  }
  preset->random.sync = preset->random.sync ? 1 : 0;
}

void SealPreset(Preset* preset) {
  preset->magic = kPresetMagic;
  preset->version = kPresetVersion;
  preset->crc = Crc32(0, preset, offsetof(Preset, crc));
}

bool PresetValid(const Preset& preset) {
  return preset.magic == kPresetMagic && preset.version == kPresetVersion &&
      preset.crc == Crc32(0, &preset, offsetof(Preset, crc));
}

void SetPresetName(Preset* preset, const char* name) {
  memset(preset->name, 0, sizeof(preset->name));
  for (size_t i = 0; i < kPresetNameLength && name[i]; ++i) {
    preset->name[i] = name[i];
  }
}

}  // namespace sidefx
