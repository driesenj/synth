// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: Tempo (internal tempo, the CLOCK jack stable,
// jittery, changing and stopped, MIDI clock, priorities, tap tempo).

#include <math.h>
#include <string.h>

#include "check.h"
#include "hal_fake.h"
#include "test_support.h"

#include "app/tempo.h"
#include "engine/config.h"

using namespace sidefx;

namespace {

const double kBlockUs = double(kBlockSize) * 1.0e6 / double(kSampleRate);

double WrapError(double a, double b) {
  double e = a - b;
  e -= floor(e + 0.5);
  return fabs(e);
}

// Runs the tempo in audio blocks with a pulse train at the CLOCK jack (or
// MIDI clock), and measures the bar phase against the pulses' own grid.
struct Sim {
  Tempo tempo;
  double now_us;
  double next_pulse_us;
  double period_us;      // 0: no pulses
  double jitter_us;      // each edge off by up to this much
  bool midi;
  int ppqn;              // pulses per quarter at the jack (24 for MIDI)
  int settings_ppqn;     // what Process() is told
  float internal_bpm;
  // Grid: the pulse count and the time of the latest pulse.
  long pulses;
  double last_pulse_us;
  double max_phase_error;
  uint32_t noise;
  // A second train: MIDI clock alongside the jack.
  double midi_period_us;
  double midi_next_us;

  Sim() : now_us(1000.0), next_pulse_us(0.0), period_us(0.0), jitter_us(0.0),
          midi(false), ppqn(4), settings_ppqn(4), internal_bpm(100.0f),
          pulses(-1), last_pulse_us(0.0), max_phase_error(0.0), noise(1),
          midi_period_us(0.0), midi_next_us(0.0) {
    test::ResetHal();
    test::Hal().time_us = uint64_t(now_us);
    tempo.Init();
  }

  void StartPulses(double bpm, int pulses_per_quarter) {
    ppqn = pulses_per_quarter;
    period_us = 60.0e6 / (bpm * pulses_per_quarter);
    next_pulse_us = now_us + 100.0;
    pulses = -1;
  }

  void SetBpm(double bpm) { period_us = 60.0e6 / (bpm * ppqn); }
  void StopPulses() { period_us = 0.0; }

  // Expected bar phase now from the pulse grid (downbeat at pulse 0).
  double GridPhase() const {
    const double ppb = 4.0 * ppqn;
    const double since = (now_us - last_pulse_us) / period_us;
    double p = (double(pulses % long(ppb)) + since) / ppb;
    return p - floor(p);
  }

  void Run(double seconds, double settle_seconds = 1e9) {
    const double end = now_us + seconds * 1.0e6;
    const double settle = now_us + settle_seconds * 1.0e6;
    while (now_us < end) {
      now_us += kBlockUs;
      while (period_us > 0.0 && next_pulse_us <= now_us) {
        double j = jitter_us * double(test::Noise(&noise));
        double t = next_pulse_us + j;
        if (t > now_us) t = now_us;
        if (midi) {
          tempo.PushMidiRealtime(0xf8, uint32_t(t));
        } else {
          tempo.PushClockEdge(uint32_t(t));
        }
        ++pulses;
        last_pulse_us = next_pulse_us;
        next_pulse_us += period_us;
      }
      while (midi_period_us > 0.0 && midi_next_us <= now_us) {
        tempo.PushMidiRealtime(0xf8, uint32_t(midi_next_us));
        midi_next_us += midi_period_us;
      }
      test::Hal().time_us = uint64_t(now_us);
      tempo.Process(internal_bpm, settings_ppqn, kBlockSize);
      if (period_us > 0.0 && pulses >= 0 && now_us > settle) {
        double e = WrapError(tempo.state().bar_phase, GridPhase());
        if (e > max_phase_error) {
          max_phase_error = e;
        }
      }
    }
  }
};

}  // namespace

