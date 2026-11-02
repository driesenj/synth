// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the UI on the whole App, the fake board and the fake
// blocks. Scripted knob and button events for navigation, editing,
// modulation, sync, type changes, save / load, settings and the tools, the
// redraw economy, and a screenshot of every page and overlay in
// test/build/ui_screens/.

#include <math.h>
#include <string.h>
#include <sys/stat.h>

#include "check.h"
#include "display_fake.h"
#include "fake_registry.h"
#include "hal_fake.h"
#include "png_writer.h"
#include "test_support.h"

#include "app/app.h"
#include "gfx/canvas.h"
#include "ui/ui.h"

using namespace sidefx;

namespace {

float FakeCpu() { return 0.23f; }

// An App and a Ui on a frame buffer, run as main.cc runs them: audio
// blocks, then the App's and the UI's Poll and a flush of the dirty rows.
struct UiRig {
  test::TestMemory memory;
  App app;
  Canvas canvas;
  Ui ui;
  uint16_t* frame;
  Frame in[kBlockSize];
  Frame out[kBlockSize];
  uint32_t noise;
  float input_level;
  bool ok;
  int frames;  // passes of Run() that sent anything

  UiRig()
      : memory(2u << 20, 200u << 10), noise(7), input_level(0.3f), frames(0) {
    frame = new uint16_t[Canvas::kWidth * Canvas::kHeight];
    ok = app.Init(memory.memory());
    canvas.Init(frame);
    ui.Init(&app, &canvas, FakeCpu);
  }
  ~UiRig() { delete[] frame; }

  void Run(float seconds) {
    const double block_us = double(kBlockSize) * 1.0e6 / double(kSampleRate);
    const int blocks = int(seconds * kSampleRate / float(kBlockSize) + 0.5f);
    for (int b = 0; b < blocks; ++b) {
      for (size_t i = 0; i < kBlockSize; ++i) {
        in[i].l = input_level * test::Noise(&noise);
        in[i].r = input_level * test::Noise(&noise);
      }
      test::AdvanceUs(uint64_t(block_us));
      app.Process(in, out, kBlockSize);
      const uint32_t now = hal::Milliseconds();
      app.Poll(now);
      Event event;
      while (app.controls.PopEvent(&event)) {
        ui.OnEvent(event);
      }
      ui.Poll(now);
      // The canvas hands out one band of dirty rows at a time; main.cc's
      // loop goes round many times a block, so every band of a frame goes
      // out before the next frame is drawn.
      int y0, y1;
      bool sent = false;
      while (!hal::DisplayBusy() && canvas.TakeDirty(&y0, &y1)) {
        hal::DisplayFlush(frame, y0, y1);
        sent = true;
      }
      frames += sent ? 1 : 0;
    }
  }

  // One detent of a real EC11 on knob `knob` through the control interrupt
  // (Controls decodes it, with the encoder settings): +1 the way that
  // counts up with ENCODER on NORMAL.
  void Detent(int knob, int direction) {
    static const uint8_t kUp[4] = { 1, 3, 2, 0 };
    static const uint8_t kDown[4] = { 2, 3, 1, 0 };
    for (int i = 0; i < 4; ++i) {
      hal::ControlScan scan;
      memset(&scan, 0, sizeof(scan));
      scan.encoder[knob] = direction > 0 ? kUp[i] : kDown[i];
      scan.time_us = hal::Microseconds();
      app.OnControlScan(scan);
      test::AdvanceUs(1000);
    }
    Run(0.01f);
  }

  void Send(uint8_t type, uint8_t id, int delta, bool shift, bool handled) {
    Event e;
    e.type = type;
    e.id = id;
    e.delta = int8_t(delta);
    e.shift = shift;
    e.handled = handled;
    e.time_ms = hal::Milliseconds();
    e.time_us = hal::Microseconds();
    ui.OnEvent(e);
  }

  // A slow click (no acceleration), then a few blocks of audio and UI.
  void Turn(int knob, int delta, bool shift = false) {
    test::AdvanceMs(200);
    Send(EVENT_ENCODER, uint8_t(knob), delta, shift, false);
    Run(0.01f);
  }
  void FastTurn(int knob, int delta, int clicks) {
    for (int i = 0; i < clicks; ++i) {
      test::AdvanceMs(10);
      Send(EVENT_ENCODER, uint8_t(knob), delta, false, false);
    }
    Run(0.01f);
  }
  void Push(int knob, bool shift = false) {
    Send(EVENT_PRESS, uint8_t(hal::SWITCH_K1 + knob), 0, shift, false);
    Send(EVENT_RELEASE, uint8_t(hal::SWITCH_K1 + knob), 0, shift, false);
    Run(0.01f);
  }
  void ShiftDown() { Send(EVENT_PRESS, hal::SWITCH_SHIFT, 0, true, false); }
  void ShiftUp() { Send(EVENT_RELEASE, hal::SWITCH_SHIFT, 0, false, false); }
  void ShiftTap() {
    ShiftDown();
    ShiftUp();
    Run(0.01f);
  }
  // SHIFT + a send button: that slot's page (again: its next page).
  void OpenBlock(int slot) {
    ShiftDown();
    Send(EVENT_PRESS, uint8_t(slot), 0, true, false);
    Send(EVENT_RELEASE, uint8_t(slot), 0, true, false);
    ShiftUp();
    Run(0.01f);
  }
  // A send pressed alone: the interrupt toggles it, the UI hears about it.
  void SendButton(int slot) {
    app.engine.ToggleSend(slot);
    Send(EVENT_PRESS, uint8_t(slot), 0, false, true);
    Send(EVENT_RELEASE, uint8_t(slot), 0, false, true);
    Run(0.01f);
  }
  void Settle() {
    int guard = 0;
    do {
      Run(0.01f);
    } while (app.engine.loading() && ++guard < 100);
  }

  const Preset& preset() const { return app.engine.preset(); }

