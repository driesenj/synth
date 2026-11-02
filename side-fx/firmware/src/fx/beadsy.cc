// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: BEADSY, Beads' granular engine as a TEXTURE block. See beadsy.h.

// Host tests: stmlib's ARM-only inline assembly (Clip16, Sqrt) has portable
// versions under TEST, which the host test build does not define.
#if defined(SIDEFX_HOST_TEST) && !defined(TEST)
#define TEST
#endif

#include "fx/beadsy.h"

#include <math.h>
#include <string.h>

#include <algorithm>

#include "beads/dsp/mu_law.h"
#include "beads/dsp/processor.h"
#include "stmlib/dsp/units.h"

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  { "TIME", 0.30f, 0, 0, 0 },
  { "SIZE", 0.50f, 0, 0, 0 },
  { "SHAPE", 0.50f, 0, 0, 100 },
  { "PITCH", 0.50f, PARAM_BIPOLAR, 0, 48 },
  { "DENSITY", 0.70f, PARAM_BIPOLAR | PARAM_SYNC, 0, 0 },
  { "FEEDBACK", 0.20f, 0, 0, 100 },
  { "REVERB", 0.30f, 0, 0, 100 },
  { "QUALITY", 1.00f, PARAM_STEPPED, 4, 0 },
  { "T RAND", 0.50f, PARAM_BIPOLAR, 0, 100 },
  { "P RAND", 0.50f, PARAM_BIPOLAR, 0, 100 },
  { "FREEZE", 0.00f, PARAM_STEPPED, 2, 0 },
};

const BlockInfo kInfo = {
  "BEADSY", "BEADS", Beadsy::NUM_PARAMS, kParams, 0.50f, BLOCK_HANDLES_SEND,
};

// Beads' buffer: three 256 kB banks (beads.cc: one 512 kB and one 256 kB
// array, the first split in two), the reverb's 32768 16-bit words.
const size_t kBankSize = 262144;
const size_t kNumBanks = 3;
const size_t kBufferBytes = kBankSize * kNumBanks;
const size_t kReverbBufferSize = 32768;
// beads::DelayLine keeps its freeze tail (256 stereo floats) at the end of
// the last bank.
const size_t kFreezeTailBytes = 256 * 2 * sizeof(float);

// A quality change clears the buffer 16 kB per audio block: 48 blocks, 32 ms.
const size_t kClearChunk = 16384;
// The output fades over 5 ms either side of it.
const float kFadeIncrement = 1.0f / 256.0f;

// The send counts as off (the buffer freezes) as soon as it starts to fall:
// the engine ramps it over ~1.3 ms, and Beads' freeze crossfades its own
// way back in (its freeze tail), so no fade of the recording is needed.
const float kSendOnThreshold = 0.999f;

// The seed clock when DENSITY is synced: Beads' SEED input, fed from the
// tempo grid. In granular mode DENSITY divides 16ths (left of centre) or
// drops them at random (right); in delay mode the clock is the quarter note
// and DENSITY picks Beads' ratio of it. The 16ths are counted over three
// bars, which every division of Beads' divides (48 = its pulse counter's
// modulo): the dotted ones meet the bar again every third bar.
const int kSeedBars = 3;
const int kSeedSteps = 16 * kSeedBars;
const int kGranularSeedUnit = 1;  // 16ths per pulse
const int kDelaySeedUnit = 4;
// TriggerGenerator::RenderDivider's divisions and their quantizer.
const int kDivisionRatios[] = { 1, 2, 3, 4, 6, 8, 12, 16 };
const int kNumDivisionRatios = 8;
const float kDividerHysteresis = 0.075f;

// QUALITY and FREEZE under modulation: a new step only once the value is
// this far past the boundary.
const float kStepHysteresis = 0.05f;

// Seconds of audio the buffer holds in each medium, at the codec rate:
// 768000 bytes of 8-bit (24 kHz), 12-bit (24 kHz), 12-bit and 16-bit stereo.
const float kBufferSeconds[Beadsy::NUM_QUALITIES] = {
  384000.0f / (beads::kCodecSampleRate * 0.5f),
  256000.0f / (beads::kCodecSampleRate * 0.5f),
  256000.0f / beads::kCodecSampleRate,
  192000.0f / beads::kCodecSampleRate,
};

