// Plaitsy host tests, groups 3, 4 and 5: navigation, the board tables,
// calibration.

#include "port_test.h"

namespace test {

using namespace plaits;
using plaitsy::hal::AdcInput;

namespace {

int Mode(Rig& rig) { return rig.ui().mode_; }
bool Alt(Rig& rig) { return rig.ui().enable_alt_navigation_; }

const char* ModeName(int mode) {
  switch (mode) {
    case UI_MODE_NORMAL: return "normal";
    case UI_MODE_DISPLAY_ALTERNATE_PARAMETERS: return "display LPG settings";
    case UI_MODE_DISPLAY_OCTAVE: return "display octave range";
    case UI_MODE_DISPLAY_DATA_TRANSFER_PROGRESS: return "data transfer";
    case UI_MODE_CALIBRATION_C1: return "calibration C1";
    case UI_MODE_CALIBRATION_C3: return "calibration C3";
    case UI_MODE_TEST: return "test";
    case UI_MODE_ERROR: return "error";
  }
  return "?";
}

std::string Join(const std::vector<int>& v) {
  std::string s;
  for (size_t i = 0; i < v.size(); ++i) {
    s += (i ? " " : "") + std::to_string(v[i]);
  }
  return s;
}

std::vector<int> Taps(Rig* rig, int button, int count) {
  std::vector<int> engines;
  for (int i = 0; i < count; ++i) {
    rig->Tap(button);
    engines.push_back(rig->patch.engine);
  }
  return engines;
}

// The gesture: hold `held`, tap the other, release `held`.
void ToggleGesture(Rig* rig, int held) {
  rig->Press(held);
  rig->RunMs(300.0);
  rig->Tap(1 - held, 80.0, 150.0);
  rig->Release(held);
  rig->RunMs(150.0);
}

std::string ExpectedRowPattern(int engine) {
  std::string s(8, 'o');
  const char bank_colour[3] = { 'Y', 'G', 'R' };
  s[engine % 8] = bank_colour[engine / 8];
  return s;
}

}  // namespace

// ====================================================================== 3
void TestNavigation() {
  Section("3. Navigation: classic (Plaits 1.0/1.1) and 2022 (Plaits 1.2)");
  fake::ResetBoard();
  FreshFlash();
  fake::SetButtonBounceUs(3000.0);
  Rig rig;
  rig.Boot();
  rig.RunMs(500.0);  // the pots' filters settle
  LedObservation o = ObserveLeds(&rig, 64.0);
  Check("nav: boots in the classic navigation on engine 8 (green 1)",
        rig.patch.engine == 8 && !Alt(rig), "engine %d, alt %d",
        rig.patch.engine, Alt(rig));
  Check("nav: power-up LEDs: D1 green, button LEDs off",
        o.Pattern() == "Gooooooo" && !fake::button_led(0) &&
        !fake::button_led(1), "LEDs %s, button LEDs %d %d",
        o.Pattern().c_str(), fake::button_led(0), fake::button_led(1));

  std::vector<int> seq = Taps(&rig, 0, 9);
  Check("nav classic: left steps through the green bank, wrapping",
        seq == std::vector<int>({ 9, 10, 11, 12, 13, 14, 15, 8, 9 }),
        "%s", Join(seq).c_str());
  o = ObserveLeds(&rig, 64.0);
  Check("nav classic: engine 9 lights D2 green", o.Pattern() == "oGoooooo",
        "%s", o.Pattern().c_str());
  seq = Taps(&rig, 1, 9);
  Check("nav classic: right goes to the red bank, same row, then steps",
        seq == std::vector<int>({ 17, 18, 19, 20, 21, 22, 23, 16, 17 }),
        "%s", Join(seq).c_str());
  o = ObserveLeds(&rig, 64.0);
  Check("nav classic: engine 17 lights D2 red", o.Pattern() == "oRoooooo",
        "%s", o.Pattern().c_str());
  seq = Taps(&rig, 0, 1);
  Check("nav classic: left from the red bank goes to the green row",
        seq == std::vector<int>({ 9 }), "%s", Join(seq).c_str());
  Check("nav classic: button LEDs stay off",
        !fake::button_led(0) && !fake::button_led(1), "%d %d",
        fake::button_led(0), fake::button_led(1));

  // Hold right, tap left: the 2022 navigation.
  int before = rig.patch.engine;
  ToggleGesture(&rig, 1);
  Check("nav: hold right + tap left switches to the 2022 navigation",
        Alt(rig) && rig.patch.engine == before,
        "alt %d, engine %d (was %d)", Alt(rig), rig.patch.engine, before);
  Check("nav: both button LEDs lit in the 2022 navigation",
        fake::button_led(0) && fake::button_led(1), "%d %d",
        fake::button_led(0), fake::button_led(1));
  seq = Taps(&rig, 1, 16);
  Check("nav 2022: right steps forward through all 24, yellow bank included",
        seq == std::vector<int>({ 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                                  21, 22, 23, 0, 1 }), "%s", Join(seq).c_str());
  o = ObserveLeds(&rig, 64.0);
  Check("nav 2022: engine 1 (yellow 2) lights D2 yellow",
        o.Pattern() == "oYoooooo", "%s", o.Pattern().c_str());
  seq = Taps(&rig, 0, 3);
  Check("nav 2022: left steps backward, wrapping",
        seq == std::vector<int>({ 0, 23, 22 }), "%s", Join(seq).c_str());

  // Hold left, tap right: back to classic.
  before = rig.patch.engine;
  ToggleGesture(&rig, 0);
  Check("nav: hold left + tap right switches back to the classic navigation",
        !Alt(rig) && rig.patch.engine == before,
        "alt %d, engine %d (was %d)", Alt(rig), rig.patch.engine, before);
  Check("nav: button LEDs off again", !fake::button_led(0) &&
        !fake::button_led(1), "%d %d", fake::button_led(0),
        fake::button_led(1));

  // Classic from a yellow model.
  ToggleGesture(&rig, 1);
  Taps(&rig, 1, 5);  // 22 -> 23 0 1 2 3
  ToggleGesture(&rig, 0);
  const int yellow = rig.patch.engine;
  seq = Taps(&rig, 0, 1);
  std::vector<int> seq2 = Taps(&rig, 1, 1);
  Check("nav classic from a yellow model: left/right go to its green/red row",
        yellow == 3 && !Alt(rig) && seq == std::vector<int>({ 11 }) &&
        seq2 == std::vector<int>({ 19 }),
        "on %d: left -> %s, right -> %s", yellow, Join(seq).c_str(),
        Join(seq2).c_str());

  // Long presses.
  before = rig.patch.engine;
  rig.Press(0);
  rig.RunMs(2050.0);
  int mode = Mode(rig);
  o = ObserveLeds(&rig, 64.0);
  rig.Release(0);
  rig.RunMs(100.0);
  Check("nav: left held 2 s shows the LPG colour / decay (D7, D8 for decay "
        "0.5), model unchanged",
        mode == UI_MODE_DISPLAY_ALTERNATE_PARAMETERS &&
        o.Pattern() == "ooooooYY" && rig.patch.engine == before &&
        Mode(rig) == UI_MODE_NORMAL,
        "mode %s, LEDs %s, engine %d -> %d, then %s", ModeName(mode),
        o.Pattern().c_str(), before, rig.patch.engine, ModeName(Mode(rig)));
  rig.Press(1);
  rig.RunMs(2050.0);
  mode = Mode(rig);
  o = ObserveLeds(&rig, 64.0);
  rig.Release(1);
  rig.RunMs(100.0);
  Check("nav: right held 2 s shows the octave range (all yellow: full "
        "range), model unchanged",
        mode == UI_MODE_DISPLAY_OCTAVE && o.Pattern() == "YYYYYYYY" &&
        rig.patch.engine == before && Mode(rig) == UI_MODE_NORMAL,
        "mode %s, LEDs %s, engine %d -> %d, then %s", ModeName(mode),
        o.Pattern().c_str(), before, rig.patch.engine, ModeName(Mode(rig)));
  rig.Press(0);
  rig.RunMs(1500.0);
  rig.Release(0);
  rig.RunMs(100.0);
  Check("nav: left held 1.5 s still navigates on release (as on Plaits)",
        rig.patch.engine == (before / 8 == 1 ? 8 + (before + 1) % 8
                                              : 8 + before % 8),
        "engine %d -> %d", before, rig.patch.engine);

  // Both held 2 s: calibration.
  before = rig.patch.engine;
  rig.Press(0);
  rig.Press(1);
  rig.RunMs(2050.0);
  mode = Mode(rig);
  const int probe_writes = fake::probe_writes();
  o = ObserveLeds(&rig, 128.0);
  const bool quiet = fake::probe_writes() == probe_writes &&
      !fake::ProbeAt(fake::TimeUs());
  rig.Release(0);
  rig.Release(1);
  rig.RunMs(150.0);
  Check("nav: both held 2 s start the calibration (D1 blinking green, probe "
        "held low)",
        mode == UI_MODE_CALIBRATION_C1 && Mode(rig) == UI_MODE_CALIBRATION_C1 &&
        o.Pattern() == "gooooooo" && quiet && rig.patch.engine == before,
        "mode %s, LEDs %s, probe %s, engine %d -> %d", ModeName(mode),
        o.Pattern().c_str(), quiet ? "low and still" : "MOVING",
        before, rig.patch.engine);
  rig.Tap(0);  // C1 at 0 V
  const int m3 = Mode(rig);
  rig.Tap(0);  // C3 at 0 V: not 2 V apart
  const int me = Mode(rig);
  o = ObserveLeds(&rig, 128.0);
  rig.Tap(0);
  Check("nav: calibration with no voltage change ends in the error display, "
        "a press leaves it",
        m3 == UI_MODE_CALIBRATION_C3 && me == UI_MODE_ERROR &&
        o.Pattern() == "rrrrrrrr" && Mode(rig) == UI_MODE_NORMAL &&
        rig.patch.engine == before,
        "%s, %s (LEDs %s), then %s, engine %d", ModeName(m3), ModeName(me),
        o.Pattern().c_str(), ModeName(Mode(rig)), rig.patch.engine);

  // README: "hold either button and tap the other".
  {
    bool ok = true;
    std::string detail;
    for (int held = 0; held < 2; ++held) {
      for (int round = 0; round < 2; ++round) {
        FreshFlash();
        Rig r;
        r.Boot();
        r.RunMs(300.0);
        const int e0 = r.patch.engine;
        const bool a0 = Alt(r);
        r.Press(held);
        r.RunMs(200.0 + 300.0 * round);
        r.Tap(1 - held, 60.0 + 90.0 * round, 40.0 + 200.0 * round);
        r.Release(held);
        r.RunMs(150.0);
        const bool toggled = Alt(r) != a0;
        const bool moved = r.patch.engine != e0;
        ok = ok && toggled && !moved;
        char cell[64];
        snprintf(cell, sizeof(cell), " hold %s/%d: %s%s", held ? "R" : "L",
                 round, toggled ? "toggle" : "no toggle",
                 moved ? " +MOVE" : "");
        detail += cell;
      }
    }
    Check("nav: README's \"hold either button and tap the other\" switches "
          "the navigation without changing the model", ok, "%s",
          detail.c_str());
    // README: "within two seconds" (after 2 s the held button shows its
    // hidden settings and the gesture no longer switches; Plaits' code).
    FreshFlash();
    Rig r;
    r.Boot();
    r.RunMs(300.0);
    const bool a0 = Alt(r);
    r.Press(0);
    r.RunMs(2100.0);
    r.Tap(1, 80.0, 150.0);
    r.Release(0);
    r.RunMs(150.0);
    Check("nav: README's \"within two seconds\": a first button held 2.1 s "
          "does not switch the navigation", Alt(r) == a0, "alt %d -> %d, "
          "engine %d", a0, Alt(r), r.patch.engine);
  }

  // Letting go of both buttons at nearly the same time (upstream behaviour,
  // documented in the README).
  {
    fake::SetButtonBounceUs(0.0);
    std::string table;
    int worst_toggle_skew = -1;
    bool all_toggle = true;
    const int skews[] = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 40 };
    for (int first = 0; first < 2; ++first) {
      for (int skew : skews) {
        FreshFlash();
        Rig r;
        r.Boot();
        r.RunMs(300.0);
        const int e0 = r.patch.engine;
        const bool a0 = Alt(r);
        r.Press(0);
        r.Press(1);
        r.RunMs(150.0);
        r.Release(first);
        r.RunMs(skew);
        r.Release(1 - first);
        r.RunMs(150.0);
        const bool toggled = Alt(r) != a0;
        const bool moved = r.patch.engine != e0;
        char cell[48];
        if (moved) {
          snprintf(cell, sizeof(cell), " %s%dms:%s%d->%d", first ? "R" : "L",
                   skew, toggled ? "toggle+MOVE " : "MOVE ", e0,
                   r.patch.engine);
        } else {
          snprintf(cell, sizeof(cell), " %s%dms:%s", first ? "R" : "L", skew,
                   toggled ? "toggle" : "nothing");
        }
        table += cell;
        if (!toggled || moved) {
          all_toggle = false;
          worst_toggle_skew = std::max(worst_toggle_skew, skew);
        }
      }
    }
    Note("both buttons pressed together, released with a skew (first-released "
         "button, skew: outcome; all toggle: %s):%s", all_toggle ? "yes" : "no",
         table.c_str());
    Observe("the navigation switch needs the second button held >= %d ms "
            "after the first is released (Plaits 1.2 behaves the same: the "
            "release is seen 7 debounce reads late and press_time_ of the "
            "other button must still be counting); released closer together, "
            "the first-released button changes the model instead",
            worst_toggle_skew + 1);
    fake::SetButtonBounceUs(3000.0);
  }

