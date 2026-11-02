// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the whole App on the fake board and the fake
// blocks: first boot, audio, presets, the live state across a power cycle,
// settings, MIDI program changes.

#include <math.h>
#include <string.h>

#include "check.h"
#include "display_fake.h"
#include "hal_fake.h"
#include "test_support.h"

#include "app/app.h"
#include "app/factory_presets.h"

using namespace sidefx;

namespace {

// The name factory preset i gets (the bank's first slots hold them).
const char* FactoryName(int i) {
  static char names[16][16];
  Preset p;
  GetFactoryPreset(i, &p);
  strcpy(names[i & 15], p.name);
  return names[i & 15];
}

// An App with its arenas, run in audio blocks with the main loop polled
// after each one, as main.cc does.
struct AppRig {
  test::TestMemory memory;
  App app;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  uint32_t noise;
  bool ok;

  AppRig() : memory(2u << 20, 200u << 10), noise(7) {
    ok = app.Init(memory.memory());
  }

  void Run(float seconds) {
    const double block_us = double(kBlockSize) * 1.0e6 / double(kSampleRate);
    const int blocks = int(seconds * kSampleRate / float(kBlockSize) + 0.5f);
    for (int b = 0; b < blocks; ++b) {
      for (size_t i = 0; i < kBlockSize; ++i) {
        in[i].l = 0.3f * test::Noise(&noise);
        in[i].r = 0.3f * test::Noise(&noise);
      }
      test::AdvanceUs(uint64_t(block_us));
      app.Process(in, out, kBlockSize);
      app.Poll(hal::Milliseconds());
    }
  }

  void Settle() {
    int guard = 0;
    do {
      Run(0.005f);
    } while (app.engine.loading() && ++guard < 100);
  }
};

void PowerCycle() { test::PowerCycleHal(); }

}  // namespace

TEST(app_app, first_boot) {
  test::ResetHal();
  test::ResetDisplay();
  AppRig* rig = new AppRig();
  CHECK(rig->ok);
  CHECK(rig->app.current_preset() == 0);
  CHECK(!strcmp(rig->app.engine.preset().name, FactoryName(0)));
  CHECK(rig->app.engine.preset().slot[SLOT_DELAY].send == 1);
  CHECK(rig->app.engine.preset().slot[SLOT_REVERB].send == 1);
  CHECK(!rig->app.modified());
  CHECK(rig->app.settings.cc_b == 11);
  CHECK_NEAR(test::Display().backlight, 0.8f, 1e-6);
  CHECK(!strcmp(rig->app.bank.name(1), FactoryName(1)));
  CHECK(!strcmp(rig->app.bank.name(NumFactoryPresets()), "INIT"));
  rig->Run(0.2f);
  CHECK(test::Hal().watchdog_feeds > 0);
  bool finite = true;
  for (size_t i = 0; i < kBlockSize; ++i) {
    finite = finite && test::Finite(rig->out[i]);
  }
  CHECK(finite);
  CHECK(rig->app.tempo.source() == TEMPO_INTERNAL);
  CHECK_NEAR(rig->app.tempo.bpm(), rig->app.engine.preset().tempo * 0.1f, 1e-3);
  delete rig;
}

TEST(app_app, live_state_survives_a_power_cycle) {
  test::ResetHal();
  {
    AppRig rig;
    rig.Run(0.1f);
    rig.app.engine.mutable_preset()->wet = 20000;
    rig.app.PresetEdited();
    CHECK(rig.app.modified());
    // The send buttons are performance state: not "modified", but kept.
    rig.app.engine.ToggleSend(SLOT_PITCH);
    rig.Run(6.0f);
  }
  PowerCycle();
  AppRig rig;
  CHECK(rig.app.engine.preset().wet == 20000);
  CHECK(rig.app.engine.preset().slot[SLOT_PITCH].send == 1);
  CHECK(rig.app.current_preset() == 0);
  CHECK(rig.app.modified());
  // Sends alone do not count as a modification: WET back as stored.
  Preset stored;
  rig.app.bank.Load(0, &stored);
  rig.app.engine.mutable_preset()->wet = stored.wet;
  CHECK(!rig.app.modified());
}

TEST(app_app, sends_saved_without_an_edit_call) {
  test::ResetHal();
  {
    AppRig rig;
    rig.Run(0.1f);
    // A send toggled from the panel (the interrupt) or by MIDI CC: nobody
    // calls PresetEdited(), the App notices.
    const uint8_t cc[] = { 0xb0, 82, 127 };
    test::PushMidi(cc, 3);
    rig.Run(6.0f);
  }
  PowerCycle();
  AppRig rig;
  CHECK(rig.app.engine.preset().slot[SLOT_TEXTURE].send == 1);
}

