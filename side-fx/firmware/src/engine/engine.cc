// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/engine.h"

#include <math.h>
#include <string.h>

#include "engine/registry.h"

namespace sidefx {

namespace {

const float kSlotFadeStep = float(kBlockSize) / (0.008f * kSampleRate);
const float kMuteStep = float(kBlockSize) / (0.010f * kSampleRate);
const float kAlgorithmFadeStep = float(kBlockSize) / (0.005f * kSampleRate);
const float kSendStep = 0.5f;           // a full swing in two blocks (1.3 ms)
// The input and output gains: +1 to -1 (a polarity flip) in 5 ms.
const float kGainStepPerSample = 2.0f / (0.005f * kSampleRate);
const float kMeterDecay = 0.9978f;      // per block: about 300 ms to fall 20 dB
const float kFaultThreshold = 1.0e6f;   // sum of |wet| over a block

inline void CompilerBarrier() {
  __asm__ __volatile__("" ::: "memory");
}

inline float StepToward(float from, float to, float max_step) {
  return to > from + max_step ? from + max_step
      : (to < from - max_step ? from - max_step : to);
}

inline float Clamp01(float x) {
  return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
}

// sin(t * pi / 2) for t in [0, 1]: Taylor to the 9th power, error < 4e-6.
inline float QuarterSine(float t) {
  const float t2 = t * t;
  return t * (1.5707963f + t2 * (-0.6459641f + t2 * (0.0796926f +
      t2 * (-0.0046818f + t2 * 0.0001604f))));
}

inline float Modulated(uint16_t raw, const ModAssign& m,
                       const ModValues& mods) {
  float v = PresetValue(raw);
  if (m.source != MOD_OFF && m.source < NUM_MOD_SOURCES && m.depth) {
    v += float(m.depth) * 0.01f * mods.value[m.source];
  }
  return Clamp01(v);
}

}  // namespace

float SoftLimit(float x) {
  const float a = fabsf(x);
  if (a <= 0.75f) {
    return x;
  }
  if (!(a < 1.0e9f)) {
    return x != x ? 0.0f : (x < 0.0f ? -1.0f : 1.0f);
  }
  const float e = (a - 0.75f) * 4.0f;
  const float y = 0.75f + 0.25f * e / (1.0f + e);
  return x < 0.0f ? -y : y;
}

bool Engine::Init(Memory* memory) {
  load_request_ = 0;
  master_state_ = MASTER_RUNNING;
  master_gain_ = 1.0f;
  algorithm_ = ALGORITHM_SERIAL;
  wet_value_ = 1.0f;
  wet_gain_ = 1.0f;
  dry_target_ = 1.0f;
  dry_gain_ = 1.0f;
  input_gain_ = 1.0f;
  output_gain_ = 1.0f;
  input_gain_target_ = 1.0f;
  output_gain_target_ = 1.0f;
  input_level_ = 0.0f;
  output_level_ = 0.0f;
  cycle_counter_ = NULL;
  cycles_per_second_ = 480.0e6f;
  memset(slot_, 0, sizeof(slot_));
  for (int s = 0; s < NUM_SLOTS; ++s) {
    slot_[s].pending_type = -1;
    slot_[s].state = SLOT_DETACHED;
  }
  bool ok = InitBlocks(memory);
  Preset preset;
  InitPreset(&preset);
  ApplyPresetNow(preset);
  return ok;
}

void Engine::ApplyPreset() {
  algorithm_ = preset_.algorithm < NUM_ALGORITHMS
      ? preset_.algorithm : ALGORITHM_SERIAL;
  for (int s = 0; s < NUM_SLOTS; ++s) {
    Slot& sl = slot_[s];
    const SlotPreset& sp = preset_.slot[s];
    sl.type = sp.type;
    sl.block = GetBlock(s, sl.type);
    if (sl.block) {
      sl.block->Reset();
    }
    sl.pending_type = -1;
    sl.request = REQUEST_NONE;
    sl.send_active = sp.send != 0;
    sl.gate_open = false;
    sl.send = sl.send_active ? 1.0f : 0.0f;
    const float m = PresetValue(sp.value[kMixValue]);
    sl.dry = QuarterSine(1.0f - m);
    sl.wet = QuarterSine(m);
    sl.fade = sl.block ? 1.0f : 0.0f;
    for (int i = 0; i < kNumSlotValues; ++i) {
      sl.values[i] = PresetValue(sp.value[i]);
    }
    sl.level = 0.0f;
    CompilerBarrier();
    sl.state = sl.block ? SLOT_ATTACHED : SLOT_DETACHED;
  }
  wet_gain_ = PresetValue(preset_.wet);
  wet_value_ = wet_gain_;
}

void Engine::ApplyPresetNow(const Preset& preset) {
  preset_ = preset;
  SanitizePreset(&preset_);
  ApplyPreset();
  load_request_ = 0;
  master_gain_ = 1.0f;
  master_state_ = MASTER_RUNNING;
}

void Engine::LoadPreset(const Preset& preset) {
  pending_preset_ = preset;
  CompilerBarrier();
  load_request_ = 1;
}

void Engine::SetBlockType(int slot, int type) {
  if (slot < 0 || slot >= NUM_SLOTS || type < 0 ||
      type >= NumBlockTypes(slot)) {
    return;
  }
  Slot& sl = slot_[slot];
  if (sl.request == REQUEST_NONE && type == sl.type) {
    return;
  }
  sl.pending_type = int8_t(type);
  CompilerBarrier();
  sl.request = REQUEST_TYPE;
}

int Engine::block_type(int slot) const {
  const Slot& sl = slot_[slot];
  return sl.request == REQUEST_TYPE && sl.pending_type >= 0
      ? sl.pending_type : sl.type;
}

Block* Engine::block(int slot) const {
  return GetBlock(slot, block_type(slot));
}

void Engine::ToggleSend(int slot) {
  preset_.slot[slot].send ^= 1;
}

void Engine::SetSend(int slot, bool on) {
  preset_.slot[slot].send = on ? 1 : 0;
}

void Engine::Poll() {
  if (master_state_ == MASTER_MUTED && load_request_) {
    preset_ = pending_preset_;
    SanitizePreset(&preset_);
    ApplyPreset();
    master_gain_ = 0.0f;
    load_request_ = 0;
    CompilerBarrier();
    master_state_ = MASTER_UNMUTING;
    return;
  }
  for (int s = 0; s < NUM_SLOTS; ++s) {
    Slot& sl = slot_[s];
    if (sl.state != SLOT_DETACHED) {
      continue;
    }
    if (sl.request == REQUEST_TYPE && sl.pending_type >= 0) {
      const int type = sl.pending_type;
      InitSlot(&preset_, s, type);
      sl.type = type;
      sl.block = GetBlock(s, type);
      const float m = PresetValue(preset_.slot[s].value[kMixValue]);
      sl.dry = QuarterSine(1.0f - m);
      sl.wet = QuarterSine(m);
      for (int i = 0; i < kNumSlotValues; ++i) {
        sl.values[i] = PresetValue(preset_.slot[s].value[i]);
      }
    }
    if (!sl.block) {
      continue;
    }
    sl.block->Reset();
    sl.fade = 0.0f;
    sl.pending_type = -1;
    sl.request = REQUEST_NONE;
    CompilerBarrier();
    sl.state = SLOT_FADING_IN;
  }
}

ProcessContext Engine::MakeContext(int slot,
                                   const TempoState& tempo) const {
  ProcessContext c;
  c.sample_rate = kSampleRate;
  c.beat_seconds = tempo.beat_seconds;
  c.bar_phase = tempo.bar_phase;
  c.bar_increment = tempo.bar_increment;
  c.external_clock = tempo.external;
  c.sync_mask = preset_.slot[slot].sync_mask;
  c.send = slot_[slot].send;
  return c;
}

void Engine::ComputeSlot(int slot, const ModValues& mods) {
  Slot& sl = slot_[slot];
  const SlotPreset& sp = preset_.slot[slot];
  if (sl.block && sl.state != SLOT_DETACHED) {
    const int n = sl.block->info().num_params;
    for (int i = 0; i < n && i < kMaxBlockParams; ++i) {
      sl.values[i] = Modulated(sp.value[i], sp.mod[i], mods);
    }
    sl.values[kMixValue] = Modulated(
        sp.value[kMixValue], sp.mod[kMixValue], mods);
  }
  bool gate = false;
  if (sp.send_gate != MOD_OFF && sp.send_gate < NUM_MOD_SOURCES) {
    const float g = mods.value[sp.send_gate];
    if (sl.gate_open) {
      sl.gate_open = g >= kGateOffThreshold;
    } else {
      sl.gate_open = g > kGateOnThreshold;
    }
    gate = sl.gate_open;
  } else {
    sl.gate_open = false;
  }
  sl.send_active = (sp.send != 0) != gate;
}

void Engine::RunSlot(int slot, const TempoState& tempo, const Frame* in,
                     Frame* out, float* unprocessed, size_t size) {
  Slot& sl = slot_[slot];
  uint8_t state = sl.state;
  if (state == SLOT_DETACHED || !sl.block) {
    for (size_t i = 0; i < size; ++i) {
      out[i] = in[i];
      unprocessed[i] = 1.0f;
    }
    sl.level *= kMeterDecay;
    sl.load *= 0.95f;
    return;
  }
  if (sl.request == REQUEST_TYPE &&
      (state == SLOT_ATTACHED || state == SLOT_FADING_IN)) {
    state = SLOT_FADING_OUT;
  }

  const float f0 = sl.fade;
  float f1 = f0;
  if (state == SLOT_FADING_OUT) {
    f1 = f0 - kSlotFadeStep;
    if (f1 < 0.0f) {
      f1 = 0.0f;
    }
  } else if (state == SLOT_FADING_IN) {
    f1 = f0 + kSlotFadeStep;
    if (f1 >= 1.0f) {
      f1 = 1.0f;
      state = SLOT_ATTACHED;
    }
  }
  const float g0 = sl.send;
  const float target = sl.send_active ? 1.0f : 0.0f;
  float g1 = target;
  if (g1 > g0 + kSendStep) {
    g1 = g0 + kSendStep;
  } else if (g1 < g0 - kSendStep) {
    g1 = g0 - kSendStep;
  }
  const float m = sl.values[kMixValue];
  const float a0 = sl.dry;
  const float b0 = sl.wet;
  const float a1 = QuarterSine(1.0f - m);
  const float b1 = QuarterSine(m);

  const bool handles_send = sl.block->info().flags & BLOCK_HANDLES_SEND;
  const float step = 1.0f / float(size);
  for (size_t i = 0; i < size; ++i) {
    const float t = float(i + 1) * step;
    const float f = f0 + (f1 - f0) * t;
    const float g = g0 + (g1 - g0) * t;
    block_in_[i] = in[i] * (handles_send ? f : g * f);
  }

  ProcessContext context = MakeContext(slot, tempo);
  context.send = g1;
  const uint32_t start = cycle_counter_ ? cycle_counter_() : 0;
  sl.block->Process(context, sl.values, block_in_, block_out_, size);
  if (cycle_counter_) {
    const float cycles = float(uint32_t(cycle_counter_() - start));
    const float period = float(size) / kSampleRate * cycles_per_second_;
    sl.load += 0.05f * (cycles / period - sl.load);
  }

  float sum = 0.0f;
  float peak = 0.0f;
  for (size_t i = 0; i < size; ++i) {
    const float l = fabsf(block_out_[i].l);
    const float r = fabsf(block_out_[i].r);
    sum += l + r;
    peak = l > peak ? l : peak;
    peak = r > peak ? r : peak;
  }
  if (!(sum < kFaultThreshold)) {
    // NaN, infinity or a runaway: bypass the slot until Poll() resets it.
    // A type change on its way out stays requested: Poll() resets the new
    // block anyway.
    ++sl.faults;
    sl.fade = 0.0f;
    if (sl.request != REQUEST_TYPE) {
      sl.request = REQUEST_RESET;
    }
    CompilerBarrier();
    sl.state = SLOT_DETACHED;
    for (size_t i = 0; i < size; ++i) {
      out[i] = in[i];
      unprocessed[i] = 1.0f;
    }
    return;
  }

  for (size_t i = 0; i < size; ++i) {
    const float t = float(i + 1) * step;
    const float f = f0 + (f1 - f0) * t;
    const float g = g0 + (g1 - g0) * t;
    const float a = a0 + (a1 - a0) * t;
    const float b = b0 + (b1 - b0) * t;
    const float passed = a + (1.0f - a) * (1.0f - g);
    const float dry = passed + (1.0f - passed) * (1.0f - f);
    const float wet = b * f;
    out[i] = in[i] * dry + block_out_[i] * wet;
    unprocessed[i] = dry;
  }
  peak *= b1 * f1;
  sl.level = peak > sl.level * kMeterDecay ? peak : sl.level * kMeterDecay;

  sl.fade = f1;
  sl.send = g1;
  sl.dry = a1;
  sl.wet = b1;
  if (state == SLOT_FADING_OUT && f1 <= 0.0f) {
    state = SLOT_DETACHED;
  }
  sl.state = state;
}

void Engine::RunBranch(const Branch& branch, const TempoState& tempo,
                       const Frame* in, Frame* out, float* unprocessed,
                       size_t size) {
  if (branch.length < 2) {
    RunSlot(branch.slot[0], tempo, in, out, unprocessed, size);
    return;
  }
  RunSlot(branch.slot[0], tempo, in, link_, link_unprocessed_, size);
  RunSlot(branch.slot[1], tempo, link_, out, unprocessed, size);
  for (size_t i = 0; i < size; ++i) {
    unprocessed[i] *= link_unprocessed_[i];
  }
}

void Engine::RunChunk(const ModValues& mods, const TempoState& tempo,
                      const Frame* in, Frame* out, size_t size) {
  // The master fade: preset loads and algorithm changes.
  uint8_t state = master_state_;
  if (state == MASTER_MUTED) {
    // Poll() owns the state now; it swaps the preset and unmutes.
    for (size_t i = 0; i < size; ++i) {
      out[i].l = out[i].r = 0.0f;
    }
    input_level_ *= kMeterDecay;
    output_level_ *= kMeterDecay;
    return;
  }
  if (load_request_ && state != MASTER_MUTING) {
    state = MASTER_MUTING;
  } else if (state == MASTER_RUNNING && preset_.algorithm != algorithm_) {
    state = MASTER_ALGORITHM_OUT;
  }
  const float master0 = master_gain_;
  float master1 = master0;
  switch (state) {
    case MASTER_RUNNING:
      master1 = 1.0f;
      break;
    case MASTER_ALGORITHM_OUT:
      master1 = master0 - kAlgorithmFadeStep;
      if (master1 <= 0.0f) {
        master1 = 0.0f;
        algorithm_ = preset_.algorithm < NUM_ALGORITHMS
            ? preset_.algorithm : ALGORITHM_SERIAL;
        state = MASTER_ALGORITHM_IN;
      }
      break;
    case MASTER_ALGORITHM_IN:
    case MASTER_UNMUTING:
      master1 = master0 + (state == MASTER_UNMUTING
          ? kMuteStep : kAlgorithmFadeStep);
      if (master1 >= 1.0f) {
        master1 = 1.0f;
        state = MASTER_RUNNING;
      }
      break;
    case MASTER_MUTING:
      master1 = master0 - kMuteStep;
      if (master1 <= 0.0f) {
        master1 = 0.0f;
        state = MASTER_MUTED;
      }
      break;
  }

  // The input and output gains glide to their settings.
  const float step = 1.0f / float(size);
  const float gain_step = kGainStepPerSample * float(size);
  const float in0 = input_gain_;
  const float in1 = StepToward(in0, input_gain_target_, gain_step);
  const float out0 = output_gain_;
  const float out1 = StepToward(out0, output_gain_target_, gain_step);
  float input_peak = 0.0f;
  for (size_t i = 0; i < size; ++i) {
    x_[i] = in[i] * (in0 + (in1 - in0) * float(i + 1) * step);
    const float l = fabsf(x_[i].l);
    const float r = fabsf(x_[i].r);
    input_peak = l > input_peak ? l : input_peak;
    input_peak = r > input_peak ? r : input_peak;
  }
  input_level_ = input_peak > input_level_ * kMeterDecay
      ? input_peak : input_level_ * kMeterDecay;

  for (int s = 0; s < NUM_SLOTS; ++s) {
    ComputeSlot(s, mods);
  }
  const float wet0 = wet_gain_;
  const float wet1 = Modulated(preset_.wet, preset_.wet_mod, mods);
  const float dry0 = dry_gain_;
  const float dry1 = Clamp01(dry_target_);

  const Topology& topology = GetTopology(algorithm_);
  if (topology.dual_mono) {
    for (size_t i = 0; i < size; ++i) {
      mono_in_[0][i].l = mono_in_[0][i].r = x_[i].l;
      mono_in_[1][i].l = mono_in_[1][i].r = x_[i].r;
    }
    const Stage& stage = topology.stage[0];
    for (int b = 0; b < 2; ++b) {
      RunBranch(stage.branch[b], tempo, mono_in_[b], branch_out_[b],
                branch_unprocessed_[b], size);
    }
    for (size_t i = 0; i < size; ++i) {
      const float t = float(i + 1) * step;
      const float wet = wet0 + (wet1 - wet0) * t;
      const float dry = dry0 + (dry1 - dry0) * t;
      const float a_l = branch_unprocessed_[0][i];
      const float a_r = branch_unprocessed_[1][i];
      const float c_l = 0.5f * (branch_out_[0][i].l + branch_out_[0][i].r);
      const float c_r = 0.5f * (branch_out_[1][i].l + branch_out_[1][i].r);
      out[i].l = dry * a_l * x_[i].l + wet * (c_l - a_l * x_[i].l);
      out[i].r = dry * a_r * x_[i].r + wet * (c_r - a_r * x_[i].r);
    }
  } else {
    for (size_t i = 0; i < size; ++i) {
      stage_in_[i] = x_[i];
      total_unprocessed_[i] = 1.0f;
    }
    for (int k = 0; k < topology.num_stages; ++k) {
      const Stage& stage = topology.stage[k];
      const int n = stage.num_branches;
      for (int b = 0; b < n; ++b) {
        RunBranch(stage.branch[b], tempo, stage_in_, branch_out_[b],
                  branch_unprocessed_[b], size);
      }
      if (n == 1) {
        for (size_t i = 0; i < size; ++i) {
          stage_in_[i] = branch_out_[0][i];
          total_unprocessed_[i] *= branch_unprocessed_[0][i];
        }
        continue;
      }
      const float inv_n = 1.0f / float(n);
      for (size_t i = 0; i < size; ++i) {
        const Frame u = stage_in_[i];
        Frame y = MakeFrame(0.0f, 0.0f);
        float mean = 0.0f;
        for (int b = 0; b < n; ++b) {
          const float a = branch_unprocessed_[b][i];
          y += branch_out_[b][i] - u * a;
          mean += a;
        }
        mean *= inv_n;
        stage_in_[i] = y + u * mean;
        total_unprocessed_[i] *= mean;
      }
    }
    for (size_t i = 0; i < size; ++i) {
      const float t = float(i + 1) * step;
      const float wet = wet0 + (wet1 - wet0) * t;
      const float dry = dry0 + (dry1 - dry0) * t;
      const Frame unprocessed = x_[i] * total_unprocessed_[i];
      out[i] = unprocessed * dry + (stage_in_[i] - unprocessed) * wet;
    }
  }

  float output_peak = 0.0f;
  for (size_t i = 0; i < size; ++i) {
    const float t = float(i + 1) * step;
    const float g = (master0 + (master1 - master0) * t) *
        (out0 + (out1 - out0) * t);
    out[i].l = SoftLimit(out[i].l * g);
    out[i].r = SoftLimit(out[i].r * g);
    const float l = fabsf(out[i].l);
    const float r = fabsf(out[i].r);
    output_peak = l > output_peak ? l : output_peak;
    output_peak = r > output_peak ? r : output_peak;
  }
  output_level_ = output_peak > output_level_ * kMeterDecay
      ? output_peak : output_level_ * kMeterDecay;

  wet_gain_ = wet1;
  wet_value_ = wet1;
  dry_gain_ = dry1;
  input_gain_ = in1;
  output_gain_ = out1;
  master_gain_ = master1;
  master_state_ = state;
}

void Engine::Process(const ModValues& mods, const TempoState& tempo,
                     const Frame* in, Frame* out, size_t size) {
  while (size) {
    const size_t n = size < kBlockSize ? size : kBlockSize;
    RunChunk(mods, tempo, in, out, n);
    in += n;
    out += n;
    size -= n;
  }
}

}  // namespace sidefx