TEST(app_tempo, internal) {
  Sim sim;
  sim.internal_bpm = 120.0f;
  sim.Run(0.1);
  CHECK(sim.tempo.source() == TEMPO_INTERNAL);
  CHECK_NEAR(sim.tempo.bpm(), 120.0f, 1e-3);
  const TempoState& s = sim.tempo.state();
  CHECK(!s.external);
  CHECK_NEAR(s.beat_seconds, 0.5f, 1e-5);
  CHECK_NEAR(s.bar_increment * 2.0f * kSampleRate, 1.0f, 1e-4);
  // A bar takes 2 s.
  float p0 = s.bar_phase;
  sim.Run(1.0);
  CHECK_NEAR(WrapError(sim.tempo.state().bar_phase, p0 + 0.5f), 0.0, 2e-3);
}

TEST(app_tempo, stable_clock) {
  Sim sim;
  sim.StartPulses(128.0, 4);
  sim.Run(4.0, 1.0);
  CHECK(sim.tempo.source() == TEMPO_CLOCK);
  CHECK(sim.tempo.state().external);
  CHECK_NEAR(sim.tempo.bpm(), 128.0f, 0.05f);
  test::Note("max bar phase error %.5f", sim.max_phase_error);
  CHECK(sim.max_phase_error < 0.003);
}

TEST(app_tempo, first_pulse_is_the_downbeat) {
  Sim sim;
  sim.internal_bpm = 97.0f;
  sim.Run(0.73);  // somewhere in the bar
  sim.StartPulses(120.0, 4);
  sim.Run(0.002);
  CHECK(sim.pulses == 0);
  CHECK(WrapError(sim.tempo.state().bar_phase, 0.0) < 0.003);
  CHECK(sim.tempo.beat_pulse());
  // A bar later the count is 16 pulses and the phase is back at 0.
  sim.Run(2.0);
  CHECK(sim.max_phase_error < 0.02);
}

TEST(app_tempo, jittery_clock) {
  Sim sim;
  sim.jitter_us = 250.0;  // the 4 kHz scan's own quantization
  sim.StartPulses(124.0, 4);
  sim.Run(8.0, 2.0);
  CHECK_NEAR(sim.tempo.bpm(), 124.0f, 0.6f);
  test::Note("bpm %.3f, max bar phase error %.5f", sim.tempo.bpm(),
             sim.max_phase_error);
  CHECK(sim.max_phase_error < 0.006);

  Sim fast;
  fast.jitter_us = 250.0;
  fast.settings_ppqn = 24;
  fast.StartPulses(140.0, 24);
  fast.Run(6.0, 2.0);
  CHECK_NEAR(fast.tempo.bpm(), 140.0f, 1.0f);
  test::Note("24 ppqn: bpm %.3f, max bar phase error %.5f", fast.tempo.bpm(),
             fast.max_phase_error);
  CHECK(fast.max_phase_error < 0.006);
}

TEST(app_tempo, small_change_glides_big_change_jumps) {
  Sim sim;
  sim.StartPulses(120.0, 4);
  sim.Run(3.0);
  CHECK_NEAR(sim.tempo.bpm(), 120.0f, 0.05f);
  sim.SetBpm(126.0);  // 5 %: glides
  sim.Run(0.25);      // the old interval, then one new one
  float after_one = sim.tempo.bpm();
  CHECK(after_one > 120.5f && after_one < 125.5f);
  sim.Run(3.0, 0.0);
  CHECK_NEAR(sim.tempo.bpm(), 126.0f, 0.1f);
  test::Note("glide: %.2f after one pulse; phase error %.4f", after_one,
             sim.max_phase_error);
  CHECK(sim.max_phase_error < 0.02);

  sim.SetBpm(90.0);  // 29 %: a new song, taken at the second pulse
  sim.Run(0.12 + 0.17 * 2);
  CHECK_NEAR(sim.tempo.bpm(), 90.0f, 0.2f);
  sim.max_phase_error = 0.0;
  sim.Run(2.0, 0.5);
  CHECK(sim.max_phase_error < 0.01);
}

TEST(app_tempo, one_stray_interval_is_ignored) {
  Sim sim;
  sim.StartPulses(120.0, 4);
  sim.Run(2.0);
  // One pulse 40 % late, then back on the grid.
  sim.next_pulse_us += 0.4 * sim.period_us;
  sim.Run(0.2);
  sim.next_pulse_us -= 0.4 * sim.period_us;
  sim.Run(0.5);
  CHECK_NEAR(sim.tempo.bpm(), 120.0f, 0.5f);
}