TEST(app_app, save_and_load_presets) {
  test::ResetHal();
  {
    AppRig rig;
    rig.Run(0.05f);
    SetPresetName(rig.app.engine.mutable_preset(), "HYPNO");
    rig.app.engine.mutable_preset()->tempo = 1260;
    rig.app.PresetEdited();
    CHECK(rig.app.modified());
    CHECK(rig.app.SavePreset(5));
    CHECK(rig.app.current_preset() == 5);
    CHECK(!rig.app.modified());
    CHECK(!strcmp(rig.app.bank.name(5), "HYPNO"));
    rig.Run(0.1f);
    CHECK_NEAR(rig.app.tempo.bpm(), 126.0f, 1e-3);

    rig.app.LoadPreset(0);
    rig.Settle();
    CHECK(!strcmp(rig.app.engine.preset().name, FactoryName(0)));
    CHECK(rig.app.current_preset() == 0);
    CHECK(!rig.app.modified());

    // MIDI program change 6 is slot 5 (preset "6" on the screen).
    const uint8_t pc[] = { 0xc5, 5 };
    test::PushMidi(pc, 2);
    rig.Settle();
    rig.Settle();
    CHECK(!strcmp(rig.app.engine.preset().name, "HYPNO"));
    CHECK(rig.app.current_preset() == 5);
    rig.Run(6.0f);  // the settings remember the slot
  }
  PowerCycle();
  AppRig rig;
  CHECK(rig.app.current_preset() == 5);
  CHECK(!strcmp(rig.app.engine.preset().name, "HYPNO"));
  CHECK(!rig.app.modified());
  // An empty slot loads INIT.
  rig.app.LoadPreset(40);
  rig.Settle();
  CHECK(!strcmp(rig.app.engine.preset().name, "INIT"));
}

TEST(app_app, settings_changed) {
  test::ResetHal();
  test::ResetDisplay();
  static Frame a_out[kBlockSize];
  {
    AppRig rig;
    rig.app.settings.brightness = 3;
    rig.app.settings.display_flip = 1;
    rig.app.settings.clock_ppqn = 5;
    rig.app.SettingsChanged();
    CHECK_NEAR(test::Display().backlight, 0.3f, 1e-6);
    CHECK(test::Display().flip);
    rig.Run(6.0f);
  }
  PowerCycle();
  {
    AppRig rig;
    CHECK(rig.app.settings.brightness == 3);
    CHECK(rig.app.settings.clock_ppqn == 5);
    CHECK(rig.app.settings.display_flip == 1);
  }

  // OUT polarity: two Apps from the same flash, one inverted.
  PowerCycle();
  AppRig a;
  AppRig b;
  b.app.settings.invert_output = 1;
  b.app.SettingsChanged();
  // The flip glides over 5 ms.
  a.Run(0.01f);
  b.Run(0.01f);
  double sum = 0.0;
  for (int k = 0; k < 20; ++k) {
    a.Run(0.001f);
    memcpy(a_out, a.out, sizeof(a_out));
    b.Run(0.001f);
    for (size_t i = 0; i < kBlockSize; ++i) {
      CHECK_NEAR(b.out[i].l, -a_out[i].l, 1e-6);
      CHECK_NEAR(b.out[i].r, -a_out[i].r, 1e-6);
      sum += fabs(a_out[i].l);
    }
  }
  CHECK(sum > 0.1);
}

TEST(app_app, cv_reaches_the_sources) {
  test::ResetHal();
  AppRig rig;
  test::SetCvVolts(1, 4.0f);
  rig.Run(0.01f);
  CHECK_NEAR(rig.app.mods.values().value[MOD_CV2], 1.0f, 1e-3);
  CHECK_NEAR(rig.app.mods.cv_volts(1), 4.0f, 1e-3);
}

TEST(app_app, external_clock_through_the_control_scan) {
  test::ResetHal();
  AppRig rig;
  hal::ControlScan scan;
  memset(&scan, 0, sizeof(scan));
  // 4 PPQN (the default) at 132 BPM: 113.6 ms per pulse. The control
  // interrupt runs at 4 kHz between audio blocks.
  const double period_us = 60.0e6 / (132.0 * 4.0);
  double next = double(test::NowUs()) + 1000.0;
  const double block_us = double(kBlockSize) * 1.0e6 / double(kSampleRate);
  double scan_at = double(test::NowUs());
  for (int b = 0; b < int(3.0 * 1e6 / block_us); ++b) {
    const double block_end = double(test::NowUs()) + block_us;
    while (scan_at < block_end) {
      test::Hal().time_us = uint64_t(scan_at);
      scan.clock = fmod(scan_at - next + 10.0 * period_us, period_us) < 5000.0 &&
          scan_at >= next;
      scan.time_us = hal::Microseconds();
      rig.app.OnControlScan(scan);
      scan_at += 250.0;
    }
    test::Hal().time_us = uint64_t(block_end);
    rig.app.Process(rig.in, rig.out, kBlockSize);
    rig.app.Poll(hal::Milliseconds());
  }
  CHECK(rig.app.tempo.source() == TEMPO_CLOCK);
  CHECK_NEAR(rig.app.tempo.bpm(), 132.0f, 0.5f);
  CHECK(rig.app.tempo.state().external);
}
