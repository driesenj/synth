// Copyright 2015 Emilie Gillet.
//
// Author: Emilie Gillet (emilie.o.gillet@gmail.com)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
//
// See http://creativecommons.org/licenses/MIT/ for more information.
//
// -----------------------------------------------------------------------------
//
// Settings storage.

#include "marbles/settings.h"

#include <algorithm>
#include <string.h>

#include "hal.h"

namespace marbles {

using namespace std;

const Scale preset_scales[6] = {
  // C major
  {
    1.0f,
    12,
    {
      { 0.0000f, 255 },  // C
      { 0.0833f, 16 },   // C#
      { 0.1667f, 96 },   // D
      { 0.2500f, 24 },   // D#
      { 0.3333f, 128 },  // E
      { 0.4167f, 64 },   // F
      { 0.5000f, 8 },    // F#
      { 0.5833f, 192 },  // G
      { 0.6667f, 16 },   // G#
      { 0.7500f, 96 },   // A
      { 0.8333f, 24 },   // A#
      { 0.9167f, 128 },  // B
    }
  },

  // C minor
  {
    1.0f,
    12,
    {
      { 0.0000f, 255 },  // C
      { 0.0833f, 16 },   // C#
      { 0.1667f, 96 },   // D
      { 0.2500f, 128 },  // Eb
      { 0.3333f, 8 },    // E
      { 0.4167f, 64 },   // F
      { 0.5000f, 4 },    // F#
      { 0.5833f, 192 },  // G
      { 0.6667f, 96 },   // G#
      { 0.7500f, 16 },   // A
      { 0.8333f, 128 },  // Bb
      { 0.9167f, 16 },   // B
    }
  },

  // Pentatonic
  {
    1.0f,
    12,
    {
      { 0.0000f, 255 },  // C
      { 0.0833f, 4 },    // C#
      { 0.1667f, 96 },   // D
      { 0.2500f, 4 },    // Eb
      { 0.3333f, 4 },    // E
      { 0.4167f, 140 },  // F
      { 0.5000f, 4 },    // F#
      { 0.5833f, 192 },  // G
      { 0.6667f, 4 },    // G#
      { 0.7500f, 96 },   // A
      { 0.8333f, 4 },    // Bb
      { 0.9167f, 4 },    // B
    }
  },

  // Pelog
  {
    1.0f,
    7,
    {
      { 0.0000f, 255 },  // C
      { 0.1275f, 128 },  // Db+
      { 0.2625f, 32 },  // Eb-
      { 0.4600f, 8 },    // F#-
      { 0.5883f, 192 },  // G
      { 0.7067f, 64 },  // Ab
      { 0.8817f, 16 },    // Bb+
    }
  },

  // Raag Bhairav That
  {
    1.0f,
    12,
    {
      { 0.0000f, 255 }, // ** Sa
      { 0.0752f, 128 }, // ** Komal Re
      { 0.1699f, 4 },   //    Re
      { 0.2630f, 4 },   //    Komal Ga
      { 0.3219f, 128 }, // ** Ga
      { 0.4150f, 64 },  // ** Ma
      { 0.4918f, 4 },   //    Tivre Ma
      { 0.5850f, 192 }, // ** Pa
      { 0.6601f, 64 },  // ** Komal Dha
      { 0.7549f, 4 },   //    Dha
      { 0.8479f, 4 },   //    Komal Ni
      { 0.9069f, 64 },  // ** Ni
    }
  },

  // Raag Shri
  {
    1.0f,
    12,
    {
      { 0.0000f, 255 }, // ** Sa
      { 0.0752f, 4 },   //    Komal Re
      { 0.1699f, 128 }, // ** Re
      { 0.2630f, 64 },  // ** Komal Ga
      { 0.3219f, 4 },   //    Ga
      { 0.4150f, 128 }, // ** Ma
      { 0.4918f, 4 },   //    Tivre Ma
      { 0.5850f, 192 }, // ** Pa
      { 0.6601f, 4 },   //    Komal Dha
      { 0.7549f, 64 },  // ** Dha
      { 0.8479f, 128 }, // ** Komal Ni
      { 0.9069f, 4 },   //    Ni
    }
  },
};

#define FIX_OUTLIER(destination, expected_value) if (fabsf(destination / expected_value - 1.0f) > 0.1f) { destination = expected_value; }

// Marblesy: QSPI flash layout. The Daisy bootloader leaves the first 256 kB
// free and keeps the program from 0x40000 on. One record holds the
// persistent data and the state (952 bytes), in a ring of 1 kB slots over
// the first 64 kB.
const uint32_t kSettingsFlashOffset = 0x00000;
const uint32_t kSettingsFlashSectors = 16;
const uint32_t kSettingsSlotSize = 1024;
const uint32_t kSettingsTag = 0x3159424d;  // MBY1
// libDaisy rewrites the flash chip's non-volatile status register around
// each write and erase (QuadEnable on every QSPI mode switch, 2.5 times per
// save on average), which the ring cannot spread, so saves are kept rare:
// only if something changed, and only after a while without a change. The
// state alone (modes, ranges, deja vu, hidden settings) waits 30 s, so a
// set's worth of button presses costs a few saves; a calibration or a scale
// waits 5 s. Marbles saves at every press. A failed save is retried a few
// times, each in the next slot.
const uint32_t kStateSaveDelay = 30000;  // ms without a change
const uint32_t kPersistentDataSaveDelay = 5000;
const int kMaxSaveRetries = 3;

void Settings::ResetScale(int i) {
  persistent_data_.scale[i] = preset_scales[i];
}

void Settings::Init() {
  freshly_baked_ = false;

  // Set default values for all calibration and state settings.
  // This settings will be written to flash memory the first time the module
  // is powered on, or if corrupted data is found in the flash sector,
  // following a major firmware upgrade.
  CalibrationData& c = persistent_data_.calibration_data;
  fill(&c.adc_scale[0], &c.adc_scale[ADC_CHANNEL_LAST], -2.0f);
  fill(&c.adc_offset[0], &c.adc_offset[ADC_CHANNEL_LAST], +1.0f);
  // Marblesy: the nominal MCP4922 output stage (dac.h), not Marbles' DAC8564.
  fill(&c.dac_scale[0], &c.dac_scale[DAC_CHANNEL_LAST], kDacScale);
  fill(&c.dac_offset[0], &c.dac_offset[DAC_CHANNEL_LAST], kDacOffset);
  c.adc_offset[ADC_CHANNEL_T_RATE] = 60.0f;
  c.adc_scale[ADC_CHANNEL_T_RATE] = -120.0f;

  for (size_t i = 0; i < kNumScales; ++i) {
    ResetScale(i);
  }
  memset(persistent_data_.padding, 0, sizeof(persistent_data_.padding));

  state_.t_deja_vu = 0;
  state_.t_model = 0;
  state_.t_range = 1;
  state_.t_pulse_width_mean = 128;
  state_.t_pulse_width_std = 0;

  state_.x_deja_vu = 0;
  state_.x_control_mode = 0;
  state_.x_register_mode = 0;
  state_.x_range = 2;
  state_.x_scale = 0;

  state_.y_spread = 128;
  state_.y_bias = 128;
  state_.y_steps = 0;
  state_.y_divider = 128;
  state_.y_range = 2;

  state_.color_blind = 0;
  state_.explicit_reset = 0;
  memset(state_.padding, 0, sizeof(state_.padding));

  // Marblesy: the newest valid record in the QSPI ring.
  store_.Init(
      kSettingsFlashOffset,
      kSettingsFlashSectors,
      kSettingsSlotSize,
      kSettingsTag);
  Record record;
  bool success = store_.Load(&record, sizeof(record));
  if (success) {
    persistent_data_ = record.persistent_data;
    state_ = record.state;
    last_saved_ = record;
  }
  has_last_saved_ = success;
  freshly_baked_ = !success;

  if (!freshly_baked_) {
    CONSTRAIN(state_.t_model, 0, 5);
    CONSTRAIN(state_.t_range, 0, 2);
    CONSTRAIN(state_.x_control_mode, 0, 2);
    CONSTRAIN(state_.x_range, 0, 2);
    CONSTRAIN(state_.x_scale, 0, 5);
    CONSTRAIN(state_.y_range, 0, 2);
    CONSTRAIN(state_.t_deja_vu, DEJA_VU_OFF, DEJA_VU_LOCKED);
    CONSTRAIN(state_.x_deja_vu, DEJA_VU_OFF, DEJA_VU_LOCKED);

    CalibrationData& c = persistent_data_.calibration_data;
    for (size_t i = 0; i < ADC_CHANNEL_LAST; ++i) {
      if (i == ADC_CHANNEL_T_RATE) {
        FIX_OUTLIER(c.adc_scale[i], -120.0f);
        FIX_OUTLIER(c.adc_offset[i], 60.0f);
      } else {
        FIX_OUTLIER(c.adc_scale[i], -2.0f);
        FIX_OUTLIER(c.adc_offset[i], +1.0f);
      }
    }
    for (size_t i = 0; i < DAC_CHANNEL_LAST; ++i) {
      FIX_OUTLIER(c.dac_scale[i], kDacScale);
      FIX_OUTLIER(c.dac_offset[i], kDacOffset);
    }
  }

  saved_persistent_data_ = persistent_data_;
  dirty_ = false;
  dirty_time_ = 0;
  persistent_data_pending_ = false;
  save_retries_ = 0;
}

void Settings::MarkDirty() {
  dirty_time_ = marblesy::hal::Milliseconds();
  dirty_ = true;
}

void Settings::SavePersistentData() {
  saved_persistent_data_ = persistent_data_;
  persistent_data_pending_ = true;
  MarkDirty();
}

void Settings::SaveState() {
  MarkDirty();
}

void Settings::Persist() {
  const uint32_t delay = persistent_data_pending_
      ? kPersistentDataSaveDelay
      : kStateSaveDelay;
  if (!dirty_ || marblesy::hal::Milliseconds() - dirty_time_ < delay) {
    return;
  }
  // Byte copies into a zeroed record, so the padding compares equal too.
  Record record;
  memset(&record, 0, sizeof(record));
  uint32_t interrupts = marblesy::hal::EnterCritical();
  dirty_ = false;
  const bool persistent_data = persistent_data_pending_;
  persistent_data_pending_ = false;
  memcpy(&record.persistent_data, &saved_persistent_data_,
         sizeof(record.persistent_data));
  memcpy(&record.state, &state_, sizeof(record.state));
  marblesy::hal::ExitCritical(interrupts);
  if (has_last_saved_ && memcmp(&record, &last_saved_, sizeof(record)) == 0) {
    save_retries_ = 0;
    return;  // back where the flash already is
  }
  if (store_.Save(&record, sizeof(record))) {
    last_saved_ = record;
    has_last_saved_ = true;
    save_retries_ = 0;
  } else if (++save_retries_ <= kMaxSaveRetries) {
    interrupts = marblesy::hal::EnterCritical();
    persistent_data_pending_ = persistent_data_pending_ || persistent_data;
    MarkDirty();
    marblesy::hal::ExitCritical(interrupts);
  } else {
    save_retries_ = 0;  // until the next change
  }
}

}  // namespace marbles
