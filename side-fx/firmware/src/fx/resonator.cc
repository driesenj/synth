// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: RESONATOR (see resonator.h).

#include "fx/resonator.h"

#include "stmlib/dsp/units.h"

namespace sidefx {

namespace {

const ParamInfo kParams[] = {
  // +-24 semitones: one per detent.
  { "PITCH", 0.5f, PARAM_BIPOLAR, 0, 48 },
  { "CHORD", 2.0f / 9.0f, PARAM_STEPPED, Resonator::NUM_CHORDS, 0 },
  { "DECAY", 0.5f, PARAM_SYNC, 0, 0 },
  { "DAMP", 0.4f, 0, 0, 100 },
  { "DETUNE", 0.25f, 0, 0, 100 },
  { "SPREAD", 0.6f, 0, 0, 100 },
  { "DRIVE", 0.2f, 0, 0, 100 },
};

const BlockInfo kInfo = {
  "RESONATOR", "RESO", Resonator::NUM_PARAMS, kParams, 0.50f, 0,
};

const char* const kChordLabels[] = {
  "UNISON", "OCTAVES", "FIFTHS", "MAJOR", "MINOR", "SUS4", "MAJ7", "MIN7",
  "ADD9", "CLUSTER",
};

// Semitones above the root, voice by voice. Voice 0 is always the root;
// the others alternate sides of the stereo field (kPan).
const float kChords[Resonator::NUM_CHORDS][Resonator::kNumVoices] = {
  { 0.0f, 0.0f, 0.0f, 0.0f },     // UNISON (DETUNE makes it a chorus)
  { 0.0f, 12.0f, -12.0f, 24.0f },  // OCTAVES
  { 0.0f, 7.0f, 12.0f, 19.0f },   // FIFTHS
  { 0.0f, 4.0f, 7.0f, 12.0f },    // MAJOR
  { 0.0f, 3.0f, 7.0f, 12.0f },    // MINOR
  { 0.0f, 5.0f, 7.0f, 12.0f },    // SUS4
  { 0.0f, 4.0f, 7.0f, 11.0f },    // MAJ7
  { 0.0f, 3.0f, 7.0f, 10.0f },    // MIN7
  { 0.0f, 4.0f, 7.0f, 14.0f },    // ADD9
  { 0.0f, 2.0f, 3.0f, 5.0f },     // CLUSTER
};

// DETUNE's share per voice: the root stays put, so the chord stays in tune
// with the track while the others beat against it.
const float kDetune[Resonator::kNumVoices] = { 0.0f, 1.0f, -1.0f, 0.5f };
// SPREAD's pan per voice: the outer pair goes furthest.
const float kPan[Resonator::kNumVoices] = { -1.0f, 1.0f, -0.5f, 0.5f };

const char* const kNoteNames[] = {
  "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
};

const float kRootHz = 130.8128f;  // C3
const float kPitchRange = 24.0f;
const float kMaxDetuneCents = 50.0f;
const float kMinDecay = 0.05f;
const float kMaxDecay = 10.0f;
const float kMinHz = 16.0f;
const float kMaxHz = 4000.0f;
// DAMP 0: the lowpass corner 256 times the fundamental (effectively off;
// past the Nyquist frequency for high voices, where the coefficient goes
// on towards 1 rather than stopping at its fs / 2 value, 0.957, which
// would dull a 2 kHz voice's overtones); DAMP 1: twice the fundamental
// (almost a sine after a few cycles).
const float kMinDampRatio = 2.0f;
const float kMaxDampRatio = 256.0f;
const float kMaxDampHz = 4.0f * kSampleRate;
// The loop's gain at DC (where the lowpass passes everything) stays below
// this, so the loop is stable whatever DECAY asks for. 10 s at 4 kHz needs
// 0.99983 at the fundamental.
const float kMaxLoopGain = 0.99995f;
// The loop length moves at most this many samples per sample: reading the
// line at 0.5..1.5 times its speed, so a pitch or chord change slides (a
// semitone in about a millisecond, two octaves in tens) instead of
// clicking or squealing.
const float kMaxDelaySlew = 0.5f;
// Per block: DRIVE settles within ~2 ms.
const float kSmoothing = 0.3f;
// The loop saturator's ceiling: 2.5 (nearly clean at line level) at DRIVE
// 0, 0.5 at DRIVE 1.
const float kCleanCeiling = 2.5f;
const float kDriveRange = 4.0f;

inline float SoftLimit(float x) {
  if (x > 2.0f) {
    return 2.0f + dsp::SoftSaturate(x - 2.0f);
  } else if (x < -2.0f) {
    return -2.0f + dsp::SoftSaturate(x + 2.0f);
  }
  return x;
}

// Appends source at text's end, within size.
void Append(char* text, size_t size, const char* source) {
  size_t n = 0;
  while (n + 1 < size && text[n]) {
    ++n;
  }
  while (n + 1 < size && *source) {
    text[n++] = *source++;
  }
  if (n < size) {
    text[n] = '\0';
  }
}

}  // namespace

const BlockInfo& Resonator::info() const {
  return kInfo;
}

bool Resonator::Init(Memory* memory) {
  for (int v = 0; v < kNumVoices; ++v) {
    float* buffer = memory->external->AllocateArray<float>(kDelaySize);
    if (!buffer) {
      return false;
    }
    line_[v].Init(buffer, kDelaySize);
  }
  Reset();
  return true;
}

void Resonator::Reset() {
  for (int v = 0; v < kNumVoices; ++v) {
    line_[v].Clear();
    reader_[v].Reset();
    Voice& voice = voice_[v];
    voice.delay = 1.0f;
    voice.feedback = 0.0f;
    voice.damp = 1.0f;
    voice.input_gain = 0.0f;
    voice.pan_l = voice.pan_r = 0.7071f;
    voice.lowpass = 0.0f;
    voice_hz_[v] = kRootHz;
  }
  dc_[0].Reset();
  dc_[1].Reset();
  drive_ = 0.0f;
  primed_ = false;
}

void Resonator::Process(const ProcessContext& context, const float* params,
                        const Frame* in, Frame* out, size_t size) {
  if (!size) {
    return;
  }
  const float root = Bipolar(dsp::Clamp(params[PARAM_PITCH], 0.0f, 1.0f),
                             kPitchRange);
  const int chord = StepIndex(params[PARAM_CHORD], NUM_CHORDS);
  float decay = TimeParam(dsp::Clamp(params[PARAM_DECAY], 0.0f, 1.0f),
                          context.synced(PARAM_DECAY), context.beat_seconds,
                          kMinDecay, kMaxDecay);
  decay = dsp::Clamp(decay, kMinDecay, kMaxDecay);
  const float damp_ratio = ExpMap(
      1.0f - dsp::Clamp(params[PARAM_DAMP], 0.0f, 1.0f),
      kMinDampRatio, kMaxDampRatio);
  const float detune_knob = dsp::Clamp(params[PARAM_DETUNE], 0.0f, 1.0f);
  // Quadratic: the first half of the knob is the subtle 0..12 cents.
  const float detune = kMaxDetuneCents * 0.01f * detune_knob * detune_knob;
  const float spread = dsp::Clamp(params[PARAM_SPREAD], 0.0f, 1.0f);
  const float drive_target = dsp::Clamp(params[PARAM_DRIVE], 0.0f, 1.0f);

  const float drive_start = drive_;
  drive_ = primed_ ? drive_ + kSmoothing * (drive_target - drive_)
      : drive_target;
  const float inv_size = 1.0f / float(size);

  // Per voice, per block: the loop's length, gain and filter, as steps
  // that ramp the per-sample values there over this block.
  float delay_step[kNumVoices];
  float feedback_step[kNumVoices];
  float damp_step[kNumVoices];
  float input_gain_step[kNumVoices];
  float pan_l_step[kNumVoices];
  float pan_r_step[kNumVoices];
  for (int v = 0; v < kNumVoices; ++v) {
    Voice& voice = voice_[v];
    const float target = root + kChords[chord][v] + detune * kDetune[v];
    const float hz = dsp::Clamp(
        kRootHz * stmlib::SemitonesToRatio(target), kMinHz, kMaxHz);
    voice_hz_[v] = hz;
    const float period = kSampleRate / hz;
    const float w = dsp::kTwoPi * hz / kSampleRate;
    const float cos_w = cosf(w);
    const float sin_w = sinf(w);

    // RT60 = decay at the fundamental: the loop's gain there.
    const float wanted = expf(-6.9077553f / (hz * decay));

    // The damping lowpass y += c (x - y), c/(1 - p z^-1) with p = 1 - c.
    // Its gain at the fundamental, |H|^2 = c^2 / (c^2 + 2 (1 - c)(1 - cos w)),
    // must be at least wanted / kMaxLoopGain, or the feedback would need a
    // DC gain over kMaxLoopGain to reach DECAY: a dark DAMP with a long
    // DECAY opens up to the darkest corner that still lets the fundamental
    // ring that long (c^2 + K c - K = 0, K = 2 G^2 (1 - cos w) / (1 - G^2)).
    float c = dsp::OnePoleCoefficient(
        dsp::Clamp(hz * damp_ratio, 1.0f, kMaxDampHz), kSampleRate);
    const float floor_gain = wanted * (1.0f / kMaxLoopGain);
    if (floor_gain >= 1.0f) {
      c = 1.0f;
    } else {
      const float g2 = floor_gain * floor_gain;
      const float k = 2.0f * g2 * (1.0f - cos_w) / (1.0f - g2);
      const float c_min = 0.5f * (sqrtf(k * k + 4.0f * k) - k);
      c = c < c_min ? c_min : c;
    }
    const float p = 1.0f - c;
    const float re = 1.0f - p * cos_w;
    const float im = p * sin_w;
    const float lowpass_gain = c / sqrtf(re * re + im * im);
    const float lowpass_delay = atan2f(im, re) / w;

    float feedback = wanted / lowpass_gain;
    if (feedback > kMaxLoopGain) {
      feedback = kMaxLoopGain;
    }
    const float loop_gain = feedback * lowpass_gain;
    // Constant power for a broadband input, whatever the decay.
    const float input_gain = sqrtf(1.0f - loop_gain * loop_gain);

    // One sample through the line's write, the read, the lowpass.
    float delay = dsp::Clamp(period - 1.0f - lowpass_delay, 1.0f,
                             float(kDelaySize - 4));
    if (primed_) {
      const float slew = kMaxDelaySlew * float(size);
      delay = voice.delay + dsp::Clamp(delay - voice.delay, -slew, slew);
    }
    float pan_l, pan_r;
    dsp::PanGains(spread * kPan[v], &pan_l, &pan_r);

    if (!primed_) {
      voice.delay = delay;
      voice.feedback = feedback;
      voice.damp = c;
      voice.input_gain = input_gain;
      voice.pan_l = pan_l;
      voice.pan_r = pan_r;
    }
    delay_step[v] = (delay - voice.delay) * inv_size;
    feedback_step[v] = (feedback - voice.feedback) * inv_size;
    damp_step[v] = (c - voice.damp) * inv_size;
    input_gain_step[v] = (input_gain - voice.input_gain) * inv_size;
    pan_l_step[v] = (pan_l - voice.pan_l) * inv_size;
    pan_r_step[v] = (pan_r - voice.pan_r) * inv_size;
  }
  primed_ = true;

  // The saturator's ceiling, ramped too; the output makes up part of what
  // the lower ceiling takes away.
  const float ceiling_start = kCleanCeiling / (1.0f + kDriveRange * drive_start);
  const float ceiling_end = kCleanCeiling / (1.0f + kDriveRange * drive_);
  const float ceiling_step = (ceiling_end - ceiling_start) * inv_size;
  const float inverse_start = 1.0f / ceiling_start;
  const float inverse_step = (1.0f / ceiling_end - inverse_start) * inv_size;
  const float makeup_start = 0.5f * sqrtf(1.0f + kDriveRange * drive_start);
  const float makeup_step = (0.5f * sqrtf(1.0f + kDriveRange * drive_) -
                             makeup_start) * inv_size;
  float ceiling = ceiling_start;
  float inverse = inverse_start;
  float makeup = makeup_start;

  for (size_t i = 0; i < size; ++i) {
    ceiling += ceiling_step;
    inverse += inverse_step;
    makeup += makeup_step;
    // DC would sit in every loop at 1 / (1 - gain): keep it out.
    const float l = 0.7071f * dc_[0].Process(in[i].l, 0.9995f);
    const float r = 0.7071f * dc_[1].Process(in[i].r, 0.9995f);
    float out_l = 0.0f;
    float out_r = 0.0f;
    for (int v = 0; v < kNumVoices; ++v) {
      Voice& voice = voice_[v];
      voice.delay += delay_step[v];
      voice.feedback += feedback_step[v];
      voice.damp += damp_step[v];
      voice.input_gain += input_gain_step[v];
      voice.pan_l += pan_l_step[v];
      voice.pan_r += pan_r_step[v];

      const float x = voice.pan_l * l + voice.pan_r * r;
      // Allpass interpolation: Hermite would take up to 0.2 % per pass
      // at 4 kHz, a 1 s RT60 whatever DECAY says.
      const float tap = reader_[v].Read(line_[v], voice.delay);
      voice.lowpass += voice.damp * (tap - voice.lowpass);
      const float s = ceiling * dsp::SoftSaturate(
          inverse * (voice.input_gain * x + voice.feedback * voice.lowpass));
      line_[v].Write(s);
      out_l += voice.pan_l * s;
      out_r += voice.pan_r * s;
    }
    out[i].l = SoftLimit(makeup * out_l);
    out[i].r = SoftLimit(makeup * out_r);
  }
}

void Resonator::Format(int param, float value, const ProcessContext& context,
                       char* text, size_t size) const {
  switch (param) {
    case PARAM_PITCH:
      {
        // "G3 +7st": the root note and its offset from C3.
        const float semitones = Bipolar(value, kPitchRange);
        const int n = static_cast<int>(semitones + kPitchRange + 0.5f) -
            static_cast<int>(kPitchRange);
        const int midi = 48 + n;  // C3
        CopyText(text, size, kNoteNames[midi % 12]);
        char octave[2] = { char('0' + midi / 12 - 1), '\0' };
        Append(text, size, octave);
        Append(text, size, " ");
        const size_t used = strlen(text);
        if (used < size) {
          FormatSemitones(text + used, size - used, float(n), false);
        }
      }
      break;
    case PARAM_CHORD:
      FormatLabel(text, size, kChordLabels, StepIndex(value, NUM_CHORDS));
      break;
    case PARAM_DECAY:
      if (context.synced(param)) {
        // A note value outside 50 ms .. 10 s rings for the clamped time:
        // show that instead.
        const float seconds = SyncedSeconds(value, context.beat_seconds);
        if (seconds >= kMinDecay && seconds <= kMaxDecay) {
          FormatNoteValue(text, size, NoteValueIndex(value));
        } else {
          FormatSeconds(text, size,
                        dsp::Clamp(seconds, kMinDecay, kMaxDecay));
        }
      } else {
        FormatSeconds(text, size, ExpMap(value, kMinDecay, kMaxDecay));
      }
      break;
    case PARAM_DETUNE:
      FormatNumber(text, size, kMaxDetuneCents * value * value, 0, false,
                   "ct");
      break;
    case PARAM_DAMP:
    case PARAM_SPREAD:
    case PARAM_DRIVE:
      FormatPercent(text, size, value);
      break;
    default:
      CopyText(text, size, "");
      break;
  }
}

}  // namespace sidefx
