// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: MIDI in (TRS type A, 31250 baud, receive only).
//
// A small parser (running status, real-time bytes anywhere, SysEx skipped)
// and what the messages do, on the channel in the settings (or any, omni):
//   Note on / off       NOTE and GATE sources (last note wins)
//   CC (settings' A, B) CC A, CC B sources
//   CC 80..83           sends PITCH, DELAY, TEXTURE, REVERB (>= 64 on)
//   CC 85               WET
//   CC 120, 123         all notes off
//   Program change n    preset n + 1 (TakeProgramChange)
//   Clock, start, continue, stop   the tempo (any channel)

#ifndef SIDEFX_APP_MIDI_H_
#define SIDEFX_APP_MIDI_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {

class Engine;
class ModSources;
class Tempo;
struct Settings;

class MidiIn {
 public:
  MidiIn() { }
  ~MidiIn() { }

  void Init(Engine* engine, ModSources* mods, Tempo* tempo,
            const Settings* settings);

  // Main loop: reads every waiting byte from the board.
  void Poll();
  // One byte (Poll() calls this; the tests feed it directly).
  void ProcessByte(uint8_t byte, uint32_t time_us);

  // The last program change not yet taken; false when none.
  bool TakeProgramChange(int* program);

  uint32_t messages() const { return messages_; }  // for the screen's MIDI activity dot

 private:
  void Dispatch();

  Engine* engine_;
  ModSources* mods_;
  Tempo* tempo_;
  const Settings* settings_;
  uint8_t status_;
  uint8_t data_[2];
  uint8_t data_count_;
  bool in_sysex_;
  int program_;
  uint32_t messages_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_MIDI_H_
