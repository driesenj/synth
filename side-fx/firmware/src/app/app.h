// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: everything but the screen and the board, wired together.
// main.cc owns one App and calls it from the audio callback, the control
// interrupt and the main loop; the UI drives it through the methods below.

#ifndef SIDEFX_APP_APP_H_
#define SIDEFX_APP_APP_H_

#include <stddef.h>
#include <stdint.h>

#include "app/controls.h"
#include "app/midi.h"
#include "app/mod_sources.h"
#include "app/preset_bank.h"
#include "app/settings.h"
#include "app/tempo.h"
#include "engine/engine.h"
#include "engine/memory.h"
#include "hal.h"

namespace sidefx {

class App {
 public:
  App() { }
  ~App() { }

  // Main loop, before the audio starts: engine and blocks, settings, bank,
  // then the live state from flash (or the last preset, or INIT).
  bool Init(Memory* memory);

  // Audio interrupt: in is IN 1 / IN 2 as l / r, out is OUT 1 / OUT 2.
  // Reads the CV inputs (hal::ReadCv), runs the tempo, the sources and the
  // engine, and applies the output polarity setting.
  void Process(const Frame* in, Frame* out, size_t size);

  // Control interrupt.
  uint8_t OnControlScan(const hal::ControlScan& scan) {
    return controls.OnScan(scan);
  }

  // Main loop: MIDI, program changes, the engine's Poll(), the stores.
  void Poll(uint32_t now_ms);

  // Preset handling for the UI and MIDI.
  void LoadPreset(int index);        // from the bank, faded
  bool SavePreset(int index);        // the live state into slot index
  int current_preset() const { return current_preset_; }
  // The live state differs from what slot current_preset() holds (sends
  // aside: they are performance state).
  bool modified() const;

  // Call after changing `settings`: pushes them to the engine, tempo,
  // controls, sources and the board, and schedules a save.
  void SettingsChanged();
  // Call after editing the live preset: schedules the live-state save.
  void PresetEdited();

  Engine engine;
  Controls controls;
  Tempo tempo;
  ModSources mods;
  MidiIn midi;
  Settings settings;
  SettingsStore settings_store;
  PresetBank bank;

 private:
  // How often Poll() looks for live-state changes nobody announced (send
  // buttons, MIDI CCs): a CRC of the preset, cheap at this rate.
  static const uint32_t kLiveCheckMs = 250;

  void ApplySettings();

  int current_preset_;
  Preset stored_;   // what slot current_preset_ held when loaded or saved
  uint32_t now_ms_;
  uint32_t live_check_ms_;
  uint32_t live_crc_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_APP_H_