  // Persistence.
  {
    fake::ResetBoard();
    FreshFlash();
    fake::SetButtonBounceUs(3000.0);
    Rig a;
    a.Boot();
    a.RunMs(300.0);
    Taps(&a, 0, 5);  // 8 -> 13
    ToggleGesture(&a, 1);
    a.RunMs(20.0);
    const int writes_early = fake::flash_stats().write_calls;
    a.RunMs(5100.0);  // saved once nothing has changed for 5 s
    const bool dirty = a.settings().dirty_;
    const int writes = fake::flash_stats().write_calls;
    Rig b;
    const bool loaded = b.Boot();
    // Let the pots' filters settle: they start from 0 at Init(), and while
    // they rise a held button engages the pots' hidden parameters (as on
    // Plaits), which would swallow the first tap.
    b.RunMs(500.0);
    Check("nav: model and navigation saved (one write, 5 s after the last "
          "change) and restored at power-up",
          writes_early == 0 && !dirty && writes == 1 && loaded &&
          b.patch.engine == 13 && Alt(b) && fake::button_led(0) &&
          fake::button_led(1),
          "flash writes %d during the presses, %d after; dirty %d; reloaded "
          "%d: engine %d, alt %d, button LEDs %d %d", writes_early, writes,
          dirty, loaded, b.patch.engine, Alt(b), fake::button_led(0),
          fake::button_led(1));
    Taps(&b, 0, 10);  // 13 -> 3
    ToggleGesture(&b, 0);
    b.RunMs(5100.0);
    Rig c;
    c.Boot();
    c.RunMs(500.0);
    Check("nav: a yellow model saved with the classic navigation comes back "
          "in the 2022 one (Plaits' rule)",
          b.patch.engine == 3 && !Alt(b) && c.patch.engine == 3 && Alt(c) &&
          c.settings().state().enable_alt_navigation == 0 &&
          fake::button_led(0),
          "saved engine %d alt %d; restored engine %d alt %d (stored flag %d)",
          b.patch.engine, Alt(b), c.patch.engine, Alt(c),
          c.settings().state().enable_alt_navigation);
  }

