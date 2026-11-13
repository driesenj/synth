// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: ModSources (CV and calibration, LFOs free and
// synced, RANDOM, the envelope follower, MIDI notes and CCs) and MidiIn
// (the parser and its mappings).

#include <math.h>
#include <string.h>

#include "check.h"
#include "hal_fake.h"
#include "test_support.h"

#include "app/midi.h"
#include "app/mod_sources.h"
#include "app/settings.h"
#include "app/tempo.h"
#include "engine/engine.h"
#include "engine/params.h"

using namespace sidefx;

namespace {

const float kPi = 3.14159265f;

// The preset value of a free rate in Hz.
uint16_t FreeRate(float hz) {
  return PresetRaw(ExpUnmap(hz, 0.02f, 20.0f));
}

// The preset value of a synced rate with this label.
uint16_t SyncedRate(const char* label) {
  for (int i = 0; i < kNumNoteValues; ++i) {
    if (!strcmp(kNoteValues[i].label, label)) {
      return PresetRaw(1.0f - StepValue(i, kNumNoteValues));
    }
  }
  return 0;
}

struct ModRig {
  ModSources mods;
  Preset preset;
  TempoState tempo;
  float cv[4];
  Frame in[kBlockSize];

  ModRig() {
    test::ResetHal();
    mods.Init();
    memset(&preset, 0, sizeof(preset));
    tempo = test::Tempo120();
    tempo.downbeat = false;
    for (int i = 0; i < 4; ++i) {
      cv[i] = test::CvRawForVolts(0.0f);
    }
    memset(in, 0, sizeof(in));
  }

  // One block; the tempo advances by itself (120 BPM, internal).
  const ModValues& Block() {
    mods.Process(preset, tempo, cv, in, kBlockSize);
    tempo.bar_phase += tempo.bar_increment * float(kBlockSize);
    tempo.bar_phase -= floorf(tempo.bar_phase);
    return mods.values();
  }

  int BlocksFor(float seconds) const {
    return int(seconds * kSampleRate / float(kBlockSize) + 0.5f);
  }
};

}  // namespace

TEST(app_mods, cv_volts_and_calibration) {
  ModRig rig;
  rig.cv[0] = test::CvRawForVolts(2.0f);
  rig.cv[1] = test::CvRawForVolts(-5.0f);
  rig.cv[2] = test::CvRawForVolts(1.0f / 12.0f);
  rig.cv[3] = 0.305f;  // +5 V or so
  const ModValues& v = rig.Block();
  CHECK_NEAR(rig.mods.cv_volts(0), 2.0f, 1e-4);
  CHECK_NEAR(v.value[MOD_CV1], 0.5f, 1e-4);
  CHECK_NEAR(v.value[MOD_CV2], -1.25f, 1e-4);  // not clamped
  CHECK_NEAR(v.value[MOD_CV3] * 48.0f, 1.0f, 1e-3);  // a semitone on +-24 st
  CHECK_NEAR(rig.mods.cv_volts(3), 5.0f, 0.05f);
  CHECK(rig.mods.cv_raw(3) == 0.305f);
  CHECK(v.value[MOD_OFF] == 0.0f);

  // A measured calibration: this jack reads 0.512 at 0 V and 25.0 V/unit.
  CvCalibration c;
  InitCvCalibration(&c);
  c.offset[0] = 0.512f;
  c.scale[0] = -25.0f;
  rig.mods.set_calibration(c);
  rig.cv[0] = 0.512f - 3.0f / 25.0f;
  rig.Block();
  CHECK_NEAR(rig.mods.cv_volts(0), 3.0f, 1e-4);
}

