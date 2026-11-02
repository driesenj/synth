// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: a registry of fake blocks with the real blocks'
// names and parameter lists, for testing the engine, the app and the UI
// without any DSP. What a fake does with its input (FakeBlock::Kind):
//   type 0 of every slot  GAIN: wet = in * 2 * params[0]
//   type 1                ECHO: wet = in delayed by 64 samples, feedback 0.5
//                         (a tail that rings on after the send closes)
//   type 2                NAN: wet = NaN once params[0] > 0.99, else in
//   type 3                FREEZE: holds its last input while the send is off
//                         (as Beadsy: reads ProcessContext::send)
//   others                GAIN

#include "fake_registry.h"

#include <math.h>
#include <string.h>

namespace sidefx {

const char* const kSlotNames[NUM_SLOTS] = {
  "PITCH", "DELAY", "TEXTURE", "REVERB",
};

namespace {

const ParamInfo kParams0[] = {
  { "PITCH A", 0.645833f, PARAM_BIPOLAR, 0, 48 },
  { "PITCH B", 0.395833f, PARAM_BIPOLAR, 0, 48 },
  { "DETUNE", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "DELAY", 0.300000f, PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.200000f, 0, 0, 100 },
  { "WINDOW", 0.500000f, 0, 0, 0 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
};
const ParamInfo kParams1[] = {
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },
  { "SPREAD", 0.200000f, 0, 0, 100 },
  { "DENSITY", 0.500000f, 0, 0, 0 },
  { "SIZE", 0.400000f, 0, 0, 0 },
  { "DELAY", 0.200000f, PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.000000f, 0, 0, 100 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
};
const ParamInfo kParams2[] = {
  { "TIME L", 0.450000f, PARAM_SYNC, 0, 0 },
  { "TIME R", 0.500000f, PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.400000f, 0, 0, 100 },
  { "CROSS", 0.300000f, 0, 0, 100 },
  { "TONE", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "MOD", 0.100000f, 0, 0, 100 },
  { "WIDTH", 1.000000f, 0, 0, 100 },
};
const ParamInfo kParams3[] = {
  { "TIME", 0.450000f, PARAM_SYNC, 0, 0 },
  { "SPREAD", 0.600000f, PARAM_BIPOLAR, 0, 100 },
  { "FEEDBACK", 0.400000f, 0, 0, 100 },
  { "FREQ", 0.500000f, 0, 0, 0 },
  { "Q", 0.300000f, 0, 0, 100 },
  { "TILT", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
};
const ParamInfo kParams4[] = {
  { "TIME", 0.600000f, PARAM_SYNC, 0, 0 },
  { "PATTERN", 0.000000f, PARAM_STEPPED, 8, 0 },
  { "TAPS", 1.000000f, PARAM_STEPPED, 8, 0 },
  { "DECAY", 0.500000f, 0, 0, 100 },
  { "FEEDBACK", 0.200000f, 0, 0, 100 },
  { "SPREAD", 0.700000f, 0, 0, 100 },
  { "TONE", 0.500000f, PARAM_BIPOLAR, 0, 100 },
};
const ParamInfo kParams5[] = {
  { "TIME", 0.450000f, PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.450000f, 0, 0, 100 },
  { "HEADS", 0.000000f, PARAM_STEPPED, 7, 0 },
  { "WOBBLE", 0.250000f, 0, 0, 100 },
  { "DRIVE", 0.300000f, 0, 0, 100 },
  { "AGE", 0.400000f, 0, 0, 100 },
  { "WIDTH", 0.500000f, 0, 0, 100 },
};
const ParamInfo kParams6[] = {
  { "SLICE", 0.400000f, PARAM_SYNC, 0, 0 },
  { "CHANCE", 0.300000f, 0, 0, 100 },
  { "REPEATS", 0.300000f, PARAM_STEPPED, 8, 0 },
  { "REVERSE", 0.200000f, 0, 0, 100 },
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },
  { "CRUSH", 0.000000f, 0, 0, 100 },
  { "SHUFFLE", 0.200000f, 0, 0, 100 },
};
const ParamInfo kParams7[] = {
  { "FREQ", 0.500000f, 0, 0, 0 },
  { "FEEDBACK", 0.700000f, PARAM_BIPOLAR, 0, 100 },
  { "RATE", 0.300000f, PARAM_SYNC, 0, 0 },
  { "DEPTH", 0.400000f, 0, 0, 100 },
  { "VOICES", 0.330000f, PARAM_STEPPED, 4, 0 },
  { "SPREAD", 0.700000f, 0, 0, 100 },
  { "DAMP", 0.300000f, 0, 0, 100 },
};
const ParamInfo kParams8[] = {
  { "RATE", 0.350000f, PARAM_SYNC, 0, 0 },
  { "DEPTH", 0.700000f, 0, 0, 100 },
  { "CENTER", 0.500000f, 0, 0, 0 },
  { "FEEDBACK", 0.600000f, PARAM_BIPOLAR, 0, 100 },
  { "STAGES", 0.400000f, PARAM_STEPPED, 6, 0 },
  { "SPREAD", 0.500000f, 0, 0, 100 },
  { "SHAPE", 0.000000f, PARAM_STEPPED, 3, 0 },
};
const ParamInfo kParams9[] = {
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },
  { "CHORD", 0.000000f, PARAM_STEPPED, 10, 0 },
  { "DECAY", 0.500000f, 0, 0, 100 },
  { "DAMP", 0.400000f, 0, 0, 100 },
  { "DETUNE", 0.100000f, 0, 0, 100 },
  { "SPREAD", 0.600000f, 0, 0, 100 },
  { "DRIVE", 0.200000f, 0, 0, 100 },
};
const ParamInfo kParams10[] = {
  { "MODE", 0.000000f, PARAM_STEPPED, 6, 0 },
  { "DRIVE", 0.300000f, 0, 0, 100 },
  { "BIAS", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "TONE", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "BITS", 1.000000f, 0, 0, 100 },
  { "RATE", 1.000000f, 0, 0, 100 },
  { "LEVEL", 0.500000f, PARAM_BIPOLAR, 0, 100 },
};
const ParamInfo kParams11[] = {
  { "DRIVE", 0.300000f, 0, 0, 100 },
  { "WOW", 0.200000f, 0, 0, 100 },
  { "FLUTTER", 0.200000f, 0, 0, 100 },
  { "AGE", 0.300000f, 0, 0, 100 },
  { "HISS", 0.100000f, 0, 0, 100 },
  { "DROPOUT", 0.000000f, 0, 0, 100 },
  { "BUMP", 0.400000f, 0, 0, 100 },
};
const ParamInfo kParams12[] = {
  { "TIME", 0.300000f, 0, 0, 0 },
  { "SIZE", 0.500000f, 0, 0, 0 },
  { "SHAPE", 0.500000f, 0, 0, 0 },
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },
  { "DENSITY", 0.700000f, PARAM_BIPOLAR, 0, 0 },
  { "FEEDBACK", 0.200000f, 0, 0, 100 },
  { "REVERB", 0.300000f, 0, 0, 100 },
  { "QUALITY", 1.000000f, PARAM_STEPPED, 4, 0 },
  { "T RAND", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "P RAND", 0.500000f, PARAM_BIPOLAR, 0, 100 },
  { "FREEZE", 0.000000f, PARAM_STEPPED, 2, 0 },
};
const ParamInfo kParams13[] = {
  { "DECAY", 0.500000f, 0, 0, 100 },
  { "SIZE", 0.600000f, 0, 0, 100 },
  { "PREDELAY", 0.100000f, PARAM_SYNC, 0, 0 },
  { "DAMP", 0.400000f, 0, 0, 100 },
  { "DIFFUSE", 0.700000f, 0, 0, 100 },
  { "MOD", 0.300000f, 0, 0, 100 },
  { "LOWCUT", 0.100000f, 0, 0, 100 },
};
const ParamInfo kParams14[] = {
  { "DECAY", 0.500000f, 0, 0, 100 },
  { "SIZE", 0.600000f, 0, 0, 100 },
  { "DAMP", 0.400000f, 0, 0, 100 },
  { "LOWCUT", 0.100000f, 0, 0, 100 },
  { "MOD", 0.300000f, 0, 0, 100 },
  { "PREDELAY", 0.100000f, PARAM_SYNC, 0, 0 },
  { "WIDTH", 1.000000f, 0, 0, 100 },
};
const ParamInfo kParams15[] = {
  { "PITCH", 0.500000f, PARAM_BIPOLAR, 0, 48 },
  { "STRUCT", 0.300000f, 0, 0, 100 },
  { "DECAY", 0.500000f, 0, 0, 100 },
  { "BRIGHT", 0.500000f, 0, 0, 100 },
  { "DENSITY", 0.600000f, 0, 0, 100 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
  { "DRIFT", 0.200000f, 0, 0, 100 },
};
const ParamInfo kParams16[] = {
  { "LENGTH", 0.500000f, 0, 0, 100 },
  { "STAGES", 0.500000f, PARAM_STEPPED, 8, 0 },
  { "DIFFUSE", 0.600000f, 0, 0, 100 },
  { "FEEDBACK", 0.500000f, 0, 0, 100 },
  { "DAMP", 0.400000f, 0, 0, 100 },
  { "MOD", 0.300000f, 0, 0, 100 },
  { "WIDTH", 0.800000f, 0, 0, 100 },
};

struct FakeEntry {
  int slot;
  BlockInfo info;
};

FakeEntry kEntries[] = {
  { SLOT_PITCH, { "DUAL SHIFT", "SHIFT", 7, kParams0, 0.50f, 0 } },
  { SLOT_PITCH, { "GRANULATOR", "GRAIN", 7, kParams1, 0.50f, 0 } },
  { SLOT_DELAY, { "DUAL DELAY", "DUAL", 7, kParams2, 0.35f, 0 } },
  { SLOT_DELAY, { "BAND DELAY", "BAND", 7, kParams3, 0.35f, 0 } },
  { SLOT_DELAY, { "TAP DELAY", "TAPS", 7, kParams4, 0.35f, 0 } },
  { SLOT_DELAY, { "TAPE DELAY", "TAPE", 7, kParams5, 0.35f, 0 } },
  { SLOT_DELAY, { "GLITCH", "GLTCH", 7, kParams6, 1.00f, 0 } },
  { SLOT_DELAY, { "MOD COMBS", "COMBS", 7, kParams7, 0.50f, 0 } },
  { SLOT_TEXTURE, { "PHASER", "PHASE", 7, kParams8, 0.50f, 0 } },
  { SLOT_TEXTURE, { "RESONATOR", "RESO", 7, kParams9, 0.50f, 0 } },
  { SLOT_TEXTURE, { "WAVESHAPER", "SHAPE", 7, kParams10, 1.00f, 0 } },
  { SLOT_TEXTURE, { "TAPE SIM", "TSIM", 7, kParams11, 1.00f, 0 } },
  { SLOT_TEXTURE, { "BEADSY", "BEADS", 11, kParams12, 0.50f, BLOCK_HANDLES_SEND } },
  { SLOT_REVERB, { "PLATE", "PLATE", 7, kParams13, 0.35f, 0 } },
  { SLOT_REVERB, { "FDN VERB", "FDN", 7, kParams14, 0.35f, 0 } },
  { SLOT_REVERB, { "MODAL", "MODAL", 7, kParams15, 0.35f, 0 } },
  { SLOT_REVERB, { "APF CHAIN", "APF", 7, kParams16, 0.35f, 0 } },
};

const int kNumEntries = sizeof(kEntries) / sizeof(kEntries[0]);
const int kMaxTypes = 8;

FakeBlock fakes_[kNumEntries];
Block* blocks_[NUM_SLOTS][kMaxTypes];
int num_types_[NUM_SLOTS];

}  // namespace

bool FakeBlock::Init(Memory* memory) {
  echo_ = memory->external->AllocateArray<Frame>(kEchoLength);
  return echo_ != NULL;
}

void FakeBlock::Reset() {
  ++resets;
  memset(echo_, 0, sizeof(Frame) * kEchoLength);
  echo_index_ = 0;
  held_ = MakeFrame(0.0f, 0.0f);
}

void FakeBlock::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  ++process_calls;
  last_context = context;
  for (int i = 0; i < kNumSlotValues; ++i) {
    last_params[i] = params[i < info_.num_params ? i : 0];
  }
  for (size_t i = 0; i < size; ++i) {
    switch (kind_) {
      case KIND_ECHO: {
        Frame delayed = echo_[echo_index_];
        echo_[echo_index_] = in[i] + delayed * 0.5f;
        echo_index_ = (echo_index_ + 1) % kEchoLength;
        out[i] = delayed;
        break;
      }
      case KIND_NAN:
        if (params[0] > 0.99f) {
          out[i].l = out[i].r = nanf("");
        } else {
          out[i] = in[i];
        }
        break;
      case KIND_FREEZE:
        if (context.send >= 0.5f) {
          held_ = in[i];
        }
        out[i] = held_;
        break;
      default:
        out[i] = in[i] * (2.0f * params[0]);
        break;
    }
  }
}

