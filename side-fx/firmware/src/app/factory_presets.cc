// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the factory presets, sixteen starting points for dark ambient,
// dub and hypnotic techno and future / US bass, played live: sends set up
// for throws (a dub delay off, ready to be hit), tempo-locked modulation,
// slowly mutating random, a CV or two on the knobs that matter live.
//
// Every value is set by the block's and the parameter's NAME (Builder
// below), never by an index, so a block that reorders or renames its
// parameters cannot silently scramble a preset: an unknown name is skipped
// and counted (FactoryPresetMisses(), which the host test requires to stay
// 0). Each slot starts from its block's defaults with every sync bit off;
// a preset syncs exactly the parameters it means to (Note(), Rate(),
// Synced()).
//
//   #  name            algorithm  PITCH       DELAY       TEXTURE     REVERB
//   0  CLEAN START     SERIAL     shift  -    dual   on   phaser -    plate on
//   1  DUB THROW       SERIAL     shift  -    tape   -    tsim   on   fdn   on
//   2  DUB CHORDS      SERIAL     shift  on   dual   on   phaser on   fdn   on
//   3  SHIMMER HALO    P|D>T>R    grain  on   taps   on   tsim   on   fdn   on
//   4  BEADS CLOUD     P|D|T>R    grain  -    band   -    beadsy on   plate on
//   5  BEADS FREEZE    PD|TR      shift  on   tape   on   beadsy on   apf   on
//   6  GLITCH BREAKS   P>D|T>R    grain  -    glitch on   shaper on   plate on
//   7  METAL RINGS     P>D|T>R    shift  -    taps   on   reso   on   fdn   on
//   8  COMB DRONE      SERIAL     grain  on   combs  on   phaser -    modal on
//   9  WOBBLE BASS     SERIAL     shift  on   combs  on   shaper on   plate -
//  10  SPECTRAL DUB    PD|TR      shift  -    band   on   phaser on   plate on
//  11  MODAL BELLS     P|D>T>R    grain  on   dual   on   reso   -    modal on
//  12  FOUR SENDS      PARALLEL   grain  -    tape   -    reso   -    plate on
//  13  RHYTHM GATES    PARALLEL   shift  -    taps   -    beadsy on   apf   on
//  14  SPLIT RIG       DUAL MONO  shift  on   tape   on   tsim   on   apf   on
//  15  SPLIT GLITCH    DUAL MONO  grain  on   glitch on   shaper on   modal on
//
// ("-": the send is off, ready to throw; 12 and 13 throw by send gates.)

#include "app/factory_presets.h"

#include <string.h>

#include "engine/algorithm.h"
#include "engine/block.h"
#include "engine/params.h"
#include "engine/registry.h"