TEST(app_mods, lfo_free_rate_and_shapes) {
  ModRig rig;
  rig.preset.lfo[0].rate = FreeRate(2.0f);
  rig.preset.lfo[0].shape = LFO_SINE;
  rig.preset.lfo[1].rate = FreeRate(0.5f);
  rig.preset.lfo[1].shape = LFO_SQUARE;
  int crossings = 0;
  float previous = 0.0f;
  float lo = 0.0f, hi = 0.0f;
  int square_flips = 0;
  float previous_square = 1.0f;
  const int blocks = rig.BlocksFor(4.0f);
  for (int i = 0; i < blocks; ++i) {
    const ModValues& v = rig.Block();
    float s = v.value[MOD_LFO1];
    if (previous < 0.0f && s >= 0.0f) {
      ++crossings;
    }
    previous = s;
    lo = s < lo ? s : lo;
    hi = s > hi ? s : hi;
    float q = v.value[MOD_LFO2];
    CHECK(q == 1.0f || q == -1.0f);
    square_flips += q != previous_square;
    previous_square = q;
  }
  CHECK(crossings == 8);  // 2 Hz for 4 s
  CHECK(lo < -0.99f && hi > 0.99f);
  CHECK(square_flips == 4);  // 0.5 Hz: two cycles

  // The other shapes over one slow cycle.
  const int kShapes[3] = { LFO_TRIANGLE, LFO_RAMP_UP, LFO_RAMP_DOWN };
  for (int k = 0; k < 3; ++k) {
    ModRig r;
    r.preset.lfo[0].rate = FreeRate(1.0f);
    r.preset.lfo[0].shape = uint8_t(kShapes[k]);
    float mn = 2.0f, mx = -2.0f, max_step = 0.0f, last = 0.0f;
    for (int i = 0; i < r.BlocksFor(0.99f); ++i) {
      float x = r.Block().value[MOD_LFO1];
      if (i) {
        max_step = fabsf(x - last) > max_step ? fabsf(x - last) : max_step;
      }
      last = x;
      mn = x < mn ? x : mn;
      mx = x > mx ? x : mx;
    }
    CHECK(mn < -0.97f && mx > 0.97f && mn >= -1.0f && mx <= 1.0f);
    CHECK(max_step < 0.01f);  // no jumps within the cycle
  }
}

TEST(app_mods, lfo_steps_new_value_each_cycle) {
  ModRig rig;
  rig.preset.lfo[0].rate = FreeRate(4.0f);
  rig.preset.lfo[0].shape = LFO_STEPS;
  int changes = 0;
  float last = rig.Block().value[MOD_LFO1];
  for (int i = 0; i < rig.BlocksFor(2.0f); ++i) {
    float x = rig.Block().value[MOD_LFO1];
    CHECK(x >= -1.0f && x < 1.0f);
    changes += x != last;
    last = x;
  }
  CHECK(changes >= 7 && changes <= 8);
}

TEST(app_mods, synced_lfo_locks_to_the_bar) {
  ModRig rig;
  rig.preset.lfo[0].rate = SyncedRate("1/4");
  rig.preset.lfo[0].sync = 1;
  rig.preset.lfo[0].shape = LFO_RAMP_UP;
  rig.preset.lfo[1].rate = SyncedRate("2 BAR");
  rig.preset.lfo[1].sync = 1;
  rig.preset.lfo[1].shape = LFO_RAMP_UP;
  float max_error = 0.0f;
  float max_error_2bar = 0.0f;
  int bars = 0;
  float last_phase = 0.0f;
  for (int i = 0; i < rig.BlocksFor(8.0f); ++i) {
    float bar = rig.tempo.bar_phase;
    if (bar < last_phase) {
      ++bars;
    }
    last_phase = bar;
    const ModValues& v = rig.Block();
    float beat = bar * 4.0f - floorf(bar * 4.0f);
    float e = fabsf(v.value[MOD_LFO1] - (2.0f * beat - 1.0f));
    if (e < 1.5f) {  // away from the wrap itself
      max_error = e > max_error ? e : max_error;
    }
    float two = (float(bars % 2) + bar) * 0.5f;
    float e2 = fabsf(v.value[MOD_LFO2] - (2.0f * two - 1.0f));
    if (e2 < 1.5f) {
      max_error_2bar = e2 > max_error_2bar ? e2 : max_error_2bar;
    }
  }
  CHECK(bars == 3 || bars == 4);
  CHECK(max_error < 1e-3f);
  CHECK(max_error_2bar < 1e-3f);

  // A jump in the bar (an external clock's downbeat) moves the LFO with it.
  rig.tempo.bar_phase = 0.125f;
  const ModValues& v = rig.Block();
  CHECK_NEAR(v.value[MOD_LFO1], 2.0f * 0.5f - 1.0f, 1e-3);
}