TEST(app_tempo, stopped_clock_falls_back) {
  Sim sim;
  sim.internal_bpm = 90.0f;
  sim.StartPulses(130.0, 4);
  sim.Run(2.0);
  CHECK(sim.tempo.source() == TEMPO_CLOCK);
  sim.StopPulses();
  sim.Run(1.5);
  CHECK(sim.tempo.source() == TEMPO_CLOCK);  // a 2 s grace
  CHECK_NEAR(sim.tempo.bpm(), 130.0f, 0.1f);
  sim.Run(0.6);
  CHECK(sim.tempo.source() == TEMPO_INTERNAL);
  CHECK_NEAR(sim.tempo.bpm(), 90.0f, 1e-3);
  // Slow clocks get four periods: 1 PPQN at 25 BPM is 2.4 s per pulse.
  Sim slow;
  slow.settings_ppqn = 1;
  slow.StartPulses(25.0, 1);
  slow.Run(9.0);
  CHECK(slow.tempo.source() == TEMPO_CLOCK);
  CHECK_NEAR(slow.tempo.bpm(), 25.0f, 0.05f);
}

TEST(app_tempo, midi_clock_start_stop) {
  Sim sim;
  sim.midi = true;
  sim.internal_bpm = 80.0f;
  sim.settings_ppqn = 4;  // the jack's setting does not matter for MIDI
  sim.Run(0.37);
  sim.tempo.PushMidiRealtime(0xfa, uint32_t(sim.now_us));
  sim.StartPulses(100.0, 24);
  sim.Run(0.002);
  CHECK(sim.tempo.source() == TEMPO_MIDI);
  CHECK(WrapError(sim.tempo.state().bar_phase, 0.0) < 0.003);
  sim.Run(3.0, 0.5);
  CHECK_NEAR(sim.tempo.bpm(), 100.0f, 0.1f);
  test::Note("midi max bar phase error %.5f", sim.max_phase_error);
  CHECK(sim.max_phase_error < 0.004);
  // STOP: the internal tempo takes over at once, even with clocks going.
  sim.tempo.PushMidiRealtime(0xfc, uint32_t(sim.now_us));
  sim.Run(0.1);
  CHECK(sim.tempo.source() == TEMPO_INTERNAL);
  CHECK_NEAR(sim.tempo.bpm(), 80.0f, 1e-3);
  // START again: the next clock is the downbeat.
  sim.tempo.PushMidiRealtime(0xfa, uint32_t(sim.now_us));
  sim.pulses = -1;
  sim.Run(0.03);
  CHECK(sim.tempo.source() == TEMPO_MIDI);
  sim.max_phase_error = 0.0;
  sim.Run(2.0, 0.0);
  CHECK(sim.max_phase_error < 0.004);
}

TEST(app_tempo, jack_wins_over_midi) {
  Sim sim;
  sim.StartPulses(110.0, 4);
  // MIDI clock at 150 BPM alongside.
  sim.midi_period_us = 60.0e6 / (150.0 * 24.0);
  sim.midi_next_us = sim.now_us;
  sim.Run(3.0);
  CHECK(sim.tempo.source() == TEMPO_CLOCK);
  CHECK_NEAR(sim.tempo.bpm(), 110.0f, 0.2f);
  sim.StopPulses();
  sim.Run(3.0);
  CHECK(sim.tempo.source() == TEMPO_MIDI);
  CHECK_NEAR(sim.tempo.bpm(), 150.0f, 1.0f);
}

TEST(app_tempo, tap) {
  Tempo tempo;
  test::ResetHal();
  tempo.Init();
  float bpm = 0.0f;
  uint32_t t = 1000000;
  CHECK(!tempo.Tap(t, &bpm));
  t += 500000;
  CHECK(tempo.Tap(t, &bpm));
  CHECK_NEAR(bpm, 120.0f, 0.01f);
  // The average of the last four intervals: 500, 500, 520, 480 ms.
  t += 500000;
  tempo.Tap(t, &bpm);
  t += 520000;
  tempo.Tap(t, &bpm);
  t += 480000;
  CHECK(tempo.Tap(t, &bpm));
  CHECK_NEAR(bpm, 120.0f, 0.01f);
  // Older taps drop out: four more at 400 ms give 150.
  for (int i = 0; i < 4; ++i) {
    t += 400000;
    tempo.Tap(t, &bpm);
  }
  CHECK_NEAR(bpm, 150.0f, 0.01f);
  // A pause over 2 s starts over.
  t += 2500000;
  CHECK(!tempo.Tap(t, &bpm));
  t += 1000000;
  CHECK(tempo.Tap(t, &bpm));
  CHECK_NEAR(bpm, 60.0f, 0.01f);
}

