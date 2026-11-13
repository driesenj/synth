// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the module settings, their defaults and their store.

#include "app/settings.h"

#include <math.h>
#include <string.h>

#include "engine/crc32.h"

namespace sidefx {

const uint8_t kClockPpqnValues[kNumClockPpqn] = { 1, 2, 4, 8, 12, 24 };

namespace {

const uint32_t kSettingsTag = 0x54534653;  // "SFST"
const uint32_t kSettingsSlotSize = 128;
const uint32_t kSaveDelayMs = 5000;

// Nominal calibration within these bounds is kept; anything else (a
// corrupt record, a calibration run with nothing patched) falls back.
const float kMinOffset = 0.42f;   // nominal 0.502; +-0.08 is about +-2 V
const float kMaxOffset = 0.58f;
const float kMinScale = -40.0f;   // nominal -25.38
const float kMaxScale = -12.0f;

template<typename T>
T Clamp(T x, T lo, T hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

uint32_t SettingsCrc(const Settings& s) {
  return Crc32(0, &s, offsetof(Settings, crc));
}

void Seal(Settings* s) {
  s->magic = kSettingsMagic;
  s->version = kSettingsVersion;
  s->crc = SettingsCrc(*s);
}

}  // namespace

void InitSettings(Settings* s) {
  memset(s, 0, sizeof(*s));
  s->magic = kSettingsMagic;
  s->version = kSettingsVersion;
  s->last_preset = 0;
  s->midi_channel = 0;
  s->cc_a = 1;
  s->cc_b = 11;
  s->clock_ppqn = 2;
  s->brightness = 8;
  s->display_flip = 0;
  s->encoder_steps = 4;
  s->encoder_reverse = 0;
  s->invert_output = 0;
  s->dry = 65535;
  s->input_gain = 0;
  s->output_gain = 0;
  InitCvCalibration(&s->calibration);
  s->crc = SettingsCrc(*s);
}

void SanitizeSettings(Settings* s) {
  s->last_preset = Clamp<uint8_t>(s->last_preset, 0, 63);
  s->midi_channel = Clamp<uint8_t>(s->midi_channel, 0, 16);
  s->cc_a = Clamp<uint8_t>(s->cc_a, 0, 127);
  s->cc_b = Clamp<uint8_t>(s->cc_b, 0, 127);
  s->clock_ppqn = Clamp<uint8_t>(s->clock_ppqn, 0, kNumClockPpqn - 1);
  s->brightness = Clamp<uint8_t>(s->brightness, 1, 10);
  s->display_flip = s->display_flip ? 1 : 0;
  s->encoder_steps = s->encoder_steps == 2 ? 2 : 4;
  s->encoder_reverse = s->encoder_reverse ? 1 : 0;
  s->invert_output = s->invert_output ? 1 : 0;
  s->input_gain = Clamp<int16_t>(s->input_gain, -120, 120);
  s->output_gain = Clamp<int16_t>(s->output_gain, -120, 120);
  CvCalibration nominal;
  InitCvCalibration(&nominal);
  for (int i = 0; i < 4; ++i) {
    float o = s->calibration.offset[i];
    float k = s->calibration.scale[i];
    if (!(o >= kMinOffset && o <= kMaxOffset) ||
        !(k >= kMinScale && k <= kMaxScale)) {
      s->calibration.offset[i] = nominal.offset[i];
      s->calibration.scale[i] = nominal.scale[i];
    }
  }
}

void SettingsStore::Init() {
  store_.Init(kSettingsFlashOffset, kSettingsFlashSectors, kSettingsSlotSize,
              kSettingsTag);
  dirty_ = false;
  request_ms_ = 0;
  InitSettings(&stored_);
  pending_ = stored_;
}

bool SettingsStore::Load(Settings* settings) {
  Settings s;
  bool ok = store_.Load(&s, sizeof(s)) &&
      s.magic == kSettingsMagic &&
      s.version == kSettingsVersion &&
      s.crc == SettingsCrc(s);
  if (!ok) {
    InitSettings(settings);
    // Nothing valid in flash: the defaults are not stored yet, so the
    // first save writes even if nothing changed.
    memset(&stored_, 0, sizeof(stored_));
    return false;
  }
  SanitizeSettings(&s);
  Seal(&s);
  *settings = s;
  stored_ = s;
  return true;
}

void SettingsStore::RequestSave(const Settings& settings, uint32_t now_ms) {
  pending_ = settings;
  dirty_ = true;
  request_ms_ = now_ms;
}

void SettingsStore::Poll(uint32_t now_ms) {
  if (!dirty_ || now_ms - request_ms_ < kSaveDelayMs) {
    return;
  }
  dirty_ = false;
  Settings s = pending_;
  Seal(&s);
  if (memcmp(&s, &stored_, sizeof(s)) != 0) {
    SaveNow(s);
  }
}

void SettingsStore::SaveNow(const Settings& settings) {
  Settings s = settings;
  Seal(&s);
  dirty_ = false;
  if (store_.Save(&s, sizeof(s))) {
    stored_ = s;
  }
}

}  // namespace sidefx
