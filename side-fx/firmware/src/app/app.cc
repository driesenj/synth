// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the app, wiring engine, controls, tempo, sources, MIDI and
// storage together.

#include "app/app.h"

#include <math.h>
#include <string.h>

#include "engine/crc32.h"

namespace sidefx {

namespace {

inline float DecibelsToGain(float db) { return expf(db * 0.11512925f); }

// The parts of a preset that make it "modified": everything but the
// sends (performance state) and the seal.
void MaskForCompare(Preset* p) {
  p->magic = 0;
  p->version = 0;
  p->crc = 0;
  for (int i = 0; i < NUM_SLOTS; ++i) {
    p->slot[i].send = 0;
  }
}

}  // namespace

bool App::Init(Memory* memory) {
  const bool ok = engine.Init(memory);
  engine.set_cycle_counter(&hal::CycleCount, hal::kCyclesPerSecond);

  settings_store.Init();
  settings_store.Load(&settings);  // the defaults when none is stored
  SanitizeSettings(&settings);

  tempo.Init();
  controls.Init(&engine, &tempo);
  mods.Init();
  midi.Init(&engine, &mods, &tempo, &settings);
  ApplySettings();

  bank.Init();
  current_preset_ = settings.last_preset;
  bank.Load(current_preset_, &stored_);
  Preset live;
  if (bank.LoadState(&live)) {
    engine.ApplyPresetNow(live);
  } else {
    engine.ApplyPresetNow(stored_);
  }
  now_ms_ = hal::Milliseconds();
  live_check_ms_ = now_ms_;
  live_crc_ = Crc32(0, &engine.preset(), sizeof(Preset));
  return ok;
}

void App::ApplySettings() {
  engine.set_dry(float(settings.dry) * (1.0f / 65535.0f));
  // OUT POLARITY as the output gain's sign: the engine glides through it.
  const float output_gain = DecibelsToGain(float(settings.output_gain) * 0.1f);
  engine.set_gains(DecibelsToGain(float(settings.input_gain) * 0.1f),
                   settings.invert_output ? -output_gain : output_gain);
  controls.set_steps_per_detent(settings.encoder_steps);
  controls.set_reverse(settings.encoder_reverse != 0);
  mods.set_calibration(settings.calibration);
  hal::SetBacklight(float(settings.brightness) * 0.1f);
  hal::SetDisplayFlip(settings.display_flip != 0);
}

void App::Process(const Frame* in, Frame* out, size_t size) {
  float cv[hal::kNumCvInputs];
  for (int i = 0; i < hal::kNumCvInputs; ++i) {
    cv[i] = hal::ReadCv(i);
  }
  const Preset& preset = engine.preset();
  tempo.Process(float(preset.tempo) * 0.1f,
                kClockPpqnValues[settings.clock_ppqn < kNumClockPpqn
                                 ? settings.clock_ppqn : 2],
                size);
  mods.Process(preset, tempo.state(), cv, in, size);
  engine.Process(mods.values(), tempo.state(), in, out, size);
  hal::FeedWatchdog();
}

void App::Poll(uint32_t now_ms) {
  now_ms_ = now_ms;
  midi.Poll();
  int program;
  if (midi.TakeProgramChange(&program) && program < kNumPresets) {
    LoadPreset(program);
  }
  engine.Poll();

  if (now_ms - live_check_ms_ >= kLiveCheckMs && !engine.loading()) {
    live_check_ms_ = now_ms;
    const uint32_t crc = Crc32(0, &engine.preset(), sizeof(Preset));
    if (crc != live_crc_) {
      live_crc_ = crc;
      bank.RequestStateSave(engine.preset(), now_ms);
    }
  }
  settings_store.Poll(now_ms);
  bank.Poll(now_ms);
}

void App::LoadPreset(int index) {
  if (index < 0 || index >= kNumPresets) {
    return;
  }
  Preset p;
  bank.Load(index, &p);  // INIT for an empty slot
  stored_ = p;
  current_preset_ = index;
  engine.LoadPreset(p);
  const uint32_t now = hal::Milliseconds();
  settings.last_preset = uint8_t(index);
  settings_store.RequestSave(settings, now);
  bank.RequestStateSave(p, now);
}

bool App::SavePreset(int index) {
  if (index < 0 || index >= kNumPresets) {
    return false;
  }
  Preset p = engine.preset();
  if (!bank.Save(index, p)) {
    return false;
  }
  SealPreset(&p);
  stored_ = p;
  current_preset_ = index;
  settings.last_preset = uint8_t(index);
  settings_store.RequestSave(settings, hal::Milliseconds());
  return true;
}

bool App::modified() const {
  if (engine.loading()) {
    return false;  // the swap is not done yet
  }
  Preset a = engine.preset();
  Preset b = stored_;
  MaskForCompare(&a);
  MaskForCompare(&b);
  return memcmp(&a, &b, sizeof(Preset)) != 0;
}

void App::SettingsChanged() {
  SanitizeSettings(&settings);
  ApplySettings();
  settings_store.RequestSave(settings, hal::Milliseconds());
}

void App::PresetEdited() {
  const uint32_t now = hal::Milliseconds();
  live_crc_ = Crc32(0, &engine.preset(), sizeof(Preset));
  bank.RequestStateSave(engine.preset(), now);
}

}  // namespace sidefx