  // Lit pixels in a band of rows, from x on.
  int LitPixels(int y0, int y1, int x0 = 0) const {
    int n = 0;
    for (int y = y0; y <= y1; ++y) {
      for (int x = x0; x < Canvas::kWidth; ++x) {
        n += frame[y * Canvas::kWidth + x] != 0;
      }
    }
    return n;
  }
};

void MakeDirectory(const char* path) {
  mkdir(path, 0755);
}

// Every screenshot also goes onto a contact sheet, to look at many at once.
struct Sheet {
  static const int kColumns = 6;
  static const int kGutter = 8;
  static const int kMax = 36;
  uint16_t* pixels;
  int count;
  char names[kMax][32];

  Sheet() : count(0) {
    pixels = new uint16_t[size_t(Width()) * Height(kMax)];
    memset(pixels, 0x08, sizeof(uint16_t) * size_t(Width()) * Height(kMax));
  }
  ~Sheet() { delete[] pixels; }
  static int Width() { return kColumns * (Canvas::kWidth + kGutter) + kGutter; }
  static int Height(int n) {
    const int rows = (n + kColumns - 1) / kColumns;
    return rows * (Canvas::kHeight + kGutter) + kGutter;
  }
  void Add(const uint16_t* frame) {
    if (count >= kMax) {
      return;
    }
    const int col = count % kColumns;
    const int row = count / kColumns;
    const int x0 = kGutter + col * (Canvas::kWidth + kGutter);
    const int y0 = kGutter + row * (Canvas::kHeight + kGutter);
    for (int y = 0; y < Canvas::kHeight; ++y) {
      memcpy(&pixels[size_t(y0 + y) * Width() + x0], &frame[y * Canvas::kWidth],
             sizeof(uint16_t) * Canvas::kWidth);
    }
    ++count;
  }
};

void Shot(UiRig* rig, Sheet* sheet, const char* name, bool diagram = false) {
  rig->Run(0.08f);
  char path[128] = "test/build/ui_screens/";
  strncat(path, name, sizeof(path) - strlen(path) - 5);
  strcat(path, ".png");
  CHECK(test::WritePng(path, rig->frame, Canvas::kWidth, Canvas::kHeight,
                       Canvas::kWidth, 2));
  // What the panel shows (the flushed rows) is what the frame holds.
  CHECK(!memcmp(test::Display().panel, rig->frame,
                sizeof(uint16_t) * Canvas::kWidth * Canvas::kHeight));
  sheet->Add(rig->frame);
  test::Note("%s", path);
  // Nothing runs off the sides: the two outer columns stay black, except
  // in gap B when HOME's diagram has its IN and OUT lines there.
  int edge = 0;
  for (int y = 0; y < Canvas::kHeight; ++y) {
    if (diagram && y >= 127 && y < 185) {
      continue;
    }
    const uint16_t* row = &rig->frame[y * Canvas::kWidth];
    edge += (row[0] != 0) + (row[1] != 0) + (row[Canvas::kWidth - 2] != 0) +
            (row[Canvas::kWidth - 1] != 0);
  }
  if (!CHECK(edge == 0)) {
    test::Note("%s: %d pixels on the edges", name, edge);
  }
}

}  // namespace

TEST(ui, navigation) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  CHECK(rig->ok);
  rig->Run(0.1f);
  const int algorithm = rig->preset().algorithm;
  rig->Turn(1, 1);  // HOME: K2 = ALGORITHM
  CHECK(rig->preset().algorithm == algorithm + 1);
  rig->ShiftTap();  // MOD 1: K2 = LFO1 SHAPE
  const int shape = rig->preset().lfo[0].shape;
  rig->Turn(1, 1);
  CHECK(rig->preset().lfo[0].shape == shape + 1);
  rig->ShiftTap();  // MOD 2: K2 = RND SMOOTH
  const int smooth = rig->preset().random.smooth;
  rig->Turn(1, 1);
  CHECK(rig->preset().random.smooth != smooth);
  rig->ShiftTap();  // SENDS: K1 = PITCH's gate
  rig->Turn(0, 1);
  CHECK(rig->preset().slot[SLOT_PITCH].send_gate == MOD_CV1);
  rig->ShiftTap();  // SETUP 1: K1 = DRY
  const int dry = rig->app.settings.dry;
  rig->Turn(0, -1);
  CHECK(rig->app.settings.dry < dry);
  rig->ShiftTap();  // SETUP 2: K1 = MIDI CHANNEL
  const int channel = rig->app.settings.midi_channel;
  rig->Turn(0, 1);
  CHECK(rig->app.settings.midi_channel == channel + 1);
  rig->ShiftTap();  // SETUP 3: K1 = BRIGHTNESS
  const int brightness = rig->app.settings.brightness;
  rig->Turn(0, -1);
  CHECK(rig->app.settings.brightness == brightness - 1);
  rig->ShiftTap();  // back to HOME
  rig->Turn(1, 1);
  CHECK(rig->preset().algorithm == algorithm + 2);

  // SHIFT + DELAY: DELAY's first page; K1 its first value.
  rig->OpenBlock(SLOT_DELAY);
  const uint16_t time_l = rig->preset().slot[SLOT_DELAY].value[0];
  rig->Turn(0, 1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[0] != time_l);
  // Again: the second (last) page, MIX on K4.
  rig->OpenBlock(SLOT_DELAY);
  const uint16_t mix = rig->preset().slot[SLOT_DELAY].value[kMixValue];
  rig->Turn(3, -1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[kMixValue] < mix);
  // Again: wraps to the first page.
  rig->OpenBlock(SLOT_DELAY);
  const uint16_t feedback = rig->preset().slot[SLOT_DELAY].value[2];
  rig->Turn(2, 1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[2] > feedback);
  // Another slot's button opens that slot.
  rig->OpenBlock(SLOT_REVERB);
  const uint16_t decay = rig->preset().slot[SLOT_REVERB].value[0];
  rig->Turn(0, 1);
  CHECK(rig->preset().slot[SLOT_REVERB].value[0] > decay);
  // SHIFT alone from a block page: HOME.
  rig->ShiftTap();
  rig->Turn(1, -1);
  CHECK(rig->preset().algorithm == algorithm + 1);
  // A send pressed alone is the interrupt's business; the page stays.
  const bool pitch_on = rig->app.engine.send_active(SLOT_PITCH);
  rig->SendButton(SLOT_PITCH);
  CHECK(rig->app.engine.send_active(SLOT_PITCH) != pitch_on);
  rig->Turn(1, 1);
  CHECK(rig->preset().algorithm == algorithm + 2);
  // SHIFT held while a knob turns is not a tap: the page stays.
  rig->ShiftDown();
  rig->Turn(3, 1, true);
  rig->ShiftUp();
  rig->Run(0.01f);
  rig->Turn(1, -1);
  CHECK(rig->preset().algorithm == algorithm + 1);
  delete rig;
}

