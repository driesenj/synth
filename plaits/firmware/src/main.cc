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
// Plaitsy: Mutable Instruments Plaits 1.2 on a Daisy Seed.
//
// Port of plaits/plaits.cc (Emilie Gillet, MIT licence). Plaits renders and
// polls its UI in the audio interrupt, 12 samples at a time at 48 kHz, and so
// does this: AudioCallback() is FillBuffer(). What Plaits does in the
// interrupt that takes a while here (shifting the LED frame out, writing the
// QSPI flash) moves to the main loop.

#include "daisy_seed.h"

#include "plaits/dsp/dsp.h"
#include "plaits/dsp/voice.h"
#include "plaits/settings.h"
#include "plaits/ui.h"
#include "plaits/user_data.h"
#include "plaits/user_data_receiver.h"

#include "hal.h"

using namespace daisy;
using namespace plaits;
using namespace stm_audio_bootloader;
using namespace stmlib;

// Plaits writes -32767 * sample to its DAC because its output stage inverts;
// this undoes that, so a positive sample is a positive output voltage
// whenever the breakout's output stage does not invert. If it does, set
// kOutputPolarity to +1 to get Plaits' polarity back. On its own the
// polarity is inaudible; it only shows when OUT or AUX meets a related signal.
const float kOutputPolarity = -1.0f;
const float kOutputScale = kOutputPolarity / 32768.0f;

DaisySeed hw;
Modulations modulations;
Patch patch;
Settings settings;
Ui ui;
UserData user_data;
UserDataReceiver user_data_receiver;
Voice voice;

char shared_buffer[16384];
// Plaits receives user data into the end of shared_buffer, over the engines'
// memory; there is room here for a buffer of its own.
uint8_t user_data_buffer[UserData::SIZE];
uint32_t test_ramp;

void AudioCallback(
    AudioHandle::InputBuffer in,
    AudioHandle::OutputBuffer out,
    size_t size) {
  plaitsy::hal::FeedWatchdog();
  ui.Poll();

  if (ui.test_mode()) {
    // 100 Hz ascending and descending ramps.
    for (size_t i = 0; i < size; ++i) {
      out[0][i] = static_cast<float>(static_cast<int16_t>(~test_ramp >> 16)) / 32768.0f;
      out[1][i] = static_cast<float>(static_cast<int16_t>(test_ramp >> 16)) / 32768.0f;
      test_ramp += 8947848;
    }
    return;
  }

  if (modulations.timbre_patched) {
    PacketDecoderState state = \
        user_data_receiver.Process(modulations.timbre);
    if (state == PACKET_DECODER_STATE_END_OF_TRANSMISSION) {
      if (user_data_receiver.progress() == 1.0f) {
        int slot = voice.active_engine();
        bool success = user_data.Save(user_data_receiver.rx_buffer(), slot);
        if (success) {
          voice.ReloadUserData();
        } else {
          ui.DisplayDataTransferProgress(-1.0f);
        }
      }
      user_data_receiver.Reset();
    } else if (state == PACKET_DECODER_STATE_OK) {
      ui.DisplayDataTransferProgress(user_data_receiver.progress());
    } else if (state == PACKET_DECODER_STATE_ERROR_CRC) {
      ui.DisplayDataTransferProgress(-1.0f);
    }
  }

  Voice::Frame frames[kMaxBlockSize];
  voice.Render(patch, modulations, frames, size);
  ui.set_active_engine(voice.active_engine());

  for (size_t i = 0; i < size; ++i) {
    out[0][i] = kOutputScale * static_cast<float>(frames[i].out);  // OUT
    out[1][i] = kOutputScale * static_cast<float>(frames[i].aux);  // AUX
  }
}

int main(void) {
  hw.Init(true);  // 480 MHz
  plaitsy::hal::Init(&hw);

  // The 74HC595s power up with random outputs: clear the LED column first.
  plaitsy::hal::InitLeds();
  plaitsy::hal::Service();

  // The left button held at power-up: on Plaits it starts the audio
  // firmware updater; here it restarts into the Daisy bootloader and keeps
  // it waiting for a firmware upload, so the Seed's own BOOT button behind
  // the panel is not needed. Enabling the pull-ups this early also lets
  // them settle before Ui::Init() reads the right button (colour-blind).
  plaitsy::hal::InitButtons();
  System::Delay(1);
  if (plaitsy::hal::ButtonPressed(plaitsy::hal::BUTTON_A)) {
    // Alternate red and green on the column (the Seed's own LED is behind
    // the panel); the 74HC595s hold it while the bootloader waits.
    static Leds leds;
    leds.Init();
    for (int i = 0; i < kNumLEDs; ++i) {
      leds.set(i, i & 1 ? LED_COLOR_GREEN : LED_COLOR_RED);
    }
    leds.Write();
    plaitsy::hal::Service();
    System::ResetToBootloader(System::BootloaderMode::DAISY_INFINITE_TIMEOUT);
  }

  BufferAllocator allocator(shared_buffer, sizeof(shared_buffer));
  voice.Init(&allocator);
  user_data_receiver.Init(user_data_buffer, UserData::SIZE);

  settings.Init();
  UserData::Init();
  ui.Init(&patch, &modulations, &settings);

  hw.SetAudioSampleRate(SaiHandle::Config::SampleRate::SAI_48KHZ);
  hw.SetAudioBlockSize(kBlockSize);
  hw.StartAudio(AudioCallback);
  plaitsy::hal::StartWatchdog();

  while (true) {
    plaitsy::hal::Service();
    settings.Persist();
    UserData::Persist();
  }
}