const char* const kQualityLabels[] = {
  "DIRTY TAPE", "CLEAN TAPE", "LOFI 12BIT", "HIFI 16BIT",
};

const char* const kFreezeLabels[] = { "OFF", "ON" };

// Synced DENSITY in granular mode: Beads' divider ratios of the 16th note.
const char* const kDividerLabels[] = {
  "1/16", "1/8", "1/8.", "1/4", "1/4.", "1/2", "1/2.", "1 BAR",
};

// Synced DENSITY in delay mode: Beads' kRatio table (delay_controller.cc)
// as fractions of the quarter-note clock.
const char* const kDelayRatioLabels[] = {
  "1/64", "1/64", "1/32", "1/32", "1/16", "1/16", "1/8", "1/8", "1/4", "1/4",
  "1/4", "1/4", "1/8", "1/8T", "1/16", "1/16T", "1/32", "1/40", "1/32T",
  "1/64", "1/64",
};

// Beads' DENSITY: no grains in the middle (0.48 .. 0.52).
const float kDensityDeadLow = 0.48f;
const float kDensityDeadHigh = 0.52f;
const float kMaxGrainFrequency = 130.81278f;  // trigger_generator.cc

inline float Clamp01(float x) {
  return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
}

// Beads' attenuverter pots (cv_reader.h, LAW_ATTENUVERTER): 0 within 3 % of
// the centre, then quadratic, +-1 at the ends.
inline float Attenuverter(float value) {
  const float v = Clamp01(value) - 0.5f;
  const float a = (2.0f / 0.47f) * v * std::max(fabsf(v) - 0.03f, 0.0f);
  return a < -1.0f ? -1.0f : (a > 1.0f ? 1.0f : a);
}

// StepIndex with hysteresis: `current` holds until the value is more than
// kStepHysteresis past the boundary of its step.
int StepIndexFrom(float value, int num_steps, int current) {
  const float x = value * float(num_steps - 1);
  if (current >= 0 && current < num_steps &&
      fabsf(x - float(current)) <
          0.5f + kStepHysteresis * float(num_steps - 1)) {
    return current;
  }
  return StepIndex(value, num_steps);
}

// Silence in each medium's format: 0 for the 12- and 16-bit ones, mu-law
// zero for the 8-bit one.
inline uint8_t SilenceByte(int quality) {
  return quality == Beadsy::QUALITY_DIRTY_TAPE ? beads::Lin2MuLaw(0) : 0;
}

// Writes `prefix` and returns its length, so a formatter can follow it.
size_t Prefix(char* text, size_t size, const char* prefix) {
  CopyText(text, size, prefix);
  return strlen(text);
}

}  // namespace

const BlockInfo& Beadsy::info() const {
  return kInfo;
}

bool Beadsy::Init(Memory* memory) {
  // The processor is 8.2 kB, more than a block's share of the internal
  // arena: it lives in SDRAM. Only the active medium's grains (~1 kB) are
  // touched every sample, so they stay in the D-cache.
  processor_ = memory->external->Create<beads::Processor>();
  for (size_t i = 0; i < kNumBanks; ++i) {
    delay_buffer_[i] = memory->external->AllocateArray<uint8_t>(kBankSize);
  }
  reverb_buffer_ = memory->external->AllocateArray<uint16_t>(
      kReverbBufferSize);
  if (!processor_ || !delay_buffer_[0] || !delay_buffer_[1] ||
      !delay_buffer_[2] || !reverb_buffer_) {
    return false;
  }
  // Once, at boot: sets up the delay lines' pointers (and clears the
  // buffer once per delay line and medium, as Beads does).
  processor_->Init(delay_buffer_, reverb_buffer_);
  quality_ = target_quality_ = QUALITY_DIGITAL_16_BIT;
  Reset();
  return true;
}