TEST(ui, editing_and_acceleration) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  rig->OpenBlock(SLOT_PITCH);  // DUAL SHIFT: PITCH A, 48 detents (semitones)
  const SlotPreset& pitch = rig->preset().slot[SLOT_PITCH];
  const float a = PresetValue(pitch.value[0]);
  rig->Turn(0, 1);
  CHECK_NEAR(PresetValue(pitch.value[0]) - a, 1.0 / 48.0, 1e-4);
  rig->Turn(0, -2);
  CHECK_NEAR(PresetValue(pitch.value[0]) - a, -1.0 / 48.0, 1e-4);
  // Values land on the detent grid: exact semitones.
  CHECK_NEAR(PresetValue(pitch.value[0]) * 48.0,
             floor(PresetValue(pitch.value[0]) * 48.0 + 0.5), 1e-3);
  // Fast clicks move more each.
  const float before = PresetValue(pitch.value[5]);  // WINDOW, 128 detents
  rig->OpenBlock(SLOT_PITCH);  // page 2: WINDOW is row 2
  rig->Turn(1, 1);
  const float slow = PresetValue(pitch.value[5]) - before;
  CHECK_NEAR(slow, 1.0 / 128.0, 1e-4);
  const float mid = PresetValue(pitch.value[5]);
  rig->FastTurn(1, -1, 6);
  const float fast = mid - PresetValue(pitch.value[5]);
  CHECK(fast > 6.0f * 4.0f / 128.0f);
  test::Note("6 fast clicks moved %.3f (slow click %.4f)", fast, slow);
  // SHIFT + turn stays exact, even fast.
  const float exact = PresetValue(pitch.value[5]);
  for (int i = 0; i < 4; ++i) {
    test::AdvanceMs(10);
    rig->Send(EVENT_ENCODER, 1, 1, true, false);
  }
  CHECK_NEAR(PresetValue(pitch.value[5]) - exact, 4.0 / 128.0, 1e-4);

  // Stepped values move one step per click, however fast.
  rig->OpenBlock(SLOT_TEXTURE);  // PHASER page 2: STAGES (6 steps) on K1
  rig->OpenBlock(SLOT_TEXTURE);
  const SlotPreset& texture = rig->preset().slot[SLOT_TEXTURE];
  const int stages = StepIndex(PresetValue(texture.value[4]), 6);
  rig->FastTurn(0, 1, 1);
  CHECK(StepIndex(PresetValue(texture.value[4]), 6) == stages + 1);
  rig->FastTurn(0, 1, 8);
  CHECK(StepIndex(PresetValue(texture.value[4]), 6) == 5);

  // A synced time steps one note value per click.
  rig->OpenBlock(SLOT_DELAY);  // DUAL DELAY: TIME L, synced by default
  const SlotPreset& delay = rig->preset().slot[SLOT_DELAY];
  CHECK(delay.sync_mask & 1);
  const int note = NoteValueIndex(PresetValue(delay.value[0]));
  rig->FastTurn(0, 1, 3);
  CHECK(NoteValueIndex(PresetValue(delay.value[0])) == note + 3);

  // HOME's tempo: whole BPM per click, SHIFT tenths, tap.
  rig->ShiftTap();
  Preset* live = rig->app.engine.mutable_preset();
  live->tempo = 1204;
  rig->Turn(3, 1);
  CHECK(rig->preset().tempo == 1210);
  rig->Turn(3, 3, true);
  CHECK(rig->preset().tempo == 1213);
  for (int i = 0; i < 4; ++i) {
    test::AdvanceMs(490);  // + the 10 ms Push() runs: 500 ms apart
    rig->Push(3);
  }
  CHECK(abs(int(rig->preset().tempo) - 1200) <= 2);
  // WET.
  const uint16_t wet = rig->preset().wet;
  rig->Turn(2, -1);
  CHECK_NEAR(PresetValue(rig->preset().wet), PresetValue(wet) - 0.01f, 1e-3);
  // Edits reach the live-state store: the App sees them.
  CHECK(rig->app.modified());
  delete rig;
}

