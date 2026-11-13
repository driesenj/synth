// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: Controls (debounce, encoders, the event queue,
// sends in the interrupt, LEDs).

#include <string.h>

#include "check.h"
#include "hal_fake.h"
#include "test_support.h"

#include "app/controls.h"
#include "app/tempo.h"
#include "engine/engine.h"

using namespace sidefx;

namespace {

struct Rig {
  test::TestMemory memory;
  Engine engine;
  Tempo tempo;
  Controls controls;
  hal::ControlScan scan;

  Rig() : memory(1u << 20, 200u << 10) {
    test::ResetHal();
    engine.Init(memory.memory());
    tempo.Init();
    controls.Init(&engine, &tempo);
    memset(&scan, 0, sizeof(scan));
  }

  // One 4 kHz scan with the current raw state.
  uint8_t Scan() {
    test::AdvanceUs(250);
    scan.time_us = hal::Microseconds();
    return controls.OnScan(scan);
  }

  void Scans(int n) {
    for (int i = 0; i < n; ++i) {
      Scan();
    }
  }

  void SetSwitch(int sw, bool on) {
    if (on) {
      scan.switches = uint16_t(scan.switches | (1u << sw));
    } else {
      scan.switches = uint16_t(scan.switches & ~(1u << sw));
    }
  }

  // A bouncy press: chatter for `bounces` scans, then held.
  void Press(int sw, int bounces = 3) {
    for (int i = 0; i < bounces; ++i) {
      SetSwitch(sw, i % 2 == 0);
      Scan();
    }
    SetSwitch(sw, true);
    Scans(30);   // past the 24-scan (6 ms) debounce
  }

  void Release(int sw, int bounces = 3) {
    for (int i = 0; i < bounces; ++i) {
      SetSwitch(sw, i % 2 != 0);
      Scan();
    }
    SetSwitch(sw, false);
    Scans(30);
  }

  // One detent of encoder `e` (+1 clockwise) through the four quadrature
  // states, each transition with contact bounce.
  void Turn(int e, int direction, int steps_per_detent = 4) {
    static const uint8_t kCw[4] = { 1, 3, 2, 0 };
    int transitions = steps_per_detent;
    for (int t = 0; t < transitions; ++t) {
      uint8_t from = scan.encoder[e];
      int index = 0;
      for (int k = 0; k < 4; ++k) {
        if (kCw[k] == from) {
          index = k;
        }
      }
      // The state after `from` in the chosen direction.
      uint8_t to = direction > 0 ? kCw[(index + 1) % 4]
          : kCw[(index + 3) % 4];
      // Bounce: to, from, to, from, then settled.
      for (int b = 0; b < 2; ++b) {
        scan.encoder[e] = to;
        Scan();
        scan.encoder[e] = from;
        Scan();
      }
      scan.encoder[e] = to;
      Scans(2);
    }
  }

  int DrainEncoder(int e, int* events = NULL) {
    Event ev;
    int sum = 0;
    int n = 0;
    while (controls.PopEvent(&ev)) {
      if (ev.type == EVENT_ENCODER && ev.id == e) {
        sum += ev.delta;
        ++n;
      }
    }
    if (events) {
      *events = n;
    }
    return sum;
  }
};

}  // namespace

TEST(app_controls, debounce_one_event_per_press) {
  Rig rig;
  const uint32_t start_us = hal::Microseconds();
  rig.Press(hal::SWITCH_K2, 5);
  CHECK(rig.controls.pressed(hal::SWITCH_K2));
  Event e;
  CHECK(rig.controls.PopEvent(&e));
  CHECK(e.type == EVENT_PRESS && e.id == hal::SWITCH_K2);
  CHECK(!e.shift && !e.handled);
  // Stamped by the scan that confirmed it (tap tempo times taps from
  // there, however late the main loop gets to the event).
  CHECK(e.time_us > start_us && e.time_us <= rig.scan.time_us);
  CHECK(!rig.controls.PopEvent(&e));
  rig.Release(hal::SWITCH_K2, 5);
  CHECK(!rig.controls.pressed(hal::SWITCH_K2));
  CHECK(rig.controls.PopEvent(&e));
  CHECK(e.type == EVENT_RELEASE && e.id == hal::SWITCH_K2);
  CHECK(!rig.controls.PopEvent(&e));
}