  // Colour-blind toggle: the right button held at power-up (Plaits').
  {
    fake::ResetBoard();
    FreshFlash();
    fake::SetMuxChannel(board::kPotMuxChannel[POTS_ADC_CHANNEL_HARMONICS_POT],
                        0.3);
    fake::SetButton(plaitsy::hal::BUTTON_B, true);
    Rig d;
    d.Boot();
    const int e0 = d.patch.engine;
    const float octave0 = d.ui().octave_;
    d.RunMs(800.0);
    const int held_mode = Mode(d);
    d.Release(1);
    d.RunMs(5200.0);
    Rig e;
    e.Boot();
    e.RunMs(20.0);
    Check("nav: right held at power-up toggles the colour-blind mode, saved",
          e.settings().state().color_blind == 1, "color_blind %d",
          e.settings().state().color_blind);
    Observe("right held at power-up (colour-blind toggle), HARMONICS at 30 %%: "
            "while held the UI is in '%s' and the octave range follows "
            "HARMONICS (%.3f -> %.3f), because the pots' filters start at 0 "
            "and rise past the 0.03 lock threshold; on release the model "
            "stays %d -> %d. Same code as Plaits 1.2 (its pot filters also "
            "start at 0)", ModeName(held_mode), octave0, d.ui().octave_, e0,
            d.patch.engine);
  }
}