TEST(ui, modulation_and_sync) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  rig->OpenBlock(SLOT_DELAY);
  rig->Push(2);  // FEEDBACK's modulation
  rig->Turn(1, MOD_LFO1);
  for (int i = 0; i < 4; ++i) {
    rig->Turn(2, 10);
  }
  const ModAssign& mod = rig->preset().slot[SLOT_DELAY].mod[2];
  CHECK(mod.source == MOD_LFO1);
  CHECK(mod.depth == 40);
  // K1 in the overlay still sets the value itself.
  const uint16_t feedback = rig->preset().slot[SLOT_DELAY].value[2];
  rig->Turn(0, 1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[2] > feedback);
  // Depth stops at +-100.
  rig->FastTurn(2, 1, 20);
  CHECK(mod.depth == 100);
  rig->FastTurn(2, -1, 40);
  CHECK(mod.depth == -100);
  rig->Turn(2, 50);
  CHECK(mod.depth == -50);
  // A push closes it; K3 is FEEDBACK again.
  rig->Push(0);
  const uint16_t feedback2 = rig->preset().slot[SLOT_DELAY].value[2];
  rig->Turn(2, -1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[2] < feedback2);
  CHECK(mod.depth == -50);
  // The engine moves the value with the LFO.
  rig->Run(1.0f);
  float lo = 1.0f;
  float hi = 0.0f;
  for (int i = 0; i < 100; ++i) {
    rig->Run(0.02f);
    const float v = rig->app.engine.value(SLOT_DELAY, 2);
    lo = v < lo ? v : lo;
    hi = v > hi ? v : hi;
  }
  CHECK(hi - lo > 0.05f);
  // SHIFT + push toggles sync on a PARAM_SYNC value only.
  CHECK(rig->preset().slot[SLOT_DELAY].sync_mask & 1);
  rig->Push(0, true);
  CHECK(!(rig->preset().slot[SLOT_DELAY].sync_mask & 1));
  rig->Push(0, true);
  CHECK(rig->preset().slot[SLOT_DELAY].sync_mask & 1);
  const uint16_t mask = rig->preset().slot[SLOT_DELAY].sync_mask;
  rig->Push(2, true);  // FEEDBACK: no sync
  CHECK(rig->preset().slot[SLOT_DELAY].sync_mask == mask);
  // HOME's WET has its own modulation.
  rig->ShiftTap();
  rig->Push(2);
  rig->Turn(1, MOD_ENVELOPE);
  rig->Turn(2, 25);
  CHECK(rig->preset().wet_mod.source == MOD_ENVELOPE);
  CHECK(rig->preset().wet_mod.depth == 25);
  rig->ShiftTap();  // SHIFT backs out of an overlay
  rig->Turn(1, 1);
  CHECK(rig->preset().wet_mod.source == MOD_ENVELOPE);  // K2 was ALGORITHM
  // LFO sync on MOD 1.
  rig->ShiftTap();
  const int sync = rig->preset().lfo[1].sync;
  rig->Push(2);
  CHECK(rig->preset().lfo[1].sync == !sync);
  delete rig;
}

TEST(ui, type_change_debounce) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  rig->OpenBlock(SLOT_DELAY);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 0);
  rig->ShiftDown();
  test::AdvanceMs(100);
  rig->Send(EVENT_ENCODER, 0, 1, true, false);
  rig->Run(0.1f);
  test::AdvanceMs(50);
  rig->Send(EVENT_ENCODER, 0, 1, true, false);
  rig->Run(0.1f);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 0);  // still turning
  test::AdvanceMs(50);
  rig->Send(EVENT_ENCODER, 0, 1, true, false);
  rig->ShiftUp();
  rig->Run(0.2f);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 0);
  rig->Run(0.1f);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 3);  // TAPE DELAY
  rig->Settle();
  CHECK(!rig->app.engine.changing(SLOT_DELAY));
  CHECK(rig->preset().slot[SLOT_DELAY].type == 3);
  // Turning K1 while a type is pending changes nothing else.
  // Backwards wraps round the list.
  rig->ShiftDown();
  test::AdvanceMs(100);
  rig->Send(EVENT_ENCODER, 0, -4, true, false);
  rig->ShiftUp();
  rig->Run(0.4f);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 5);  // 3 - 4 + 6
  // The new type's values are its defaults; K1 edits them.
  const uint16_t v0 = rig->preset().slot[SLOT_DELAY].value[1];
  rig->Turn(1, 1);
  CHECK(rig->preset().slot[SLOT_DELAY].value[1] > v0);
  // main.cc reads the clock before it pops events, so an event can be
  // stamped a little after the `now` Poll() gets: it still waits.
  rig->ShiftDown();
  Event e;
  e.type = EVENT_ENCODER;
  e.id = 0;
  e.delta = 1;
  e.shift = true;
  e.handled = false;
  e.time_ms = hal::Milliseconds() + 2;
  e.time_us = hal::Microseconds() + 2000;
  rig->ui.OnEvent(e);
  rig->ui.Poll(hal::Milliseconds());
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 5);
  rig->ShiftUp();
  rig->Run(0.4f);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 0);  // wrapped round
  delete rig;
}

TEST(ui, save_and_load) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  CHECK(rig->app.current_preset() == 0);
  char first[16];
  strcpy(first, rig->preset().name);
  char untouched[16];
  strcpy(untouched, rig->app.bank.name(5));
  // The name the edits below make: first letter one back, second three on,
  // in the editor's letters.
  const char* letters = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.#&+/";
  const int num_letters = int(strlen(letters));
  char expected[16];
  strcpy(expected, first);
  const int c0 = int(strchr(letters, expected[0]) - letters);
  const int c1 = int(strchr(letters, expected[1]) - letters);
  expected[0] = letters[(c0 + num_letters - 1) % num_letters];
  expected[1] = letters[(c1 + 3) % num_letters];

  rig->Turn(3, 4);  // an edit
  CHECK(rig->app.modified());
  rig->Push(0, true);  // SHIFT + push K1: save
  for (int i = 0; i < 4; ++i) {
    rig->Turn(0, 1);  // slot 5 (index 4)
  }
  rig->Turn(2, -1);   // first letter
  rig->Turn(1, 1);    // cursor to the second letter
  rig->Turn(2, 3);
  rig->Push(3);
  test::Note("saved as '%s' (was '%s')", rig->app.bank.name(4), first);
  CHECK(rig->app.current_preset() == 4);
  CHECK(!strcmp(rig->app.bank.name(4), expected));
  CHECK(!rig->app.modified());
  CHECK(!strcmp(rig->preset().name, expected));
  // SHIFT cancels a save.
  rig->Push(0, true);
  rig->Turn(0, 1);
  rig->ShiftTap();
  CHECK(!strcmp(rig->app.bank.name(5), untouched));
  CHECK(rig->app.current_preset() == 4);
  // Browse back to slot 1 and load it.
  rig->Turn(0, -4);
  CHECK(rig->app.current_preset() == 4);  // browsing alone loads nothing
  rig->Push(0);
  rig->Settle();
  CHECK(rig->app.current_preset() == 0);
  CHECK(!strcmp(rig->preset().name, first));
  // Browsing gives up after a while: a push then loads nothing.
  rig->Turn(0, 4);
  rig->Run(9.0f);
  rig->Push(0);
  rig->Settle();
  CHECK(rig->app.current_preset() == 0);
  delete rig;
}