TEST(app_tempo, tap_pulls_the_beat_onto_the_tap) {
  Sim sim;
  sim.internal_bpm = 120.0f;
  sim.Run(0.3);
  float bpm;
  // Taps at a beat-sized interval but a third of a beat off the grid.
  sim.tempo.Tap(uint32_t(sim.now_us), &bpm);
  sim.Run(0.5);
  sim.tempo.Tap(uint32_t(sim.now_us), &bpm);
  const double tap_us = sim.now_us;
  sim.Run(1.0);
  // Where the beat grid is now relative to the tap.
  const double beats = sim.tempo.state().bar_phase * 4.0 -
      (sim.now_us - tap_us) / 500000.0;
  CHECK(WrapError(beats, 0.0) < 0.02);
}

TEST(app_tempo, beat_pulse_30ms) {
  Sim sim;
  sim.internal_bpm = 120.0f;
  int on_blocks = 0;
  int rises = 0;
  bool previous = false;
  for (int i = 0; i < int(2.1e6 / kBlockUs); ++i) {
    sim.Run(kBlockUs * 1e-6);
    bool on = sim.tempo.beat_pulse();
    on_blocks += on;
    rises += on && !previous;
    previous = on;
  }
  CHECK(rises == 4);  // one per beat: 0.5, 1, 1.5 and 2 s
  CHECK_NEAR(on_blocks * kBlockUs / rises, 30000.0, 1000.0);
}

TEST(app_tempo, stopped_clock_stays_gone_across_the_us_wrap) {
  // Microseconds() wraps every 2^32 us (71.6 min): a clock unplugged long
  // ago must not come back for its timeout when the difference to its
  // last pulse is small again.
  for (int midi = 0; midi < 2; ++midi) {
    Sim sim;
    sim.midi = midi != 0;
    sim.internal_bpm = 120.0f;
    sim.settings_ppqn = 4;
    sim.StartPulses(90.0, midi ? 24 : 4);
    sim.Run(3.0);
    CHECK(sim.tempo.source() == (midi ? TEMPO_MIDI : TEMPO_CLOCK));
    // Unplugged (MIDI: the cable pulled, no STOP byte).
    const double last = sim.last_pulse_us;
    sim.StopPulses();
    sim.Run(5.0);
    CHECK(sim.tempo.source() == TEMPO_INTERNAL);
    // The module keeps running: jump to just past one wrap after the last
    // pulse, a block at a time from there.
    sim.now_us = last + 4294967296.0 - 0.5e6;
    int external_blocks = 0;
    for (int b = 0; b < int(3.0e6 / kBlockUs); ++b) {
      sim.Run(kBlockUs * 1e-6);
      if (sim.tempo.source() != TEMPO_INTERNAL ||
          sim.tempo.state().external) {
        ++external_blocks;
      }
    }
    test::Note("%s: %d blocks on the stale clock", midi ? "midi" : "jack",
               external_blocks);
    CHECK(external_blocks == 0);
    CHECK_NEAR(sim.tempo.bpm(), 120.0f, 1e-3);
  }
}

TEST(app_tempo, stream_back_after_a_pause_is_a_new_downbeat) {
  Sim sim;
  sim.internal_bpm = 100.0f;
  sim.StartPulses(120.0, 4);
  sim.Run(1.03);
  CHECK(!sim.tempo.state().downbeat);
  sim.StopPulses();
  sim.Run(3.0);
  CHECK(sim.tempo.source() == TEMPO_INTERNAL);
  sim.Run(0.31);  // somewhere in the bar
  // Back: the first pulse is the downbeat, flagged for that block only.
  sim.StartPulses(120.0, 4);
  int downbeats = 0;
  bool first_block = false;
  for (int b = 0; b < int(2.0e6 / kBlockUs); ++b) {
    sim.Run(kBlockUs * 1e-6);
    if (sim.tempo.state().downbeat) {
      ++downbeats;
      first_block = sim.pulses == 0;
      CHECK(WrapError(sim.tempo.state().bar_phase, 0.0) < 0.003);
    }
  }
  CHECK(downbeats == 1);
  CHECK(first_block);
}

