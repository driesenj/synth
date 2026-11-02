// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/params.h"

#include <math.h>

namespace sidefx {

const NoteValue kNoteValues[] = {
  { "1/64", 0.0625f },
  { "1/32T", 1.0f / 12.0f },
  { "1/32", 0.125f },
  { "1/16T", 1.0f / 6.0f },
  { "1/32.", 0.1875f },
  { "1/16", 0.25f },
  { "1/8T", 1.0f / 3.0f },
  { "1/16.", 0.375f },
  { "1/8", 0.5f },
  { "1/4T", 2.0f / 3.0f },
  { "1/8.", 0.75f },
  { "1/4", 1.0f },
  { "1/2T", 4.0f / 3.0f },
  { "1/4.", 1.5f },
  { "1/2", 2.0f },
  { "1/1T", 8.0f / 3.0f },
  { "1/2.", 3.0f },
  { "1 BAR", 4.0f },
  { "2 BAR", 8.0f },
  { "4 BAR", 16.0f },
};
const int kNumNoteValues = sizeof(kNoteValues) / sizeof(kNoteValues[0]);

float ExpMap(float value, float min, float max) {
  return min * expf(logf(max / min) * value);
}

float ExpUnmap(float x, float min, float max) {
  return logf(x / min) / logf(max / min);
}

int NoteValueIndex(float value) {
  return StepIndex(value, kNumNoteValues);
}

float SyncedSeconds(float value, float beat_seconds) {
  return kNoteValues[NoteValueIndex(value)].beats * beat_seconds;
}

int SyncedRateIndex(float value) {
  return NoteValueIndex(1.0f - value);
}

float SyncedHz(float value, float beat_seconds) {
  return 1.0f / (kNoteValues[SyncedRateIndex(value)].beats * beat_seconds);
}

float TimeParam(float value, bool synced, float beat_seconds,
                float min_seconds, float max_seconds) {
  if (synced) {
    float t = SyncedSeconds(value, beat_seconds);
    return t > max_seconds ? max_seconds : t;
  }
  return ExpMap(value, min_seconds, max_seconds);
}

float RateParam(float value, bool synced, float beat_seconds,
                float min_hz, float max_hz) {
  return synced
      ? SyncedHz(value, beat_seconds)
      : ExpMap(value, min_hz, max_hz);
}

// --- text -------------------------------------------------------------------

void CopyText(char* text, size_t size, const char* source) {
  if (!size) {
    return;
  }
  size_t i = 0;
  while (source && source[i] && i + 1 < size) {
    text[i] = source[i];
    ++i;
  }
  text[i] = '\0';
}

size_t FormatNumber(char* text, size_t size, float value, int decimals,
                    bool plus_sign, const char* suffix) {
  if (!size) {
    return 0;
  }
  char buffer[32];
  size_t n = 0;
  uint32_t scale = 1;
  for (int i = 0; i < decimals; ++i) {
    scale *= 10;
  }
  float magnitude = fabsf(value) * float(scale) + 0.5f;
  if (!(magnitude < 4.0e9f)) {
    magnitude = 4.0e9f;  // also catches NaN
  }
  uint32_t scaled = static_cast<uint32_t>(magnitude);
  if (scaled != 0) {
    if (value < 0.0f) {
      buffer[n++] = '-';
    } else if (plus_sign) {
      buffer[n++] = '+';
    }
  }
  uint32_t integer = scaled / scale;
  uint32_t fraction = scaled % scale;
  char digits[12];
  size_t d = 0;
  do {
    digits[d++] = char('0' + integer % 10);
    integer /= 10;
  } while (integer && d < sizeof(digits));
  while (d) {
    buffer[n++] = digits[--d];
  }
  if (decimals > 0) {
    buffer[n++] = '.';
    uint32_t divisor = scale / 10;
    for (int i = 0; i < decimals; ++i) {
      buffer[n++] = char('0' + (fraction / divisor) % 10);
      divisor /= 10;
      if (!divisor) {
        divisor = 1;
      }
    }
  }
  while (suffix && *suffix && n + 1 < sizeof(buffer)) {
    buffer[n++] = *suffix++;
  }
  buffer[n] = '\0';
  CopyText(text, size, buffer);
  return n < size ? n : size - 1;
}

void FormatPercent(char* text, size_t size, float value) {
  FormatNumber(text, size, value * 100.0f, 0, false, "%");
}

void FormatBipolarPercent(char* text, size_t size, float value) {
  FormatNumber(text, size, Bipolar(value, 100.0f), 0, true, "%");
}

void FormatSeconds(char* text, size_t size, float seconds) {
  if (seconds < 0.00995f) {
    FormatNumber(text, size, seconds * 1000.0f, 1, false, "ms");
  } else if (seconds < 0.9995f) {
    FormatNumber(text, size, seconds * 1000.0f, 0, false, "ms");
  } else if (seconds < 9.995f) {
    FormatNumber(text, size, seconds, 2, false, "s");
  } else {
    FormatNumber(text, size, seconds, 1, false, "s");
  }
}

void FormatHz(char* text, size_t size, float hz) {
  if (hz < 9.995f) {
    FormatNumber(text, size, hz, 2, false, "Hz");
  } else if (hz < 99.95f) {
    FormatNumber(text, size, hz, 1, false, "Hz");
  } else if (hz < 999.5f) {
    FormatNumber(text, size, hz, 0, false, "Hz");
  } else {
    FormatNumber(text, size, hz / 1000.0f, 1, false, "kHz");
  }
}

void FormatSemitones(char* text, size_t size, float semitones,
                     bool fractional) {
  if (fractional) {
    FormatNumber(text, size, semitones, 2, true, "");
  } else {
    FormatNumber(text, size, semitones, 0, true, "st");
  }
}

void FormatDecibels(char* text, size_t size, float db) {
  FormatNumber(text, size, db, fabsf(db) < 9.95f ? 1 : 0, true, "dB");
}

void FormatNoteValue(char* text, size_t size, int index) {
  if (index < 0) {
    index = 0;
  } else if (index >= kNumNoteValues) {
    index = kNumNoteValues - 1;
  }
  CopyText(text, size, kNoteValues[index].label);
}

void FormatLabel(char* text, size_t size, const char* const* labels,
                 int index) {
  CopyText(text, size, labels[index]);
}

}  // namespace sidefx
