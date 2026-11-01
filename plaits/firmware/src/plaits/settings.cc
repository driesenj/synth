// Copyright 2016 Emilie Gillet.
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

#include "plaits/settings.h"

#include <string.h>

#include "hal.h"

namespace plaits {

using namespace plaitsy;

// QSPI flash layout: the Daisy bootloader leaves the first 256 kB free and
// keeps the program from 0x40000 on. Settings use the first 64 kB, the user
// data block (plaits/user_data.h) the next.
const uint32_t kSettingsFlashOffset = 0x00000;
const uint32_t kSettingsFlashSectors = 16;
const uint32_t kSettingsSlotSize = 256;
const uint32_t kSettingsTag = 0x31594c50;  // PLY1
// Each write stalls the main loop (LED updates) for a few ms, and libDaisy
// rewrites the flash chip's non-volatile status register around each one
// (QuadEnable on every QSPI mode switch, about twice per save). The ring
// spreads the wear of the data, not of that register, so saves are kept
// rare: only after 5 s without a change, and only if something changed.
const uint32_t kSettingsSaveDelay = 5000;  // ms without a change

bool Settings::Init() {
  ChannelCalibrationData* c = persistent_data_.channel_calibration_data;
  c[CV_ADC_CHANNEL_MODEL].offset = 0.025f;
  c[CV_ADC_CHANNEL_MODEL].scale = -1.03f;
  c[CV_ADC_CHANNEL_MODEL].normalization_detection_threshold = 0;

  c[CV_ADC_CHANNEL_V_OCT].offset = 25.71;
  c[CV_ADC_CHANNEL_V_OCT].scale = -60.0f;
  c[CV_ADC_CHANNEL_V_OCT].normalization_detection_threshold = 0;

  c[CV_ADC_CHANNEL_FM].offset = 0.0f;
  c[CV_ADC_CHANNEL_FM].scale = -60.0f;
  c[CV_ADC_CHANNEL_FM].normalization_detection_threshold = -2945;

  c[CV_ADC_CHANNEL_HARMONICS].offset = 0.0f;
  c[CV_ADC_CHANNEL_HARMONICS].scale = -1.0f;
  c[CV_ADC_CHANNEL_HARMONICS].normalization_detection_threshold = 0;

  c[CV_ADC_CHANNEL_TIMBRE].offset = 0.0f;
  c[CV_ADC_CHANNEL_TIMBRE].scale = -1.6f;
  c[CV_ADC_CHANNEL_TIMBRE].normalization_detection_threshold = -2945;

  c[CV_ADC_CHANNEL_MORPH].offset = 0.0f;
  c[CV_ADC_CHANNEL_MORPH].scale = -1.6f;
  c[CV_ADC_CHANNEL_MORPH].normalization_detection_threshold = -2945;

  c[CV_ADC_CHANNEL_TRIGGER].offset = 0.4f;
  c[CV_ADC_CHANNEL_TRIGGER].scale = -0.6f;
  c[CV_ADC_CHANNEL_TRIGGER].normalization_detection_threshold = 13663;

  c[CV_ADC_CHANNEL_LEVEL].offset = 0.49f;
  c[CV_ADC_CHANNEL_LEVEL].scale = -0.6f;
  c[CV_ADC_CHANNEL_LEVEL].normalization_detection_threshold = 21403;
  memset(persistent_data_.padding, 0, sizeof(persistent_data_.padding));

  // Plaitsy: the offsets above are Plaits' factory guesses for its own
  // parts; MODEL's alone would shift the model by one at 0 V here. CvAdc
  // reads Plaits' nominal circuit exactly, so start from what calibration
  // would measure on it: 0 V reads 0 on every input. Calibrating still
  // pays, for the tolerances of Plaitsy's bias resistors.
  for (int i = 0; i < CV_ADC_CHANNEL_LAST; ++i) {
    c[i].offset = -c[i].scale * CvAdc::zero_volt_value(CvAdcChannel(i));
  }

  state_.engine = 8;
  state_.lpg_colour = 0;
  state_.decay = 128;
  state_.octave = 255;
  state_.color_blind = 0;
  state_.enable_alt_navigation = 0;
  state_.fine_tune = 128;
  state_.padding[0] = 0;

  dirty_ = false;
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

  CONSTRAIN(state_.engine, 0, 23);
  saved_persistent_data_ = persistent_data_;
  dirty_time_ = 0;

  return success;
}

void Settings::Persist() {
  if (!dirty_ || hal::Milliseconds() - dirty_time_ < kSettingsSaveDelay) {
    return;
  }
  // Byte copies into a zeroed record, so the padding compares equal too.
  Record record;
  memset(&record, 0, sizeof(record));
  uint32_t interrupts = hal::EnterCritical();
  dirty_ = false;
  memcpy(&record.persistent_data, &saved_persistent_data_,
         sizeof(record.persistent_data));
  memcpy(&record.state, &state_, sizeof(record.state));
  hal::ExitCritical(interrupts);
  if (has_last_saved_ && memcmp(&record, &last_saved_, sizeof(record)) == 0) {
    return;  // back where the flash already is
  }
  if (store_.Save(&record, sizeof(record))) {
    last_saved_ = record;
    has_last_saved_ = true;
  }
}

}  // namespace plaits