TEST(app_mods, long_synced_cycles_start_at_midi_start) {
  // A 4 BAR LFO starts the song at its phase 0, however long the module
  // ran on its internal tempo before the DAW pressed play, and wherever
  // in the bar that left it.
  const double block_us = double(kBlockSize) * 1.0e6 / double(kSampleRate);
  for (int pre_bars = 0; pre_bars < 4; ++pre_bars) {
    for (int late = 0; late < 2; ++late) {
      test::ResetHal();
      Tempo tempo;
      tempo.Init();
      ModRig rig;
      rig.preset.lfo[0].sync = 1;
      rig.preset.lfo[0].shape = LFO_RAMP_UP;
      rig.preset.lfo[0].rate = SyncedRate("4 BAR");
      double now = 1000.0;
      const double pre_us = (pre_bars + (late ? 0.6 : 0.3)) * 2.0e6;
      while (now < pre_us) {
        now += block_us;
        test::Hal().time_us = uint64_t(now);
        tempo.Process(120.0f, 4, kBlockSize);
        rig.mods.Process(rig.preset, tempo.state(), rig.cv, rig.in,
                         kBlockSize);
      }
      tempo.PushMidiRealtime(0xfa, uint32_t(now));
      const double period = 60.0e6 / (120.0 * 24.0);
      double next = now + 200.0;
      float phase = -1.0f;
      for (int b = 0; b < 20; ++b) {
        now += block_us;
        while (next <= now) {
          tempo.PushMidiRealtime(0xf8, uint32_t(next));
          next += period;
        }
        test::Hal().time_us = uint64_t(now);
        tempo.Process(120.0f, 4, kBlockSize);
        rig.mods.Process(rig.preset, tempo.state(), rig.cv, rig.in,
                         kBlockSize);
        phase = 0.5f * (rig.mods.values().value[MOD_LFO1] + 1.0f);
      }
      // 20 blocks (13 ms) into a 4-bar (8 s) cycle.
      test::Note("%d.%d bars before START: LFO phase %.4f", pre_bars,
                 late ? 6 : 3, phase);
      CHECK(phase >= 0.0f && phase < 0.003f);
    }
  }
}

TEST(app_mods, random_steps_and_smooth) {
  ModRig rig;
  rig.preset.random.rate = FreeRate(4.0f);
  rig.preset.random.smooth = 0;
  int changes = 0;
  float last = rig.Block().value[MOD_RANDOM];
  float lo = 1.0f, hi = -1.0f;
  for (int i = 0; i < rig.BlocksFor(4.0f); ++i) {
    float x = rig.Block().value[MOD_RANDOM];
    changes += x != last;
    last = x;
    lo = x < lo ? x : lo;
    hi = x > hi ? x : hi;
  }
  CHECK(changes >= 15 && changes <= 16);
  CHECK(lo >= -1.0f && hi < 1.0f && hi - lo > 0.5f);

  ModRig smooth;
  smooth.preset.random.rate = FreeRate(4.0f);
  smooth.preset.random.smooth = 65535;
  float max_step = 0.0f;
  float previous = smooth.Block().value[MOD_RANDOM];
  for (int i = 0; i < smooth.BlocksFor(4.0f); ++i) {
    float x = smooth.Block().value[MOD_RANDOM];
    max_step = fabsf(x - previous) > max_step ? fabsf(x - previous) : max_step;
    previous = x;
  }
  // A cosine glide over a 250 ms cycle moves at most pi/2 * 2 per cycle.
  test::Note("smooth random max step per block %.4f", max_step);
  CHECK(max_step < 0.03f);

  // Synced: a new value exactly on each 1/8.
  ModRig synced;
  synced.preset.random.rate = SyncedRate("1/8");
  synced.preset.random.sync = 1;
  int steps = 0;
  float p = synced.Block().value[MOD_RANDOM];
  for (int i = 0; i < synced.BlocksFor(2.0f); ++i) {
    float x = synced.Block().value[MOD_RANDOM];
    steps += x != p;
    p = x;
  }
  CHECK(steps == 8);
}