TEST(app_controls, debounce_ignores_short_glitches) {
  Rig rig;
  // Under 6 ms: a 5.75 ms bounce gap (23 scans) down, then up.
  rig.SetSwitch(hal::SWITCH_K1, true);
  rig.Scans(23);
  rig.SetSwitch(hal::SWITCH_K1, false);
  rig.Scans(30);
  Event e;
  CHECK(!rig.controls.PopEvent(&e));
  // Exactly 24 stable scans (6 ms) make a press.
  rig.SetSwitch(hal::SWITCH_K1, true);
  rig.Scans(23);
  CHECK(!rig.controls.pressed(hal::SWITCH_K1));
  rig.Scan();
  CHECK(rig.controls.pressed(hal::SWITCH_K1));
}

TEST(app_controls, encoder_one_step_per_detent_with_bounce) {
  Rig rig;
  for (int i = 0; i < 10; ++i) {
    rig.Turn(2, +1);
  }
  int events = 0;
  CHECK(rig.DrainEncoder(2, &events) == 10);
  CHECK(events == 10);
  for (int i = 0; i < 7; ++i) {
    rig.Turn(2, -1);
  }
  CHECK(rig.DrainEncoder(2) == -7);
  // Wobbling half a detent and back is no step.
  rig.scan.encoder[2] = 1;
  rig.Scans(3);
  rig.scan.encoder[2] = 3;
  rig.Scans(3);
  rig.scan.encoder[2] = 1;
  rig.Scans(3);
  rig.scan.encoder[2] = 0;
  rig.Scans(3);
  CHECK(rig.DrainEncoder(2) == 0);
}

TEST(app_controls, encoder_half_cycle_and_reverse) {
  Rig rig;
  rig.controls.set_steps_per_detent(2);
  for (int i = 0; i < 6; ++i) {
    rig.Turn(0, +1, 2);
  }
  CHECK(rig.DrainEncoder(0) == 6);
  rig.controls.set_reverse(true);
  for (int i = 0; i < 4; ++i) {
    rig.Turn(0, +1, 2);
  }
  CHECK(rig.DrainEncoder(0) == -4);
  rig.controls.set_steps_per_detent(4);
  rig.controls.set_reverse(false);
  // Back on a full-cycle rest (00) first.
  rig.scan.encoder[0] = 0;
  rig.Scans(4);
  rig.DrainEncoder(0);
  rig.Turn(0, -1);
  CHECK(rig.DrainEncoder(0) == -1);
}

TEST(app_controls, sends_toggle_in_the_interrupt) {
  Rig rig;
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 0);
  rig.Press(hal::SWITCH_DELAY);
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 1);
  Event e;
  CHECK(rig.controls.PopEvent(&e));
  CHECK(e.type == EVENT_PRESS && e.id == hal::SWITCH_DELAY && e.handled);
  rig.Release(hal::SWITCH_DELAY);
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 1);  // a toggle, not a gate
  rig.Press(hal::SWITCH_DELAY);
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 0);
  rig.Release(hal::SWITCH_DELAY);
  while (rig.controls.PopEvent(&e)) { }

  // With SHIFT held: only an event, for the UI.
  rig.Press(hal::SWITCH_SHIFT);
  rig.Press(hal::SWITCH_REVERB);
  CHECK(rig.engine.preset().slot[SLOT_REVERB].send == 0);
  CHECK(rig.controls.PopEvent(&e));
  CHECK(e.type == EVENT_PRESS && e.id == hal::SWITCH_SHIFT && e.shift);
  CHECK(rig.controls.PopEvent(&e));
  CHECK(e.type == EVENT_PRESS && e.id == hal::SWITCH_REVERB);
  CHECK(e.shift && !e.handled);
  rig.Release(hal::SWITCH_REVERB);
  rig.Release(hal::SWITCH_SHIFT);
  CHECK(rig.controls.PopEvent(&e) && e.type == EVENT_RELEASE && e.shift);
  CHECK(rig.controls.PopEvent(&e) && e.id == hal::SWITCH_SHIFT && !e.shift);
}

