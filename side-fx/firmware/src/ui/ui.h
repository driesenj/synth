// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the screen and what the knobs and buttons do with it.
//
// Pages (SHIFT tapped alone steps HOME > MOD 1 > MOD 2 > SENDS > SETUP 1..3
// > HOME; from a block page it returns HOME):
//   HOME       K1 PRESET (push: load), K2 ALGORITHM, K3 WET (push: its
//              modulation), K4 TEMPO (push: tap); SHIFT + push K1: save
//              into the selected slot. The algorithm diagram, each block's
//              type and send, meters, CPU.
//   BLOCK x4   SHIFT + a send button opens that slot's page; again flips
//              its parameter pages (four rows each, MIX the last row of the
//              last page). SHIFT + turn K1: the block type. Push a knob:
//              that row's modulation (source, depth); SHIFT + push: sync on
//              or off for a time / rate.
//   MOD 1      LFO1 RATE, LFO1 SHAPE, LFO2 RATE, LFO2 SHAPE (push a RATE:
//              sync)
//   MOD 2      RND RATE, RND SMOOTH, ENV ATTACK, ENV RELEASE; push K4 to
//              swap the last row between RELEASE and GAIN
//   SENDS      each slot's send gate source (push: the send on / off)
//   SETUP 1    AUDIO: DRY, IN GAIN, OUT GAIN, OUT POLARITY
//   SETUP 2    MIDI: MIDI CH, CC A, CC B, CLOCK PPQN
//   SETUP 3    PANEL: BRIGHTNESS, FLIP, ENCODER (taken over once K3 has
//              rested a second), TOOLS (turn: CV ZERO or
//              FACTORY, push: start, with a confirmation)
//
// Rows line up with the knobs beside the screen: K1..K4 sit at about
// y = 14, 111, 209, 306 px (see kKnobRowY in ui.cc).

#ifndef SIDEFX_UI_UI_H_
#define SIDEFX_UI_UI_H_

#include <stddef.h>
#include <stdint.h>

#include "app/app.h"
#include "app/controls.h"
#include "engine/algorithm.h"
#include "gfx/canvas.h"

namespace sidefx {

class Ui {
 public:
  Ui() { }
  ~Ui() { }

  // cpu_load: the audio callback's share of its period, 0..1, or NULL.
  void Init(App* app, Canvas* canvas, float (*cpu_load)());

  void OnEvent(const Event& event);

  // Main loop: timers, then redraws what changed (only while the display
  // is not busy sending the previous frame).
  void Poll(uint32_t now_ms);

  // A line of text over the page for a while ("SAVED 12").
  void ShowMessage(const char* text, uint32_t duration_ms);

 private:
  enum Page {
    PAGE_HOME,
    PAGE_MOD1,
    PAGE_MOD2,
    PAGE_SENDS,
    PAGE_SETUP1,
    PAGE_SETUP2,
    PAGE_SETUP3,
    NUM_CYCLE_PAGES,  // the pages SHIFT steps through
    PAGE_BLOCK = NUM_CYCLE_PAGES,
  };

  enum Overlay {
    OVERLAY_NONE,
    OVERLAY_MOD,  // one value's modulation
    OVERLAY_SAVE,
    OVERLAY_CALIBRATE,
    OVERLAY_RESTORE,
  };

  // The screen's areas: one per knob row, the three gaps between them and
  // the message box. Each is redrawn only when what it shows changes.
  enum Region {
    REGION_ROW1,
    REGION_ROW2,
    REGION_ROW3,
    REGION_ROW4,
    REGION_GAP_A,  // K1..K2: the title (HOME: meters)
    REGION_GAP_B,  // K2..K3: HOME's diagram; messages cover it
    REGION_GAP_C,  // K3..K4
    REGION_MESSAGE,
    NUM_REGIONS
  };

  struct RowView;