TEST(app_mods, envelope_follower) {
  ModRig rig;
  rig.preset.envelope.attack = 0;          // 1 ms
  rig.preset.envelope.release = PresetRaw(ExpUnmap(0.1f, 0.01f, 5.0f));
  rig.preset.envelope.gain = 0;
  CHECK(rig.Block().value[MOD_ENVELOPE] == 0.0f);
  int n = 0;
  for (int b = 0; b < rig.BlocksFor(0.05f); ++b) {
    for (size_t i = 0; i < kBlockSize; ++i, ++n) {
      float s = 0.5f * sinf(2.0f * kPi * 220.0f * float(n) / kSampleRate);
      rig.in[i].l = s;
      rig.in[i].r = -0.2f * s;
    }
    rig.Block();
  }
  float level = rig.mods.values().value[MOD_ENVELOPE];
  CHECK(level > 0.45f && level <= 0.5f);
  // Release: 100 ms time constant.
  memset(rig.in, 0, sizeof(rig.in));
  for (int b = 0; b < rig.BlocksFor(0.1f); ++b) {
    rig.Block();
  }
  level = rig.mods.values().value[MOD_ENVELOPE];
  test::Note("after one release time constant %.3f", level);
  CHECK(level > 0.15f && level < 0.22f);
  // +24 dB clamps a 0.5 peak to 1.
  rig.preset.envelope.gain = 65535;
  for (int i = 0; i < int(kBlockSize); ++i) {
    rig.in[i].l = 0.5f;
  }
  for (int b = 0; b < 10; ++b) {
    rig.Block();
  }
  CHECK(rig.mods.values().value[MOD_ENVELOPE] == 1.0f);
}

TEST(app_mods, notes_and_ccs) {
  ModRig rig;
  rig.mods.NoteOn(72);
  const ModValues& v = rig.Block();
  CHECK_NEAR(v.value[MOD_NOTE], 0.25f, 1e-6);
  CHECK(v.value[MOD_GATE] == 1.0f);
  rig.mods.NoteOn(48);
  rig.Block();
  CHECK_NEAR(v.value[MOD_NOTE], -0.25f, 1e-6);
  rig.mods.NoteOff(48);
  rig.Block();
  CHECK_NEAR(v.value[MOD_NOTE], 0.25f, 1e-6);  // back to the held one
  CHECK(v.value[MOD_GATE] == 1.0f);
  rig.mods.NoteOff(72);
  rig.Block();
  CHECK(v.value[MOD_GATE] == 0.0f);
  CHECK_NEAR(v.value[MOD_NOTE], 0.25f, 1e-6);  // the pitch stays
  for (int i = 0; i < 20; ++i) {
    rig.mods.NoteOn(40 + i);  // more than 16 held: the oldest go
  }
  rig.Block();
  CHECK_NEAR(v.value[MOD_NOTE], float(59 - 60) / 48.0f, 1e-6);
  rig.mods.AllNotesOff();
  rig.Block();
  CHECK(v.value[MOD_GATE] == 0.0f);
  rig.mods.SetCc(0, 0.25f);
  rig.mods.SetCc(1, 2.0f);
  rig.Block();
  CHECK(v.value[MOD_CC_A] == 0.25f);
  CHECK(v.value[MOD_CC_B] == 1.0f);
}