void Beadsy::Reset() {
  // Every medium's state back to Beads' Init(), without its clears of the
  // buffer: one pass over it here (this is the main loop, with the slot
  // muted), and the reverb's 64 kB tank.
  processor_->Init(delay_buffer_, reverb_buffer_, false);
  quality_ = target_quality_;
  ClearBuffer(quality_, 0, kBufferBytes);
  processor_->Configure(beads::Processor::Media(quality_), false, false);
  state_ = STATE_RUNNING;
  clear_offset_ = 0;
  gain_ = 1.0f;
  input_gain_ = 1.0f;
  fresh_ = true;
  freeze_on_ = false;
  frozen_ = false;
  delay_mode_ = false;
  send_ = 0.0f;
  divider_quantizer_.Init(kNumDivisionRatios, kDividerHysteresis, false);
  previous_seed_ = stmlib::GATE_FLAG_LOW;
  seed_running_ = false;
  pulse_on_ = false;
  seed_unit_ = kGranularSeedUnit;
  last_step_ = 0;
  bar_count_ = 0;
  last_bar_phase_ = 0.0f;
}

void Beadsy::ClearBuffer(int quality, size_t begin, size_t end) {
  // The freeze tail (floats) is cleared to 0 last.
  const uint8_t silence = SilenceByte(quality);
  while (begin < end) {
    const size_t bank = begin / kBankSize;
    const size_t offset = begin % kBankSize;
    size_t n = kBankSize - offset;
    if (n > end - begin) {
      n = end - begin;
    }
    memset(delay_buffer_[bank] + offset, silence, n);
    begin += n;
  }
  if (end == kBufferBytes) {
    memset(delay_buffer_[kNumBanks - 1] + kBankSize - kFreezeTailBytes, 0,
           kFreezeTailBytes);
  }
}

void Beadsy::MakeSeedClock(const ProcessContext& context, size_t offset,
                           int unit, int division, stmlib::GateFlags* flags,
                           size_t size) {
  // A pulse every `unit` 16ths, of which those on a multiple of `division`
  // pulses (counted from the start of the three-bar cycle) are let through:
  // high for the first half of the pulse, so Beads sees a rising edge on
  // each one. A clock that starts (or changes its unit) between two grid
  // steps waits for the next one.
  const int period = unit * division;
  const float step_increment = context.bar_increment * 16.0f;
  if (unit != seed_unit_) {
    seed_unit_ = unit;
    pulse_on_ = false;
  }
  for (size_t i = 0; i < size; ++i) {
    const float y = context.bar_phase +
        float(offset + i) * context.bar_increment;
    const int bar = int(y);  // 1 once past the bar's end within the block
    const float x = (y - float(bar)) * 16.0f;
    int sixteenth = int(x);
    sixteenth = sixteenth > 15 ? 15 : (sixteenth < 0 ? 0 : sixteenth);
    const float fraction = x - float(sixteenth);
    const int step = ((bar_count_ + bar) % kSeedBars) * 16 + sixteenth;
    if (!seed_running_) {
      seed_running_ = true;
      pulse_on_ = false;
      // On the step's first sample: count it as the step starting now.
      last_step_ = fraction < step_increment
          ? (step + kSeedSteps - 1) % kSeedSteps : step;
    }
    // A new step. One back, late in it, is the tempo's phase correction or
    // rounding at a block's edge, not a new step.
    const bool back = step == (last_step_ + kSeedSteps - 1) % kSeedSteps &&
        fraction > 0.5f;
    if (step != last_step_ && !back) {
      last_step_ = step;
      if (step % unit == 0) {
        pulse_on_ = step % period == 0;
      }
    }
    const float in_pulse = float(last_step_ % unit) +
        (step == last_step_ ? fraction : 0.0f);
    const bool gate = pulse_on_ && in_pulse < 0.5f * float(unit);
    previous_seed_ = flags[i] = stmlib::ExtractGateFlags(previous_seed_, gate);
  }
}