// ====================================================================== 4
void TestBoardTables() {
  Section("4. LED bits and pot channels against circuit.py");
  fake::ResetBoard();
  Leds leds;
  leds.Init();
  uint32_t used = 0;
  bool distinct = true;
  for (int i = 0; i < kNumLEDs; ++i) {
    const uint32_t colours[3] = { LED_COLOR_RED, LED_COLOR_GREEN,
                                  LED_COLOR_YELLOW };
    bool ok = true;
    std::string detail;
    for (uint32_t colour : colours) {
      leds.Clear();
      leds.set(i, colour);
      leds.Write();
      const uint16_t word = fake::led_word_written();
      uint16_t want = 0;
      if (colour & LED_COLOR_RED) want |= 1u << board::kLedRedBit[i];
      if (colour & LED_COLOR_GREEN) want |= 1u << board::kLedGreenBit[i];
      ok = ok && word == want;
      char text[64];
      snprintf(text, sizeof(text), "%s0x%04x (want 0x%04x)",
               detail.empty() ? "" : ", ", word, want);
      detail += text;
      if (colour != LED_COLOR_YELLOW) {
        distinct = distinct && !(used & want);
        used |= want;
      }
    }
    char name[96];
    snprintf(name, sizeof(name), "leds: UI row %d lights %s (red bit %d, "
             "green bit %d)", i, board::kLedRef[i], board::kLedRedBit[i],
             board::kLedGreenBit[i]);
    Check(name, ok, "red, green, yellow: %s", detail.c_str());
  }
  Check("leds: the 16 LED lines are 16 different bits",
        distinct && used == 0xffff, "bits used 0x%04x", used);
  leds.Clear();
  leds.set(3, LED_COLOR_YELLOW);
  leds.Write();
  plaitsy::hal::Service();
  Check("leds: Service() latches the frame", fake::led_word_latched() ==
        fake::led_word_written(), "latched 0x%04x, written 0x%04x",
        fake::led_word_latched(), fake::led_word_written());
  leds.set_buttons(true, false);
  leds.Write();
  const bool a_only = fake::button_led(0) && !fake::button_led(1);
  leds.set_buttons(false, true);
  leds.Write();
  const bool b_only = !fake::button_led(0) && fake::button_led(1);
  Check("leds: button LEDs A (SW1, left) and B (SW2, right) separately",
        a_only && b_only, "A only %d, B only %d", a_only, b_only);

  PotsAdc pots;
  pots.Init();
  for (int ch = 0; ch < plaitsy::hal::kNumMuxChannels; ++ch) {
    fake::SetMuxChannel(ch, 0.1 * (ch + 1));
  }
  pots.Convert();
  for (int p = 0; p < POTS_ADC_CHANNEL_LAST; ++p) {
    const int ch = board::kPotMuxChannel[p];
    const int want = static_cast<int>(floor(0.1 * (ch + 1) * 65535.0 + 0.5));
    char name[96];
    snprintf(name, sizeof(name), "pots: %s (%s) reads mux channel %d",
             board::kPotLabel[p], board::kPotRef[p], ch);
    Check(name, pots.value(PotsAdcChannel(p)) == want,
          "value %d (channel %d holds %d)", pots.value(PotsAdcChannel(p)), ch,
          want);
  }
  bool grounded_unused = true;
  for (int k = 0; k < board::kNumGroundedMuxChannels; ++k) {
    grounded_unused = grounded_unused &&
        board::kGroundedMuxChannels[k] >= plaitsy::hal::kNumMuxChannels;
  }
  Check("pots: the grounded mux channel is not scanned", grounded_unused &&
        fake::hal_violations() == 0, "grounded channel %d, hal scans %d",
        board::kGroundedMuxChannels[0], plaitsy::hal::kNumMuxChannels);

  for (int i = 0; i < board::kNumPinChecks; ++i) {
    const board::PinCheck& c = board::kPinChecks[i];
    Check(std::string("pins: hal_daisy.cc ") + c.what, c.ok,
          "seed::%s; netlist: %s", c.hal_pin, c.netlist);
  }
  std::string problems;
  for (int i = 0; i < board::kNumProblems; ++i) {
    problems += std::string(i ? "; " : "") + board::kProblems[i];
  }
  Check("netlist: gen_board_tables.py found no inconsistencies",
        board::kNumProblems == 0, "%d%s%s", board::kNumProblems,
        problems.empty() ? "" : ": ", problems.c_str());
}