TEST(ui, settings_and_tools) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  for (int i = 0; i < 4; ++i) {
    rig->ShiftTap();  // SETUP 1
  }
  rig->Turn(1, -6);
  CHECK(rig->app.settings.input_gain == -30);
  rig->Turn(2, 2);
  CHECK(rig->app.settings.output_gain == 10);
  rig->Turn(3, 1);
  CHECK(rig->app.settings.invert_output == 1);
  rig->ShiftTap();  // SETUP 2
  rig->Turn(1, 2);
  CHECK(rig->app.settings.cc_a == 3);
  rig->Turn(3, 1);
  CHECK(rig->app.settings.clock_ppqn == 3);
  rig->ShiftTap();  // SETUP 3
  rig->Turn(0, -3);
  CHECK(rig->app.settings.brightness == 5);
  CHECK_NEAR(test::Display().backlight, 0.5f, 1e-6);
  rig->Turn(1, 1);
  CHECK(test::Display().flip);
  rig->Turn(1, -1);
  CHECK(!test::Display().flip);
  // ENCODER takes over once K3 rests.
  rig->Turn(2, 3);
  CHECK(rig->app.settings.encoder_steps == 4);
  rig->Run(1.1f);
  CHECK(rig->app.settings.encoder_steps == 2);
  CHECK(rig->app.settings.encoder_reverse == 1);
  rig->Turn(2, -2);
  rig->Run(1.1f);
  CHECK(rig->app.settings.encoder_steps == 4);
  CHECK(rig->app.settings.encoder_reverse == 1);

  // CV ZERO: every input's raw reading at 0 V becomes its offset.
  for (int ch = 0; ch < 4; ++ch) {
    test::Hal().cv[ch] = 0.49f + 0.01f * float(ch);
  }
  rig->Push(3);
  rig->Run(0.05f);
  rig->Push(1);
  for (int ch = 0; ch < 4; ++ch) {
    CHECK_NEAR(rig->app.settings.calibration.offset[ch],
               0.49f + 0.01f * float(ch), 1e-4);
  }
  rig->Run(0.05f);
  CHECK_NEAR(rig->app.mods.cv_volts(2), 0.0f, 1e-3);
  // An input far off 0 V keeps its offset.
  test::SetCvVolts(1, 5.0f);
  rig->Push(3);
  rig->Run(0.05f);
  rig->Push(0);
  CHECK_NEAR(rig->app.settings.calibration.offset[1], 0.50f, 1e-4);

  // RESTORE: NO backs out, YES rewrites the bank.
  rig->Turn(3, 1);
  rig->Push(3);
  rig->Push(3);  // NO
  const int erases = test::Hal().flash_erases;
  CHECK(erases == test::Hal().flash_erases);
  rig->Push(3);
  rig->Turn(3, 1);
  rig->Push(3);  // YES
  CHECK(test::Hal().flash_erases > erases);
  rig->Settle();
  CHECK(rig->app.current_preset() == 0);
  CHECK(!strcmp(rig->preset().name, rig->app.bank.name(0)));
  delete rig;
}

// DISPLAY FLIP turns the whole picture at once, not only the rows that
// change: the glass shows the frame turned by 180 degrees (and straight
// again after turning it off).
TEST(ui, display_flip_turns_whole_picture) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->input_level = 0.0f;
  rig->Run(0.1f);
  for (int i = 0; i < 6; ++i) {
    rig->ShiftTap();  // SETUP 3
  }
  rig->Run(0.1f);
  const int n = Canvas::kWidth * Canvas::kHeight;
  CHECK(!memcmp(test::Display().panel, rig->frame, sizeof(uint16_t) * n));
  rig->Turn(1, 1);
  rig->Run(0.1f);
  CHECK(test::Display().flip);
  int wrong = 0;
  for (int i = 0; i < n; ++i) {
    wrong += test::Display().panel[n - 1 - i] != rig->frame[i];
  }
  if (!CHECK(wrong == 0)) {
    test::Note("flip on: %d of %d pixels not turned", wrong, n);
  }
  rig->Turn(1, -1);
  rig->Run(0.1f);
  CHECK(!test::Display().flip);
  CHECK(!memcmp(test::Display().panel, rig->frame, sizeof(uint16_t) * n));
  delete rig;
}

TEST(ui, redraw_economy) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->input_level = 0.0f;
  rig->Run(0.5f);
  for (int i = 0; i < 4; ++i) {
    rig->ShiftTap();  // SETUP 1: nothing live on it
  }
  rig->Run(0.3f);
  const int flushes = test::Display().flushes;
  rig->Run(1.0f);
  CHECK(test::Display().flushes == flushes);  // nothing changed, nothing sent
  // One edit redraws one row: a strip, not the frame.
  rig->Turn(0, -1);
  rig->Run(0.1f);
  CHECK(test::Display().flushes > flushes);
  CHECK(test::Display().last_y0 >= 0 &&
        test::Display().last_y1 - test::Display().last_y0 < 40);
  // Never more than ~30 frames a second, even with everything moving.
  rig->ShiftTap();
  rig->ShiftTap();
  rig->ShiftTap();
  rig->ShiftTap();  // HOME
  rig->input_level = 0.5f;
  const int before = rig->frames;
  rig->Run(1.0f);
  const int frames = rig->frames - before;
  test::Note("HOME with audio: %d frames in 1 s", frames);
  CHECK(frames <= 31);
  delete rig;
}

