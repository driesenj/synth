// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the panel's buttons, encoders and LEDs.
//
// OnScan() runs in the 4 kHz control interrupt with each raw scan of the
// shift-register chain: it debounces the nine switches, decodes the four
// encoders' quadrature into detent steps, passes CLOCK jack edges to the
// tempo, and queues events for the main loop's UI.
//
// A send button pressed without SHIFT toggles its send right there in the
// interrupt (Engine::ToggleSend), so a dub throw lands within a scan
// whatever the main loop is busy with; its event still goes to the UI,
// with `handled` set. With SHIFT held the press is only an event (the UI
// opens that block's page).
//
// LEDs: each send LED shows Engine::send_active(); SHIFT's LED is lit while
// SHIFT is held and flashes on every beat otherwise. The UI can take an LED
// over for a while (SetLedOverride). Brightness has 16 levels (software
// PWM over 16 scans: 250 Hz).

#ifndef SIDEFX_APP_CONTROLS_H_
#define SIDEFX_APP_CONTROLS_H_

#include <stddef.h>
#include <stdint.h>

#include "hal.h"

namespace sidefx {

class Engine;
class Tempo;

enum EventType {
  EVENT_ENCODER,  // id: encoder 0..3 (K1..K4), delta: detent steps (+ = clockwise)
  EVENT_PRESS,    // id: hal::Switch
  EVENT_RELEASE,  // id: hal::Switch
};

struct Event {
  uint8_t type;      // EventType
  uint8_t id;
  int8_t delta;
  bool shift;        // SHIFT was held when this happened
  bool handled;      // a send already toggled by the interrupt
  uint32_t time_ms;  // hal::Milliseconds() at the scan
  uint32_t time_us;  // hal::Microseconds() at the scan (tap tempo)
};

class Controls {
 public:
  Controls() { }
  ~Controls() { }

  void Init(Engine* engine, Tempo* tempo);

  // Control interrupt: one raw scan in, the LED bits for the next scan out.
  uint8_t OnScan(const hal::ControlScan& scan);

  // Main loop: the next queued event; false when none.
  bool PopEvent(Event* event);

  // Debounced state.
  bool pressed(int sw) const { return (debounced_ >> sw) & 1; }

  // Quadrature transitions per detent: 4 (one full cycle, most EC11s) or 2.
  void set_steps_per_detent(int steps) { steps_per_detent_ = steps; }
  void set_reverse(bool reverse) { reverse_ = reverse; }

  // The UI's LED override: `level` 0..15 for `duration_ms`.
  void SetLedOverride(int led, uint8_t level, uint32_t duration_ms);

 private:
  static const int kQueueSize = 64;

  Engine* engine_;
  Tempo* tempo_;
  volatile uint16_t debounced_;
  int steps_per_detent_;
  bool reverse_;
  // A switch must read the same for this many scans (1 ms) to change.
  static const uint8_t kDebounceScans = 4;

  bool Push(const Event& event);
  void Debounce(const hal::ControlScan& scan, uint32_t now_ms);
  void DecodeEncoders(const hal::ControlScan& scan, uint32_t now_ms);
  uint8_t Leds(uint32_t now_ms);

  uint8_t debounce_count_[hal::NUM_SWITCHES];
  uint8_t encoder_state_[hal::kNumEncoders];         // last AB, 0..3
  int8_t encoder_accumulator_[hal::kNumEncoders];    // transitions since the last detent
  int16_t encoder_pending_[hal::kNumEncoders];       // steps not yet queued (queue full)
  bool clock_previous_;
  uint8_t pwm_phase_;
  volatile uint8_t override_level_[hal::NUM_LEDS];
  volatile uint32_t override_until_ms_[hal::NUM_LEDS];
  volatile bool override_active_[hal::NUM_LEDS];
  Event queue_[kQueueSize];
  volatile uint16_t queue_head_;  // written by the interrupt
  volatile uint16_t queue_tail_;  // written by the main loop
};

}  // namespace sidefx

#endif  // SIDEFX_APP_CONTROLS_H_
