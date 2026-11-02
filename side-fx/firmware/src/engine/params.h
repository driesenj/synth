// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: parameter descriptions, the shared mappings from a knob's 0..1
// value to physical units, the tempo-synced note values, and the text the
// screen shows for them.
//
// Every parameter travels as a float in 0..1 (stored as 0..65535 in a
// preset). A block maps it to whatever it means; the helpers below keep the
// common mappings and their display identical across blocks. The text
// formatters write at most `size` bytes including the terminating zero and
// never use printf (newlib-nano's has no floats).

#ifndef SIDEFX_ENGINE_PARAMS_H_
#define SIDEFX_ENGINE_PARAMS_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {

enum ParamFlags {
  // A time or a rate. When the parameter's sync bit is set (SHIFT + push
  // its knob), it steps through kNoteValues at the current tempo instead.
  PARAM_SYNC = 1,
  // Neutral in the middle (pitch, bipolar feedback): the screen draws the
  // value bar from the centre.
  PARAM_BIPOLAR = 2,
  // num_steps discrete values; the block reads StepIndex(value, num_steps).
  PARAM_STEPPED = 4,
};

struct ParamInfo {
  const char* name;      // the row's label, at most 8 characters, upper case
  float default_value;   // 0..1 (stepped: StepValue(index, num_steps))
  uint8_t flags;         // ParamFlags
  uint8_t num_steps;     // PARAM_STEPPED: number of values, >= 2
  // Encoder detents across the whole range when turned slowly: 48 for a
  // +-24 semitone pitch gives one semitone per detent. 0 means 128. Stepped
  // parameters move one step per detent and ignore this.
  uint16_t detents;
};

inline int StepIndex(float value, int num_steps) {
  int i = static_cast<int>(value * float(num_steps - 1) + 0.5f);
  return i < 0 ? 0 : (i > num_steps - 1 ? num_steps - 1 : i);
}

inline float StepValue(int index, int num_steps) {
  return num_steps > 1 ? float(index) / float(num_steps - 1) : 0.0f;
}

// --- mappings ---------------------------------------------------------------

// min * (max / min) ^ value. min and max > 0.
float ExpMap(float value, float min, float max);
// Inverse of ExpMap, for defaults: the value that maps to x.
float ExpUnmap(float x, float min, float max);

// (2 * value - 1) * range: a bipolar parameter, 0 in the middle.
inline float Bipolar(float value, float range) {
  return (2.0f * value - 1.0f) * range;
}

// --- tempo-synced note values ---------------------------------------------

struct NoteValue {
  const char* label;  // "1/8.", "1/4T", "1 BAR"
  float beats;        // in quarter notes
};

// Shortest first: 1/64 ... 4 BAR.
extern const NoteValue kNoteValues[];
extern const int kNumNoteValues;

// value 0 -> kNoteValues[0] (shortest), 1 -> the longest.
int NoteValueIndex(float value);
// A synced time: the note value's length at this tempo.
float SyncedSeconds(float value, float beat_seconds);
// A synced rate: value 0 is the slowest (4 bars), 1 the fastest (1/64).
float SyncedHz(float value, float beat_seconds);
// The note value a synced rate parameter shows.
int SyncedRateIndex(float value);

// A time parameter: ExpMap(value, min, max) seconds, or the note value when
// synced (clamped to max_seconds: the block's buffer is only so long).
float TimeParam(float value, bool synced, float beat_seconds,
                float min_seconds, float max_seconds);
// A rate parameter: ExpMap(value, min_hz, max_hz), or the synced rate.
float RateParam(float value, bool synced, float beat_seconds,
                float min_hz, float max_hz);

// --- text -------------------------------------------------------------------

// "7", "-12", "+3" (plus_sign), "1.25", "-0.5" with `decimals` digits after
// the point. Appends suffix. Returns the length written.
size_t FormatNumber(char* text, size_t size, float value, int decimals,
                    bool plus_sign, const char* suffix);

void FormatPercent(char* text, size_t size, float value);         // 0..1 -> "62%"
void FormatBipolarPercent(char* text, size_t size, float value);  // 0..1 -> "-100%".."+100%"
void FormatSeconds(char* text, size_t size, float seconds);       // "4.5ms" "350ms" "1.25s" "12.5s"
void FormatHz(char* text, size_t size, float hz);                 // "0.25Hz" "12.5Hz" "1.2kHz"
void FormatSemitones(char* text, size_t size, float semitones, bool fractional);  // "+7st" "-12st" "+7.25"
void FormatDecibels(char* text, size_t size, float db);           // "-6.0dB" "+12dB"
void FormatNoteValue(char* text, size_t size, int index);
void FormatLabel(char* text, size_t size, const char* const* labels, int index);
void CopyText(char* text, size_t size, const char* source);

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_PARAMS_H_