// HOME with audio and a modulated WET changes small things all down the
// screen every frame (the meters, the slot levels, WET's tick, the beat):
// only those bands go out, not one span from the first to the last.
TEST(ui, flushes_only_the_changed_bands) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  Preset* p = rig->app.engine.mutable_preset();
  p->wet_mod.source = MOD_LFO1;
  p->wet_mod.depth = 50;
  p->lfo[0].rate = PresetRaw(0.8f);
  for (int slot = 0; slot < NUM_SLOTS; ++slot) {
    rig->app.engine.SetSend(slot, true);
  }
  rig->input_level = 0.5f;
  rig->Run(0.5f);
  const int frames = rig->frames;
  const int flushes = test::Display().flushes;
  const int rows = test::Display().rows_sent;
  rig->Run(2.0f);
  const int n = rig->frames - frames;
  const float rows_per_frame =
      float(test::Display().rows_sent - rows) / float(n > 0 ? n : 1);
  test::Note("HOME, 2 s: %d frames in %d flushes, %.1f rows a frame "
             "(%.1f ms of SPI at 12.5 MHz)", n,
             test::Display().flushes - flushes, rows_per_frame,
             rows_per_frame * 0.218f);
  CHECK(n > 20);
  CHECK(rows_per_frame < 100.0f);
  // And what the panel shows is still the frame.
  CHECK(!memcmp(test::Display().panel, rig->frame,
                sizeof(uint16_t) * Canvas::kWidth * Canvas::kHeight));
  delete rig;
}

TEST(ui, rows_line_up_with_knobs) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.2f);
  const int knob_y[4] = { 14, 111, 209, 306 };
  for (int page = 0; page < 7; ++page) {
    for (int row = 0; row < 4; ++row) {
      // Each row's value (right half of the screen) lies within ~30 px of
      // its knob.
      const int y0 = knob_y[row] - 26 < 0 ? 0 : knob_y[row] - 26;
      const int y1 = knob_y[row] + 12 > 319 ? 319 : knob_y[row] + 12;
      CHECK(rig->LitPixels(y0, y1, 100) > 20);
    }
    rig->ShiftTap();
  }
  delete rig;
}

TEST(ui, messages) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.1f);
  uint16_t before[Canvas::kWidth * 10];
  memcpy(before, &rig->frame[150 * Canvas::kWidth], sizeof(before));
  rig->ui.ShowMessage("HELLO", 500);
  rig->Run(0.1f);
  CHECK(memcmp(before, &rig->frame[150 * Canvas::kWidth], sizeof(before)) != 0);
  rig->Run(0.6f);
  // Gone: the diagram is back (the message box rows match the page again).
  rig->input_level = 0.0f;
  rig->Run(0.1f);
  int gold = 0;
  for (int x = 10; x < 160; ++x) {
    gold += rig->frame[134 * Canvas::kWidth + x] == Rgb(210, 162, 76);
  }
  CHECK(gold < 10);
  delete rig;
}

TEST(ui, screenshots) {
  test::ResetHal();
  test::ResetDisplay();
  MakeDirectory("test/build");
  MakeDirectory("test/build/ui_screens");
  Sheet* sheet = new Sheet();
  UiRig* rig = new UiRig();
  // A playing state: LFO on DELAY's FEEDBACK, RANDOM on PITCH B, PITCH on.
  Preset* p = rig->app.engine.mutable_preset();
  p->slot[SLOT_DELAY].mod[2].source = MOD_LFO1;
  p->slot[SLOT_DELAY].mod[2].depth = 40;
  p->slot[SLOT_PITCH].mod[1].source = MOD_RANDOM;
  p->slot[SLOT_PITCH].mod[1].depth = -25;
  p->lfo[0].rate = PresetRaw(0.55f);
  p->tempo = 1240;
  rig->SendButton(SLOT_PITCH);
  rig->Run(0.6f);
  Shot(rig, sheet, "01_home", true);
  rig->Turn(0, 3);
  Shot(rig, sheet, "02_home_browse", true);
  rig->Push(0, true);
  rig->Turn(0, 2);
  rig->Turn(1, 3);
  Shot(rig, sheet, "03_save");
  rig->ShiftTap();
  rig->Push(2);
  rig->Turn(1, MOD_ENVELOPE);
  rig->Turn(2, 60);
  Shot(rig, sheet, "04_wet_mod");
  rig->ShiftTap();
  for (int page = 1; page < 7; ++page) {
    static const char* const kNames[7] = {
      "", "05_mod1", "06_mod2", "07_sends", "08_setup1", "09_setup2",
      "10_setup3",
    };
    rig->ShiftTap();
    if (page == 2) {
      rig->Push(3);  // ENV GAIN instead of RELEASE
    }
    Shot(rig, sheet, kNames[page]);
  }
  rig->Push(3);
  Shot(rig, sheet, "11_cv_zero");
  rig->ShiftTap();
  rig->Turn(3, 1);
  rig->Push(3);
  rig->Turn(3, 1);
  Shot(rig, sheet, "12_restore");
  rig->ShiftTap();
  rig->ShiftTap();  // HOME
  rig->OpenBlock(SLOT_PITCH);
  Shot(rig, sheet, "13_pitch_p1");
  rig->OpenBlock(SLOT_PITCH);
  Shot(rig, sheet, "14_pitch_p2");
  rig->OpenBlock(SLOT_DELAY);
  Shot(rig, sheet, "15_delay_p1");
  rig->Push(2);
  Shot(rig, sheet, "16_delay_feedback_mod");
  rig->Push(2);
  rig->ShiftDown();
  rig->Run(0.05f);
  Shot(rig, sheet, "17_delay_shift");
  test::AdvanceMs(10);
  rig->Send(EVENT_ENCODER, 0, 3, true, false);
  Shot(rig, sheet, "18_delay_type_pending");
  rig->ShiftUp();
  rig->Run(0.4f);
  rig->Settle();
  Shot(rig, sheet, "19_tape_delay");
  rig->OpenBlock(SLOT_TEXTURE);
  rig->ShiftDown();
  test::AdvanceMs(10);
  rig->Send(EVENT_ENCODER, 0, 4, true, false);  // BEADSY: 3 pages
  rig->ShiftUp();
  rig->Run(0.4f);
  rig->Settle();
  Shot(rig, sheet, "20_beadsy_p1");
  rig->OpenBlock(SLOT_TEXTURE);
  rig->OpenBlock(SLOT_TEXTURE);
  Shot(rig, sheet, "21_beadsy_p3");
  rig->OpenBlock(SLOT_REVERB);
  Shot(rig, sheet, "22_reverb");
  rig->ShiftTap();
  rig->ui.ShowMessage("SAVED 12", 2000);
  Shot(rig, sheet, "23_message", true);
  rig->Run(2.0f);
  for (int a = 0; a < NUM_ALGORITHMS; ++a) {
    rig->app.engine.mutable_preset()->algorithm = uint8_t(a);
    rig->Run(0.05f);
    char name[24] = "algorithm_1";
    name[10] = char('1' + a);
    Shot(rig, sheet, name, true);
  }
  CHECK(test::WritePng("test/build/ui_screens/sheet.png", sheet->pixels,
                       Sheet::Width(), Sheet::Height(sheet->count),
                       Sheet::Width(), 1));
  delete rig;
  delete sheet;
}