namespace {

struct MidiRig {
  test::TestMemory memory;
  Engine engine;
  ModSources mods;
  Tempo tempo;
  Settings settings;
  MidiIn midi;
  Preset preset;
  TempoState tempo_state;
  float cv[4];

  MidiRig() : memory(1u << 20, 200u << 10) {
    test::ResetHal();
    engine.Init(memory.memory());
    mods.Init();
    tempo.Init();
    InitSettings(&settings);
    midi.Init(&engine, &mods, &tempo, &settings);
    memset(&preset, 0, sizeof(preset));
    tempo_state = test::Tempo120();
    tempo_state.downbeat = false;
    for (int i = 0; i < 4; ++i) {
      cv[i] = 0.5022f;
    }
  }

  void Bytes(const uint8_t* bytes, int n) {
    for (int i = 0; i < n; ++i) {
      midi.ProcessByte(bytes[i], hal::Microseconds());
    }
  }

  const ModValues& Values() {
    mods.Process(preset, tempo_state, cv, NULL, kBlockSize);
    return mods.values();
  }
};

}  // namespace

TEST(app_midi, running_status_and_realtime_inside) {
  MidiRig rig;
  const uint8_t a[] = { 0x90, 60, 100, 0xf8, 72, 0xfe, 90 };
  rig.Bytes(a, sizeof(a));
  CHECK_NEAR(rig.Values().value[MOD_NOTE], 0.25f, 1e-6);
  CHECK(rig.Values().value[MOD_GATE] == 1.0f);
  // Running-status note-offs as velocity 0.
  const uint8_t b[] = { 72, 0, 60, 0 };
  rig.Bytes(b, sizeof(b));
  CHECK(rig.Values().value[MOD_GATE] == 0.0f);
  CHECK(rig.midi.messages() == 4);
  // Note off messages too.
  const uint8_t c[] = { 0x91, 50, 1, 0x81, 50, 64 };
  rig.Bytes(c, sizeof(c));
  CHECK(rig.Values().value[MOD_GATE] == 0.0f);
  CHECK_NEAR(rig.Values().value[MOD_NOTE], -10.0f / 48.0f, 1e-6);
}

TEST(app_midi, sysex_and_system_common_skipped) {
  MidiRig rig;
  const uint8_t a[] = { 0xb0, 1, 10,                  // CC A = 10
                        0xf0, 0x7e, 1, 64, 0xf8, 0x09, 0xf7,
                        1, 127,                         // no running status after SysEx
                        0xb0, 11, 127,                  // CC B
                        0xf2, 0x10, 0x20,               // song position: ignored
                        1, 50 };                        // ignored too
  rig.Bytes(a, sizeof(a));
  const ModValues& v = rig.Values();
  CHECK_NEAR(v.value[MOD_CC_A], 10.0f / 127.0f, 1e-6);
  CHECK(v.value[MOD_CC_B] == 1.0f);
  // A new status byte ends an unterminated SysEx.
  const uint8_t b[] = { 0xf0, 1, 2, 3, 0xb0, 1, 127 };
  rig.Bytes(b, sizeof(b));
  CHECK(rig.Values().value[MOD_CC_A] == 1.0f);
}

TEST(app_midi, channel_filter) {
  MidiRig rig;
  rig.settings.midi_channel = 3;
  const uint8_t wrong[] = { 0x90, 60, 100, 0xb1, 1, 127 };
  rig.Bytes(wrong, sizeof(wrong));
  CHECK(rig.Values().value[MOD_GATE] == 0.0f);
  CHECK(rig.Values().value[MOD_CC_A] == 0.0f);
  CHECK(rig.midi.messages() == 0);
  const uint8_t right[] = { 0x92, 60, 100, 0xb2, 1, 127 };
  rig.Bytes(right, sizeof(right));
  CHECK(rig.Values().value[MOD_GATE] == 1.0f);
  CHECK(rig.Values().value[MOD_CC_A] == 1.0f);
  // Omni takes any channel.
  rig.settings.midi_channel = 0;
  const uint8_t any[] = { 0x9f, 61, 100 };
  rig.Bytes(any, sizeof(any));
  CHECK_NEAR(rig.Values().value[MOD_NOTE], 1.0f / 48.0f, 1e-6);
  // The CC numbers come from the settings.
  rig.settings.cc_a = 74;
  const uint8_t cc[] = { 0xb0, 74, 64, 1, 0 };
  rig.Bytes(cc, sizeof(cc));
  CHECK_NEAR(rig.Values().value[MOD_CC_A], 64.0f / 127.0f, 1e-6);
}