// ====================================================================== 5
namespace {

struct CalibrationResult {
  int m1, m2, m3;
  bool probe_quiet;
  double note_error;   // max |note - 12 V| over 0..3 V
  double wide_error;   // max |note - 12 V| over -2..+6 V
  double offset_error[CV_ADC_CHANNEL_LAST];
  bool reloaded_same;
  double pre_error;    // before calibration, at 1 V and 3 V
};

CalibrationResult Calibrate(double bias_a, double bias_v) {
  CalibrationResult r;
  fake::ResetBoard();
  FreshFlash();
  SetBiasErrorOnNet("BIAS_A", bias_a);
  SetBiasErrorOnNet("BIAS_V", bias_v);
  Rig rig;
  rig.Boot();
  rig.RunMs(500.0);
  r.pre_error = 0.0;
  for (double v = 1.0; v <= 3.0; v += 2.0) {
    fake::Patch(plaitsy::hal::ADC_V_OCT, v);
    rig.RunMs(60.0);
    r.pre_error = std::max(r.pre_error, fabs(rig.modulations.note - 12.0 * v));
  }
  // The procedure, as the README gives it.
  fake::Patch(plaitsy::hal::ADC_V_OCT, 1.0);
  rig.Press(0);
  rig.Press(1);
  rig.RunMs(2050.0);
  rig.Release(0);
  rig.Release(1);
  rig.RunMs(200.0);
  r.m1 = Mode(rig);
  const int writes = fake::probe_writes();
  rig.RunMs(100.0);
  r.probe_quiet = fake::probe_writes() == writes &&
      !fake::ProbeAt(fake::TimeUs());
  rig.Tap(0);
  r.m2 = Mode(rig);
  fake::Patch(plaitsy::hal::ADC_V_OCT, 3.0);
  rig.RunMs(200.0);
  rig.Tap(0);
  r.m3 = Mode(rig);
  rig.RunMs(50.0);

  r.note_error = 0.0;
  for (double v = 0.0; v <= 3.0; v += 1.0) {
    fake::Patch(plaitsy::hal::ADC_V_OCT, v);
    rig.RunMs(60.0);
    r.note_error = std::max(r.note_error, fabs(rig.modulations.note - 12.0 * v));
  }
  r.wide_error = 0.0;
  for (double v = -2.0; v <= 6.0; v += 0.5) {
    fake::Patch(plaitsy::hal::ADC_V_OCT, v);
    rig.RunMs(30.0);
    r.wide_error = std::max(r.wide_error, fabs(rig.modulations.note - 12.0 * v));
  }
  fake::Unpatch(plaitsy::hal::ADC_V_OCT);

  // Every other input patched with 0 V.
  for (int ch = 0; ch < CV_ADC_CHANNEL_LAST; ++ch) {
    if (ch != CV_ADC_CHANNEL_V_OCT) {
      fake::Patch(kHalInputOf[ch], 0.0);
    }
  }
  rig.RunMs(60.0);
  const float* m = &rig.modulations.engine;
  for (int ch = 0; ch < CV_ADC_CHANNEL_LAST; ++ch) {
    r.offset_error[ch] = ch == CV_ADC_CHANNEL_V_OCT ? 0.0 : fabs(m[ch]);
  }
  // Reload, once the main loop has saved (5 s after the last change).
  rig.RunMs(5100.0);
  Settings reloaded;
  reloaded.Init();
  r.reloaded_same = memcmp(&reloaded.persistent_data_,
                           &rig.settings().persistent_data_,
                           sizeof(PersistentData)) == 0;
  return r;
}

}  // namespace

