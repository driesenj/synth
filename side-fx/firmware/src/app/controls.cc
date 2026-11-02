// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: debouncing, encoder decoding, the event queue and the LEDs.

#include "app/controls.h"

#include <string.h>

#include "app/tempo.h"
#include "engine/engine.h"

namespace sidefx {

namespace {

// Keeps the compiler from moving the queue's stores across the index
// update. Interrupt and main loop share one core, which sees its own
// stores in program order, so no hardware barrier is needed.
inline void CompilerBarrier() { __asm__ __volatile__("" ::: "memory"); }

// Gray-code steps: kQuadrature[previous << 2 | current] is +1, -1 or 0
// (no change, or both phases at once: a missed transition, ignored).
const int8_t kQuadrature[16] = {
  0, +1, -1, 0,
  -1, 0, 0, +1,
  +1, 0, 0, -1,
  0, -1, +1, 0,
};

const uint8_t kLedFull = 15;

}  // namespace

void Controls::Init(Engine* engine, Tempo* tempo) {
  engine_ = engine;
  tempo_ = tempo;
  debounced_ = 0;
  steps_per_detent_ = 4;
  reverse_ = false;
  memset(debounce_count_, 0, sizeof(debounce_count_));
  memset(encoder_state_, 0, sizeof(encoder_state_));
  memset(encoder_accumulator_, 0, sizeof(encoder_accumulator_));
  memset(encoder_pending_, 0, sizeof(encoder_pending_));
  clock_previous_ = false;
  pwm_phase_ = 0;
  for (int i = 0; i < hal::NUM_LEDS; ++i) {
    override_level_[i] = 0;
    override_until_ms_[i] = 0;
    override_active_[i] = false;
  }
  queue_head_ = 0;
  queue_tail_ = 0;
}

bool Controls::Push(const Event& event) {
  const uint16_t head = queue_head_;
  const uint16_t next = uint16_t((head + 1) % kQueueSize);
  if (next == queue_tail_) {
    return false;
  }
  queue_[head] = event;
  CompilerBarrier();
  queue_head_ = next;
  return true;
}

bool Controls::PopEvent(Event* event) {
  const uint16_t tail = queue_tail_;
  if (tail == queue_head_) {
    return false;
  }
  CompilerBarrier();
  *event = queue_[tail];
  CompilerBarrier();
  queue_tail_ = uint16_t((tail + 1) % kQueueSize);
  return true;
}

void Controls::Debounce(const hal::ControlScan& scan, uint32_t now_ms) {
  uint16_t state = debounced_;
  // SHIFT first, so a button that lands in the same scan sees it.
  static const uint8_t kOrder[hal::NUM_SWITCHES] = {
    hal::SWITCH_SHIFT, hal::SWITCH_PITCH, hal::SWITCH_DELAY,
    hal::SWITCH_TEXTURE, hal::SWITCH_REVERB, hal::SWITCH_K1, hal::SWITCH_K2,
    hal::SWITCH_K3, hal::SWITCH_K4,
  };
  for (int n = 0; n < hal::NUM_SWITCHES; ++n) {
    const int sw = kOrder[n];
    const bool raw = (scan.switches >> sw) & 1;
    const bool held = (state >> sw) & 1;
    if (raw == held) {
      debounce_count_[sw] = 0;
      continue;
    }
    if (++debounce_count_[sw] < kDebounceScans) {
      continue;
    }
    debounce_count_[sw] = 0;
    state = uint16_t(state ^ (1u << sw));
    debounced_ = state;
    const bool shift = (state >> hal::SWITCH_SHIFT) & 1;

    Event e;
    e.type = raw ? EVENT_PRESS : EVENT_RELEASE;
    e.id = uint8_t(sw);
    e.delta = 0;
    e.shift = shift;
    e.handled = false;
    e.time_ms = now_ms;
    e.time_us = scan.time_us;
    if (raw && sw <= hal::SWITCH_REVERB && !shift && engine_) {
      engine_->ToggleSend(sw);
      e.handled = true;
    }
    Push(e);
  }
}

void Controls::DecodeEncoders(const hal::ControlScan& scan, uint32_t now_ms) {
  const bool shift = pressed(hal::SWITCH_SHIFT);
  for (int i = 0; i < hal::kNumEncoders; ++i) {
    const uint8_t ab = scan.encoder[i] & 3;
    const uint8_t previous = encoder_state_[i];
    if (ab != previous) {
      encoder_accumulator_[i] = int8_t(
          encoder_accumulator_[i] + kQuadrature[(previous << 2) | ab]);
      encoder_state_[i] = ab;
      // A detent is a rest position (both contacts open, and both closed
      // too on a half-cycle encoder). Contact bounce only goes back and
      // forth, so the transitions between two rests add up to a whole
      // number of detents: rounding them makes one step per detent
      // whatever the bounce.
      const bool rest = ab == 0 || (steps_per_detent_ == 2 && ab == 3);
      if (rest) {
        const int a = encoder_accumulator_[i];
        const int half = steps_per_detent_ / 2;
        int steps = a >= 0
            ? (a + half) / steps_per_detent_
            : -((-a + half) / steps_per_detent_);
        encoder_accumulator_[i] = 0;
        if (reverse_) {
          steps = -steps;
        }
        encoder_pending_[i] = int16_t(encoder_pending_[i] + steps);
      } else if (encoder_accumulator_[i] > 8 || encoder_accumulator_[i] < -8) {
        // Never at rest for two detents' worth: lost track; start over.
        encoder_accumulator_[i] = 0;
      }
    }
    int pending = encoder_pending_[i];
    if (pending) {
      if (pending > 127) pending = 127;
      if (pending < -127) pending = -127;
      Event e;
      e.type = EVENT_ENCODER;
      e.id = uint8_t(i);
      e.delta = int8_t(pending);
      e.shift = shift;
      e.handled = false;
      e.time_ms = now_ms;
      e.time_us = scan.time_us;
      if (Push(e)) {
        encoder_pending_[i] = int16_t(encoder_pending_[i] - pending);
      }
    }
  }
}

void Controls::SetLedOverride(int led, uint8_t level, uint32_t duration_ms) {
  if (led < 0 || led >= hal::NUM_LEDS) {
    return;
  }
  override_active_[led] = false;
  CompilerBarrier();
  override_level_[led] = level > kLedFull ? kLedFull : level;
  override_until_ms_[led] = hal::Milliseconds() + duration_ms;
  CompilerBarrier();
  override_active_[led] = duration_ms != 0;
}

uint8_t Controls::Leds(uint32_t now_ms) {
  uint8_t level[hal::NUM_LEDS];
  for (int i = 0; i < NUM_SLOTS; ++i) {
    level[i] = engine_ && engine_->send_active(i) ? kLedFull : 0;
  }
  const bool beat = tempo_ && tempo_->beat_pulse();
  level[hal::LED_SHIFT] = pressed(hal::SWITCH_SHIFT) || beat ? kLedFull : 0;
  for (int i = 0; i < hal::NUM_LEDS; ++i) {
    if (override_active_[i]) {
      if (int32_t(override_until_ms_[i] - now_ms) > 0) {
        level[i] = override_level_[i];
      } else {
        override_active_[i] = false;
      }
    }
  }
  // 16 levels over 16 scans: level n is lit for n of them, 15 always.
  uint8_t bits = 0;
  for (int i = 0; i < hal::NUM_LEDS; ++i) {
    if (level[i] >= kLedFull || level[i] > pwm_phase_) {
      bits = uint8_t(bits | (1u << i));
    }
  }
  pwm_phase_ = uint8_t((pwm_phase_ + 1) & 15);
  return bits;
}

uint8_t Controls::OnScan(const hal::ControlScan& scan) {
  const uint32_t now_ms = hal::Milliseconds();
  if (scan.clock && !clock_previous_ && tempo_) {
    tempo_->PushClockEdge(scan.time_us);
  }
  clock_previous_ = scan.clock;
  Debounce(scan, now_ms);
  DecodeEncoders(scan, now_ms);
  return Leds(now_ms);
}

}  // namespace sidefx