  // Input.
  void OnShiftTap();
  void OnSendPress(int slot, bool shift, bool handled);
  void OnPush(int knob, bool shift, uint32_t time_us);
  void OnTurn(int knob, int delta, bool shift, uint32_t time_ms);
  int Acceleration(int knob, int delta, uint32_t time_ms);
  void TurnHome(int knob, int delta, int steps, bool shift);
  void TurnValue(int slot, int index, int delta, int steps);
  void TurnModOverlay(int knob, int delta, int steps);
  void TurnSetting(int row, int delta, int steps);
  void TurnSave(int knob, int delta, int steps);
  void ApplyEncoderMode();
  void OpenPage(int page);
  void OpenOverlay(int overlay);
  void OpenModOverlay(int slot, int index);
  void DoSave();
  void DoCalibrate();
  void DoRestore();
  void Edited();

  // Where things are.
  int NumBlockPages(int slot) const;
  int ParamAt(int slot, int page, int row) const;  // -1: an empty row
  int ShownType(int slot) const;

  // Drawing.
  void Draw();
  void Invalidate();
  bool Changed(int region, uint32_t key);
  void BuildRow(int row, RowView* view);
  void BuildHomeRow(int row, RowView* view);
  void BuildValueRow(int slot, int index, RowView* view);
  void BuildModRow(int row, RowView* view);
  void BuildSourcesRow(int row, RowView* view);
  void BuildSettingRow(int row, RowView* view);
  void BuildSaveRow(int row, RowView* view);
  void BuildOtherRow(int row, RowView* view);
  void DrawRow(int row, const RowView& view);
  void DrawGapA();
  void DrawGapB();
  void DrawGapC();
  void DrawMessage();
  void DrawTitle(const char* title, uint16_t title_color,
                 const char* subtitle, uint16_t subtitle_color);
  void DrawDiagram(int y0, int y1);
  void DrawChain(const Topology& topology, int y0, int y1);
  void DrawSlotBox(int slot, int x, int y, int w, int h);
  void FormatValue(int slot, int index, float value, char* text, size_t size);
  float RawValue(int slot, int index) const;
  float LiveValue(int slot, int index) const;
  const ModAssign& Mod(int slot, int index) const;
  uint16_t Accent() const;

  App* app_;
  Canvas* canvas_;
  float (*cpu_load_)();

  uint8_t page_;
  uint8_t overlay_;
  uint8_t block_slot_;
  uint8_t block_page_[4];

  // OVERLAY_MOD: the value (slot, index); slot -1 is HOME's WET.
  int8_t mod_slot_;
  int8_t mod_index_;

  // HOME's K1 browses the bank; a push loads.
  int8_t browse_;
  bool browsing_;
  uint32_t browse_ms_;

  int8_t save_slot_;
  int8_t save_cursor_;
  char save_name_[16];

  bool restore_yes_;
  uint8_t tool_;       // SETUP 3's last row: 0 CV CALIBRATE, 1 RESTORE
  bool env_gain_row_;  // MOD 2's last row shows ENV GAIN instead of RELEASE

  int8_t pending_type_[4];  // SHIFT + K1 on a block page; -1: none
  uint32_t pending_type_ms_[4];

  // SETUP 3's ENCODER row: the mode being picked, applied once the knob
  // rests (it changes how that knob itself counts); -1: none.
  int8_t pending_encoder_;
  uint32_t pending_encoder_ms_;

  bool shift_held_;
  bool shift_used_;  // a knob or button was used while SHIFT was down

  uint32_t last_turn_ms_[4];
  int8_t last_turn_dir_[4];

  char message_[24];
  uint32_t message_until_ms_;
  bool message_active_;

  uint32_t region_key_[NUM_REGIONS];
  uint16_t region_valid_;  // bit per region: region_key_ is on screen

  uint32_t now_ms_;
  uint32_t last_draw_ms_;
  uint32_t cpu_ms_;
  uint8_t cpu_percent_;
  uint32_t midi_messages_;
  uint32_t midi_activity_ms_;
};

}  // namespace sidefx

#endif  // SIDEFX_UI_UI_H_