void TestCalibration() {
  Section("5. Calibration (V/OCT scale, every input's offset)");
  struct Variant {
    const char* name;
    double bias_a, bias_v;
  } variants[] = {
    { "nominal parts", 0.0, 0.0 },
    { "bias A +1 %, bias V -1 %", 0.01, -0.01 },
    { "bias A -1 %, bias V +1 %", -0.01, 0.01 },
  };
  // FM is in semitones; the others are fractions of their range.
  const double tolerance[CV_ADC_CHANNEL_LAST] = {
    0.002, 0.0, 0.02, 0.002, 0.002, 0.002, 0.002, 0.002,
  };
  for (const Variant& v : variants) {
    const CalibrationResult r = Calibrate(v.bias_a, v.bias_v);
    char name[160];
    snprintf(name, sizeof(name), "cal (%s): C1 -> C3 -> normal, probe held "
             "low and still", v.name);
    Check(name, r.m1 == UI_MODE_CALIBRATION_C1 &&
          r.m2 == UI_MODE_CALIBRATION_C3 && r.m3 == UI_MODE_NORMAL &&
          r.probe_quiet, "%s, %s, %s; probe %s", ModeName(r.m1),
          ModeName(r.m2), ModeName(r.m3), r.probe_quiet ? "quiet" : "MOVING");
    snprintf(name, sizeof(name), "cal (%s): V/OCT 0/1/2/3 V -> 0/12/24/36 "
             "semitones +- 0.05", v.name);
    Check(name, r.note_error <= 0.05, "max error %.4f st (-2..+6 V: %.4f st; "
          "before calibration %.3f st)", r.note_error, r.wide_error,
          r.pre_error);
    std::string detail;
    bool ok = true;
    for (int ch = 0; ch < CV_ADC_CHANNEL_LAST; ++ch) {
      if (ch == CV_ADC_CHANNEL_V_OCT) continue;
      ok = ok && r.offset_error[ch] <= tolerance[ch];
      char text[64];
      snprintf(text, sizeof(text), "%s%s %.4f", detail.empty() ? "" : ", ",
               kChannelName[ch], r.offset_error[ch]);
      detail += text;
    }
    snprintf(name, sizeof(name), "cal (%s): every other input reads ~0 at "
             "0 V (probe-low correction on the normalized ones)", v.name);
    Check(name, ok, "%s (FM in semitones, tolerance 0.02; others 0.002)",
          detail.c_str());
    snprintf(name, sizeof(name), "cal (%s): saved and reloaded", v.name);
    Check(name, r.reloaded_same, "%s", r.reloaded_same ? "same" : "DIFFERENT");
  }
  {
    CvAdc cv;
    Observe("probe-low correction: without it the calibrated 0 V of FM would "
            "be off by %.2f semitones, TIMBRE/MORPH by %.3f, TRIG by %.3f, "
            "LEVEL by %.3f",
            fabs(cv.probe_low_offset(CV_ADC_CHANNEL_FM) * 60.0),
            fabs(cv.probe_low_offset(CV_ADC_CHANNEL_TIMBRE) * 1.6),
            fabs(cv.probe_low_offset(CV_ADC_CHANNEL_TRIGGER) * 0.6),
            fabs(cv.probe_low_offset(CV_ADC_CHANNEL_LEVEL) * 0.6));
  }

  // A failed calibration (voltages not 2 V apart).
  {
    fake::ResetBoard();
    FreshFlash();
    Rig rig;
    rig.Boot();
    rig.RunMs(300.0);
    const PersistentData before = rig.settings().persistent_data_;
    fake::Patch(plaitsy::hal::ADC_V_OCT, 1.0);
    fake::Patch(plaitsy::hal::ADC_FM, 1.0);  // a cable left in FM
    rig.Press(0);
    rig.Press(1);
    rig.RunMs(2050.0);
    rig.Release(0);
    rig.Release(1);
    rig.RunMs(200.0);
    rig.Tap(0);
    fake::Patch(plaitsy::hal::ADC_V_OCT, 1.5);
    rig.RunMs(200.0);
    rig.Tap(0);
    const int mode = Mode(rig);
    const ChannelCalibrationData& c = rig.settings().calibration_data(
        CV_ADC_CHANNEL_V_OCT);
    const bool v_oct_kept = c.scale == before.channel_calibration_data[
        CV_ADC_CHANNEL_V_OCT].scale && c.offset == before.channel_calibration_data[
        CV_ADC_CHANNEL_V_OCT].offset;
    rig.Tap(0);
    rig.RunMs(50.0);
    const int writes_after_error = fake::flash_stats().write_calls;
    Check("cal: voltages 0.5 V apart -> error display, V/OCT calibration "
          "kept, nothing saved",
          mode == UI_MODE_ERROR && v_oct_kept && writes_after_error == 0,
          "mode %s, V/OCT kept %d, flash writes %d", ModeName(mode),
          v_oct_kept, writes_after_error);
    const float fm_offset_in_ram = rig.settings().calibration_data(
        CV_ADC_CHANNEL_FM).offset;
    rig.Tap(0);  // a model change saves the state
    rig.RunMs(5200.0);
    Settings reloaded;
    reloaded.Init();
    const PersistentData& stored = reloaded.persistent_data_;
    const bool calibration_unchanged = memcmp(
        &stored, &before, sizeof(PersistentData)) == 0;
    Check("cal: after a failed calibration, the next model change saves the "
          "state but not the offsets C1 measured (as Plaits' ChunkStorage)",
          calibration_unchanged && reloaded.state().engine == rig.patch.engine,
          "FM offset %.3f in RAM after C1 with a cable in FM, %.3f in flash "
          "(before %.3f); engine stored %d, playing %d", fm_offset_in_ram,
          stored.channel_calibration_data[CV_ADC_CHANNEL_FM].offset,
          before.channel_calibration_data[CV_ADC_CHANNEL_FM].offset,
          reloaded.state().engine, rig.patch.engine);
  }
}

}  // namespace test