TEST(ui, follows_preset_loads) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  // TEXTURE on BEADSY (11 values, 3 pages), its third page, and the
  // modulation of its tenth value open.
  rig->OpenBlock(SLOT_TEXTURE);
  rig->ShiftDown();
  test::AdvanceMs(10);
  rig->Send(EVENT_ENCODER, 0, 4 - rig->app.engine.block_type(SLOT_TEXTURE),
            true, false);
  rig->ShiftUp();
  rig->Run(0.4f);
  rig->Settle();
  CHECK(rig->app.engine.block_type(SLOT_TEXTURE) == 4);
  rig->OpenBlock(SLOT_TEXTURE);
  rig->OpenBlock(SLOT_TEXTURE);
  rig->Push(1);  // P RAND, value 9
  rig->Turn(1, MOD_LFO2);
  CHECK(rig->preset().slot[SLOT_TEXTURE].mod[9].source == MOD_LFO2);
  // A program change brings INIT: TEXTURE back on PHASER (7 values).
  Preset init;
  InitPreset(&init);
  rig->app.engine.LoadPreset(init);
  rig->Settle();
  rig->Run(0.1f);
  CHECK(rig->app.engine.block_type(SLOT_TEXTURE) == 0);
  // The overlay closed and the page is a real one: K1 edits RATE.
  const uint16_t rate = rig->preset().slot[SLOT_TEXTURE].value[0];
  rig->Turn(0, 1);
  CHECK(rig->preset().slot[SLOT_TEXTURE].value[0] > rate);
  delete rig;
}

// SETUP 3's ENCODER row changes how K3 itself counts: picked first, applied
// once the knob rests, so turning one way walks the whole list (it used to
// flip between NORMAL and REVERSED, the reverse taking effect at once).
TEST(ui, encoder_mode_walks_the_list) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  for (int i = 0; i < 6; ++i) {
    rig->ShiftTap();  // SETUP 3
  }
  for (int i = 0; i < 3; ++i) {
    test::AdvanceMs(150);
    rig->Detent(2, +1);
  }
  // Still turning: K3 counts as before.
  CHECK(rig->app.settings.encoder_steps == 4);
  CHECK(rig->app.settings.encoder_reverse == 0);
  rig->Run(1.2f);
  test::Note("three detents up: steps %d, reverse %d",
             rig->app.settings.encoder_steps,
             rig->app.settings.encoder_reverse);
  CHECK(rig->app.settings.encoder_steps == 2);  // HALF REV
  CHECK(rig->app.settings.encoder_reverse == 1);
  // HALF REV on a full-cycle EC11: a detent counts two, the other way.
  // Still one way round, back to NORMAL.
  for (int i = 0; i < 2; ++i) {
    test::AdvanceMs(150);
    rig->Detent(2, +1);
  }
  rig->Run(1.2f);
  CHECK(rig->app.settings.encoder_steps == 4);
  CHECK(rig->app.settings.encoder_reverse == 0);
  // Leaving the page applies a pick at once.
  test::AdvanceMs(150);
  rig->Detent(2, +1);
  rig->ShiftTap();
  CHECK(rig->app.settings.encoder_reverse == 1);
  delete rig;
}

// A preset load (here a MIDI program change) that lands while a SHIFT + K1
// type change still waits keeps the loaded slot: the old choice's defaults
// do not replace it.
TEST(ui, preset_load_drops_a_pending_type) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  Preset p;
  InitPreset(&p);
  InitSlot(&p, SLOT_DELAY, 2);
  p.slot[SLOT_DELAY].value[0] = 12345;
  CHECK(rig->app.bank.Save(5, p));
  rig->OpenBlock(SLOT_DELAY);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 0);
  rig->ShiftDown();
  test::AdvanceMs(10);
  rig->Send(EVENT_ENCODER, 0, 1, true, false);  // type 1, pending
  rig->ShiftUp();
  rig->Run(0.05f);
  const uint8_t program_change[2] = { 0xc0, 5 };
  test::PushMidi(program_change, 2);
  rig->Run(0.5f);
  rig->Settle();
  rig->Run(0.3f);
  CHECK(rig->app.current_preset() == 5);
  CHECK(rig->app.engine.block_type(SLOT_DELAY) == 2);
  CHECK(rig->preset().slot[SLOT_DELAY].type == 2);
  CHECK(rig->preset().slot[SLOT_DELAY].value[0] == 12345);
  delete rig;
}

