// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: tempo sources, bar position and tap tempo.

#include "app/tempo.h"

#include <math.h>

#include "engine/config.h"
#include "hal.h"

namespace sidefx {

namespace {

const uint32_t kMinTimeoutUs = 2000000;   // a clock is gone after 2 s ...
const uint32_t kTimeoutPeriods = 4;        // ... or four periods if slower
// The second pulse may come this late and still count as one stream (a
// 1 PPQN clock at 15 BPM), though the source counts as gone after 2 s
// until a period is known.
const uint32_t kFirstIntervalUs = 4000000;
const uint32_t kTapWindowUs = 2000000;
const float kBeatPulseSeconds = 0.03f;
const float kMinBpm = 20.0f;
const float kMaxBpm = 400.0f;
const float kMinTapBpm = 30.0f;            // the preset's tempo range
const float kMaxTapBpm = 300.0f;
// An interval within this ratio of the period glides; one further off
// waits for a second like it (one stray interval is not a new song).
const float kGlideRatio = 1.2f;
// An interval under a third of the period is no tempo on its own: pulses
// bunched together, or a much faster clock if a run of them (this many,
// lasting an old period) keeps coming.
const float kBunchRatio = 3.0f;
const uint32_t kFastRunPulses = 4;
// A phase error above this is no drift but a lost count: jump.
const float kMaxPullBars = 0.125f;
const uint8_t kMidiClock = 0xf8;
const uint8_t kMidiStart = 0xfa;
const uint8_t kMidiContinue = 0xfb;
const uint8_t kMidiStop = 0xfc;

inline float Clamp(float x, float lo, float hi) {
  return x < lo ? lo : (x > hi ? hi : x);
}

inline float Wrap(float x) { return x - floorf(x); }

inline bool Near(float a, float b) {
  return a < b * kGlideRatio && a * kGlideRatio > b;
}

// Per-pulse glide: about a beat's worth of pulses at high PPQN (MIDI
// jitter averages out), a couple of pulses at low PPQN.
inline float GlideFor(int ppqn) {
  return Clamp(1.0f / float(ppqn), 0.04f, 0.5f);
}

inline float MinPeriodFor(int ppqn) {
  return 0.5f * 60.0e6f / (kMaxBpm * float(ppqn));
}

}  // namespace

void Tempo::PulseTracker::Init() {
  started = false;
  has_period = false;
  restart = false;
  pulsed = false;
  reset = false;
  last_us = 0;
  count = 0;
  period_us = 0.0f;
  candidate_us = 0.0f;
  glide = 0.25f;
  min_period_us = MinPeriodFor(24);
  run_us = 0.0f;
  run_count = 0;
}

uint32_t Tempo::PulseTracker::timeout_us() const {
  const float slow = has_period ? period_us * float(kTimeoutPeriods) : 0.0f;
  return slow > float(kMinTimeoutUs) ? uint32_t(slow) : kMinTimeoutUs;
}

uint32_t Tempo::PulseTracker::pause_us() const {
  return has_period ? timeout_us() : kFirstIntervalUs;
}

uint32_t Tempo::PulseTracker::age_us(uint32_t now_us) const {
  // Signed: an edge the control interrupt stamped after Process() read
  // the time is no age of 71 minutes. Expire() keeps ages far below 2^31.
  const int32_t age = int32_t(now_us - last_us);
  return age > 0 ? uint32_t(age) : 0u;
}

bool Tempo::PulseTracker::alive(uint32_t now_us) const {
  return started && age_us(now_us) < timeout_us();
}

void Tempo::PulseTracker::Expire(uint32_t now_us) {
  if (started && age_us(now_us) >= pause_us()) {
    started = false;
    has_period = false;
    candidate_us = 0.0f;
    run_us = 0.0f;
    run_count = 0;
  }
}

void Tempo::PulseTracker::Pulse(uint32_t time_us) {
  pulsed = true;
  if (!started || time_us - last_us >= pause_us()) {
    // After a pause the count starts over, and the old period is stale.
    started = true;
    has_period = false;
    restart = false;
    candidate_us = 0.0f;
    run_us = 0.0f;
    run_count = 0;
    count = 0;
    reset = true;
    last_us = time_us;
    return;
  }
  const float interval = float(time_us - last_us);
  last_us = time_us;
  if (restart) {
    restart = false;
    count = 0;
    reset = true;
  } else {
    ++count;
  }
  if (interval < min_period_us) {
    return;  // bunched: counted for the bar, but no tempo
  }
  if (!has_period) {
    period_us = interval;
    has_period = true;
    return;
  }
  if (interval * kBunchRatio < period_us) {
    // Far faster than the period: pulses bunched up after a hiccup, or
    // a much faster clock, which a run lasting an old period shows.
    run_us += interval;
    ++run_count;
    if (run_count >= kFastRunPulses && run_us >= period_us) {
      period_us = run_us / float(run_count);
      candidate_us = 0.0f;
      run_us = 0.0f;
      run_count = 0;
    }
    return;
  }
  run_us = 0.0f;
  run_count = 0;
  if (Near(interval, period_us)) {
    period_us += (interval - period_us) * glide;
    candidate_us = 0.0f;
  } else if (candidate_us > 0.0f && Near(interval, candidate_us)) {
    period_us = interval;  // a jump, confirmed: taken at once
    candidate_us = 0.0f;
  } else {
    candidate_us = interval;
  }
}

void Tempo::Init() {
  bpm_ = 120.0f;
  source_ = TEMPO_INTERNAL;
  beat_pulse_ = false;
  clock_head_ = clock_tail_ = 0;
  midi_head_ = midi_tail_ = 0;
  num_taps_ = 0;
  tap_us_ = 0;
  tap_request_ = false;
  clock_.Init();
  midi_.Init();
  midi_.glide = GlideFor(24);
  midi_running_ = true;
  phase_ = 0.0f;
  phase_error_ = 0.0f;
  period_samples_ = 0.5f * kSampleRate;
  beat_pulse_samples_ = 0;
  state_.beat_seconds = 0.5f;
  state_.bar_phase = 0.0f;
  state_.bar_increment = 1.0f / (2.0f * kSampleRate);
  state_.external = false;
  state_.downbeat = false;
}

void Tempo::PushClockEdge(uint32_t time_us) {
  const uint8_t head = clock_head_;
  const uint8_t next = uint8_t((head + 1) % kRingSize);
  if (next == clock_tail_) {
    return;
  }
  clock_ring_[head] = time_us;
  __asm__ __volatile__("" ::: "memory");
  clock_head_ = next;
}

void Tempo::PushMidiRealtime(uint8_t byte, uint32_t time_us) {
  if (byte != kMidiClock && byte != kMidiStart && byte != kMidiContinue &&
      byte != kMidiStop) {
    return;
  }
  const uint8_t head = midi_head_;
  const uint8_t next = uint8_t((head + 1) % kRingSize);
  if (next == midi_tail_) {
    return;
  }
  midi_ring_[head] = time_us;
  midi_type_ring_[head] = byte;
  __asm__ __volatile__("" ::: "memory");
  midi_head_ = next;
}

bool Tempo::Tap(uint32_t time_us, float* bpm) {
  if (num_taps_ > 0 && time_us - taps_[num_taps_ - 1] > kTapWindowUs) {
    num_taps_ = 0;
  }
  if (num_taps_ == kNumTaps) {
    for (int i = 1; i < kNumTaps; ++i) {
      taps_[i - 1] = taps_[i];
    }
    --num_taps_;
  }
  taps_[num_taps_++] = time_us;
  if (num_taps_ < 2) {
    return false;
  }
  const float interval =
      float(taps_[num_taps_ - 1] - taps_[0]) / float(num_taps_ - 1);
  if (interval <= 0.0f) {
    return false;
  }
  *bpm = Clamp(60.0e6f / interval, kMinTapBpm, kMaxTapBpm);
  // The beat follows the taps too (see Process()).
  tap_us_ = time_us;
  __asm__ __volatile__("" ::: "memory");
  tap_request_ = true;
  return true;
}

void Tempo::Align(const PulseTracker& tracker, int ppqn, uint32_t now_us,
                  float increment) {
  const uint32_t pulses_per_bar = uint32_t(ppqn) * 4u;
  const float since =
      float(tracker.age_us(now_us)) * (kSampleRate * 1.0e-6f);
  const float target = Wrap(
      float(tracker.count % pulses_per_bar) / float(pulses_per_bar) +
      since * increment);
  if (tracker.reset) {
    phase_ = target;
    phase_error_ = 0.0f;
    beat_pulse_samples_ = int32_t(kBeatPulseSeconds * kSampleRate);
    return;
  }
  float error = Wrap(target - phase_ + 0.5f) - 0.5f;
  if (fabsf(error) > kMaxPullBars) {
    phase_ = target;
    phase_error_ = 0.0f;
  } else {
    phase_error_ = error;
  }
}

void Tempo::Process(float internal_bpm, int ppqn, size_t size) {
  const uint32_t now = hal::Microseconds();
  if (ppqn < 1) {
    ppqn = 1;
  }
  clock_.glide = GlideFor(ppqn);
  clock_.min_period_us = MinPeriodFor(ppqn);
  clock_.pulsed = clock_.reset = false;
  midi_.pulsed = midi_.reset = false;

  while (clock_tail_ != clock_head_) {
    const uint8_t tail = clock_tail_;
    __asm__ __volatile__("" ::: "memory");
    clock_.Pulse(clock_ring_[tail]);
    clock_tail_ = uint8_t((tail + 1) % kRingSize);
  }
  while (midi_tail_ != midi_head_) {
    const uint8_t tail = midi_tail_;
    __asm__ __volatile__("" ::: "memory");
    const uint8_t type = midi_type_ring_[tail];
    const uint32_t t = midi_ring_[tail];
    midi_tail_ = uint8_t((tail + 1) % kRingSize);
    if (type == kMidiClock) {
      midi_.Pulse(t);
    } else if (type == kMidiStart) {
      midi_running_ = true;
      midi_.restart = true;
    } else if (type == kMidiContinue) {
      midi_running_ = true;
    } else if (type == kMidiStop) {
      midi_running_ = false;
    }
  }
  clock_.Expire(now);
  midi_.Expire(now);
  int source = TEMPO_INTERNAL;
  if (clock_.alive(now)) {
    source = TEMPO_CLOCK;
  } else if (midi_running_ && midi_.alive(now)) {
    source = TEMPO_MIDI;
  }
  source_ = source;

  PulseTracker* tracker = NULL;
  int tracker_ppqn = 24;
  if (source == TEMPO_CLOCK) {
    tracker = &clock_;
    tracker_ppqn = ppqn;
  } else if (source == TEMPO_MIDI) {
    tracker = &midi_;
  }

  if (tracker) {
    if (tracker->has_period) {
      bpm_ = Clamp(60.0e6f / (tracker->period_us * float(tracker_ppqn)),
                   kMinBpm, kMaxBpm);
      period_samples_ = tracker->period_us * (kSampleRate * 1.0e-6f);
    }
  } else {
    bpm_ = Clamp(internal_bpm, kMinTapBpm, kMaxTapBpm);
    period_samples_ = 60.0f / bpm_ * kSampleRate;
  }
  const float increment = bpm_ * (1.0f / (240.0f * kSampleRate));

  if (tracker && tracker->pulsed) {
    Align(*tracker, tracker_ppqn, now, increment);
  } else if (!tracker && tap_request_) {
    tap_request_ = false;
    // The tap lands on a beat: pull the nearest beat onto it.
    const float since = float(now - tap_us_) * (kSampleRate * 1.0e-6f);
    const float beats = Wrap(phase_ - since * increment) * 4.0f;
    phase_error_ = (floorf(beats + 0.5f) - beats) * 0.25f;
  }
  if (tracker) {
    tap_request_ = false;
  }

  state_.bar_phase = phase_;
  state_.bar_increment = increment;
  state_.beat_seconds = 60.0f / bpm_;
  state_.external = source != TEMPO_INTERNAL;
  // The bar started over: MIDI START, or the first pulse after a pause.
  state_.downbeat = tracker && tracker->pulsed && tracker->reset;

  // Advance, pulling any error in over half a pulse period, never
  // backwards.
  const float nominal = increment * float(size);
  float k = float(size) / (0.5f * (period_samples_ > 1.0f ? period_samples_ : 1.0f));
  if (k > 1.0f) {
    k = 1.0f;
  }
  float advance = nominal + phase_error_ * k;
  if (advance < 0.1f * nominal) {
    advance = 0.1f * nominal;
  }
  phase_error_ -= advance - nominal;
  const float before = phase_ * 4.0f;
  phase_ = Wrap(phase_ + advance);
  if (phase_ >= 1.0f) {
    phase_ = 0.0f;
  }
  if (floorf(phase_ * 4.0f) != floorf(before)) {
    beat_pulse_samples_ = int32_t(kBeatPulseSeconds * kSampleRate);
  } else if (beat_pulse_samples_ > 0) {
    beat_pulse_samples_ -= int32_t(size);
  }
  beat_pulse_ = beat_pulse_samples_ > 0;
}

}  // namespace sidefx