TEST(app_midi, sends_wet_notes_off_program) {
  MidiRig rig;
  const uint8_t sends[] = { 0xb0, 80, 127, 83, 64, 81, 63 };
  rig.Bytes(sends, sizeof(sends));
  CHECK(rig.engine.preset().slot[SLOT_PITCH].send == 1);
  CHECK(rig.engine.preset().slot[SLOT_REVERB].send == 1);
  CHECK(rig.engine.preset().slot[SLOT_DELAY].send == 0);
  const uint8_t off[] = { 0xb0, 80, 0 };
  rig.Bytes(off, sizeof(off));
  CHECK(rig.engine.preset().slot[SLOT_PITCH].send == 0);
  const uint8_t wet[] = { 0xb0, 85, 127, 0xb0, 85, 0 };
  rig.Bytes(wet, 3);
  CHECK(rig.engine.preset().wet == 65535);
  rig.Bytes(wet + 3, 3);
  CHECK(rig.engine.preset().wet == 0);

  const uint8_t notes[] = { 0x90, 60, 100, 62, 100, 0xb0, 123, 0 };
  rig.Bytes(notes, sizeof(notes));
  CHECK(rig.Values().value[MOD_GATE] == 0.0f);
  const uint8_t notes2[] = { 0x90, 60, 100, 0xb0, 120, 0 };
  rig.Bytes(notes2, sizeof(notes2));
  CHECK(rig.Values().value[MOD_GATE] == 0.0f);

  int program = -1;
  CHECK(!rig.midi.TakeProgramChange(&program));
  const uint8_t pc[] = { 0xc0, 4, 9 };  // running status: the last one counts
  rig.Bytes(pc, sizeof(pc));
  CHECK(rig.midi.TakeProgramChange(&program));
  CHECK(program == 9);
  CHECK(!rig.midi.TakeProgramChange(&program));
}

TEST(app_midi, poll_and_clock) {
  MidiRig rig;
  // MIDI clock at 125 BPM for 2 s, through the board's byte queue, with
  // a START first and notes in between.
  const uint8_t start = 0xfa;
  test::PushMidi(&start, 1);
  const double period_us = 60.0e6 / (125.0 * 24.0);
  double next = double(test::NowUs());
  const double block_us = double(kBlockSize) * 1.0e6 / double(kSampleRate);
  int note = 0;
  for (double t = 0.0; t < 2.0e6; t += block_us) {
    test::AdvanceUs(uint64_t(block_us));
    while (next <= double(test::NowUs())) {
      uint64_t now = test::NowUs();
      test::Hal().time_us = uint64_t(next);
      test::PushMidi(0xf8);
      if (++note % 48 == 0) {
        const uint8_t n[] = { 0x90, uint8_t(50 + note / 48), 100 };
        test::PushMidi(n, 3);
      }
      test::Hal().time_us = now;
      next += period_us;
    }
    rig.midi.Poll();
    rig.tempo.Process(100.0f, 4, kBlockSize);
  }
  CHECK(test::MidiPending() == 0);
  CHECK(rig.tempo.source() == TEMPO_MIDI);
  CHECK_NEAR(rig.tempo.bpm(), 125.0f, 0.2f);
  CHECK(rig.Values().value[MOD_GATE] == 1.0f);
}
