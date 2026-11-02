// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the MIDI parser and what the messages do.

#include "app/midi.h"

#include "app/mod_sources.h"
#include "app/settings.h"
#include "app/tempo.h"
#include "engine/engine.h"
#include "hal.h"

namespace sidefx {

namespace {

const int kSendCcFirst = 80;  // 80..83: PITCH, DELAY, TEXTURE, REVERB
const int kWetCc = 85;
const int kAllSoundOffCc = 120;
const int kAllNotesOffCc = 123;
// Enough for a burst of clocks and notes; the rest waits for the next pass.
const int kMaxBytesPerPoll = 256;

}  // namespace

void MidiIn::Init(Engine* engine, ModSources* mods, Tempo* tempo,
                  const Settings* settings) {
  engine_ = engine;
  mods_ = mods;
  tempo_ = tempo;
  settings_ = settings;
  status_ = 0;
  data_[0] = data_[1] = 0;
  data_count_ = 0;
  in_sysex_ = false;
  program_ = -1;
  messages_ = 0;
}

void MidiIn::Poll() {
  uint8_t byte;
  uint32_t time_us;
  for (int i = 0; i < kMaxBytesPerPoll && hal::ReadMidiByte(&byte, &time_us);
       ++i) {
    ProcessByte(byte, time_us);
  }
}

void MidiIn::ProcessByte(uint8_t byte, uint32_t time_us) {
  if (byte >= 0xf8) {
    // Real-time: anywhere, even inside another message, which goes on.
    if (tempo_) {
      tempo_->PushMidiRealtime(byte, time_us);
    }
    if (byte != 0xf8 && byte != 0xfe) {
      ++messages_;  // clock and active sensing would keep the dot lit
    }
    return;
  }
  if (byte & 0x80) {
    data_count_ = 0;
    if (byte == 0xf0) {
      in_sysex_ = true;
      status_ = 0;
    } else if (byte == 0xf7) {
      in_sysex_ = false;
    } else if (byte >= 0xf1) {
      // System common (MTC, song position, select, tune): cancels running
      // status; its data bytes are ignored.
      in_sysex_ = false;
      status_ = 0;
    } else {
      in_sysex_ = false;
      status_ = byte;
    }
    return;
  }
  if (in_sysex_ || status_ == 0) {
    return;
  }
  data_[data_count_++] = byte;
  const uint8_t type = status_ & 0xf0;
  const uint8_t needed = (type == 0xc0 || type == 0xd0) ? 1 : 2;
  if (data_count_ >= needed) {
    Dispatch();
    data_count_ = 0;  // running status: the next data bytes reuse status_
  }
}

void MidiIn::Dispatch() {
  const uint8_t type = status_ & 0xf0;
  const int channel = (status_ & 0x0f) + 1;
  if (settings_ && settings_->midi_channel != 0 &&
      settings_->midi_channel != channel) {
    return;
  }
  ++messages_;
  switch (type) {
    case 0x90:
      if (data_[1]) {
        mods_->NoteOn(data_[0]);
      } else {
        mods_->NoteOff(data_[0]);
      }
      break;
    case 0x80:
      mods_->NoteOff(data_[0]);
      break;
    case 0xb0: {
      const int cc = data_[0];
      const int value = data_[1];
      if (settings_ && cc == settings_->cc_a) {
        mods_->SetCc(0, float(value) * (1.0f / 127.0f));
      }
      if (settings_ && cc == settings_->cc_b) {
        mods_->SetCc(1, float(value) * (1.0f / 127.0f));
      }
      if (cc >= kSendCcFirst && cc < kSendCcFirst + NUM_SLOTS) {
        engine_->SetSend(cc - kSendCcFirst, value >= 64);
      } else if (cc == kWetCc) {
        engine_->mutable_preset()->wet = uint16_t((value * 65535 + 63) / 127);
      } else if (cc == kAllSoundOffCc || cc == kAllNotesOffCc) {
        mods_->AllNotesOff();
      }
      break;
    }
    case 0xc0:
      program_ = data_[0];
      break;
    default:
      break;  // aftertouch, pitch bend: not used
  }
}

bool MidiIn::TakeProgramChange(int* program) {
  if (program_ < 0) {
    return false;
  }
  *program = program_;
  program_ = -1;
  return true;
}

}  // namespace sidefx