TEST(app_controls, send_leds_follow_the_engine) {
  Rig rig;
  static Frame in[kBlockSize];
  static Frame out[kBlockSize];
  memset(in, 0, sizeof(in));
  ModValues mods;
  memset(&mods, 0, sizeof(mods));
  rig.Press(hal::SWITCH_TEXTURE);
  rig.engine.Process(mods, test::Tempo120(), in, out, kBlockSize);
  uint8_t all = 0xff;
  for (int i = 0; i < 16; ++i) {
    all &= rig.Scan();
  }
  CHECK(all & (1 << hal::LED_TEXTURE));
  CHECK(!(all & (1 << hal::LED_PITCH)));
  uint8_t any = 0;
  for (int i = 0; i < 16; ++i) {
    any |= rig.Scan();
  }
  CHECK(!(any & (1 << hal::LED_PITCH)));
  CHECK(!(any & (1 << hal::LED_REVERB)));
}

TEST(app_controls, shift_led_held_and_beat) {
  Rig rig;
  // The tempo.s beat pulse lights SHIFT for 30 ms from each beat.
  int guard = 0;
  while (!rig.tempo.beat_pulse() && guard++ < 2000) {
    rig.tempo.Process(120.0f, 4, kBlockSize);
  }
  CHECK(rig.tempo.beat_pulse());
  CHECK(rig.Scan() & (1 << hal::LED_SHIFT));
  while (rig.tempo.beat_pulse() && guard++ < 4000) {
    rig.tempo.Process(120.0f, 4, kBlockSize);
  }
  CHECK(!(rig.Scan() & (1 << hal::LED_SHIFT)));
  rig.Press(hal::SWITCH_SHIFT);
  CHECK(rig.Scan() & (1 << hal::LED_SHIFT));
}

TEST(app_controls, led_override_and_pwm) {
  Rig rig;
  rig.controls.SetLedOverride(hal::LED_PITCH, 8, 100);
  int lit = 0;
  for (int i = 0; i < 16; ++i) {
    lit += (rig.Scan() >> hal::LED_PITCH) & 1;
  }
  CHECK(lit == 8);
  rig.controls.SetLedOverride(hal::LED_PITCH, 15, 100);
  lit = 0;
  for (int i = 0; i < 16; ++i) {
    lit += (rig.Scan() >> hal::LED_PITCH) & 1;
  }
  CHECK(lit == 16);
  // 100 ms later (400 scans) it is the send's own state again: off.
  rig.Scans(400);
  lit = 0;
  for (int i = 0; i < 16; ++i) {
    lit += (rig.Scan() >> hal::LED_PITCH) & 1;
  }
  CHECK(lit == 0);
  // An override can darken a lit LED too.
  rig.controls.SetLedOverride(hal::LED_SHIFT, 0, 50);
  rig.Press(hal::SWITCH_SHIFT);
  CHECK(!(rig.Scan() & (1 << hal::LED_SHIFT)));
}

TEST(app_controls, queue_full_keeps_encoder_steps) {
  Rig rig;
  // Fill the queue with presses and releases nobody reads.
  for (int i = 0; i < 40; ++i) {
    rig.Press(hal::SWITCH_K3, 0);
    rig.Release(hal::SWITCH_K3, 0);
  }
  for (int i = 0; i < 5; ++i) {
    rig.Turn(1, +1);
  }
  Event e;
  int popped = 0;
  while (rig.controls.PopEvent(&e)) {
    ++popped;
  }
  CHECK(popped == 63);
  // The steps that did not fit arrive with the next scans.
  rig.Scans(2);
  CHECK(rig.DrainEncoder(1) == 5);
}

TEST(app_controls, clock_edges_reach_the_tempo) {
  Rig rig;
  // 120 BPM at 4 PPQN: a 5 ms pulse every 125 ms.
  for (int p = 0; p < 12; ++p) {
    rig.scan.clock = true;
    rig.Scans(20);
    rig.scan.clock = false;
    rig.Scans(480);
    rig.tempo.Process(100.0f, 4, kBlockSize);
  }
  CHECK(rig.tempo.source() == TEMPO_CLOCK);
  CHECK_NEAR(rig.tempo.bpm(), 120.0f, 0.5f);
}
