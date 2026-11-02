// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the tempo every synced parameter follows.
//
// Three sources, the first that is alive wins:
//   1. the CLOCK jack: pulses at the PPQN in the settings (1, 2, 4, 8, 12
//      or 24 per quarter note); alive while pulses keep coming (2 s, or
//      four pulse periods at slow tempos, after the last);
//   2. MIDI clock (24 per quarter note), alive while it runs; START resets
//      the bar, STOP lets the internal tempo take over;
//   3. the preset's internal tempo (HOME page, tap tempo on K4's push).
//
// The bar position follows the source: an external clock's pulses are
// counted into 4/4 bars from the first pulse after a pause (or MIDI
// START), and the phase between pulses is extrapolated at the measured
// tempo, then pulled back in line at each pulse, so synced LFOs and
// glitches stay on the grid. Tempo jumps under 20 % glide over a few
// pulses; bigger ones (a new song) are taken at the second interval like
// them. Pulses bunched far closer than the period (a MIDI interface
// catching up after a hiccup) still count for the bar but say nothing
// about the tempo, unless a run of them lasts a whole old period. A
// stream that pauses is forgotten: the downbeat of the next pulse sets
// TempoState::downbeat.

#ifndef SIDEFX_APP_TEMPO_H_
#define SIDEFX_APP_TEMPO_H_

#include <stddef.h>
#include <stdint.h>

#include "engine/tempo_state.h"

namespace sidefx {

enum TempoSource {
  TEMPO_INTERNAL,
  TEMPO_CLOCK,
  TEMPO_MIDI,
};

class Tempo {
 public:
  Tempo() { }
  ~Tempo() { }

  void Init();

  // Control interrupt: a rising edge at the CLOCK jack.
  void PushClockEdge(uint32_t time_us);
  // Main loop: MIDI real-time bytes (0xF8 clock, 0xFA start, 0xFB continue,
  // 0xFC stop) with their arrival time.
  void PushMidiRealtime(uint8_t byte, uint32_t time_us);

  // Main loop: a tap on K4. True, with *bpm set, once two or more taps
  // within 2 s of each other give a tempo (the average of the last four).
  bool Tap(uint32_t time_us, float* bpm);

  // Audio interrupt, once per block before the engine: consumes the queued
  // edges and advances the bar. internal_bpm from the preset, ppqn from the
  // settings.
  void Process(float internal_bpm, int ppqn, size_t size);

  const TempoState& state() const { return state_; }
  float bpm() const { return bpm_; }       // the tempo in use
  int source() const { return source_; }  // TempoSource
  // True for 30 ms from the start of every beat (the SHIFT LED).
  bool beat_pulse() const { return beat_pulse_; }

 private:
  static const int kRingSize = 32;

  TempoState state_;
  float bpm_;
  volatile int source_;
  volatile bool beat_pulse_;
  static const int kNumTaps = 5;  // four intervals

  // One external pulse stream (the jack or MIDI clock): its period and
  // where it is in the bar.
  struct PulseTracker {
    bool started;        // a pulse came, and no pause since
    bool has_period;
    bool restart;        // MIDI START: the next pulse is a downbeat
    bool pulsed;         // a pulse in this block
    bool reset;          // ... and it began a new count (downbeat)
    uint32_t last_us;    // the latest pulse
    uint32_t count;      // pulses since the downbeat
    float period_us;     // filtered
    float candidate_us;  // an interval far off the period, waiting for a second
    float glide;         // the filter's coefficient (per pulse)
    // Intervals shorter than this are pulses bunched together (a MIDI
    // interface catching up), never a tempo: half a pulse at 400 BPM.
    float min_period_us;
    float run_us;        // a run of intervals far below the period ...
    uint32_t run_count;  // ... and how many

    void Init();
    void Pulse(uint32_t time_us);
    uint32_t timeout_us() const;
    // How long without a pulse before the next one starts a new count.
    uint32_t pause_us() const;
    // Time since the latest pulse; 0 for one stamped after now_us.
    uint32_t age_us(uint32_t now_us) const;
    bool alive(uint32_t now_us) const;
    // After a pause: forget the stream, so that only a real pulse brings
    // it back (Microseconds() wraps every 71.6 minutes).
    void Expire(uint32_t now_us);
  };

  void Align(const PulseTracker& tracker, int ppqn, uint32_t now_us,
             float increment);

  uint32_t clock_ring_[kRingSize];
  volatile uint8_t clock_head_;
  volatile uint8_t clock_tail_;
  uint32_t midi_ring_[kRingSize];
  uint8_t midi_type_ring_[kRingSize];
  volatile uint8_t midi_head_;
  volatile uint8_t midi_tail_;
  uint32_t taps_[kNumTaps];
  int num_taps_;
  volatile uint32_t tap_us_;
  volatile bool tap_request_;
  PulseTracker clock_;
  PulseTracker midi_;
  bool midi_running_;
  float phase_;        // bar position now, [0, 1)
  float phase_error_;  // still to be pulled in (bars)
  float period_samples_;  // the active source's pulse period, for the pull-in speed
  int32_t beat_pulse_samples_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_TEMPO_H_
