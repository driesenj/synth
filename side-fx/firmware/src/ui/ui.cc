// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the screen and what the knobs and buttons do with it (see
// ui.h for the pages).
//
// Layout. The 170 x 320 screen sits left of the four encoders, so every
// page is four knob rows at the knobs' heights with three gaps between
// them. A row is a small grey label line (with the modulation source or a
// state on its right), the value right-aligned towards its knob in a big
// font, and a thin value bar. The gaps hold the title (gap A, the same
// place on every page) and whatever the page shows live: HOME's meters,
// algorithm diagram and slot list, a block's level, the LFOs' motion.
// The background stays black (an IPS panel glows where it is lit); gold is
// the house accent, each slot keeps its colour everywhere, SHIFT is red
// and modulation is green.
//
// Redrawing. Each region builds a description of what it would draw and
// hashes it; only regions whose hash changed are cleared and drawn, at
// most every kFrameMs and never while the display is still sending, so
// the SPI link (about 0.22 ms a row) mostly carries thin strips.

#include "ui/ui.h"

#include <math.h>
#include <string.h>

#include "engine/algorithm.h"
#include "engine/modulation.h"
#include "engine/params.h"
#include "engine/registry.h"
#include "gfx/font.h"

namespace sidefx {

namespace {

// --- geometry ---------------------------------------------------------------

const int kWidth = Canvas::kWidth;
const int kMargin = 4;
const int kRight = kWidth - 4;

// The knobs' centres beside the screen, K1 at the top (the panel drawing's
// zigzag), and the rows that line up with them: each row's value sits
// within ~10 px of its knob, pulled inwards at the two ends so the rows
// fit on the screen.
const int kRowHeight = 37;
constexpr int RowTop(int knob_y) {
  return knob_y - 22 < 2 ? 2 : (knob_y - 22 > 280 ? 280 : knob_y - 22);
}
constexpr int kKnobRowY[kRowsPerPage] = { 14, 111, 209, 306 };
constexpr int kRowTop[kRowsPerPage] = {
  RowTop(kKnobRowY[0]), RowTop(kKnobRowY[1]), RowTop(kKnobRowY[2]),
  RowTop(kKnobRowY[3]),
};
// Inside a row: the label line at the top, the value's baseline, the bar.
const int kValueBaseline = 30;
const int kBarOffset = 32;
const int kBarHeight = 3;
const int kBarX = kMargin;
const int kBarWidth = kRight - kMargin;

// The gaps between the rows.
const int kGapTop[3] = { 40, 127, 225 };
const int kGapBottom[3] = { 87, 185, 278 };  // exclusive

// HOME's IN and OUT meters.
const int kInMeterX = 22;
const int kOutLabelX = 90;
const int kMeterWidth = 54;

// The message box, over gap B.
const int kMessageY = 134;
const int kMessageHeight = 44;

// --- timing -----------------------------------------------------------------

const uint32_t kFrameMs = 33;            // ~30 fps at most
const uint32_t kTypeDebounceMs = 250;    // SHIFT + K1 rests, then it changes
const uint32_t kEncoderModeMs = 1000;    // SETUP 3's ENCODER row rests
const uint32_t kBrowseTimeoutMs = 8000;  // HOME's K1 browsing gives up
const uint32_t kCpuRefreshMs = 500;
const uint32_t kMidiDotMs = 120;
const uint32_t kMessageMs = 1500;

// --- colours ----------------------------------------------------------------

// Rgb() as a constant expression, so the palette needs no constructor.
constexpr Color Rgb565(int r, int g, int b) {
  return Color((((((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3)) >> 8) |
                ((((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3)) << 8)) &
               0xffff);
}

const Color kBlack = 0;
const Color kWhite = Rgb565(236, 234, 228);
const Color kGrey = Rgb565(150, 146, 138);
const Color kDim = Rgb565(92, 90, 86);
const Color kTrack = Rgb565(44, 42, 40);
const Color kGold = Rgb565(210, 162, 76);
const Color kGoldDark = Rgb565(34, 26, 12);
const Color kRed = Rgb565(228, 64, 56);
const Color kModColor = Rgb565(112, 214, 140);
const Color kSlotColor[NUM_SLOTS] = {
  Rgb565(64, 204, 224),   // PITCH cyan
  Rgb565(244, 164, 52),   // DELAY amber
  Rgb565(228, 84, 196),   // TEXTURE magenta
  Rgb565(150, 118, 248),  // REVERB violet
};

// --- text -------------------------------------------------------------------

void Append(char* text, size_t size, const char* source) {
  size_t n = strlen(text);
  while (*source && n + 1 < size) {
    text[n++] = *source++;
  }
  text[n] = '\0';
}

void AppendNumber(char* text, size_t size, float value, int decimals,
                  bool plus_sign, const char* suffix) {
  char number[16];
  FormatNumber(number, sizeof(number), value, decimals, plus_sign, suffix);
  Append(text, size, number);
}

// "07": bank slots are shown 1..64 with two digits.
void FormatSlot(char* text, size_t size, int index) {
  const int n = index + 1;
  char digits[3] = { char('0' + (n / 10) % 10), char('0' + n % 10), '\0' };
  CopyText(text, size, digits);
}

// The letters a preset name can use, space first.
const char kNameChars[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.#&+/";
const int kNumNameChars = sizeof(kNameChars) - 1;

int NameCharIndex(char c) {
  if (c >= 'a' && c <= 'z') {
    c = char(c - 'a' + 'A');
  }
  for (int i = 0; i < kNumNameChars; ++i) {
    if (kNameChars[i] == c) {
      return i;
    }
  }
  return 0;
}

const char* const kSourceLabels[3] = { "INT", "CLOCK", "MIDI" };
const char* const kEncoderLabels[4] = {
  "NORMAL", "REVERSED", "HALF STEP", "HALF REV",
};
const char* const kToolLabels[2] = { "CV ZERO", "FACTORY" };
const char* const kPageTitles[7] = {
  "", "LFO 1", "RANDOM", "SENDS", "AUDIO", "MIDI", "PANEL",
};

// --- hashing ----------------------------------------------------------------

// FNV-1a over what a region shows: equal hashes, nothing to redraw.
struct Hash {
  uint32_t h;
  Hash() : h(2166136261u) { }
  void Bytes(const void* data, size_t size) {
    const uint8_t* p = static_cast<const uint8_t*>(data);
    for (size_t i = 0; i < size; ++i) {
      h = (h ^ p[i]) * 16777619u;
    }
  }
  void Int(int32_t v) { Bytes(&v, sizeof(v)); }
  void Text(const char* s) {
    Bytes(s, strlen(s));
    Int(0);
  }
};

int Clamp(int v, int lo, int hi) { return v < lo ? lo : (v > hi ? hi : v); }

float Clampf(float v, float lo, float hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

int BarPixels(float value) {
  return Clamp(int(Clampf(value, 0.0f, 1.0f) * float(kBarWidth - 1) + 0.5f),
               0, kBarWidth - 1);
}

// A peak level on a -48..0 dB scale, 0..1.
float MeterFraction(float level) {
  if (level < 0.004f) {
    return 0.0f;
  }
  return Clampf((20.0f * log10f(level) + 48.0f) * (1.0f / 48.0f), 0.0f, 1.0f);
}

// The range a modulation source covers: bipolar ones swing both ways.
bool SourceBipolar(int source) {
  return !(source == MOD_ENVELOPE || source == MOD_CC_A ||
           source == MOD_CC_B || source == MOD_GATE);
}

const Font& FontFor(int index) {
  return index == 0 ? kFontLarge : (index == 1 ? kFontMedium : kFontSmall);
}

enum BarMode {
  BAR_NONE,
  BAR_UNIPOLAR,
  BAR_BIPOLAR,
  BAR_STEPS,  // `steps` segments, `step` lit
  BAR_BEATS,  // four segments, the beat lit
  BAR_LEVEL,  // `steps` segments, those up to `step` lit
};

}  // namespace

// One knob row, as text and numbers: what DrawRow() draws and what its
// hash compares.
struct Ui::RowView {
  char label[16];
  char tag[20];     // right of the label: the mod source, a state
  char prefix[8];   // left of the value in the big font (HOME's slot number)
  char value[24];
  char suffix[8];   // after the value, small ("BPM")
  Color label_color;
  Color tag_color;
  Color value_color;
  Color prefix_color;
  Color bar_color;
  uint8_t value_font;  // 0 large, 1 medium (shrinks further to fit)
  uint8_t bar_mode;    // BarMode
  uint8_t steps;
  uint8_t step;
  bool synced;         // the note symbol after the label
  bool align_left;     // the value starts at the margin (name editing)
  int16_t bar;         // the knob's value, pixels into the bar
  int16_t mod;         // the modulated value, pixels; -1: none
  int16_t range0;      // the modulation's span under the bar; -1: none
  int16_t range1;
  int8_t cursor;       // the character underlined; -1: none
};

// --- setup ------------------------------------------------------------------

void Ui::Init(App* app, Canvas* canvas, float (*cpu_load)()) {
  app_ = app;
  canvas_ = canvas;
  cpu_load_ = cpu_load;
  page_ = PAGE_HOME;
  overlay_ = OVERLAY_NONE;
  block_slot_ = 0;
  for (int i = 0; i < NUM_SLOTS; ++i) {
    block_page_[i] = 0;
    pending_type_[i] = -1;
    pending_type_ms_[i] = 0;
  }
  pending_encoder_ = -1;
  pending_encoder_ms_ = 0;
  mod_slot_ = -1;
  mod_index_ = 0;
  browse_ = 0;
  browsing_ = false;
  browse_ms_ = 0;
  save_slot_ = 0;
  save_cursor_ = 0;
  memset(save_name_, 0, sizeof(save_name_));
  restore_yes_ = false;
  tool_ = 0;
  env_gain_row_ = false;
  shift_held_ = false;
  shift_used_ = false;
  for (int i = 0; i < 4; ++i) {
    last_turn_ms_[i] = 0;
    last_turn_dir_[i] = 0;
  }
  message_[0] = '\0';
  message_until_ms_ = 0;
  message_active_ = false;
  memset(region_key_, 0, sizeof(region_key_));
  region_valid_ = 0;
  now_ms_ = hal::Milliseconds();
  last_draw_ms_ = now_ms_ - kFrameMs;
  cpu_ms_ = now_ms_ - kCpuRefreshMs;
  cpu_percent_ = 0;
  midi_messages_ = app_->midi.messages();
  midi_activity_ms_ = now_ms_ - kMidiDotMs;
  canvas_->ResetClip();
  canvas_->Clear(kBlack);
}

void Ui::ShowMessage(const char* text, uint32_t duration_ms) {
  CopyText(message_, sizeof(message_), text);
  message_until_ms_ = hal::Milliseconds() + duration_ms;
  message_active_ = true;
  region_valid_ &= ~(1u << REGION_MESSAGE);
}

// --- input ------------------------------------------------------------------

void Ui::OnEvent(const Event& event) {
  if (event.id == hal::SWITCH_SHIFT) {
    if (event.type == EVENT_PRESS) {
      shift_held_ = true;
      shift_used_ = false;
    } else if (event.type == EVENT_RELEASE) {
      shift_held_ = false;
      if (!shift_used_) {
        OnShiftTap();
      }
    }
    return;
  }
  if (event.shift) {
    shift_used_ = true;
  }
  if (event.type == EVENT_ENCODER) {
    if (event.id < 4 && event.delta != 0) {
      OnTurn(event.id, event.delta, event.shift, event.time_ms);
    }
  } else if (event.type == EVENT_PRESS) {
    if (event.id <= hal::SWITCH_REVERB) {
      OnSendPress(event.id, event.shift, event.handled);
    } else if (event.id >= hal::SWITCH_K1 && event.id <= hal::SWITCH_K4) {
      OnPush(event.id - hal::SWITCH_K1, event.shift, event.time_us);
    }
  }
}

void Ui::OnShiftTap() {
  if (overlay_ != OVERLAY_NONE) {
    // SHIFT backs out of every overlay without doing anything.
    OpenOverlay(OVERLAY_NONE);
  } else if (page_ == PAGE_BLOCK) {
    OpenPage(PAGE_HOME);
  } else {
    OpenPage((page_ + 1) % NUM_CYCLE_PAGES);
  }
}

void Ui::OnSendPress(int slot, bool shift, bool handled) {
  if (!shift) {
    // The control interrupt already toggled it (a dub throw must not wait
    // for the main loop); the screen follows send_active().
    if (!handled) {
      app_->engine.ToggleSend(slot);
    }
    return;
  }
  overlay_ = OVERLAY_NONE;
  if (page_ == PAGE_BLOCK && block_slot_ == slot) {
    block_page_[slot] = uint8_t((block_page_[slot] + 1) % NumBlockPages(slot));
  } else {
    page_ = PAGE_BLOCK;
    block_slot_ = uint8_t(slot);
    if (block_page_[slot] >= NumBlockPages(slot)) {
      block_page_[slot] = 0;
    }
  }
  browsing_ = false;
  Invalidate();
}

void Ui::OnPush(int knob, bool shift, uint32_t time_us) {
  Preset* preset = app_->engine.mutable_preset();
  switch (overlay_) {
    case OVERLAY_MOD:
      OpenOverlay(OVERLAY_NONE);
      return;
    case OVERLAY_SAVE:
      if (knob == 0 || knob == 3) {
        DoSave();
      }
      return;
    case OVERLAY_CALIBRATE:
      DoCalibrate();
      return;
    case OVERLAY_RESTORE:
      if (knob == 3) {
        if (restore_yes_) {
          DoRestore();
        } else {
          OpenOverlay(OVERLAY_NONE);
        }
      }
      return;
    default:
      break;
  }
  switch (page_) {
    case PAGE_HOME:
      if (knob == 0) {
        if (shift) {
          save_slot_ = int8_t(browsing_ ? browse_ : app_->current_preset());
          memset(save_name_, ' ', kPresetNameLength);
          save_name_[kPresetNameLength] = '\0';
          for (size_t i = 0; i < kPresetNameLength && preset->name[i]; ++i) {
            save_name_[i] = kNameChars[NameCharIndex(preset->name[i])];
          }
          save_cursor_ = 0;
          OpenOverlay(OVERLAY_SAVE);
        } else if (browsing_) {
          app_->LoadPreset(browse_);
          browsing_ = false;
        }
      } else if (knob == 2) {
        OpenModOverlay(-1, 0);
      } else if (knob == 3) {
        // The tap counts from the scan that saw the press, not from now: a
        // flash write or a long redraw between the two must not skew the
        // tempo or the downbeat.
        float bpm;
        if (app_->tempo.Tap(time_us, &bpm)) {
          preset->tempo = uint16_t(Clamp(int(bpm * 10.0f + 0.5f), 300, 3000));
          Edited();
        }
      }
      break;
    case PAGE_BLOCK: {
      const int index = ParamAt(block_slot_, block_page_[block_slot_], knob);
      if (index < 0) {
        break;
      }
      if (shift) {
        const Block* block = app_->engine.block(block_slot_);
        if (block && index < block->info().num_params &&
            (block->info().params[index].flags & PARAM_SYNC)) {
          preset->slot[block_slot_].sync_mask ^= uint16_t(1u << index);
          Edited();
        } else {
          ShowMessage("NO SYNC HERE", kMessageMs);
        }
      } else {
        OpenModOverlay(block_slot_, index);
      }
      break;
    }
    case PAGE_MOD1:
      if (knob == 0 || knob == 2) {
        preset->lfo[knob / 2].sync ^= 1;
        Edited();
      }
      break;
    case PAGE_MOD2:
      if (knob == 0) {
        preset->random.sync ^= 1;
        Edited();
      } else if (knob == 3) {
        env_gain_row_ = !env_gain_row_;
      }
      break;
    case PAGE_SENDS:
      app_->engine.ToggleSend(knob);
      break;
    case PAGE_SETUP3:
      if (knob == 3) {
        restore_yes_ = false;
        OpenOverlay(tool_ == 0 ? OVERLAY_CALIBRATE : OVERLAY_RESTORE);
      }
      break;
    default:
      break;
  }
}

int Ui::Acceleration(int knob, int delta, uint32_t time_ms) {
  // Slow clicks move one detent each; the faster they come in one
  // direction, the more each one moves, so a sweep across a 128-detent
  // range takes a quick twist while fine moves stay exact.
  const int direction = delta > 0 ? 1 : -1;
  const uint32_t dt = time_ms - last_turn_ms_[knob];
  int multiplier = 1;
  if (direction == last_turn_dir_[knob]) {
    if (dt < 25) {
      multiplier = 8;
    } else if (dt < 45) {
      multiplier = 4;
    } else if (dt < 80) {
      multiplier = 2;
    }
  }
  last_turn_ms_[knob] = time_ms;
  last_turn_dir_[knob] = int8_t(direction);
  return delta * multiplier;
}

void Ui::OnTurn(int knob, int delta, bool shift, uint32_t time_ms) {
  // SHIFT + turn is always precise: one detent per click.
  const int accelerated = Acceleration(knob, delta, time_ms);
  const int steps = shift ? delta : accelerated;
  switch (overlay_) {
    case OVERLAY_MOD:
      TurnModOverlay(knob, delta, steps);
      return;
    case OVERLAY_SAVE:
      TurnSave(knob, delta, steps);
      return;
    case OVERLAY_RESTORE:
      if (knob == 3) {
        restore_yes_ = delta > 0;
      }
      return;
    case OVERLAY_CALIBRATE:
      return;
    default:
      break;
  }
  if (page_ == PAGE_HOME) {
    TurnHome(knob, delta, steps, shift);
  } else if (page_ == PAGE_BLOCK) {
    const int slot = block_slot_;
    if (shift && knob == 0) {
      // The type changes once the knob rests, so turning through the list
      // does not fade every type in and out on the way.
      const int n = NumBlockTypes(slot);
      if (n > 0) {
        int type = (ShownType(slot) + delta) % n;
        if (type < 0) {
          type += n;
        }
        pending_type_[slot] = int8_t(type);
        pending_type_ms_[slot] = time_ms;
      }
    } else {
      const int index = ParamAt(slot, block_page_[slot], knob);
      if (index >= 0 && pending_type_[slot] < 0) {
        TurnValue(slot, index, delta, steps);
      }
    }
  } else {
    TurnSetting(knob, delta, steps);
  }
}

void Ui::TurnHome(int knob, int delta, int steps, bool shift) {
  Preset* preset = app_->engine.mutable_preset();
  switch (knob) {
    case 0:
      if (!browsing_) {
        browse_ = int8_t(app_->current_preset());
      }
      browse_ = int8_t(Clamp(browse_ + steps, 0, kNumPresets - 1));
      browsing_ = true;
      browse_ms_ = now_ms_;
      break;
    case 1:
      preset->algorithm = uint8_t(Clamp(preset->algorithm + delta, 0,
                                        NUM_ALGORITHMS - 1));
      Edited();
      break;
    case 2:
      TurnValue(-1, 0, delta, steps);
      break;
    case 3: {
      // Whole BPM per detent (snapping onto them); SHIFT: tenths.
      int tempo = preset->tempo;
      if (shift) {
        tempo += delta;
      } else {
        tempo = ((tempo + 5) / 10 + steps) * 10;
      }
      preset->tempo = uint16_t(Clamp(tempo, 300, 3000));
      Edited();
      break;
    }
    default:
      break;
  }
}

void Ui::TurnValue(int slot, int index, int delta, int steps) {
  Preset* preset = app_->engine.mutable_preset();
  uint16_t* raw = slot < 0 ? &preset->wet : &preset->slot[slot].value[index];
  const Block* block = slot < 0 ? NULL : app_->engine.block(slot);
  const ParamInfo* info = NULL;
  if (block && index < block->info().num_params) {
    info = &block->info().params[index];
  }
  float value = PresetValue(*raw);
  if (info && (info->flags & PARAM_STEPPED)) {
    const int n = info->num_steps < 2 ? 2 : info->num_steps;
    value = StepValue(Clamp(StepIndex(value, n) + delta, 0, n - 1), n);
  } else if (info && (info->flags & PARAM_SYNC) &&
             ((preset->slot[slot].sync_mask >> index) & 1)) {
    // Synced: one note value per detent.
    value = StepValue(Clamp(NoteValueIndex(value) + delta, 0,
                            kNumNoteValues - 1), kNumNoteValues);
  } else {
    const int detents = info ? (info->detents ? info->detents : 128) : 100;
    const int position = Clamp(
        int(floorf(value * float(detents) + 0.5f)) + steps, 0, detents);
    value = float(position) / float(detents);
  }
  *raw = PresetRaw(value);
  Edited();
}

void Ui::TurnModOverlay(int knob, int delta, int steps) {
  Preset* preset = app_->engine.mutable_preset();
  ModAssign* mod = mod_slot_ < 0 ? &preset->wet_mod
                                 : &preset->slot[mod_slot_].mod[mod_index_];
  switch (knob) {
    case 0:
      TurnValue(mod_slot_, mod_index_, delta, steps);
      break;
    case 1:
      mod->source = uint8_t(Clamp(mod->source + delta, 0, NUM_MOD_SOURCES - 1));
      Edited();
      break;
    case 2:
      mod->depth = int8_t(Clamp(mod->depth + steps, -100, 100));
      Edited();
      break;
    default:
      break;
  }
}

namespace {

// A source's rate in a preset: free (128 detents, accelerated) or synced
// (one note value per detent).
void TurnRate(uint16_t* rate, bool synced, int delta, int steps) {
  float value = PresetValue(*rate);
  if (synced) {
    value = StepValue(Clamp(StepIndex(value, kNumNoteValues) + delta, 0,
                            kNumNoteValues - 1), kNumNoteValues);
  } else {
    value = float(Clamp(int(floorf(value * 128.0f + 0.5f)) + steps, 0, 128)) /
            128.0f;
  }
  *rate = PresetRaw(value);
}

void TurnRaw(uint16_t* raw, int detents, int steps) {
  const int position = Clamp(
      int(floorf(PresetValue(*raw) * float(detents) + 0.5f)) + steps, 0,
      detents);
  *raw = PresetRaw(float(position) / float(detents));
}

}  // namespace

void Ui::TurnSetting(int row, int delta, int steps) {
  Preset* preset = app_->engine.mutable_preset();
  Settings* settings = &app_->settings;
  switch (page_) {
    case PAGE_MOD1: {
      LfoPreset* lfo = &preset->lfo[row / 2];
      if (row % 2 == 0) {
        TurnRate(&lfo->rate, lfo->sync, delta, steps);
      } else {
        lfo->shape = uint8_t(Clamp(lfo->shape + delta, 0, NUM_LFO_SHAPES - 1));
      }
      Edited();
      return;
    }
    case PAGE_MOD2:
      if (row == 0) {
        TurnRate(&preset->random.rate, preset->random.sync, delta, steps);
      } else if (row == 1) {
        TurnRaw(&preset->random.smooth, 100, steps);
      } else if (row == 2) {
        TurnRaw(&preset->envelope.attack, 128, steps);
      } else if (env_gain_row_) {
        TurnRaw(&preset->envelope.gain, 48, steps);  // 0.5 dB a detent
      } else {
        TurnRaw(&preset->envelope.release, 128, steps);
      }
      Edited();
      return;
    case PAGE_SENDS: {
      SlotPreset* slot = &preset->slot[row];
      slot->send_gate = uint8_t(Clamp(slot->send_gate + delta, 0,
                                      NUM_MOD_SOURCES - 1));
      Edited();
      return;
    }
    case PAGE_SETUP1:
      if (row == 0) {
        TurnRaw(&settings->dry, 100, steps);
      } else if (row == 1 || row == 2) {
        int16_t* gain =
            row == 1 ? &settings->input_gain : &settings->output_gain;
        *gain = int16_t(Clamp(*gain + steps * 5, -120, 120));  // 0.5 dB
      } else {
        settings->invert_output = delta > 0 ? 1 : 0;
      }
      break;
    case PAGE_SETUP2:
      if (row == 0) {
        settings->midi_channel =
            uint8_t(Clamp(settings->midi_channel + delta, 0, 16));
      } else if (row == 1 || row == 2) {
        uint8_t* cc = row == 1 ? &settings->cc_a : &settings->cc_b;
        *cc = uint8_t(Clamp(*cc + steps, 1, 119));
      } else {
        settings->clock_ppqn = uint8_t(Clamp(settings->clock_ppqn + delta, 0,
                                             kNumClockPpqn - 1));
      }
      break;
    case PAGE_SETUP3:
      if (row == 0) {
        settings->brightness =
            uint8_t(Clamp(settings->brightness + delta, 1, 10));
      } else if (row == 1) {
        // hal::SetDisplayFlip sends the whole frame again the new way up.
        settings->display_flip = delta > 0 ? 1 : 0;
      } else if (row == 2) {
        // The mode changes how K3 itself counts (its direction, its steps
        // per detent), so it is only picked here and applied once the knob
        // rests (Poll): turning one way walks the whole list.
        const int mode = pending_encoder_ >= 0
            ? pending_encoder_
            : (settings->encoder_steps == 2 ? 2 : 0) +
                  (settings->encoder_reverse ? 1 : 0);
        pending_encoder_ = int8_t(Clamp(mode + delta, 0, 3));
        pending_encoder_ms_ = hal::Milliseconds();
        return;
      } else {
        tool_ = delta > 0 ? 1 : 0;
        return;
      }
      break;
    default:
      return;
  }
  app_->SettingsChanged();
}

void Ui::ApplyEncoderMode() {
  const int mode = pending_encoder_;
  pending_encoder_ = -1;
  if (mode < 0) {
    return;
  }
  Settings* settings = &app_->settings;
  const uint8_t steps = mode >= 2 ? 2 : 4;
  const uint8_t reverse = uint8_t(mode & 1);
  if (steps != settings->encoder_steps || reverse != settings->encoder_reverse) {
    settings->encoder_steps = steps;
    settings->encoder_reverse = reverse;
    app_->SettingsChanged();
  }
}

void Ui::TurnSave(int knob, int delta, int steps) {
  switch (knob) {
    case 0:
      save_slot_ = int8_t(Clamp(save_slot_ + steps, 0, kNumPresets - 1));
      break;
    case 1:
      save_cursor_ = int8_t(Clamp(save_cursor_ + delta, 0,
                                  int(kPresetNameLength) - 1));
      break;
    case 2: {
      int c = (NameCharIndex(save_name_[save_cursor_]) + delta) % kNumNameChars;
      if (c < 0) {
        c += kNumNameChars;
      }
      save_name_[save_cursor_] = kNameChars[c];
      break;
    }
    default:
      break;
  }
}

void Ui::OpenPage(int page) {
  page_ = uint8_t(page);
  overlay_ = OVERLAY_NONE;
  browsing_ = false;
  Invalidate();
}

void Ui::OpenOverlay(int overlay) {
  overlay_ = uint8_t(overlay);
  Invalidate();
}

void Ui::OpenModOverlay(int slot, int index) {
  mod_slot_ = int8_t(slot);
  mod_index_ = int8_t(index);
  OpenOverlay(OVERLAY_MOD);
}

void Ui::DoSave() {
  char name[kPresetNameLength + 1];
  CopyText(name, sizeof(name), save_name_);
  int n = int(strlen(name));
  while (n > 0 && name[n - 1] == ' ') {
    name[--n] = '\0';
  }
  if (n == 0) {
    CopyText(name, sizeof(name), "PRESET ");
    char number[4];
    FormatSlot(number, sizeof(number), save_slot_);
    Append(name, sizeof(name), number);
  }
  SetPresetName(app_->engine.mutable_preset(), name);
  char text[24];
  if (app_->SavePreset(save_slot_)) {
    CopyText(text, sizeof(text), "SAVED ");
    char number[4];
    FormatSlot(number, sizeof(number), save_slot_);
    Append(text, sizeof(text), number);
  } else {
    CopyText(text, sizeof(text), "SAVE FAILED");
  }
  browsing_ = false;
  OpenPage(PAGE_HOME);
  ShowMessage(text, kMessageMs);
}

void Ui::DoCalibrate() {
  // Nothing plugged in: every input reads 0 V, so the raw readings are the
  // offsets. The scales stay nominal: 1 % resistors and the 3V3A reference
  // (an LP2985, +-3.5 %) spread them by up to about 6 % between modules.
  int bad = -1;
  for (int ch = 0; ch < 4; ++ch) {
    const float raw = app_->mods.cv_raw(ch);
    if (raw >= 0.42f && raw <= 0.58f) {   // 0 V +- about 2 V (nominal 0.502)
      app_->settings.calibration.offset[ch] = raw;
    } else if (bad < 0) {
      bad = ch;
    }
  }
  app_->SettingsChanged();
  OpenOverlay(OVERLAY_NONE);
  if (bad >= 0) {
    char text[24] = "CV";
    AppendNumber(text, sizeof(text), float(bad + 1), 0, false, " NOT AT 0 V");
    ShowMessage(text, 2 * kMessageMs);
  } else {
    ShowMessage("CV ZEROED", kMessageMs);
  }
}

void Ui::DoRestore() {
  app_->bank.RestoreFactory();
  app_->LoadPreset(0);
  OpenPage(PAGE_HOME);
  ShowMessage("FACTORY RESTORED", kMessageMs);
}

void Ui::Edited() {
  app_->PresetEdited();
}

// --- where things are -------------------------------------------------------

int Ui::NumBlockPages(int slot) const {
  const Block* block = app_->engine.block(slot);
  const int n = block ? block->info().num_params : 0;
  return (n + 1 + kRowsPerPage - 1) / kRowsPerPage;  // MIX is one more row
}

int Ui::ParamAt(int slot, int page, int row) const {
  const Block* block = app_->engine.block(slot);
  const int n = block ? block->info().num_params : 0;
  if (page == NumBlockPages(slot) - 1 && row == kRowsPerPage - 1) {
    return kMixValue;
  }
  const int index = page * kRowsPerPage + row;
  return index < n ? index : -1;
}

int Ui::ShownType(int slot) const {
  return pending_type_[slot] >= 0 ? pending_type_[slot]
                                  : app_->engine.block_type(slot);
}

float Ui::RawValue(int slot, int index) const {
  const Preset& preset = app_->engine.preset();
  return PresetValue(slot < 0 ? preset.wet : preset.slot[slot].value[index]);
}

float Ui::LiveValue(int slot, int index) const {
  return slot < 0 ? app_->engine.wet_value() : app_->engine.value(slot, index);
}

const ModAssign& Ui::Mod(int slot, int index) const {
  const Preset& preset = app_->engine.preset();
  return slot < 0 ? preset.wet_mod : preset.slot[slot].mod[index];
}

uint16_t Ui::Accent() const {
  if (overlay_ == OVERLAY_MOD) {
    return mod_slot_ < 0 ? kGold : kSlotColor[mod_slot_];
  }
  return page_ == PAGE_BLOCK ? kSlotColor[block_slot_] : kGold;
}

void Ui::FormatValue(int slot, int index, float value, char* text,
                     size_t size) {
  const Block* block = slot < 0 ? NULL : app_->engine.block(slot);
  if (!block || index >= block->info().num_params) {
    FormatPercent(text, size, value);
  } else {
    block->Format(index, value,
                  app_->engine.MakeContext(slot, app_->tempo.state()), text,
                  size);
  }
}

// --- main loop --------------------------------------------------------------

void Ui::Poll(uint32_t now_ms) {
  now_ms_ = now_ms;
  if (app_->engine.loading()) {
    // A preset load (a program change, K1's push) brings its own types:
    // a type still waiting on SHIFT + K1 would replace the loaded slot
    // with the old choice's defaults.
    for (int slot = 0; slot < NUM_SLOTS; ++slot) {
      pending_type_[slot] = -1;
    }
  }
  for (int slot = 0; slot < NUM_SLOTS; ++slot) {
    if (pending_type_[slot] >= 0 &&
        int32_t(now_ms - pending_type_ms_[slot]) >= int32_t(kTypeDebounceMs)) {
      const int type = pending_type_[slot];
      pending_type_[slot] = -1;
      if (type != app_->engine.block_type(slot)) {
        app_->engine.SetBlockType(slot, type);
        block_page_[slot] = 0;
        Edited();
      }
    }
  }
  if (pending_encoder_ >= 0 &&
      (int32_t(now_ms - pending_encoder_ms_) >= int32_t(kEncoderModeMs) ||
       page_ != PAGE_SETUP3 || overlay_ != OVERLAY_NONE)) {
    ApplyEncoderMode();
  }
  if (browsing_ && int32_t(now_ms - browse_ms_) >= int32_t(kBrowseTimeoutMs)) {
    browsing_ = false;
  }
  // A preset load (a MIDI program change, say) can bring a type with
  // fewer values: keep the block page and the mod overlay on real ones.
  if (block_page_[block_slot_] >= NumBlockPages(block_slot_)) {
    block_page_[block_slot_] = 0;
    Invalidate();
  }
  if (overlay_ == OVERLAY_MOD && mod_slot_ >= 0 && mod_index_ != kMixValue) {
    const Block* block = app_->engine.block(mod_slot_);
    if (!block || mod_index_ >= block->info().num_params) {
      OpenOverlay(OVERLAY_NONE);
    }
  }
  if (message_active_ && int32_t(now_ms - message_until_ms_) >= 0) {
    message_active_ = false;
    region_valid_ &= ~((1u << REGION_GAP_B) | (1u << REGION_MESSAGE));
  }
  if (app_->midi.messages() != midi_messages_) {
    midi_messages_ = app_->midi.messages();
    midi_activity_ms_ = now_ms;
  }
  if (now_ms - cpu_ms_ >= kCpuRefreshMs) {
    cpu_ms_ = now_ms;
    const float load = cpu_load_ ? cpu_load_() : 0.0f;
    cpu_percent_ = uint8_t(Clamp(int(load * 100.0f + 0.5f), 0, 99));
  }
  if (now_ms - last_draw_ms_ < kFrameMs || hal::DisplayBusy()) {
    return;
  }
  last_draw_ms_ = now_ms;
  Draw();
}

void Ui::Invalidate() {
  region_valid_ = 0;
}

bool Ui::Changed(int region, uint32_t key) {
  const uint16_t bit = uint16_t(1u << region);
  if ((region_valid_ & bit) && region_key_[region] == key) {
    return false;
  }
  region_key_[region] = key;
  region_valid_ |= bit;
  return true;
}

void Ui::Draw() {
  for (int row = 0; row < kRowsPerPage; ++row) {
    RowView view;
    BuildRow(row, &view);
    Hash hash;
    hash.Bytes(&view, sizeof(view));
    if (Changed(REGION_ROW1 + row, hash.h)) {
      DrawRow(row, view);
    }
  }
  DrawGapA();
  if (!message_active_) {
    DrawGapB();
  }
  DrawGapC();
  if (message_active_) {
    DrawMessage();
  }
}

// --- rows -------------------------------------------------------------------

void Ui::BuildRow(int row, RowView* view) {
  memset(view, 0, sizeof(*view));
  view->label_color = kGrey;
  view->tag_color = kModColor;
  view->value_color = kWhite;
  view->prefix_color = kGold;
  view->bar_color = Accent();
  view->mod = -1;
  view->range0 = -1;
  view->range1 = -1;
  view->cursor = -1;
  switch (overlay_) {
    case OVERLAY_MOD:
      BuildModRow(row, view);
      return;
    case OVERLAY_SAVE:
      BuildSaveRow(row, view);
      return;
    case OVERLAY_CALIBRATE:
    case OVERLAY_RESTORE:
      BuildOtherRow(row, view);
      return;
    default:
      break;
  }
  switch (page_) {
    case PAGE_HOME:
      BuildHomeRow(row, view);
      break;
    case PAGE_BLOCK: {
      const int index = ParamAt(block_slot_, block_page_[block_slot_], row);
      if (index >= 0) {
        BuildValueRow(block_slot_, index, view);
        if (pending_type_[block_slot_] >= 0) {
          // The rows belong to the type being left: grey until it changes.
          view->value_color = kDim;
          view->bar_color = kDim;
        }
      }
      break;
    }
    case PAGE_MOD1:
    case PAGE_MOD2:
    case PAGE_SENDS:
      BuildSourcesRow(row, view);
      break;
    default:
      BuildSettingRow(row, view);
      break;
  }
}

void Ui::BuildValueRow(int slot, int index, RowView* view) {
  const Block* block = slot < 0 ? NULL : app_->engine.block(slot);
  const ParamInfo* info = NULL;
  if (block && index < block->info().num_params) {
    info = &block->info().params[index];
  }
  CopyText(view->label, sizeof(view->label),
           slot < 0 ? "WET" : (info ? info->name : "MIX"));
  const float value = RawValue(slot, index);
  FormatValue(slot, index, value, view->value, sizeof(view->value));
  view->bar = int16_t(BarPixels(value));
  view->bar_mode = BAR_UNIPOLAR;
  if (info && (info->flags & PARAM_STEPPED)) {
    view->bar_mode = BAR_STEPS;
    view->steps = uint8_t(info->num_steps);
    view->step = uint8_t(StepIndex(value, info->num_steps));
  } else if (info && (info->flags & PARAM_BIPOLAR)) {
    view->bar_mode = BAR_BIPOLAR;
  }
  if (info && (info->flags & PARAM_SYNC)) {
    view->synced =
        (app_->engine.preset().slot[slot].sync_mask >> index) & 1;
  }
  const ModAssign& mod = Mod(slot, index);
  if (mod.source != MOD_OFF && mod.source < NUM_MOD_SOURCES) {
    CopyText(view->tag, sizeof(view->tag), kModSourceNames[mod.source]);
    Append(view->tag, sizeof(view->tag), " ");
    AppendNumber(view->tag, sizeof(view->tag), float(mod.depth), 0,
                 mod.depth != 0, "%");
    view->mod = int16_t(BarPixels(LiveValue(slot, index)));
  }
}

void Ui::BuildHomeRow(int row, RowView* view) {
  const Preset& preset = app_->engine.preset();
  switch (row) {
    case 0: {
      CopyText(view->label, sizeof(view->label), "PRESET");
      const int shown = browsing_ ? browse_ : app_->current_preset();
      FormatSlot(view->prefix, sizeof(view->prefix), shown);
      view->value_font = 1;
      if (browsing_) {
        CopyText(view->value, sizeof(view->value), app_->bank.name(shown));
        CopyText(view->tag, sizeof(view->tag), "PUSH: LOAD");
        view->tag_color = kGold;
        view->value_color = kGold;
      } else {
        CopyText(view->value, sizeof(view->value), preset.name);
        if (app_->engine.loading()) {
          CopyText(view->tag, sizeof(view->tag), "LOADING");
          view->tag_color = kGrey;
        } else if (app_->modified()) {
          CopyText(view->tag, sizeof(view->tag), "EDITED");
          view->tag_color = kGold;
        }
      }
      break;
    }
    case 1: {
      CopyText(view->label, sizeof(view->label), "ALGORITHM");
      const int algorithm = Clamp(preset.algorithm, 0, NUM_ALGORITHMS - 1);
      CopyText(view->value, sizeof(view->value), kAlgorithmNames[algorithm]);
      AppendNumber(view->tag, sizeof(view->tag), float(algorithm + 1), 0,
                   false, "/7");
      view->tag_color = kDim;
      break;
    }
    case 2:
      BuildValueRow(-1, 0, view);
      break;
    default: {
      CopyText(view->label, sizeof(view->label), "TEMPO");
      const int source = Clamp(app_->tempo.source(), 0, 2);
      CopyText(view->tag, sizeof(view->tag), kSourceLabels[source]);
      view->tag_color = source == TEMPO_INTERNAL ? kDim : kGold;
      FormatNumber(view->value, sizeof(view->value), app_->tempo.bpm(), 1,
                   false, "");
      CopyText(view->suffix, sizeof(view->suffix), "BPM");
      view->bar_mode = BAR_BEATS;
      view->steps = 4;
      view->step = uint8_t(
          Clamp(int(app_->tempo.state().bar_phase * 4.0f), 0, 3));
      break;
    }
  }
}

void Ui::BuildModRow(int row, RowView* view) {
  const ModAssign& mod = Mod(mod_slot_, mod_index_);
  const float base = RawValue(mod_slot_, mod_index_);
  switch (row) {
    case 0:
      BuildValueRow(mod_slot_, mod_index_, view);
      view->tag[0] = '\0';
      view->mod = -1;
      break;
    case 1:
      CopyText(view->label, sizeof(view->label), "SOURCE");
      CopyText(view->value, sizeof(view->value), kModSourceNames[mod.source]);
      view->value_color = mod.source == MOD_OFF ? kDim : kModColor;
      view->bar_mode = BAR_STEPS;
      view->steps = NUM_MOD_SOURCES;
      view->step = mod.source;
      view->bar_color = kModColor;
      break;
    case 2:
      CopyText(view->label, sizeof(view->label), "DEPTH");
      FormatNumber(view->value, sizeof(view->value), float(mod.depth), 0,
                   mod.depth != 0, "%");
      view->bar_mode = BAR_BIPOLAR;
      view->bar = int16_t(BarPixels(0.5f + float(mod.depth) * 0.005f));
      view->bar_color = kModColor;
      break;
    default: {
      CopyText(view->label, sizeof(view->label), "NOW");
      const float live = LiveValue(mod_slot_, mod_index_);
      FormatValue(mod_slot_, mod_index_, live, view->value,
                  sizeof(view->value));
      view->value_color = mod.source == MOD_OFF ? kDim : kModColor;
      view->bar_mode = BAR_UNIPOLAR;
      view->bar = int16_t(BarPixels(base));
      if (mod.source != MOD_OFF) {
        const float depth = float(mod.depth) * 0.01f;
        const float a = base + (SourceBipolar(mod.source) ? -depth : 0.0f);
        const float b = base + depth;
        view->range0 = int16_t(BarPixels(a < b ? a : b));
        view->range1 = int16_t(BarPixels(a < b ? b : a));
        view->mod = int16_t(BarPixels(live));
        CopyText(view->tag, sizeof(view->tag), "RANGE");
        view->tag_color = kDim;
      }
      break;
    }
  }
}

void Ui::BuildSourcesRow(int row, RowView* view) {
  const Preset& preset = app_->engine.preset();
  if (page_ == PAGE_SENDS) {
    CopyText(view->label, sizeof(view->label), kSlotNames[row]);
    view->label_color = kSlotColor[row];
    const int gate = preset.slot[row].send_gate;
    CopyText(view->value, sizeof(view->value),
             gate == MOD_OFF ? "NO GATE" : kModSourceNames[gate]);
    view->value_color = gate == MOD_OFF ? kDim : kWhite;
    const bool on = app_->engine.send_active(row);
    CopyText(view->tag, sizeof(view->tag), on ? "SEND ON" : "SEND OFF");
    view->tag_color = on ? kSlotColor[row] : kDim;
    return;
  }
  const bool mod1 = page_ == PAGE_MOD1;
  uint16_t raw = 0;
  bool rate = false;
  bool sync = false;
  if (mod1) {
    const LfoPreset& lfo = preset.lfo[row / 2];
    CopyText(view->label, sizeof(view->label), row / 2 ? "LFO2 " : "LFO1 ");
    if (row % 2 == 0) {
      Append(view->label, sizeof(view->label), "RATE");
      raw = lfo.rate;
      rate = true;
      sync = lfo.sync;
    } else {
      Append(view->label, sizeof(view->label), "SHAPE");
      const int shape = Clamp(lfo.shape, 0, NUM_LFO_SHAPES - 1);
      CopyText(view->value, sizeof(view->value), kLfoShapeNames[shape]);
      view->bar_mode = BAR_STEPS;
      view->steps = NUM_LFO_SHAPES;
      view->step = uint8_t(shape);
    }
  } else {
    static const char* const kLabels[4] = {
      "RND RATE", "RND SMOOTH", "ENV ATTACK", "ENV RELEASE",
    };
    CopyText(view->label, sizeof(view->label), kLabels[row]);
    view->bar_mode = BAR_UNIPOLAR;
    const EnvelopePreset& env = preset.envelope;
    char other[16];
    switch (row) {
      case 0:
        raw = preset.random.rate;
        rate = true;
        sync = preset.random.sync;
        break;
      case 1:
        raw = preset.random.smooth;
        FormatPercent(view->value, sizeof(view->value), PresetValue(raw));
        break;
      case 2:
        raw = env.attack;
        FormatSeconds(view->value, sizeof(view->value),
                      ExpMap(PresetValue(raw), 0.001f, 0.5f));
        break;
      default:
        if (env_gain_row_) {
          CopyText(view->label, sizeof(view->label), "ENV GAIN");
          raw = env.gain;
          FormatDecibels(view->value, sizeof(view->value),
                         PresetValue(raw) * 24.0f);
          FormatSeconds(other, sizeof(other),
                        ExpMap(PresetValue(env.release), 0.01f, 5.0f));
          CopyText(view->tag, sizeof(view->tag), "REL ");
        } else {
          raw = env.release;
          FormatSeconds(view->value, sizeof(view->value),
                        ExpMap(PresetValue(raw), 0.01f, 5.0f));
          FormatDecibels(other, sizeof(other), PresetValue(env.gain) * 24.0f);
          CopyText(view->tag, sizeof(view->tag), "GAIN ");
        }
        Append(view->tag, sizeof(view->tag), other);
        view->tag_color = kDim;
        break;
    }
  }
  if (rate) {
    const float value = PresetValue(raw);
    if (sync) {
      CopyText(view->value, sizeof(view->value),
               kNoteValues[SyncedRateIndex(value)].label);
    } else {
      FormatHz(view->value, sizeof(view->value), ExpMap(value, 0.02f, 20.0f));
    }
    view->synced = sync;
    view->bar_mode = BAR_UNIPOLAR;
  }
  view->bar = int16_t(BarPixels(PresetValue(raw)));
}

void Ui::BuildSettingRow(int row, RowView* view) {
  const Settings& s = app_->settings;
  static const char* const kLabels[3][4] = {
    { "DRY", "IN GAIN", "OUT GAIN", "OUT POLARITY" },
    { "MIDI CHANNEL", "CC A", "CC B", "CLOCK IN" },
    { "BRIGHTNESS", "FLIP", "ENCODER", "TOOLS" },
  };
  const int page = page_ - PAGE_SETUP1;
  CopyText(view->label, sizeof(view->label), kLabels[page][row]);
  switch (page * 4 + row) {
    case 0:
      FormatPercent(view->value, sizeof(view->value), PresetValue(s.dry));
      view->bar_mode = BAR_UNIPOLAR;
      view->bar = int16_t(BarPixels(PresetValue(s.dry)));
      break;
    case 1:
    case 2: {
      const int gain = row == 1 ? s.input_gain : s.output_gain;
      FormatDecibels(view->value, sizeof(view->value), float(gain) * 0.1f);
      view->bar_mode = BAR_BIPOLAR;
      view->bar = int16_t(BarPixels(0.5f + float(gain) * (0.5f / 120.0f)));
      break;
    }
    case 3:
      CopyText(view->value, sizeof(view->value),
               s.invert_output ? "INVERTED" : "NORMAL");
      break;
    case 4:
      if (s.midi_channel == 0) {
        CopyText(view->value, sizeof(view->value), "OMNI");
      } else {
        FormatNumber(view->value, sizeof(view->value), float(s.midi_channel), 0,
                     false, "");
      }
      break;
    case 5:
    case 6:
      CopyText(view->value, sizeof(view->value), "CC ");
      AppendNumber(view->value, sizeof(view->value),
                   float(row == 1 ? s.cc_a : s.cc_b), 0, false, "");
      break;
    case 7:
      FormatNumber(view->value, sizeof(view->value),
                   float(kClockPpqnValues[Clamp(s.clock_ppqn, 0,
                                                kNumClockPpqn - 1)]),
                   0, false, "");
      CopyText(view->suffix, sizeof(view->suffix), "PPQN");
      break;
    case 8:
      FormatNumber(view->value, sizeof(view->value), float(s.brightness), 0,
                   false, "");
      view->bar_mode = BAR_LEVEL;
      view->steps = 10;
      view->step = uint8_t(Clamp(s.brightness - 1, 0, 9));
      break;
    case 9:
      CopyText(view->value, sizeof(view->value), s.display_flip ? "ON" : "OFF");
      break;
    case 10: {
      const int mode = pending_encoder_ >= 0
          ? pending_encoder_
          : (s.encoder_steps == 2 ? 2 : 0) + (s.encoder_reverse ? 1 : 0);
      CopyText(view->value, sizeof(view->value), kEncoderLabels[mode]);
      if (pending_encoder_ >= 0) {
        // Picked, not applied yet: it takes over once K3 rests.
        view->value_color = kGold;
        CopyText(view->tag, sizeof(view->tag), "PENDING");
        view->tag_color = kGold;
      }
      break;
    }
    default:
      CopyText(view->value, sizeof(view->value), kToolLabels[tool_ ? 1 : 0]);
      CopyText(view->tag, sizeof(view->tag), "PUSH: START");
      view->tag_color = kGold;
      break;
  }
}

void Ui::BuildSaveRow(int row, RowView* view) {
  switch (row) {
    case 0: {
      CopyText(view->label, sizeof(view->label), "TO SLOT");
      FormatSlot(view->prefix, sizeof(view->prefix), save_slot_);
      const char* name = app_->bank.name(save_slot_);
      CopyText(view->value, sizeof(view->value), name);
      view->value_font = 1;
      view->value_color = kGrey;
      const bool empty = !strcmp(name, "INIT");
      CopyText(view->tag, sizeof(view->tag), empty ? "EMPTY" : "REPLACES");
      view->tag_color = empty ? kDim : kRed;
      break;
    }
    case 1:
      CopyText(view->label, sizeof(view->label), "NAME");
      CopyText(view->value, sizeof(view->value), save_name_);
      view->value_font = 1;
      view->align_left = true;
      view->cursor = save_cursor_;
      CopyText(view->tag, sizeof(view->tag), "TURN: MOVE");
      view->tag_color = kDim;
      break;
    case 2: {
      CopyText(view->label, sizeof(view->label), "LETTER");
      const char c = save_name_[save_cursor_];
      if (c == ' ') {
        CopyText(view->value, sizeof(view->value), "SPACE");
        view->value_color = kGrey;
      } else {
        view->value[0] = c;
        view->value[1] = '\0';
      }
      view->bar_mode = BAR_UNIPOLAR;
      view->bar = int16_t(BarPixels(float(NameCharIndex(c)) /
                                    float(kNumNameChars - 1)));
      break;
    }
    default:
      CopyText(view->label, sizeof(view->label), "CONFIRM");
      CopyText(view->value, sizeof(view->value), "PUSH: SAVE");
      view->value_color = kGold;
      CopyText(view->tag, sizeof(view->tag), "SHIFT: CANCEL");
      view->tag_color = kDim;
      break;
  }
}

void Ui::BuildOtherRow(int row, RowView* view) {
  if (overlay_ == OVERLAY_CALIBRATE) {
    char label[4] = { 'C', 'V', char('1' + row), '\0' };
    CopyText(view->label, sizeof(view->label), label);
    const float volts = app_->mods.cv_volts(row);
    FormatNumber(view->value, sizeof(view->value), volts, 2, true, "V");
    CopyText(view->tag, sizeof(view->tag), "RAW ");
    AppendNumber(view->tag, sizeof(view->tag), app_->mods.cv_raw(row), 3,
                 false, "");
    view->tag_color = kDim;
    view->bar_mode = BAR_BIPOLAR;
    view->bar = int16_t(BarPixels(0.5f + volts * 0.1f));
    return;
  }
  // RESTORE
  switch (row) {
    case 0:
      CopyText(view->label, sizeof(view->label), "PRESETS");
      CopyText(view->value, sizeof(view->value), "ALL 64");
      view->value_color = kGrey;
      break;
    case 1:
      CopyText(view->label, sizeof(view->label), "BECOME");
      CopyText(view->value, sizeof(view->value), "FACTORY");
      view->value_color = kGrey;
      break;
    case 3:
      CopyText(view->label, sizeof(view->label), "CONFIRM");
      CopyText(view->value, sizeof(view->value), restore_yes_ ? "YES" : "NO");
      view->value_color = restore_yes_ ? kRed : kWhite;
      CopyText(view->tag, sizeof(view->tag), "TURN, PUSH");
      view->tag_color = kDim;
      break;
    default:
      break;
  }
}

void Ui::DrawRow(int row, const RowView& view) {
  const int y0 = kRowTop[row];
  canvas_->FillRect(0, y0, kWidth, kRowHeight, kBlack);
  if (!view.label[0] && !view.value[0]) {
    return;
  }
  // Label line.
  int x = canvas_->DrawText(kMargin, y0, view.label, kFontSmall,
                            view.label_color);
  if (view.synced) {
    canvas_->DrawText(x + 3, y0, "\x01", kFontSmall, kGold);
  }
  if (view.tag[0]) {
    canvas_->DrawTextRight(kRight, y0, view.tag, kFontSmall, view.tag_color);
  }
  // Value line, on one baseline.
  const int baseline = y0 + kValueBaseline;
  int left = kMargin;
  if (view.prefix[0]) {
    left = canvas_->DrawText(kMargin, baseline - kFontLarge.ascent,
                             view.prefix, kFontLarge, view.prefix_color) + 8;
  }
  int right = kRight;
  if (view.suffix[0]) {
    canvas_->DrawTextRight(kRight, baseline - kFontSmall.ascent, view.suffix,
                           kFontSmall, kGrey);
    right = kRight - canvas_->TextWidth(view.suffix, kFontSmall) - 4;
  }
  // The biggest font the value fits in.
  int font_index = view.value_font;
  while (font_index < 2 &&
         canvas_->TextWidth(view.value, FontFor(font_index)) > right - left) {
    ++font_index;
  }
  const Font& font = FontFor(font_index);
  const int vx = view.align_left
      ? left : right - canvas_->TextWidth(view.value, font);
  canvas_->DrawText(vx, baseline - font.ascent, view.value, font,
                    view.value_color);
  if (view.cursor >= 0) {
    char before[24];
    CopyText(before, sizeof(before), view.value);
    before[Clamp(view.cursor, 0, int(sizeof(before)) - 1)] = '\0';
    char one[2] = { view.value[view.cursor], '\0' };
    const int cx = vx + canvas_->TextWidth(before, font);
    int cw = canvas_->TextWidth(one, font);
    if (cw < 6) {
      cw = 6;
    }
    canvas_->FillRect(cx, baseline + 3, cw, 2, kGold);
  }
  // Bar.
  const int by = y0 + kBarOffset;
  switch (view.bar_mode) {
    case BAR_UNIPOLAR:
      canvas_->FillRect(kBarX, by, kBarWidth, kBarHeight, kTrack);
      canvas_->FillRect(kBarX, by, view.bar + 1, kBarHeight, view.bar_color);
      break;
    case BAR_BIPOLAR: {
      const int centre = kBarWidth / 2;
      const int lo = view.bar < centre ? view.bar : centre;
      const int hi = view.bar < centre ? centre : view.bar;
      canvas_->FillRect(kBarX, by, kBarWidth, kBarHeight, kTrack);
      canvas_->FillRect(kBarX + centre, by - 2, 1, kBarHeight + 4, kDim);
      canvas_->FillRect(kBarX + lo, by, hi - lo + 1, kBarHeight,
                        view.bar_color);
      break;
    }
    case BAR_STEPS:
    case BAR_BEATS:
    case BAR_LEVEL: {
      const int n = view.steps < 1 ? 1 : view.steps;
      const int gap = n > 8 ? 2 : 3;
      for (int i = 0; i < n; ++i) {
        const int x0 = kBarX + (kBarWidth + gap) * i / n;
        const int x1 = kBarX + (kBarWidth + gap) * (i + 1) / n - gap;
        const bool lit = i == view.step ||
                         (view.bar_mode == BAR_LEVEL && i < view.step);
        canvas_->FillRect(x0, by, x1 - x0, kBarHeight,
                          lit ? view.bar_color : kTrack);
      }
      break;
    }
    default:
      break;
  }
  if (view.range0 >= 0) {
    canvas_->FillRect(kBarX + view.range0, by + kBarHeight + 1,
                      view.range1 - view.range0 + 1, 1, kModColor);
  }
  if (view.mod >= 0) {
    // The modulated value: a green tick across the bar, outlined in black
    // so it reads over the fill.
    const int mx = kBarX + view.mod;
    canvas_->FillRect(mx - 2, by - 4, 5, kBarHeight + 6, kBlack);
    canvas_->FillRect(mx - 1, by - 3, 3, kBarHeight + 4, kModColor);
  }
}

// --- gaps -------------------------------------------------------------------

namespace {

// Gap A's title: the large font, or the medium one on the same baseline
// for the names it would run off the screen with (GRANULATOR, WAVESHAPER).
const Font& TitleFont(const Canvas& canvas, const char* title) {
  return canvas.TextWidth(title, kFontLarge) > kRight - kMargin
      ? kFontMedium : kFontLarge;
}

}  // namespace

void Ui::DrawTitle(const char* title, uint16_t title_color,
                   const char* subtitle, uint16_t subtitle_color) {
  const int y = kGapTop[0];
  const Font& font = TitleFont(*canvas_, title);
  canvas_->DrawText(kMargin, y + 6 + kFontLarge.ascent - font.ascent, title,
                    font, title_color);
  canvas_->DrawText(kMargin, y + 30, subtitle, kFontSmall, subtitle_color);
}

namespace {

// Page dots at the right of gap A's subtitle line.
void DrawDots(Canvas* canvas, int y, int count, int current, Color color) {
  const int spacing = 9;
  int x = kRight - 2 - (count - 1) * spacing;
  for (int i = 0; i < count; ++i, x += spacing) {
    if (i == current) {
      canvas->FillCircle(x, y, 3, color);
    } else {
      canvas->FillCircle(x, y, 2, kDim);
    }
  }
}

void DrawLevelMeter(Canvas* canvas, int x, int y, int w, int h, int fill,
                    Color color) {
  canvas->FillRect(x, y, w, h, kTrack);
  // The last eighth (above -6 dB) turns red: close to the limiter.
  const int hot = w - w / 8;
  canvas->FillRect(x, y, fill < hot ? fill : hot, h, color);
  if (fill > hot) {
    canvas->FillRect(x + hot, y, fill - hot, h, kRed);
  }
}

// A bipolar source's position: a dot riding a centred line.
void DrawSourceMeter(Canvas* canvas, int x, int y, int w, int position,
                     bool bipolar, Color color) {
  canvas->FillRect(x, y, w, 1, kTrack);
  if (bipolar) {
    canvas->FillRect(x + w / 2, y - 3, 1, 7, kDim);
  }
  canvas->FillCircle(x + position, y, 3, color);
}

}  // namespace

void Ui::DrawGapA() {
  const int y0 = kGapTop[0];
  const int h = kGapBottom[0] - y0;
  const int dots_y = y0 + 35;
  Hash hash;
  hash.Int(page_);
  hash.Int(overlay_);
  if (overlay_ == OVERLAY_NONE && page_ == PAGE_HOME) {
    const int in = int(MeterFraction(app_->engine.input_level()) *
                       float(kMeterWidth));
    const int out = int(MeterFraction(app_->engine.output_level()) *
                        float(kMeterWidth));
    const bool midi = now_ms_ - midi_activity_ms_ < kMidiDotMs;
    hash.Int(in);
    hash.Int(out);
    hash.Int(cpu_percent_);
    hash.Int(midi);
    if (!Changed(REGION_GAP_A, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    // IN and OUT side by side on one line, CPU and MIDI under them.
    const int my = y0 + 9;
    canvas_->DrawText(kMargin, my, "IN", kFontSmall, kDim);
    DrawLevelMeter(canvas_, kInMeterX, my + 4, kMeterWidth, 4, in, kGold);
    canvas_->DrawText(kOutLabelX, my, "OUT", kFontSmall, kDim);
    DrawLevelMeter(canvas_, kRight - kMeterWidth, my + 4, kMeterWidth, 4, out,
                   kGold);
    const int sy = y0 + 26;
    char text[16] = "CPU ";
    AppendNumber(text, sizeof(text), float(cpu_percent_), 0, false, "%");
    canvas_->DrawText(kMargin, sy, text, kFontSmall, kDim);
    canvas_->DrawTextRight(kRight, sy, "MIDI", kFontSmall, kDim);
    const int dot_x = kRight - canvas_->TextWidth("MIDI", kFontSmall) - 7;
    canvas_->FillCircle(dot_x, sy + 5, 3, midi ? kGold : kTrack);
    return;
  }

  char title[24] = "";
  char subtitle[32] = "";
  Color title_color = kGold;
  Color subtitle_color = kDim;
  int dots = 0;
  int dot = 0;
  Color dot_color = kGold;
  int meter = -1;            // a live source under the title, MOD pages
  bool meter_bipolar = true;
  if (overlay_ == OVERLAY_MOD) {
    if (mod_slot_ < 0) {
      CopyText(title, sizeof(title), "WET");
      CopyText(subtitle, sizeof(subtitle), "MODULATION");
    } else {
      const Block* block = app_->engine.block(mod_slot_);
      CopyText(title, sizeof(title),
               block && mod_index_ < block->info().num_params
                   ? block->info().params[mod_index_].name : "MIX");
      CopyText(subtitle, sizeof(subtitle), block ? block->info().name : "");
      Append(subtitle, sizeof(subtitle), " \x04 MOD");
      subtitle_color = kSlotColor[mod_slot_];
    }
    title_color = kModColor;
  } else if (overlay_ == OVERLAY_SAVE) {
    CopyText(title, sizeof(title), "SAVE");
    CopyText(subtitle, sizeof(subtitle), "THE LIVE STATE TO A SLOT");
  } else if (overlay_ == OVERLAY_CALIBRATE) {
    CopyText(title, sizeof(title), "CV ZERO");
    CopyText(subtitle, sizeof(subtitle), "UNPLUG EVERY CV JACK");
  } else if (overlay_ == OVERLAY_RESTORE) {
    CopyText(title, sizeof(title), "RESTORE");
    title_color = kRed;
    CopyText(subtitle, sizeof(subtitle), "FACTORY PRESETS");
  } else if (page_ == PAGE_BLOCK) {
    const int slot = block_slot_;
    const Block* block = GetBlock(slot, ShownType(slot));
    CopyText(title, sizeof(title), block ? block->info().name : "");
    title_color = pending_type_[slot] >= 0 ? kWhite : kSlotColor[slot];
    if (shift_held_) {
      CopyText(subtitle, sizeof(subtitle), "TURN K1: TYPE");
      subtitle_color = kRed;
    } else {
      // "PITCH 1/2": the type's place in this slot's list.
      CopyText(subtitle, sizeof(subtitle), kSlotNames[slot]);
      Append(subtitle, sizeof(subtitle), " ");
      AppendNumber(subtitle, sizeof(subtitle), float(ShownType(slot) + 1), 0,
                   false, "/");
      AppendNumber(subtitle, sizeof(subtitle), float(NumBlockTypes(slot)), 0,
                   false, "");
      subtitle_color = kGrey;
    }
    dots = NumBlockPages(slot);
    dot = block_page_[slot];
    dot_color = kSlotColor[slot];
    hash.Int(slot);
  } else {
    CopyText(title, sizeof(title), kPageTitles[page_]);
    dots = NUM_CYCLE_PAGES;
    dot = page_;
    if (page_ == PAGE_MOD1) {
      CopyText(subtitle, sizeof(subtitle), "MOD 1");
      meter = Clamp(int((app_->mods.values().value[MOD_LFO1] + 1.0f) * 50.0f),
                    0, 100);
    } else if (page_ == PAGE_MOD2) {
      CopyText(subtitle, sizeof(subtitle), "MOD 2");
      meter = Clamp(int((app_->mods.values().value[MOD_RANDOM] + 1.0f) * 50.0f),
                    0, 100);
    } else if (page_ == PAGE_SENDS) {
      CopyText(subtitle, sizeof(subtitle), "GATE SOURCES");
    } else {
      CopyText(subtitle, sizeof(subtitle), "SETUP ");
      AppendNumber(subtitle, sizeof(subtitle), float(page_ - PAGE_SETUP1 + 1),
                   0, false, "/3");
    }
  }
  hash.Text(title);
  hash.Text(subtitle);
  hash.Int(title_color);
  hash.Int(subtitle_color);
  hash.Int(dots);
  hash.Int(dot);
  hash.Int(meter);
  if (!Changed(REGION_GAP_A, hash.h)) {
    return;
  }
  canvas_->FillRect(0, y0, kWidth, h, kBlack);
  DrawTitle(title, title_color, subtitle, subtitle_color);
  if (dots > 1) {
    DrawDots(canvas_, dots_y, dots, dot, dot_color);
  }
  if (meter >= 0) {
    // Right of the title: where the source is now.
    const int x =
        kMargin + canvas_->TextWidth(title, TitleFont(*canvas_, title)) + 12;
    const int w = kRight - 3 - x;
    DrawSourceMeter(canvas_, x, y0 + 6 + kFontLarge.ascent - 8, w,
                    meter * w / 100, meter_bipolar, kGold);
  }
}

// One slot in HOME's diagram: its short name in a box, filled while the
// send is on (and filled further with the slot's level).
void Ui::DrawSlotBox(int slot, int x, int y, int w, int h) {
  const Color color = kSlotColor[slot];
  const bool on = app_->engine.send_active(slot);
  const Block* block = GetBlock(slot, ShownType(slot));
  const char* name = block ? block->info().short_name : "";
  if (on) {
    canvas_->FillRoundRect(x, y, w, h, 3, BlendColor(kBlack, color, 56));
    // The slot's level fills the box from the left.
    const int level = int(MeterFraction(app_->engine.slot_level(slot)) *
                          float(w - 2) * 0.125f) * 8;
    if (level > 0) {
      canvas_->FillRect(x + 1, y + 1, level, h - 2,
                        BlendColor(kBlack, color, 110));
    }
    canvas_->DrawRoundRect(x, y, w, h, 3, color);
  } else {
    canvas_->DrawRoundRect(x, y, w, h, 3, BlendColor(kBlack, color, 96));
  }
  canvas_->SetClip(x + 1, y, w - 2, h);
  canvas_->DrawTextCentered(x + w / 2, y + h / 2 - kFontSmall.ascent + 4, name,
                            kFontSmall,
                            on ? kWhite : BlendColor(kBlack, color, 160));
  canvas_->ResetClip();
}

// A chain of four single slots (SERIAL). In one line each box would get
// 34 px, less than five letters of kFontSmall take (COMBS is 41 px), so the
// boxes zigzag over two lines instead, each overlapping the next by a few
// columns where a short line joins them: IN at the top left, OUT at the
// bottom right.
void Ui::DrawChain(const Topology& topology, int y0, int y1) {
  const int n = topology.num_stages;
  const int kEdge = 6;
  const int kBoxW = 50;
  const int kBoxH = 22;
  const int step = (kWidth - 2 * kEdge - kBoxW) / (n - 1);
  const int x_start = (kWidth - ((n - 1) * step + kBoxW)) / 2;
  const int gap = Clamp(y1 - y0 - 2 * kBoxH, 4, 10);
  const int top = (y0 + y1 - (2 * kBoxH + gap)) / 2;
  const int row_y[2] = { top, top + kBoxH + gap };
  const Color line = kDim;
  for (int s = 0; s < n; ++s) {
    const int slot = Clamp(topology.stage[s].branch[0].slot[0], 0,
                           NUM_SLOTS - 1);
    const int bx = x_start + s * step;
    const int by = row_y[s & 1];
    if (s == 0) {
      canvas_->DrawHLine(0, by + kBoxH / 2, bx, line);
    } else {
      // Down (or up) from the last box, in the columns the two share.
      const int x = (bx + (bx - step) + kBoxW) / 2;
      canvas_->DrawVLine(x, row_y[0] + kBoxH, gap, line);
    }
    if (s == n - 1) {
      canvas_->DrawHLine(bx + kBoxW, by + kBoxH / 2, kWidth - bx - kBoxW, line);
    }
    DrawSlotBox(slot, bx, by, kBoxW, kBoxH);
  }
}

void Ui::DrawDiagram(int y0, int y1) {
  const Preset& preset = app_->engine.preset();
  const Topology& topology =
      GetTopology(Clamp(preset.algorithm, 0, NUM_ALGORITHMS - 1));
  bool chain = !topology.dual_mono && topology.num_stages >= 4;
  for (int s = 0; s < topology.num_stages; ++s) {
    chain = chain && topology.stage[s].num_branches == 1 &&
            topology.stage[s].branch[0].length == 1;
  }
  if (chain) {
    DrawChain(topology, y0, y1);
    return;
  }
  const int kEdge = 6;
  const int kGapX = 7;
  int stage_col[4];
  int stage_width[4];
  int columns = 0;
  int max_rows = 1;
  for (int s = 0; s < topology.num_stages; ++s) {
    const Stage& stage = topology.stage[s];
    int w = 1;
    for (int b = 0; b < stage.num_branches; ++b) {
      if (stage.branch[b].length > w) {
        w = stage.branch[b].length;
      }
    }
    stage_col[s] = columns;
    stage_width[s] = w;
    columns += w;
    if (stage.num_branches > max_rows) {
      max_rows = stage.num_branches;
    }
  }
  if (columns == 0) {
    return;
  }
  const int kGapY = max_rows > 3 ? 2 : 4;
  const int box_w = (kWidth - 2 * kEdge - (columns - 1) * kGapX) / columns;
  int box_h = (y1 - y0 - (max_rows - 1) * kGapY) / max_rows;
  if (box_h > 22) {
    box_h = 22;
  }
  const int x_start = (kWidth - (columns * box_w + (columns - 1) * kGapX)) / 2;
  const int cy = (y0 + y1) / 2;
  const Color line = kDim;
  for (int s = 0; s < topology.num_stages; ++s) {
    const Stage& stage = topology.stage[s];
    const int nb = stage.num_branches;
    const int total = nb * box_h + (nb - 1) * kGapY;
    const int xl = s == 0
        ? 0
        : x_start + stage_col[s] * (box_w + kGapX) - kGapX / 2 - 1;
    const int xr = s == topology.num_stages - 1
        ? kWidth - 1
        : x_start + (stage_col[s] + stage_width[s] - 1) * (box_w + kGapX) +
              box_w + kGapX / 2;
    int y_min = cy;
    int y_max = cy;
    for (int b = 0; b < nb; ++b) {
      const Branch& branch = stage.branch[b];
      const int by = cy - total / 2 + b * (box_h + kGapY);
      const int yc = by + box_h / 2;
      y_min = yc < y_min ? yc : y_min;
      y_max = yc > y_max ? yc : y_max;
      int x_prev = xl;
      for (int p = 0; p < branch.length; ++p) {
        const int slot = Clamp(branch.slot[p], 0, NUM_SLOTS - 1);
        const int bx = x_start + (stage_col[s] + p) * (box_w + kGapX);
        canvas_->DrawHLine(x_prev, yc, bx - x_prev, line);
        x_prev = bx + box_w;
        DrawSlotBox(slot, bx, by, box_w, box_h);
      }
      if (topology.dual_mono) {
        canvas_->DrawHLine(x_prev, yc, kWidth - x_prev, line);
      } else {
        canvas_->DrawHLine(x_prev, yc, xr - x_prev + 1, line);
      }
    }
    if (!topology.dual_mono) {
      canvas_->DrawVLine(xl, y_min, y_max - y_min + 1, line);
      canvas_->DrawVLine(xr, y_min, y_max - y_min + 1, line);
    }
  }
  if (!topology.dual_mono) {
    // IN and OUT: short stubs on the edges.
    canvas_->DrawHLine(0, cy, 1, line);
  }
}

void Ui::DrawGapB() {
  const int y0 = kGapTop[1];
  const int h = kGapBottom[1] - y0;
  Hash hash;
  hash.Int(page_);
  hash.Int(overlay_);
  if (overlay_ == OVERLAY_NONE && page_ == PAGE_HOME) {
    const Preset& preset = app_->engine.preset();
    hash.Int(preset.algorithm);
    for (int slot = 0; slot < NUM_SLOTS; ++slot) {
      hash.Int(app_->engine.send_active(slot));
      hash.Int(ShownType(slot));
      if (app_->engine.send_active(slot)) {
        hash.Int(int(MeterFraction(app_->engine.slot_level(slot)) * 16.0f));
      }
    }
    if (!Changed(REGION_GAP_B, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    DrawDiagram(y0 + 2, kGapBottom[1] - 2);
    return;
  }
  if (overlay_ == OVERLAY_NONE && page_ == PAGE_BLOCK) {
    const int slot = block_slot_;
    const int level =
        int(MeterFraction(app_->engine.slot_level(slot)) * 128.0f);
    const int gate = app_->engine.preset().slot[slot].send_gate;
    const bool on = app_->engine.send_active(slot);
    const int load =
        Clamp(int(app_->engine.slot_load(slot) * 100.0f + 0.5f), 0, 99);
    hash.Int(slot);
    hash.Int(level);
    hash.Int(gate);
    hash.Int(on);
    hash.Int(load);
    if (!Changed(REGION_GAP_B, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    const Color color = kSlotColor[slot];
    canvas_->DrawText(kMargin, y0 + 8, "LEVEL", kFontSmall, kDim);
    DrawLevelMeter(canvas_, 42, y0 + 12, 124, 4, level * 124 / 128, color);
    // The send and its gate can take the whole line ("SEND OFF . GATE
    // NOTE" is ~135 px): the slot's CPU gets a line of its own.
    char text[24];
    CopyText(text, sizeof(text), on ? "SEND ON" : "SEND OFF");
    if (gate != MOD_OFF) {
      Append(text, sizeof(text), " \x04 GATE ");
      Append(text, sizeof(text), kModSourceNames[gate]);
    }
    canvas_->DrawText(kMargin, y0 + 24, text, kFontSmall, on ? color : kDim);
    char cpu[16] = "CPU ";
    AppendNumber(cpu, sizeof(cpu), float(load), 0, false, "%");
    canvas_->DrawTextRight(kRight, y0 + 40, cpu, kFontSmall, kDim);
    return;
  }
  if (overlay_ == OVERLAY_MOD) {
    // The source itself, moving: what the depth scales.
    const int source = Mod(mod_slot_, mod_index_).source;
    const bool bipolar = SourceBipolar(source);
    const float v = app_->mods.values().value[source];
    const int position = bipolar ? Clamp(int((v + 1.0f) * 50.0f), 0, 100)
                                 : Clamp(int(v * 100.0f), 0, 100);
    hash.Int(source);
    hash.Int(position);
    if (!Changed(REGION_GAP_B, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    const int cy = (y0 + kGapBottom[1]) / 2;
    if (source == MOD_OFF) {
      canvas_->DrawTextCentered(kWidth / 2, cy - 6, "TURN K2: A SOURCE",
                                kFontSmall, kDim);
    } else {
      const int x = canvas_->DrawText(kMargin, cy - 6, kModSourceNames[source],
                                      kFontSmall, kModColor) + 10;
      const int w = kRight - 3 - x;
      DrawSourceMeter(canvas_, x, cy, w, position * w / 100, bipolar,
                      kModColor);
    }
    return;
  }
  const char* line1 = "";
  const char* line2 = "";
  Color color = kDim;
  if (overlay_ == OVERLAY_CALIBRATE) {
    line1 = "PUSH ANY KNOB";
    line2 = "TO TAKE THESE AS 0 V";
  } else if (overlay_ == OVERLAY_RESTORE) {
    line1 = "EVERY SAVED PRESET";
    line2 = "IS REPLACED";
    color = kRed;
  } else if (overlay_ == OVERLAY_NONE && page_ == PAGE_SENDS) {
    line1 = "A GATE FLIPS ITS SEND";
    line2 = "PUSH: SEND ON / OFF";
  }
  hash.Text(line1);
  hash.Text(line2);
  if (!Changed(REGION_GAP_B, hash.h)) {
    return;
  }
  canvas_->FillRect(0, y0, kWidth, h, kBlack);
  const int cy = (y0 + kGapBottom[1]) / 2;
  canvas_->DrawTextCentered(kWidth / 2, cy - 13, line1, kFontSmall, color);
  canvas_->DrawTextCentered(kWidth / 2, cy + 2, line2, kFontSmall, color);
}

void Ui::DrawGapC() {
  const int y0 = kGapTop[2];
  const int h = kGapBottom[2] - y0;
  Hash hash;
  hash.Int(page_);
  hash.Int(overlay_);
  if (overlay_ == OVERLAY_NONE && page_ == PAGE_HOME) {
    for (int slot = 0; slot < NUM_SLOTS; ++slot) {
      hash.Int(app_->engine.send_active(slot));
      hash.Int(ShownType(slot));
    }
    if (!Changed(REGION_GAP_C, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    for (int slot = 0; slot < NUM_SLOTS; ++slot) {
      const int y = y0 + 1 + slot * 12;
      const Color color = kSlotColor[slot];
      const bool on = app_->engine.send_active(slot);
      if (on) {
        canvas_->FillCircle(kMargin + 3, y + 6, 3, color);
      } else {
        canvas_->DrawCircle(kMargin + 3, y + 6, 3,
                            BlendColor(kBlack, color, 110));
      }
      canvas_->DrawText(kMargin + 11, y, kSlotNames[slot], kFontSmall,
                        BlendColor(kBlack, color, on ? 255 : 150));
      const Block* block = GetBlock(slot, ShownType(slot));
      canvas_->DrawTextRight(kRight, y, block ? block->info().name : "",
                             kFontSmall, on ? kWhite : kGrey);
    }
    return;
  }
  const bool mod1 = overlay_ == OVERLAY_NONE && page_ == PAGE_MOD1;
  const bool mod2 = overlay_ == OVERLAY_NONE && page_ == PAGE_MOD2;
  if (mod1 || mod2) {
    // The second source of the page, under its own heading.
    const float v = app_->mods.values().value[mod1 ? MOD_LFO2 : MOD_ENVELOPE];
    const int position = mod1 ? Clamp(int((v + 1.0f) * 50.0f), 0, 100)
                               : Clamp(int(v * 100.0f), 0, 100);
    hash.Int(position);
    if (!Changed(REGION_GAP_C, hash.h)) {
      return;
    }
    canvas_->FillRect(0, y0, kWidth, h, kBlack);
    // A section title like gap A's, so both sources read alike.
    const char* title = mod1 ? "LFO 2" : "ENVELOPE";
    const int ty = y0 + 16;
    canvas_->DrawText(kMargin, ty, title, kFontLarge, kGold);
    const int x = kMargin + canvas_->TextWidth(title, kFontLarge) + 12;
    const int w = kRight - 3 - x;
    DrawSourceMeter(canvas_, x, ty + kFontLarge.ascent - 8, w,
                    position * w / 100, mod1, kGold);
    return;
  }
  const char* hint = "";
  if (overlay_ == OVERLAY_MOD) {
    hint = "PUSH: DONE";
  } else if (overlay_ == OVERLAY_SAVE) {
    hint = "K2 MOVES \x04 K3 CHANGES";
  } else if (overlay_ == OVERLAY_CALIBRATE) {
    hint = "SHIFT: CANCEL";
  } else if (overlay_ == OVERLAY_RESTORE) {
    hint = "SHIFT: CANCEL";
  } else if (page_ == PAGE_BLOCK) {
    hint = shift_held_ ? "PUSH: SYNC \x04 SEND: PAGE" : "PUSH: MODULATE";
  }
  hash.Text(hint);
  if (!Changed(REGION_GAP_C, hash.h)) {
    return;
  }
  canvas_->FillRect(0, y0, kWidth, h, kBlack);
  canvas_->DrawTextCentered(kWidth / 2, (y0 + kGapBottom[2]) / 2 - 6, hint,
                            kFontSmall, kDim);
}

void Ui::DrawMessage() {
  Hash hash;
  hash.Text(message_);
  if (!Changed(REGION_MESSAGE, hash.h)) {
    return;
  }
  const int x = 10;
  const int w = kWidth - 2 * x;
  canvas_->FillRect(0, kMessageY - 2, kWidth, kMessageHeight + 4, kBlack);
  canvas_->FillRoundRect(x, kMessageY, w, kMessageHeight, 6, kGoldDark);
  canvas_->DrawRoundRect(x, kMessageY, w, kMessageHeight, 6, kGold);
  const Font& font = canvas_->TextWidth(message_, kFontMedium) > w - 12
      ? kFontSmall : kFontMedium;
  canvas_->DrawTextCentered(kWidth / 2,
                            kMessageY + kMessageHeight / 2 - font.ascent +
                                (font.ascent * 11 / 12) / 2,
                            message_, font, kWhite);
}

}  // namespace sidefx