// Every block page title stays on the screen (GRANULATOR and WAVESHAPER
// are wider than the large font allows).
TEST(ui, block_titles_fit) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->input_level = 0.0f;
  rig->Run(0.05f);
  for (int slot = 0; slot < NUM_SLOTS; ++slot) {
    for (int type = 0; type < NumBlockTypes(slot); ++type) {
      rig->app.engine.SetBlockType(slot, type);
      rig->Settle();
      rig->OpenBlock(slot);
      rig->Run(0.1f);
      int edge = 0;
      for (int y = 40; y < 87; ++y) {
        const uint16_t* row = &rig->frame[y * Canvas::kWidth];
        edge += (row[0] != 0) + (row[1] != 0) +
                (row[Canvas::kWidth - 2] != 0) + (row[Canvas::kWidth - 1] != 0);
      }
      if (!CHECK(edge == 0)) {
        test::Note("%s: %d title pixels on the edges",
                   GetBlock(slot, type)->info().name, edge);
      }
      rig->ShiftTap();  // HOME
    }
  }
  delete rig;
}

// HOME's diagram: every block's short name fits its box with a pixel to
// spare on each side, in every algorithm (SERIAL's four columns gave 34 px
// boxes, too narrow for COMBS or MODAL).
TEST(ui, diagram_names_fit) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->input_level = 0.0f;
  for (int slot = 0; slot < NUM_SLOTS; ++slot) {
    rig->app.engine.SetSend(slot, true);
  }
  rig->Run(0.3f);
  // An open box's outline is drawn in the slot's colour itself.
  const Color kOutline[NUM_SLOTS] = {
    Rgb(64, 204, 224), Rgb(244, 164, 52), Rgb(228, 84, 196),
    Rgb(150, 118, 248),
  };
  for (int a = 0; a < NUM_ALGORITHMS; ++a) {
    rig->app.engine.mutable_preset()->algorithm = uint8_t(a);
    rig->Settle();
    rig->Run(0.1f);
    for (int slot = 0; slot < NUM_SLOTS; ++slot) {
      int box_w = 0;
      for (int y = 127; y < 185; ++y) {
        int lo = Canvas::kWidth;
        int hi = -1;
        for (int x = 0; x < Canvas::kWidth; ++x) {
          if (rig->frame[y * Canvas::kWidth + x] == kOutline[slot]) {
            lo = x < lo ? x : lo;
            hi = x;
          }
        }
        box_w = hi - lo + 1 > box_w ? hi - lo + 1 : box_w;
      }
      int widest = 0;
      for (int type = 0; type < NumBlockTypes(slot); ++type) {
        const int w = rig->canvas.TextWidth(
            GetBlock(slot, type)->info().short_name, kFontSmall);
        widest = w > widest ? w : widest;
      }
      if (!CHECK(box_w > 0 && widest + 2 <= box_w - 2)) {
        test::Note("algorithm %d, %s: box %d px, widest name %d px", a + 1,
                   kSlotNames[slot], box_w, widest);
      }
    }
  }
  delete rig;
}

// A block page's gap B: the send line with a gate ("SEND OFF . GATE NOTE")
// and the slot's CPU never share pixels.
TEST(ui, block_send_line_clears_cpu) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->input_level = 0.0f;
  rig->Run(0.05f);
  rig->OpenBlock(SLOT_DELAY);
  rig->Run(0.2f);
  const int y0 = 127;
  const int y1 = 185;
  const int w = Canvas::kWidth;
  static uint16_t reference[Canvas::kWidth * (185 - 127)];
  memcpy(reference, &rig->frame[y0 * w], sizeof(reference));
  // The CPU text: what is lit right of x = 100 on the rows without the
  // level meter (lit at x = 80).
  int cx0 = w, cx1 = -1, cy0 = y1, cy1 = -1;
  for (int y = 0; y < y1 - y0; ++y) {
    if (reference[y * w + 80]) {
      continue;
    }
    for (int x = 100; x < w; ++x) {
      if (reference[y * w + x]) {
        cx0 = x < cx0 ? x : cx0;
        cx1 = x > cx1 ? x : cx1;
        cy0 = y < cy0 ? y : cy0;
        cy1 = y > cy1 ? y : cy1;
      }
    }
  }
  CHECK(cx1 > cx0 && cy1 > cy0);
  for (int gate = 1; gate < NUM_MOD_SOURCES; ++gate) {
    rig->app.engine.mutable_preset()->slot[SLOT_DELAY].send_gate =
        uint8_t(gate);
    rig->Run(0.1f);
    int overlap = 0;
    for (int y = cy0 - 1; y <= cy1 + 1; ++y) {
      for (int x = cx0 - 1; x <= cx1 + 1 && x < w; ++x) {
        overlap += rig->frame[(y0 + y) * w + x] != reference[y * w + x];
      }
    }
    if (!CHECK(overlap == 0)) {
      test::Note("gate %s: %d pixels of the CPU text changed",
                 kModSourceNames[gate], overlap);
    }
  }
  delete rig;
}

// Tap tempo counts from when the button was scanned: a main loop held up
// between the scan and the event (a flash write, a long redraw) does not
// skew the tempo.
TEST(ui, tap_tempo_uses_the_scan_time) {
  test::ResetHal();
  test::ResetDisplay();
  UiRig* rig = new UiRig();
  rig->Run(0.05f);
  const uint32_t stall_ms[5] = { 0, 180, 20, 240, 60 };
  uint32_t last_stall = 0;
  for (int i = 0; i < 5; ++i) {
    test::AdvanceMs(500 - last_stall);  // the scans are 500 ms apart
    Event e;
    e.type = EVENT_PRESS;
    e.id = uint8_t(hal::SWITCH_K4);
    e.delta = 0;
    e.shift = false;
    e.handled = false;
    e.time_ms = hal::Milliseconds();
    e.time_us = hal::Microseconds();
    test::AdvanceMs(stall_ms[i]);       // the main loop gets to it late
    rig->ui.OnEvent(e);
    e.type = EVENT_RELEASE;
    rig->ui.OnEvent(e);
    last_stall = stall_ms[i];
  }
  rig->Run(0.05f);
  test::Note("tempo %.1f BPM from taps 500 ms apart",
             rig->preset().tempo * 0.1);
  CHECK(abs(int(rig->preset().tempo) - 1200) <= 2);
  delete rig;
}