void FakeBlock::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  if (info_.params[param].flags & PARAM_STEPPED) {
    FormatNumber(text, size, float(StepIndex(value, info_.params[param].num_steps) + 1), 0, false, "");
  } else if ((info_.params[param].flags & PARAM_SYNC) && context.synced(param)) {
    FormatNoteValue(text, size, NoteValueIndex(value));
  } else if (info_.params[param].flags & PARAM_BIPOLAR) {
    FormatBipolarPercent(text, size, value);
  } else {
    FormatPercent(text, size, value);
  }
}

bool InitBlocks(Memory* memory) {
  memset(blocks_, 0, sizeof(blocks_));
  memset(num_types_, 0, sizeof(num_types_));
  bool ok = true;
  for (int k = 0; k < kNumEntries; ++k) {
    const int slot = kEntries[k].slot;
    const int type = num_types_[slot];
    FakeBlock::Kind kind = type == 1 ? FakeBlock::KIND_ECHO
        : type == 2 ? FakeBlock::KIND_NAN
        : type == 3 ? FakeBlock::KIND_FREEZE : FakeBlock::KIND_GAIN;
    BlockInfo info = kEntries[k].info;
    if (kind == FakeBlock::KIND_FREEZE) {
      info.flags |= BLOCK_HANDLES_SEND;
    }
    kEntries[k].info = info;
    fakes_[k].Configure(kEntries[k].info, kind);
    blocks_[slot][num_types_[slot]++] = &fakes_[k];
    ok = fakes_[k].Init(memory) && ok;
  }
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

FakeBlock* GetFakeBlock(int slot, int type) {
  return static_cast<FakeBlock*>(GetBlock(slot, type));
}

}  // namespace sidefx