void Beadsy::Process(const ProcessContext& context, const float* params,
                     const Frame* in, Frame* out, size_t size) {
  // Bars, counted from the tempo's wraps, for the seed clock's cycle.
  if (context.bar_phase < last_bar_phase_ - 0.5f) {
    bar_count_ = (bar_count_ + 1) % kSeedBars;
  }
  last_bar_phase_ = context.bar_phase;

  size_t offset = 0;
  while (offset < size) {
    size_t n = size - offset;
    if (n > kBlockSize) {
      n = kBlockSize;
    }
    sample_offset_ = offset;
    ProcessChunk(context, params, in + offset, out + offset, n);
    offset += n;
  }
}

void Beadsy::ProcessChunk(const ProcessContext& context, const float* params,
                          const Frame* in, Frame* out, size_t size) {
  if (fresh_) {
    // The first chunk since Reset(), maybe with another preset's QUALITY:
    // nothing is recorded yet, so the new medium needs no fade, and no
    // clear either unless its silence differs.
    fresh_ = false;
    target_quality_ = StepIndex(params[QUALITY], NUM_QUALITIES);
    if (target_quality_ != quality_) {
      const bool same_silence =
          SilenceByte(target_quality_) == SilenceByte(quality_);
      quality_ = target_quality_;
      if (same_silence) {
        processor_->Configure(beads::Processor::Media(quality_), false,
                              false);
      } else {
        gain_ = 0.0f;
        clear_offset_ = 0;
        state_ = STATE_CLEARING;
      }
    }
  } else {
    target_quality_ = StepIndexFrom(params[QUALITY], NUM_QUALITIES,
                                    target_quality_);
  }

  // A quality change: fade out, clear the buffer in slices, configure the
  // new medium, fade in. Back to the old medium before the output is
  // silent: fade in again, the buffer untouched.
  if (target_quality_ != quality_ &&
      (state_ == STATE_RUNNING || state_ == STATE_FADING_IN)) {
    state_ = STATE_FADING_OUT;
  } else if (target_quality_ == quality_ && state_ == STATE_FADING_OUT) {
    state_ = STATE_FADING_IN;
  }
  if (state_ == STATE_CLEARING) {
    size_t end = clear_offset_ + kClearChunk;
    if (end > kBufferBytes) {
      end = kBufferBytes;
    }
    ClearBuffer(quality_, clear_offset_, end);
    clear_offset_ = end;
    if (clear_offset_ == kBufferBytes) {
      processor_->Configure(beads::Processor::Media(quality_), false, false);
      state_ = STATE_FADING_IN;
      input_gain_ = 0.0f;
    }
    for (size_t i = 0; i < size; ++i) {
      out[i].l = out[i].r = 0.0f;
    }
    seed_running_ = false;  // it restarts on the grid
    return;
  }

  const float size_value = Clamp01(params[SIZE]);
  // The mode this chunk's Process() runs in: Beads switches 1.5 s after
  // SIZE crosses its threshold (the old mode fades out meanwhile).
  delay_mode_ = processor_->delay_mode();
  freeze_on_ = StepIndexFrom(params[FREEZE], 2, freeze_on_ ? 1 : 0) == 1;
  // In granular mode a falling send freezes the buffer; in delay mode the
  // input follows the send and the echoes ring out.
  frozen_ = freeze_on_ || (!delay_mode_ && context.send < kSendOnThreshold);

  beads::Parameters p;
  p.time.base = Clamp01(params[TIME]);
  p.time.attenuverter = Attenuverter(params[TIME_RANDOM]);
  p.time.cv = 0.0f;
  p.time.has_cv = false;
  p.size.base = size_value;
  p.size.attenuverter = 0.0f;
  p.size.cv = 0.0f;
  p.size.has_cv = false;
  p.shape.base = Clamp01(params[SHAPE]);
  p.shape.attenuverter = 0.0f;
  p.shape.cv = 0.0f;
  p.shape.has_cv = false;
  p.pitch.base = Bipolar(Clamp01(params[PITCH]), 24.0f);
  p.pitch.attenuverter = Attenuverter(params[PITCH_RANDOM]);
  p.pitch.cv = 0.0f;
  p.pitch.has_cv = false;
  p.monophonic_mode = false;

  beads::ModulatedParameter density;
  density.base = Clamp01(params[DENSITY]);
  density.cv = 0.0f;

  beads::Processor::MixParameters m;
  m.feedback = Clamp01(params[FEEDBACK]);
  m.dry_wet = 1.0f;  // the engine mixes
  m.reverb_amount = Clamp01(params[REVERB]);
  m.output_gate = false;

  bool freeze[kBlockSize];
  stmlib::GateFlags seed[kBlockSize];
  beads::FloatFrame float_in[kBlockSize];
  beads::FloatFrame float_out[kBlockSize];
  const float send = Clamp01(context.send);
  const float send_increment = (send - send_) / float(size);
  for (size_t i = 0; i < size; ++i) {
    // After a quality change the input fades in too: recording would
    // otherwise start mid-waveform, a step the grains would replay.
    if (input_gain_ < 1.0f) {
      input_gain_ += kFadeIncrement;
      input_gain_ = input_gain_ > 1.0f ? 1.0f : input_gain_;
    }
    send_ += send_increment;
    const float gain = delay_mode_ ? input_gain_ * send_ : input_gain_;
    freeze[i] = frozen_;
    float_in[i].l = in[i].l * gain;
    float_in[i].r = in[i].r * gain;
  }
  send_ = send;

  // Synced DENSITY: the tempo grid is Beads' SEED input with its button
  // locked, so DENSITY divides (or randomly thins) the grid. Left of centre
  // the division is made here, counted from the bar, and Beads' divider
  // (whose count starts at whichever pulse it saw first) divides by 1.
  const stmlib::GateFlags* seed_input = NULL;
  if (context.synced(DENSITY)) {
    int division = 1;
    if (!delay_mode_ && density.base < kDensityDeadLow) {
      division = kDivisionRatios[
          divider_quantizer_.Process(density.base * 2.15f)];
      density.base = 0.0f;
    }
    MakeSeedClock(context, sample_offset_,
                  delay_mode_ ? kDelaySeedUnit : kGranularSeedUnit, division,
                  seed, size);
    seed_input = seed;
  } else {
    seed_running_ = false;
    previous_seed_ = stmlib::GATE_FLAG_LOW;
  }

  processor_->Process(
      beads::SEED_BUTTON_STATE_LOCKED, seed_input, freeze, density, p, m,
      float_in, float_out, size);

  for (size_t i = 0; i < size; ++i) {
    if (state_ == STATE_FADING_OUT) {
      gain_ -= kFadeIncrement;
      if (gain_ <= 0.0f) {
        gain_ = 0.0f;
      }
    } else if (state_ == STATE_FADING_IN) {
      gain_ += kFadeIncrement;
      if (gain_ >= 1.0f) {
        gain_ = 1.0f;
      }
    }
    out[i].l = float_out[i].l * gain_;
    out[i].r = float_out[i].r * gain_;
  }
  if (state_ == STATE_FADING_OUT && gain_ == 0.0f) {
    quality_ = target_quality_;
    clear_offset_ = 0;
    state_ = STATE_CLEARING;
  } else if (state_ == STATE_FADING_IN && gain_ == 1.0f) {
    state_ = STATE_RUNNING;
  }
}