TEST(app_tempo, midi_start_flags_the_downbeat) {
  Sim sim;
  sim.midi = true;
  sim.StartPulses(120.0, 24);
  sim.Run(1.37);
  CHECK(sim.tempo.source() == TEMPO_MIDI);
  sim.tempo.PushMidiRealtime(0xfa, uint32_t(sim.now_us));
  sim.pulses = -1;
  int downbeats = 0;
  for (int b = 0; b < int(1.0e6 / kBlockUs); ++b) {
    sim.Run(kBlockUs * 1e-6);
    if (sim.tempo.state().downbeat) {
      ++downbeats;
      CHECK(sim.pulses == 0);
    }
  }
  CHECK(downbeats == 1);
}

TEST(app_tempo, bunched_midi_clocks_keep_the_tempo) {
  // A USB-MIDI interface holds back clocks after a hiccup and sends them
  // back to back (320 us a byte): they count for the bar but are no tempo.
  for (int held = 2; held <= 12; held += 5) {
    test::ResetHal();
    Tempo tempo;
    tempo.Init();
    double now = 1000.0;
    const double period = 60.0e6 / (140.0 * 24.0);
    double next = now + 100.0;
    long k = 0;
    long sent = 0;
    float max_bpm = 0.0f;
    float min_bpm = 1e9f;
    double grid_error = 0.0;
    for (int b = 0; b < int(4.0e6 / kBlockUs); ++b) {
      now += kBlockUs;
      while (next <= now) {
        if (k >= 200 && k < 200 + held) {
          // held back ...
        } else if (k == 200 + held) {
          // ... and flushed right before this one
          for (int j = held; j >= 1; --j) {
            tempo.PushMidiRealtime(0xf8, uint32_t(next - 320.0 * j));
          }
          tempo.PushMidiRealtime(0xf8, uint32_t(next));
          sent += held + 1;
        } else {
          tempo.PushMidiRealtime(0xf8, uint32_t(next));
          ++sent;
        }
        ++k;
        next += period;
      }
      test::Hal().time_us = uint64_t(now);
      tempo.Process(120.0f, 4, kBlockSize);
      if (now > 1.0e6) {
        max_bpm = tempo.bpm() > max_bpm ? tempo.bpm() : max_bpm;
        min_bpm = tempo.bpm() < min_bpm ? tempo.bpm() : min_bpm;
      }
      // Once the burst is in, the bar is back on the grid.
      if (k > 200 + held + 24 && sent == k) {
        const double grid = (double(k - 1) +
            (now - (next - period)) / period) / 96.0;
        const double e = WrapError(tempo.state().bar_phase, grid);
        grid_error = e > grid_error ? e : grid_error;
      }
    }
    test::Note("%d held: bpm %.2f .. %.2f, bar error %.4f", held, min_bpm,
               max_bpm, grid_error);
    CHECK(min_bpm > 139.0f && max_bpm < 141.0f);
    CHECK(grid_error < 0.01);
  }
}

TEST(app_tempo, much_faster_clock_is_still_followed) {
  // Over three times the tempo: not bunched pulses, a new clock.
  Sim sim;
  sim.settings_ppqn = 1;
  sim.StartPulses(40.0, 1);
  sim.Run(6.0);
  CHECK_NEAR(sim.tempo.bpm(), 40.0f, 0.1f);
  sim.SetBpm(150.0);
  sim.Run(4.0);  // the old interval, then a run of new ones
  CHECK_NEAR(sim.tempo.bpm(), 150.0f, 0.5f);
  sim.max_phase_error = 0.0;
  sim.Run(4.0, 0.0);
  CHECK(sim.max_phase_error < 0.01);
}