namespace sidefx {

// For the host test (not in the header: nothing else needs it): how many
// block, parameter or note names the presets asked for and did not find.
int FactoryPresetMisses();

namespace {

int misses = 0;

// The modulation sources' ranges, as preset.h documents them.
const float kLfoMinHz = 0.02f;
const float kLfoMaxHz = 20.0f;
const float kAttackMin = 0.001f;
const float kAttackMax = 0.5f;
const float kReleaseMin = 0.01f;
const float kReleaseMax = 5.0f;
const float kEnvelopeMaxDb = 24.0f;

struct Builder {
  Preset* preset;
  int slot;
  const BlockInfo* info;  // NULL when the block was not found
};

void Miss() { ++misses; }

void Begin(Builder* b, Preset* preset, const char* name, int algorithm,
           int bpm) {
  InitPreset(preset);
  SetPresetName(preset, name);
  preset->algorithm = uint8_t(algorithm);
  preset->tempo = uint16_t(bpm * 10);
  b->preset = preset;
  b->slot = 0;
  b->info = NULL;
}

// Puts the block called `name` in `slot` (its defaults, every sync bit
// off) with the send on or off; the calls that follow edit this slot.
void UseBlock(Builder* b, int slot, const char* name, bool send) {
  b->slot = slot;
  b->info = NULL;
  SlotPreset* s = &b->preset->slot[slot];
  s->send = send ? 1 : 0;
  s->send_gate = MOD_OFF;
  for (int t = 0; t < NumBlockTypes(slot); ++t) {
    const Block* block = GetBlock(slot, t);
    if (block && !strcmp(block->info().name, name)) {
      InitSlot(b->preset, slot, t);
      s->sync_mask = 0;
      b->info = &block->info();
      return;
    }
  }
  Miss();
}

int ParamIndex(const Builder& b, const char* name) {
  if (b.info) {
    for (int i = 0; i < b.info->num_params; ++i) {
      if (!strcmp(b.info->params[i].name, name)) {
        return i;
      }
    }
  }
  Miss();
  return -1;
}

int NoteIndex(const char* label) {
  for (int i = 0; i < kNumNoteValues; ++i) {
    if (!strcmp(kNoteValues[i].label, label)) {
      return i;
    }
  }
  Miss();
  return -1;
}

// The note value `label` as a synced time (0 = the shortest) or as a
// synced rate (0 = the slowest).
float NoteTime(int index) { return StepValue(index, kNumNoteValues); }
float NoteRate(int index) { return 1.0f - StepValue(index, kNumNoteValues); }

// A free value, 0..1 (a PARAM_SYNC parameter stays free).
void Set(Builder* b, const char* name, float value) {
  const int i = ParamIndex(*b, name);
  if (i >= 0) {
    b->preset->slot[b->slot].value[i] = PresetRaw(value);
  }
}

// A stepped parameter's `index`-th value.
void Step(Builder* b, const char* name, int index) {
  const int i = ParamIndex(*b, name);
  if (i < 0) {
    return;
  }
  const ParamInfo& param = b->info->params[i];
  if (!(param.flags & PARAM_STEPPED) || index < 0 || index >= param.num_steps) {
    Miss();
    return;
  }
  b->preset->slot[b->slot].value[i] = PresetRaw(StepValue(index, param.num_steps));
}

// A PARAM_SYNC parameter at `value` with its sync bit on (for blocks that
// read a synced value their own way, like BEADSY's DENSITY).
void Synced(Builder* b, const char* name, float value) {
  const int i = ParamIndex(*b, name);
  if (i < 0) {
    return;
  }
  if (!(b->info->params[i].flags & PARAM_SYNC)) {
    Miss();
    return;
  }
  SlotPreset* s = &b->preset->slot[b->slot];
  s->value[i] = PresetRaw(value);
  s->sync_mask = uint16_t(s->sync_mask | (1u << i));
}

// A synced time: the note value called `label` ("1/8.", "1 BAR").
void Note(Builder* b, const char* name, const char* label) {
  const int n = NoteIndex(label);
  if (n >= 0) {
    Synced(b, name, NoteTime(n));
  }
}

// A synced rate: one cycle per note value `label`.
void Rate(Builder* b, const char* name, const char* label) {
  const int n = NoteIndex(label);
  if (n >= 0) {
    Synced(b, name, NoteRate(n));
  }
}

void Mix(Builder* b, float mix) {
  b->preset->slot[b->slot].value[kMixValue] = PresetRaw(mix);
}

void Mod(Builder* b, const char* name, ModSource source, int depth) {
  const int i = ParamIndex(*b, name);
  if (i >= 0) {
    b->preset->slot[b->slot].mod[i].source = uint8_t(source);
    b->preset->slot[b->slot].mod[i].depth = int8_t(depth);
  }
}

// The send inverts while `source` is above the gate threshold.
void Gate(Builder* b, ModSource source) {
  b->preset->slot[b->slot].send_gate = uint8_t(source);
}

void LfoNote(Builder* b, int lfo, LfoShape shape, const char* label) {
  const int n = NoteIndex(label);
  LfoPreset* l = &b->preset->lfo[lfo];
  l->shape = uint8_t(shape);
  l->sync = 1;
  l->rate = PresetRaw(n >= 0 ? NoteRate(n) : 0.5f);
}

void LfoHz(Builder* b, int lfo, LfoShape shape, float hz) {
  LfoPreset* l = &b->preset->lfo[lfo];
  l->shape = uint8_t(shape);
  l->sync = 0;
  l->rate = PresetRaw(ExpUnmap(hz, kLfoMinHz, kLfoMaxHz));
}

// smooth: 0 steps, 1 glides the whole cycle.
void RandomNote(Builder* b, const char* label, float smooth) {
  const int n = NoteIndex(label);
  RandomPreset* r = &b->preset->random;
  r->sync = 1;
  r->rate = PresetRaw(n >= 0 ? NoteRate(n) : 0.5f);
  r->smooth = PresetRaw(smooth);
}

void RandomHz(Builder* b, float hz, float smooth) {
  RandomPreset* r = &b->preset->random;
  r->sync = 0;
  r->rate = PresetRaw(ExpUnmap(hz, kLfoMinHz, kLfoMaxHz));
  r->smooth = PresetRaw(smooth);
}

void Envelope(Builder* b, float attack_seconds, float release_seconds,
              float gain_db) {
  EnvelopePreset* e = &b->preset->envelope;
  e->attack = PresetRaw(ExpUnmap(attack_seconds, kAttackMin, kAttackMax));
  e->release = PresetRaw(ExpUnmap(release_seconds, kReleaseMin, kReleaseMax));
  e->gain = PresetRaw(gain_db / kEnvelopeMaxDb);
}

// A +-24 semitone parameter (48 detents).
inline float Semitones(float st) { return 0.5f + st / 48.0f; }
// A bipolar parameter at x in -1..+1 of its range.
inline float Bi(float x) { return 0.5f + 0.5f * x; }
// MOD COMBS' FREQ: 20 Hz * 100^value.
inline float CombHz(float hz) { return ExpUnmap(hz, 20.0f, 2000.0f); }

// NOTE (and CV at 1 V/oct) on MOD COMBS' FREQ: its 20 Hz..2 kHz span is
// 79.7 semitones, so a semitone per MIDI note (1/48 of the source) takes
// 48 / 79.7 = 60 %.
const int kCombNoteDepth = 60;

// --- the presets --------------------------------------------------------

// The starting point: a dotted-eighth / quarter delay and a plate on,
// everything else at its defaults and off. No modulation. (The app's
// storage test expects exactly these sends on preset 0.)
void CleanStart(Builder* b, Preset* p) {
  Begin(b, p, "CLEAN START", ALGORITHM_SERIAL, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", false);
  UseBlock(b, SLOT_DELAY, "DUAL DELAY", true);
  Note(b, "TIME L", "1/8.");
  Note(b, "TIME R", "1/4");
  UseBlock(b, SLOT_TEXTURE, "PHASER", false);
  UseBlock(b, SLOT_REVERB, "PLATE", true);
}

// Dub techno insert: tape colour and a dark FDN always on; the tape echo
// is off, ready to be thrown with its send button. CV1 rides its feedback
// into runaway, LFO1 slowly ages the repeats over two bars.
void DubThrow(Builder* b, Preset* p) {
  Begin(b, p, "DUB THROW", ALGORITHM_SERIAL, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", false);
  UseBlock(b, SLOT_DELAY, "TAPE DELAY", false);
  Note(b, "TIME", "1/8.");
  Set(b, "FEEDBACK", 0.62f);
  Step(b, "HEADS", 0);  // 1
  Set(b, "WOBBLE", 0.3f);
  Set(b, "DRIVE", 0.45f);
  Set(b, "AGE", 0.55f);
  Set(b, "WIDTH", 0.4f);
  Mix(b, 0.55f);
  Mod(b, "FEEDBACK", MOD_CV1, 40);
  Mod(b, "AGE", MOD_LFO1, 15);
  UseBlock(b, SLOT_TEXTURE, "TAPE SIM", true);
  Set(b, "DRIVE", 0.35f);
  Set(b, "WOW", 0.15f);
  Set(b, "FLUTTER", 0.15f);
  Set(b, "AGE", 0.35f);
  Set(b, "HISS", 0.15f);
  Set(b, "DROPOUT", 0.0f);
  Set(b, "BUMP", 0.35f);
  UseBlock(b, SLOT_REVERB, "FDN VERB", true);
  Set(b, "DECAY", 0.62f);
  Set(b, "SIZE", 0.7f);
  Note(b, "PREDELAY", "1/16");
  Set(b, "DAMP", 0.55f);
  Set(b, "MOD", 0.45f);
  Set(b, "LOWCUT", 0.45f);
  Mix(b, 0.3f);
  LfoNote(b, 0, LFO_SINE, "2 BAR");
}

// One note becomes a minor triad (+3 / +7), then the classic chain: a
// dotted ping-pong whose feedback ducks while you play (ENV) and swells in
// the gaps, a four-bar phaser, a big dark FDN. LFO1 breathes the delay's
// tone over two bars.
void DubChords(Builder* b, Preset* p) {
  Begin(b, p, "DUB CHORDS", ALGORITHM_SERIAL, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", true);
  Set(b, "PITCH A", Semitones(3.0f));
  Set(b, "PITCH B", Semitones(7.0f));
  Set(b, "DETUNE", 0.54f);  // +-4 cents
  Set(b, "DELAY", 0.0f);
  Set(b, "FEEDBACK", 0.0f);
  Set(b, "WINDOW", 0.7f);
  Set(b, "WIDTH", 0.6f);
  Mix(b, 0.45f);
  UseBlock(b, SLOT_DELAY, "DUAL DELAY", true);
  Note(b, "TIME L", "1/8.");
  Note(b, "TIME R", "1/4");
  Set(b, "FEEDBACK", 0.55f);
  Set(b, "CROSS", 0.7f);
  Set(b, "TONE", 0.3f);
  Set(b, "MOD", 0.15f);
  Set(b, "WIDTH", 0.9f);
  Mix(b, 0.4f);
  Mod(b, "FEEDBACK", MOD_ENVELOPE, -30);
  Mod(b, "TONE", MOD_LFO1, 12);
  UseBlock(b, SLOT_TEXTURE, "PHASER", true);
  Rate(b, "RATE", "4 BAR");
  Set(b, "DEPTH", 0.55f);
  Set(b, "CENTER", 0.45f);
  Set(b, "FEEDBACK", Bi(0.6f));
  Step(b, "STAGES", 2);  // 6
  Set(b, "SPREAD", 0.5f);
  Step(b, "SHAPE", 0);   // SINE
  Mix(b, 0.3f);
  UseBlock(b, SLOT_REVERB, "FDN VERB", true);
  Set(b, "DECAY", 0.66f);
  Set(b, "SIZE", 0.75f);
  Note(b, "PREDELAY", "1/32");
  Set(b, "DAMP", 0.6f);
  Set(b, "MOD", 0.5f);
  Set(b, "LOWCUT", 0.5f);
  Mix(b, 0.32f);
  LfoNote(b, 0, LFO_SINE, "2 BAR");
  Envelope(b, 0.005f, 0.6f, 6.0f);
}

// An octave-up grain cloud beside a dotted multi-tap, both through soft
// tape into a long, wide FDN. Random slowly stretches the grains; CV1
// feeds the cloud back on itself (octaves stacking up).
void ShimmerHalo(Builder* b, Preset* p) {
  Begin(b, p, "SHIMMER HALO", ALGORITHM_PD_T_R, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", true);
  Set(b, "PITCH", Semitones(12.0f));
  Set(b, "SPREAD", 0.15f);
  Set(b, "DENSITY", 0.6f);
  Set(b, "SIZE", 0.75f);
  Set(b, "DELAY", 0.25f);
  Set(b, "FEEDBACK", 0.45f);
  Set(b, "WIDTH", 0.9f);
  Mix(b, 0.5f);
  Mod(b, "SIZE", MOD_RANDOM, 20);
  Mod(b, "FEEDBACK", MOD_CV1, 40);
  UseBlock(b, SLOT_DELAY, "TAP DELAY", true);
  Note(b, "TIME", "1 BAR");
  Step(b, "PATTERN", 1);  // DOTTED
  Step(b, "TAPS", 3);     // 4 taps
  Set(b, "DECAY", 0.45f);
  Set(b, "FEEDBACK", 0.35f);
  Set(b, "SPREAD", 0.8f);
  Set(b, "TONE", 0.35f);
  Mix(b, 0.35f);
  UseBlock(b, SLOT_TEXTURE, "TAPE SIM", true);
  Set(b, "DRIVE", 0.2f);
  Set(b, "WOW", 0.3f);
  Set(b, "FLUTTER", 0.1f);
  Set(b, "AGE", 0.45f);
  Set(b, "HISS", 0.04f);
  Set(b, "DROPOUT", 0.0f);
  Set(b, "BUMP", 0.2f);
  UseBlock(b, SLOT_REVERB, "FDN VERB", true);
  Set(b, "DECAY", 0.78f);
  Set(b, "SIZE", 0.9f);
  Note(b, "PREDELAY", "1/16");
  Set(b, "DAMP", 0.45f);
  Set(b, "MOD", 0.6f);
  Set(b, "LOWCUT", 0.55f);
  Mix(b, 0.45f);
  Mod(b, "MOD", MOD_LFO1, 20);
  LfoHz(b, 0, LFO_SINE, 0.07f);
  RandomHz(b, 0.15f, 1.0f);
}

// BEADSY as a Clouds-like cloud on the clean-tape medium (10.7 s of
// memory), random grains wandering back through it, into a plate. The band
// delay and a sub-octave cloud sit beside it, off, to be thrown. CV1 sets
// the grain density, CV2 the pitch (1 V/oct).
void BeadsCloud(Builder* b, Preset* p) {
  Begin(b, p, "BEADS CLOUD", ALGORITHM_PDT_R, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", false);
  Set(b, "PITCH", Semitones(-12.0f));
  Set(b, "SPREAD", 0.3f);
  Set(b, "DENSITY", 0.5f);
  Set(b, "SIZE", 0.8f);
  Set(b, "DELAY", 0.4f);
  Set(b, "FEEDBACK", 0.2f);
  Set(b, "WIDTH", 1.0f);
  UseBlock(b, SLOT_DELAY, "BAND DELAY", false);
  Note(b, "TIME", "1/4");
  Set(b, "SPREAD", Bi(0.7f));
  Set(b, "FEEDBACK", 0.55f);
  Set(b, "FREQ", 0.45f);
  Set(b, "Q", 0.5f);
  Set(b, "TILT", Bi(-0.3f));
  Set(b, "WIDTH", 0.9f);
  Mix(b, 0.4f);
  UseBlock(b, SLOT_TEXTURE, "BEADSY", true);
  Set(b, "TIME", 0.45f);
  Set(b, "SIZE", 0.72f);     // 270 ms
  Set(b, "SHAPE", 0.55f);
  Set(b, "PITCH", Semitones(0.0f));
  Set(b, "DENSITY", 0.8f);   // random grains, about 7 per second
  Set(b, "FEEDBACK", 0.3f);
  Set(b, "REVERB", 0.35f);
  Step(b, "QUALITY", 1);     // CLEAN TAPE
  Set(b, "T RAND", Bi(0.5f));
  Set(b, "P RAND", Bi(0.12f));
  Step(b, "FREEZE", 0);
  Mix(b, 0.6f);
  Mod(b, "TIME", MOD_RANDOM, 20);
  Mod(b, "SIZE", MOD_LFO1, 12);
  Mod(b, "DENSITY", MOD_CV1, 40);
  Mod(b, "PITCH", MOD_CV2, 100);
  UseBlock(b, SLOT_REVERB, "PLATE", true);
  Set(b, "DECAY", 0.65f);
  Set(b, "SIZE", 0.75f);
  Set(b, "PREDELAY", 0.45f);
  Set(b, "DAMP", 0.5f);
  Set(b, "DIFFUSE", 0.85f);
  Set(b, "MOD", 0.45f);
  Set(b, "LOWCUT", 0.45f);
  LfoHz(b, 0, LFO_TRIANGLE, 0.05f);
  RandomHz(b, 0.1f, 0.9f);
}

// Two chains side by side: octaves (-12 / +12) into a two-head tape echo,
// and BEADSY on dotted-eighth grains into an APF wash. Hold a MIDI note
// and the grains freeze (GATE on FREEZE) and play at that note (NOTE on
// PITCH); the TEXTURE send button freezes it too.
void BeadsFreeze(Builder* b, Preset* p) {
  Begin(b, p, "BEADS FREEZE", ALGORITHM_PD_TR, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", true);
  Set(b, "PITCH A", Semitones(-12.0f));
  Set(b, "PITCH B", Semitones(12.0f));
  Set(b, "DETUNE", 0.55f);
  Set(b, "DELAY", 0.0f);
  Set(b, "FEEDBACK", 0.0f);
  Set(b, "WINDOW", 0.8f);
  Set(b, "WIDTH", 0.5f);
  Mix(b, 0.35f);
  UseBlock(b, SLOT_DELAY, "TAPE DELAY", true);
  Note(b, "TIME", "1/4");
  Set(b, "FEEDBACK", 0.5f);
  Step(b, "HEADS", 3);  // 1+2
  Set(b, "WOBBLE", 0.3f);
  Set(b, "DRIVE", 0.35f);
  Set(b, "AGE", 0.6f);
  Set(b, "WIDTH", 0.7f);
  UseBlock(b, SLOT_TEXTURE, "BEADSY", true);
  Set(b, "TIME", 0.25f);
  Set(b, "SIZE", 0.75f);
  Set(b, "SHAPE", 0.6f);
  Set(b, "PITCH", Semitones(0.0f));
  Synced(b, "DENSITY", 0.14f);  // a grain every dotted eighth
  Set(b, "FEEDBACK", 0.15f);
  Set(b, "REVERB", 0.5f);
  Step(b, "QUALITY", 3);        // HIFI 16BIT
  Set(b, "T RAND", Bi(0.3f));
  Set(b, "P RAND", Bi(0.24f));
  Step(b, "FREEZE", 0);
  Mix(b, 0.7f);
  Mod(b, "FREEZE", MOD_GATE, 100);
  Mod(b, "PITCH", MOD_NOTE, 100);
  Mod(b, "TIME", MOD_LFO1, 15);
  UseBlock(b, SLOT_REVERB, "APF CHAIN", true);
  Set(b, "LENGTH", 0.6f);
  Step(b, "STAGES", 5);  // 12
  Set(b, "DIFFUSE", 0.7f);
  Set(b, "FEEDBACK", 0.6f);
  Set(b, "DAMP", 0.5f);
  Set(b, "MOD", 0.4f);
  Set(b, "WIDTH", 0.9f);
  Mix(b, 0.5f);
  LfoNote(b, 0, LFO_SINE, "4 BAR");
}

// Sixteenth-note stutters (glitch) beside a crushed hard clip, into a
// short plate; a fifth-up grain cloud is off, ready to throw. LFO2's
// sample-and-hold bends the repeats every half bar; CV1 raises the chance.
void GlitchBreaks(Builder* b, Preset* p) {
  Begin(b, p, "GLITCH BREAKS", ALGORITHM_P_DT_R, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", false);
  Set(b, "PITCH", Semitones(7.0f));
  Set(b, "SPREAD", 0.1f);
  Rate(b, "DENSITY", "1/16");
  Note(b, "SIZE", "1/16");
  Note(b, "DELAY", "1/8");
  Set(b, "FEEDBACK", 0.3f);
  Set(b, "WIDTH", 0.9f);
  UseBlock(b, SLOT_DELAY, "GLITCH", true);
  Note(b, "SLICE", "1/16");
  Set(b, "CHANCE", 0.3f);
  Step(b, "REPEATS", 3);  // 4
  Set(b, "REVERSE", 0.25f);
  Set(b, "PITCH", Semitones(0.0f));
  Set(b, "CRUSH", 0.15f);
  Set(b, "SHUFFLE", 0.3f);
  Mod(b, "PITCH", MOD_LFO2, 12);
  Mod(b, "CHANCE", MOD_CV1, 50);
  UseBlock(b, SLOT_TEXTURE, "WAVESHAPER", true);
  Step(b, "MODE", 1);  // HARD
  Set(b, "DRIVE", 0.35f);
  Set(b, "BIAS", Bi(0.1f));
  Set(b, "TONE", Bi(-0.2f));
  Set(b, "BITS", 0.6f);
  Set(b, "RATE", 0.8f);
  Set(b, "LEVEL", Bi(-0.1f));
  Mix(b, 0.5f);
  UseBlock(b, SLOT_REVERB, "PLATE", true);
  Set(b, "DECAY", 0.3f);
  Set(b, "SIZE", 0.4f);
  Set(b, "PREDELAY", 0.2f);
  Set(b, "DAMP", 0.5f);
  Set(b, "DIFFUSE", 0.7f);
  Set(b, "MOD", 0.2f);
  Set(b, "LOWCUT", 0.5f);
  Mix(b, 0.25f);
  LfoNote(b, 1, LFO_STEPS, "1/2");
}

// Percussion into tuned metal: a minor-seventh resonator (1 V/oct on CV1,
// random drifting between neighbouring chords every bar) beside a clave
// multi-tap, into an FDN. The fifth shifter waits, off.
void MetalRings(Builder* b, Preset* p) {
  Begin(b, p, "METAL RINGS", ALGORITHM_P_DT_R, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", false);
  Note(b, "DELAY", "1/8");
  UseBlock(b, SLOT_DELAY, "TAP DELAY", true);
  Note(b, "TIME", "1 BAR");
  Step(b, "PATTERN", 4);  // CLAVE
  Step(b, "TAPS", 4);     // 5 taps
  Set(b, "DECAY", 0.35f);
  Set(b, "FEEDBACK", 0.3f);
  Set(b, "SPREAD", 0.75f);
  Set(b, "TONE", Bi(-0.4f));
  Mix(b, 0.4f);
  UseBlock(b, SLOT_TEXTURE, "RESONATOR", true);
  Set(b, "PITCH", Semitones(0.0f));
  Step(b, "CHORD", 7);  // MIN7
  Note(b, "DECAY", "1/4");
  Set(b, "DAMP", 0.45f);
  Set(b, "DETUNE", 0.2f);
  Set(b, "SPREAD", 0.7f);
  Set(b, "DRIVE", 0.3f);
  Mix(b, 0.45f);
  Mod(b, "PITCH", MOD_CV1, 100);
  Mod(b, "CHORD", MOD_RANDOM, 20);
  UseBlock(b, SLOT_REVERB, "FDN VERB", true);
  Set(b, "DECAY", 0.55f);
  Set(b, "SIZE", 0.6f);
  Note(b, "PREDELAY", "1/32");
  Set(b, "DAMP", 0.5f);
  Set(b, "LOWCUT", 0.4f);
  Mix(b, 0.3f);
  RandomNote(b, "1 BAR", 0.0f);
}

// A drone engine: a sub-octave cloud into slowly swept combs at C2 that
// follow MIDI notes, into a modal body at C2 (which follows them too). The
// phaser is off; throw it in for movement.
void CombDrone(Builder* b, Preset* p) {
  Begin(b, p, "COMB DRONE", ALGORITHM_SERIAL, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", true);
  Set(b, "PITCH", Semitones(-12.0f));
  Set(b, "SPREAD", 0.35f);
  Set(b, "DENSITY", 0.55f);
  Set(b, "SIZE", 0.85f);
  Set(b, "DELAY", 0.5f);
  Set(b, "FEEDBACK", 0.35f);
  Set(b, "WIDTH", 1.0f);
  Mix(b, 0.4f);
  UseBlock(b, SLOT_DELAY, "MOD COMBS", true);
  Set(b, "FREQ", CombHz(65.41f));  // C2
  Set(b, "FEEDBACK", Bi(0.88f));
  Rate(b, "RATE", "2 BAR");
  Set(b, "DEPTH", 0.25f);
  Step(b, "VOICES", 2);  // 3
  Set(b, "SPREAD", 0.8f);
  Set(b, "DAMP", 0.45f);
  Mix(b, 0.55f);
  Mod(b, "FREQ", MOD_NOTE, kCombNoteDepth);
  UseBlock(b, SLOT_TEXTURE, "PHASER", false);
  Set(b, "RATE", 0.2f);
  Set(b, "DEPTH", 0.6f);
  Set(b, "CENTER", 0.4f);
  Set(b, "FEEDBACK", Bi(0.75f));
  Step(b, "STAGES", 3);  // 8
  Set(b, "SPREAD", 0.7f);
  Step(b, "SHAPE", 1);   // TRIANGLE
  UseBlock(b, SLOT_REVERB, "MODAL", true);
  Set(b, "PITCH", Semitones(0.0f));  // C2
  Set(b, "STRUCT", 0.2f);
  Set(b, "DECAY", 0.75f);
  Set(b, "BRIGHT", 0.35f);
  Set(b, "DENSITY", 0.6f);
  Set(b, "WIDTH", 0.9f);
  Set(b, "DRIFT", 0.35f);
  Mix(b, 0.4f);
  Mod(b, "PITCH", MOD_NOTE, 100);
  Mod(b, "DRIFT", MOD_LFO1, 20);
  LfoHz(b, 0, LFO_SINE, 0.03f);
}

// Future / US bass at 140: octaves around the bass, combs at C2 swept in
// triplet eighths, then a wavefolder whose drive wobbles with LFO1 (1/8T)
// and whose bias follows the playing (ENV). The plate is off, its low end
// cut, for throws on the drops.
void WobbleBass(Builder* b, Preset* p) {
  Begin(b, p, "WOBBLE BASS", ALGORITHM_SERIAL, 140);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", true);
  Set(b, "PITCH A", Semitones(-12.0f));
  Set(b, "PITCH B", Semitones(12.0f));
  Set(b, "DETUNE", 0.58f);
  Set(b, "DELAY", 0.0f);
  Set(b, "FEEDBACK", 0.0f);
  Set(b, "WINDOW", 0.45f);
  Set(b, "WIDTH", 0.4f);
  Mix(b, 0.3f);
  UseBlock(b, SLOT_DELAY, "MOD COMBS", true);
  Set(b, "FREQ", CombHz(65.41f));
  Set(b, "FEEDBACK", Bi(0.7f));
  Rate(b, "RATE", "1/8T");
  Set(b, "DEPTH", 0.35f);
  Step(b, "VOICES", 1);  // 2
  Set(b, "SPREAD", 0.6f);
  Set(b, "DAMP", 0.3f);
  Mix(b, 0.35f);
  Mod(b, "DEPTH", MOD_LFO2, 15);
  UseBlock(b, SLOT_TEXTURE, "WAVESHAPER", true);
  Step(b, "MODE", 2);  // FOLD
  Set(b, "DRIVE", 0.4f);
  Set(b, "BIAS", Bi(0.1f));
  Set(b, "TONE", Bi(-0.1f));
  Set(b, "LEVEL", Bi(-0.1f));
  Mod(b, "DRIVE", MOD_LFO1, 30);
  Mod(b, "BIAS", MOD_ENVELOPE, 20);
  UseBlock(b, SLOT_REVERB, "PLATE", false);
  Set(b, "DECAY", 0.4f);
  Set(b, "SIZE", 0.5f);
  Note(b, "PREDELAY", "1/16");
  Set(b, "DAMP", 0.55f);
  Set(b, "LOWCUT", 0.75f);
  Mix(b, 0.3f);
  LfoNote(b, 0, LFO_SINE, "1/8T");
  LfoNote(b, 1, LFO_RAMP_DOWN, "1 BAR");
  Envelope(b, 0.002f, 0.15f, 9.0f);
}

// A band-split dub echo (high bands later than low ones) whose centre
// drifts over four bars, beside a phaser into a plate. CV1 pushes the
// band feedback.
void SpectralDub(Builder* b, Preset* p) {
  Begin(b, p, "SPECTRAL DUB", ALGORITHM_PD_TR, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", false);
  Note(b, "DELAY", "1/8");
  UseBlock(b, SLOT_DELAY, "BAND DELAY", true);
  Note(b, "TIME", "1/8.");
  Set(b, "SPREAD", Bi(0.7f));
  Set(b, "FEEDBACK", 0.6f);
  Set(b, "FREQ", 0.45f);
  Set(b, "Q", 0.55f);
  Set(b, "TILT", Bi(-0.3f));
  Set(b, "WIDTH", 0.9f);
  Mix(b, 0.45f);
  Mod(b, "FREQ", MOD_LFO1, 25);
  Mod(b, "FEEDBACK", MOD_CV1, 40);
  UseBlock(b, SLOT_TEXTURE, "PHASER", true);
  Rate(b, "RATE", "2 BAR");
  Set(b, "DEPTH", 0.6f);
  Set(b, "CENTER", 0.5f);
  Set(b, "FEEDBACK", Bi(0.6f));
  Step(b, "STAGES", 4);  // 10
  Set(b, "SPREAD", 0.6f);
  Step(b, "SHAPE", 0);   // SINE
  Mix(b, 0.5f);
  UseBlock(b, SLOT_REVERB, "PLATE", true);
  Set(b, "DECAY", 0.7f);
  Set(b, "SIZE", 0.8f);
  Note(b, "PREDELAY", "1/16");
  Set(b, "DAMP", 0.55f);
  Set(b, "DIFFUSE", 0.85f);
  Set(b, "MOD", 0.5f);
  Set(b, "LOWCUT", 0.5f);
  Mix(b, 0.4f);
  LfoNote(b, 0, LFO_TRIANGLE, "4 BAR");
}

// Bells for pads and plucks: an octave-up spread cloud beside a dotted
// quarter / half ping-pong, into a bell-structured modal body ringing a
// bar, its structure wandering every two bars. A sus4 resonator is off,
// ready to throw.
void ModalBells(Builder* b, Preset* p) {
  Begin(b, p, "MODAL BELLS", ALGORITHM_PD_T_R, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", true);
  Set(b, "PITCH", Semitones(12.0f));
  Set(b, "SPREAD", 0.45f);
  Set(b, "DENSITY", 0.5f);
  Set(b, "SIZE", 0.7f);
  Set(b, "DELAY", 0.3f);
  Set(b, "FEEDBACK", 0.3f);
  Set(b, "WIDTH", 1.0f);
  Mix(b, 0.4f);
  UseBlock(b, SLOT_DELAY, "DUAL DELAY", true);
  Note(b, "TIME L", "1/4.");
  Note(b, "TIME R", "1/2");
  Set(b, "FEEDBACK", 0.45f);
  Set(b, "CROSS", 0.8f);
  Set(b, "TONE", 0.25f);
  Set(b, "MOD", 0.25f);
  Mix(b, 0.35f);
  UseBlock(b, SLOT_TEXTURE, "RESONATOR", false);
  Step(b, "CHORD", 5);  // SUS4
  Set(b, "DECAY", 0.6f);
  Set(b, "DAMP", 0.5f);
  Set(b, "DETUNE", 0.3f);
  Mix(b, 0.4f);
  UseBlock(b, SLOT_REVERB, "MODAL", true);
  Set(b, "PITCH", Semitones(12.0f));  // C3
  Set(b, "STRUCT", 0.67f);            // BELL
  Note(b, "DECAY", "1 BAR");
  Set(b, "BRIGHT", 0.55f);
  Set(b, "DENSITY", 0.75f);
  Set(b, "WIDTH", 1.0f);
  Set(b, "DRIFT", 0.3f);
  Mix(b, 0.45f);
  Mod(b, "STRUCT", MOD_RANDOM, 15);
  RandomNote(b, "2 BAR", 1.0f);
}

// Four returns for a mixer's send, only the plate open: throw the others.
// The tape echo also opens while a MIDI note is held (GATE), the
// resonator while CV4 is high (a gate from a sequencer). CV1 rides the
// echo's feedback.
void FourSends(Builder* b, Preset* p) {
  Begin(b, p, "FOUR SENDS", ALGORITHM_PARALLEL, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", false);
  Set(b, "PITCH", Semitones(-12.0f));
  Set(b, "SPREAD", 0.2f);
  Set(b, "DENSITY", 0.55f);
  Set(b, "SIZE", 0.8f);
  Set(b, "DELAY", 0.35f);
  Set(b, "FEEDBACK", 0.4f);
  Set(b, "WIDTH", 1.0f);
  Mix(b, 0.6f);
  UseBlock(b, SLOT_DELAY, "TAPE DELAY", false);
  Note(b, "TIME", "1/8.");
  Set(b, "FEEDBACK", 0.6f);
  Step(b, "HEADS", 5);  // 1+3
  Set(b, "WOBBLE", 0.25f);
  Set(b, "DRIVE", 0.4f);
  Set(b, "AGE", 0.5f);
  Set(b, "WIDTH", 0.8f);
  Mix(b, 0.6f);
  Gate(b, MOD_GATE);
  Mod(b, "FEEDBACK", MOD_CV1, 40);
  UseBlock(b, SLOT_TEXTURE, "RESONATOR", false);
  Step(b, "CHORD", 4);  // MINOR
  Note(b, "DECAY", "1/2");
  Set(b, "DAMP", 0.5f);
  Set(b, "SPREAD", 0.8f);
  Mix(b, 0.6f);
  Gate(b, MOD_CV4);
  Mod(b, "PITCH", MOD_CV2, 100);
  UseBlock(b, SLOT_REVERB, "PLATE", true);
  Set(b, "DECAY", 0.68f);
  Set(b, "SIZE", 0.8f);
  Note(b, "PREDELAY", "1/32");
  Set(b, "DAMP", 0.5f);
  Set(b, "MOD", 0.45f);
  Set(b, "LOWCUT", 0.45f);
  Mix(b, 0.5f);
}

// Hands-free throws: the sends follow synced LFO squares. The multi-tap
// opens for the first half of every bar (LFO1), the fifth shifter every
// other bar (LFO2); BEADSY plays sixteenth grains into a quarter-note
// diffuser loop.
void RhythmGates(Builder* b, Preset* p) {
  Begin(b, p, "RHYTHM GATES", ALGORITHM_PARALLEL, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", false);
  Note(b, "DELAY", "1/16");
  Set(b, "FEEDBACK", 0.45f);
  Mix(b, 0.5f);
  Gate(b, MOD_LFO2);
  UseBlock(b, SLOT_DELAY, "TAP DELAY", false);
  Note(b, "TIME", "1/2");
  Step(b, "PATTERN", 2);  // SWING
  Step(b, "TAPS", 5);     // 6 taps
  Set(b, "DECAY", 0.4f);
  Set(b, "FEEDBACK", 0.4f);
  Set(b, "SPREAD", 0.85f);
  Mix(b, 0.5f);
  Gate(b, MOD_LFO1);
  UseBlock(b, SLOT_TEXTURE, "BEADSY", true);
  Set(b, "TIME", 0.2f);
  Set(b, "SIZE", 0.55f);  // 55 ms
  Set(b, "SHAPE", 0.4f);
  Set(b, "PITCH", Semitones(0.0f));
  // Right of centre: each 16th fires with probability ((v - 0.52) * 2.15)^2,
  // here 74 %: a sixteenth pulse with a few gaps that move.
  Synced(b, "DENSITY", 0.92f);
  Set(b, "FEEDBACK", 0.2f);
  Set(b, "REVERB", 0.2f);
  Step(b, "QUALITY", 2);       // LOFI 12BIT
  Set(b, "T RAND", Bi(0.2f));
  Set(b, "P RAND", Bi(-0.3f));  // now and then a grain jumps away
  Step(b, "FREEZE", 0);
  Mix(b, 0.5f);
  Mod(b, "SIZE", MOD_RANDOM, 15);
  UseBlock(b, SLOT_REVERB, "APF CHAIN", true);
  Note(b, "LENGTH", "1/4");
  Step(b, "STAGES", 3);  // 8
  Set(b, "DIFFUSE", 0.65f);
  Set(b, "FEEDBACK", 0.55f);
  Set(b, "DAMP", 0.5f);
  Set(b, "MOD", 0.3f);
  Mix(b, 0.4f);
  LfoNote(b, 0, LFO_SQUARE, "1 BAR");
  LfoNote(b, 1, LFO_SQUARE, "2 BAR");
  RandomNote(b, "1/4", 0.3f);
}

// Two mono chains for two sources: IN 1 (a lead, a stab) through octaves
// into a three-head tape echo; IN 2 (drums, a pad) through tape into an
// APF diffuser. CV1 rides the echo's feedback, CV2 the diffuser's.
void SplitRig(Builder* b, Preset* p) {
  Begin(b, p, "SPLIT RIG", ALGORITHM_DUAL_MONO, 120);
  UseBlock(b, SLOT_PITCH, "DUAL SHIFT", true);
  Set(b, "PITCH A", Semitones(12.0f));
  Set(b, "PITCH B", Semitones(-12.0f));
  Set(b, "DETUNE", 0.56f);
  Set(b, "DELAY", 0.0f);
  Set(b, "FEEDBACK", 0.0f);
  Mix(b, 0.3f);
  UseBlock(b, SLOT_DELAY, "TAPE DELAY", true);
  Note(b, "TIME", "1/16.");
  Set(b, "FEEDBACK", 0.45f);
  Step(b, "HEADS", 6);  // 1+2+3
  Set(b, "WOBBLE", 0.35f);
  Set(b, "DRIVE", 0.4f);
  Set(b, "AGE", 0.5f);
  Mix(b, 0.4f);
  Mod(b, "FEEDBACK", MOD_CV1, 40);
  UseBlock(b, SLOT_TEXTURE, "TAPE SIM", true);
  Set(b, "DRIVE", 0.45f);
  Set(b, "WOW", 0.1f);
  Set(b, "FLUTTER", 0.15f);
  Set(b, "AGE", 0.4f);
  Set(b, "HISS", 0.06f);
  Set(b, "DROPOUT", 0.1f);
  Set(b, "BUMP", 0.5f);
  Mod(b, "WOW", MOD_LFO1, 15);
  UseBlock(b, SLOT_REVERB, "APF CHAIN", true);
  Set(b, "LENGTH", 0.55f);
  Step(b, "STAGES", 7);  // 16
  Set(b, "DIFFUSE", 0.7f);
  Set(b, "FEEDBACK", 0.5f);
  Set(b, "DAMP", 0.55f);
  Set(b, "MOD", 0.35f);
  Mix(b, 0.35f);
  Mod(b, "FEEDBACK", MOD_CV2, 40);
  LfoHz(b, 0, LFO_TRIANGLE, 0.2f);
}

// Two mono chains: IN 1 (drums) through a cloud into eighth-note
// stutters; IN 2 (a bass or a lead) through a soft fold into a string-like
// modal body that tracks CV3 at 1 V/oct.
void SplitGlitch(Builder* b, Preset* p) {
  Begin(b, p, "SPLIT GLITCH", ALGORITHM_DUAL_MONO, 120);
  UseBlock(b, SLOT_PITCH, "GRANULATOR", true);
  Set(b, "PITCH", Semitones(0.0f));
  Set(b, "SPREAD", 0.25f);
  Rate(b, "DENSITY", "1/16");
  Note(b, "SIZE", "1/32");
  Note(b, "DELAY", "1/16");
  Set(b, "FEEDBACK", 0.2f);
  Mix(b, 0.35f);
  UseBlock(b, SLOT_DELAY, "GLITCH", true);
  Note(b, "SLICE", "1/8");
  Set(b, "CHANCE", 0.4f);
  Step(b, "REPEATS", 2);  // 3
  Set(b, "REVERSE", 0.3f);
  Set(b, "PITCH", Semitones(0.0f));
  Set(b, "CRUSH", 0.0f);
  Set(b, "SHUFFLE", 0.35f);
  Mod(b, "REVERSE", MOD_RANDOM, 25);
  UseBlock(b, SLOT_TEXTURE, "WAVESHAPER", true);
  Step(b, "MODE", 5);  // SINE
  Set(b, "DRIVE", 0.3f);
  Set(b, "TONE", Bi(-0.25f));
  Mix(b, 0.6f);
  Mod(b, "DRIVE", MOD_ENVELOPE, 25);
  UseBlock(b, SLOT_REVERB, "MODAL", true);
  Set(b, "PITCH", Semitones(0.0f));
  Set(b, "STRUCT", 0.33f);  // STRING
  Set(b, "DECAY", 0.55f);
  Set(b, "BRIGHT", 0.45f);
  Set(b, "DENSITY", 0.5f);
  Set(b, "DRIFT", 0.25f);
  Mix(b, 0.4f);
  Mod(b, "PITCH", MOD_CV3, 100);
  RandomNote(b, "1/2", 0.0f);
  Envelope(b, 0.003f, 0.3f, 6.0f);
}

typedef void (*BuildFunction)(Builder* b, Preset* p);

const BuildFunction kBuilders[] = {
  CleanStart, DubThrow, DubChords, ShimmerHalo, BeadsCloud, BeadsFreeze,
  GlitchBreaks, MetalRings, CombDrone, WobbleBass, SpectralDub, ModalBells,
  FourSends, RhythmGates, SplitRig, SplitGlitch,
};

const int kNumBuilders = int(sizeof(kBuilders) / sizeof(kBuilders[0]));

}  // namespace

int FactoryPresetMisses() { return misses; }

int NumFactoryPresets() { return kNumBuilders; }

void GetFactoryPreset(int index, Preset* preset) {
  if (index < 0 || index >= kNumBuilders) {
    InitPreset(preset);
    return;
  }
  Builder b;
  kBuilders[index](&b, preset);
  SealPreset(preset);
}

}  // namespace sidefx