void Beadsy::Format(int param, float value, const ProcessContext& context,
                    char* text, size_t size) const {
  value = Clamp01(value);
  const bool delay_mode = delay_mode_;
  const int quality = quality_ >= 0 && quality_ < NUM_QUALITIES
      ? quality_ : QUALITY_DIGITAL_16_BIT;
  switch (param) {
    case TIME:
      if (delay_mode && frozen_) {
        // Beads' slice looper: TIME picks the slice, about this far back
        // (Beads rounds it down to a whole number of slices).
        size_t n = Prefix(text, size, "LOOP ");
        FormatSeconds(text + n, size - n,
                      Clamp01(value * 1.005f) * kBufferSeconds[quality]);
      } else if (delay_mode) {
        // Beads' delay mode: TIME multiplies the repeat time, x1 .. x16.
        size_t n = Prefix(text, size, "x");
        int multiplier = int(value * 1.005f * 15.0f + 1.0f);
        multiplier = multiplier > 16 ? 16 : multiplier;
        FormatNumber(text + n, size - n, float(multiplier), 0, false, "");
      } else {
        // How far back the grains start, once the buffer is full.
        FormatSeconds(text, size, value * kBufferSeconds[quality]);
      }
      break;

    case SIZE:
      if (value > (delay_mode ? 0.98f : 0.99f)) {
        CopyText(text, size, "DELAY");
      } else {
        // GranularPlayer::ComputeGrainDuration.
        const bool reverse = value < 0.3333333f;
        const float shortness_raw = reverse
            ? value * 3.0f * (2.0f - value * 3.0f)
            : 1.0f - 1.5f * (value - 0.3333333f);
        float shortness = 1.025f * shortness_raw;
        shortness = shortness > 1.0f ? 1.0f : shortness;
        const float seconds = 4.0f * stmlib::SemitonesToRatio(
            shortness * -108.0f);
        size_t n = reverse ? Prefix(text, size, "R ") : 0;
        FormatSeconds(text + n, size - n, seconds);
      }
      break;

    case PITCH:
      {
        const float semitones = Bipolar(value, 24.0f);
        const bool fractional =
            fabsf(semitones - floorf(semitones + 0.5f)) > 0.05f;
        FormatSemitones(text, size, semitones, fractional);
      }
      break;

    case DENSITY:
      if (delay_mode) {
        if (context.synced(DENSITY)) {
          int index = int(value * 20.0f + 0.5f);
          index = index > 20 ? 20 : index;
          FormatLabel(text, size, kDelayRatioLabels, index);
        } else {
          // DelayController: the repeat time, from the whole buffer at the
          // centre down to 1/512 of it at either end.
          const float seconds = kBufferSeconds[quality] *
              stmlib::SemitonesToRatio(-fabsf(value - 0.5f) * 216.0f);
          const float min_seconds = 68.0f / beads::kCodecSampleRate;
          FormatSeconds(text, size,
                        seconds < min_seconds ? min_seconds : seconds);
        }
      } else if (value >= kDensityDeadLow && value <= kDensityDeadHigh) {
        CopyText(text, size, "OFF");
      } else if (context.synced(DENSITY)) {
        if (value < kDensityDeadLow) {
          // The seed clock's divider (Beads' quantizer, without hysteresis).
          int index = int(value * 2.15f * 8.0f);
          index = index > 7 ? 7 : index;
          FormatLabel(text, size, kDividerLabels, index);
        } else {
          float p = (value - kDensityDeadHigh) * 2.15f;
          p = p * p;
          p = p > 1.0f ? 1.0f : p;
          FormatPercent(text, size, p);
          size_t n = strlen(text);
          if (n + 5 < size) {
            CopyText(text + n, size - n, " 1/16");
          }
        }
      } else if (value < kDensityDeadLow) {
        // Regular grains, fastest at the left end.
        FormatHz(text, size, kMaxGrainFrequency *
                 stmlib::SemitonesToRatio(-value * 192.0f));
      } else {
        // Random grains, densest at the right end: "~" for an average.
        size_t n = Prefix(text, size, "~");
        FormatHz(text + n, size - n, 0.5f * kMaxGrainFrequency *
                 stmlib::SemitonesToRatio(-(1.0f - value) * 192.0f));
      }
      break;

    case QUALITY:
      FormatLabel(text, size, kQualityLabels,
                  StepIndex(value, NUM_QUALITIES));
      break;

    case TIME_RANDOM:
    case PITCH_RANDOM:
      {
        // Beads' attenuverters without CV: clockwise scatters every grain
        // evenly ("SPRD"), anticlockwise throws a few grains far ("JUMP").
        const float a = Attenuverter(value);
        if (a == 0.0f) {
          CopyText(text, size, "0%");
        } else {
          size_t n = Prefix(text, size, a > 0.0f ? "SPRD " : "JUMP ");
          FormatPercent(text + n, size - n, fabsf(a));
        }
      }
      break;

    case FREEZE:
      FormatLabel(text, size, kFreezeLabels, StepIndex(value, 2));
      break;

    default:  // SHAPE, FEEDBACK, REVERB
      FormatPercent(text, size, value);
      break;
  }
}

}  // namespace sidefx
