// Plaitsy host tests, groups 1 and 2: the CV inputs and cable detection.

#include "port_test.h"

namespace test {

using namespace plaits;
using plaitsy::hal::AdcInput;

namespace {

// Plaits' value for a jack voltage, through the calibration the port boots
// with: Plaits' scales, and the offsets Plaits' calibration measures on its
// nominal circuit.
double PlaitsDefaultTransform(int channel, double volts) {
  const double v = PlaitsSdadcValueClipped(channel, volts) / 32768.0;
  return v * kPlaitsDefaults[channel].scale + PlaitsNominalOffset(channel);
}

// Where Plaits' stage and Plaitsy's ADC stop resolving a channel.
void RangeOf(int channel, double* plaits_lo, double* plaits_hi,
             double* plaitsy_lo, double* plaitsy_hi) {
  const PlaitsStage& p = kPlaitsStages[channel];
  const double pv0 = 10.0 * p.rf / p.rref;
  const double pg = p.rf / 100.0;
  *plaits_lo = (pv0 - 3.3) / pg;
  *plaits_hi = pv0 / pg;
  const fake::Stage s = fake::StageOf(kHalInputOf[channel]);
  *plaitsy_lo = (s.v0 - 3.3) / s.g;
  *plaitsy_hi = s.v0 / s.g;
}

// What a cable carries.
struct Signal {
  const char* name;
  std::function<double(double)> volts;
};

uint64_t Hash(uint64_t x) {
  x ^= x >> 33;
  x *= 0xff51afd7ed558ccdull;
  x ^= x >> 33;
  x *= 0xc4ceb9fe1a85ec53ull;
  x ^= x >> 33;
  return x;
}

std::vector<Signal> Signals(uint64_t salt) {
  std::vector<Signal> s;
  s.push_back({ "0 V", [](double) { return 0.0; } });
  s.push_back({ "+5 V", [](double) { return 5.0; } });
  s.push_back({ "-5 V", [](double) { return -5.0; } });
  s.push_back({ "slow LFO (0.5 Hz, 5 V)", [](double t) {
    return 5.0 * sin(2.0 * M_PI * 0.5 * t * 1e-6 + 0.1);
  } });
  s.push_back({ "LFO crossing the threshold (2 Hz, 0.8 V +- 1 V)", [](double t) {
    return 0.8 + 1.0 * sin(2.0 * M_PI * 2.0 * t * 1e-6);
  } });
  s.push_back({ "audio-rate noise (48 kHz, +-5 V)", [salt](double t) {
    const uint64_t sample = static_cast<uint64_t>(t / (1e6 / 48000.0));
    return (static_cast<double>(Hash(sample ^ salt) >> 11) /
            9007199254740992.0 - 0.5) * 10.0;
  } });
  s.push_back({ "500 Hz square (+-5 V)", [](double t) {
    return fmod(t, 2000.0) < 1000.0 ? 5.0 : -5.0;
  } });
  s.push_back({ "1 kHz square (0..5 V, in step with the probe)", [](double t) {
    return fmod(t, 1000.0) < 500.0 ? 5.0 : 0.0;
  } });
  return s;
}

const AdcInput kNormalizedInputs[kNumNormalizedChannels] = {
  plaitsy::hal::ADC_FM, plaitsy::hal::ADC_TIMBRE, plaitsy::hal::ADC_MORPH,
  plaitsy::hal::ADC_TRIGGER, plaitsy::hal::ADC_LEVEL,
};
const char* const kNormalizedName[kNumNormalizedChannels] = {
  "FM", "TIMBRE", "MORPH", "TRIG", "LEVEL",
};

// Runs the rig for `settle_ms`, then samples the five flags once per ms for
// `sample_ms`. Returns how many samples had each flag set.
void SampleFlags(Rig* rig, double settle_ms, double sample_ms,
                 int counts[kNumNormalizedChannels], int* samples) {
  rig->RunMs(settle_ms);
  std::fill(counts, counts + kNumNormalizedChannels, 0);
  *samples = 0;
  const bool* flags = &rig->modulations.frequency_patched;
  for (int ms = 0; ms < sample_ms; ++ms) {
    rig->RunMs(1.0);
    for (int i = 0; i < kNumNormalizedChannels; ++i) {
      counts[i] += flags[i] ? 1 : 0;
    }
    ++*samples;
  }
}

std::string FlagSummary(const int counts[kNumNormalizedChannels], int samples) {
  std::string s;
  char text[64];
  for (int i = 0; i < kNumNormalizedChannels; ++i) {
    snprintf(text, sizeof(text), "%s%s %d/%d", i ? ", " : "",
             kNormalizedName[i], counts[i], samples);
    s += text;
  }
  return s;
}

// One detection run: `patched_mask` bit i = normalized input i patched with
// `signal` (others unpatched). True when every sample is right.
bool DetectionRun(double latency_us, double noise_lsb, uint32_t patched_mask,
                  const std::vector<Signal>& signals, int signal_index,
                  bool also_patch_others, std::string* summary) {
  fake::ResetBoard();
  FreshFlash();
  fake::SetAdcLatencyUs(latency_us);
  fake::SetAdcNoiseLsb(noise_lsb);
  if (also_patch_others) {
    fake::PatchFunction(plaitsy::hal::ADC_MODEL, signals[5].volts);
    fake::PatchFunction(plaitsy::hal::ADC_HARMONICS, signals[3].volts);
    fake::Patch(plaitsy::hal::ADC_V_OCT, 1.0);
  }
  const bool several = (patched_mask & (patched_mask - 1)) != 0;
  for (int i = 0; i < kNumNormalizedChannels; ++i) {
    if (patched_mask & (1u << i)) {
      // Different inputs get different signals when several are patched.
      const int k = several
          ? (signal_index + i) % static_cast<int>(signals.size())
          : signal_index;
      fake::PatchFunction(kNormalizedInputs[i], signals[k].volts);
    }
  }
  Rig rig;
  rig.Boot();
  int counts[kNumNormalizedChannels];
  int samples = 0;
  SampleFlags(&rig, 70.0, 100.0, counts, &samples);
  bool ok = true;
  for (int i = 0; i < kNumNormalizedChannels; ++i) {
    const bool want = patched_mask & (1u << i);
    ok = ok && counts[i] == (want ? samples : 0);
  }
  if (summary) {
    *summary = FlagSummary(counts, samples);
  }
  return ok;
}

}  // namespace

// ====================================================================== 1
void TestCvMapping() {
  Section("1. CV mapping: Plaitsy's ADC rescaled to Plaits' SDADC");

  // Stage constants as the board model has them (from circuit.py).
  for (int i = 0; i < board::kNumAdcInputs; ++i) {
    const fake::Stage s = fake::StageOf(AdcInput(i));
    Note("board: %-9s g %.3f bias %.4f V v0 %.4f V (lug %s)",
         board::kAdcInputName[i], s.g, s.bias, s.v0,
         board::kNormalized[i] ? "probe" : "ground");
  }

  CvAdc cv;
  cv.Init();
  for (int ch = 0; ch < CV_ADC_CHANNEL_LAST; ++ch) {
    const AdcInput input = kHalInputOf[ch];
    const fake::Stage s = fake::StageOf(input);
    const double plaits_lsb_per_seed_lsb =
        kPlaitsStages[ch].rf / 100.0 / s.g;
    const double tolerance = 2.0 * std::max(1.0, plaits_lsb_per_seed_lsb);
    double max_error = 0.0, worst_v = 0.0;
    double max_sat_dev = 0.0, worst_sat_v = 0.0;
    int points = 0, saturated = 0;
    bool clip_consistent = true;
    for (int k = -1200; k <= 1200; ++k) {
      const double v = k * 0.01;
      fake::Patch(input, v);
      cv.Convert();
      const double got = cv.value(CvAdcChannel(ch));
      const double want = PlaitsSdadcValueClipped(ch, v);
      const double code = (s.v0 - s.g * v) / 3.3 * 65536.0;
      if (code < 0.0 || code > 65535.0) {
        // Plaitsy's ADC is saturated: it reads the voltage at its rail.
        ++saturated;
        const double v_rail = code < 0.0 ? s.v0 / s.g
                                         : (s.v0 - 3.3 * 65535.0 / 65536.0) / s.g;
        const double at_rail = PlaitsSdadcValueClipped(ch, v_rail);
        clip_consistent = clip_consistent &&
            fabs(got - at_rail) <= tolerance;
        if (fabs(got - want) > max_sat_dev) {
          max_sat_dev = fabs(got - want);
          worst_sat_v = v;
        }
        continue;
      }
      ++points;
      if (fabs(got - want) > max_error) {
        max_error = fabs(got - want);
        worst_v = v;
      }
    }
    fake::Unpatch(input);
    char name[96];
    snprintf(name, sizeof(name), "cv: %s matches Plaits' SDADC, -12..+12 V",
             kChannelName[ch]);
    Check(name, max_error <= tolerance,
          "%d points, max error %.2f LSB at %+.2f V (tolerance %.1f: 2 x "
          "%.2f Plaits LSB per Seed LSB)",
          points, max_error, worst_v, tolerance, plaits_lsb_per_seed_lsb);
    double plo, phi, ylo, yhi;
    RangeOf(ch, &plo, &phi, &ylo, &yhi);
    if (saturated) {
      snprintf(name, sizeof(name), "cv: %s holds its rail value where the "
               "Seed's ADC saturates", kChannelName[ch]);
      Check(name, clip_consistent, "%d points beyond %+.3f / %+.3f V",
            saturated, ylo, yhi);
      Observe("%s: Plaits resolves %+.3f..%+.3f V, Plaitsy's ADC %+.3f.."
              "%+.3f V; beyond Plaitsy's range the value differs from "
              "Plaits' by up to %.0f LSB (at %+.2f V)",
              kChannelName[ch], plo, phi, ylo, yhi, max_sat_dev, worst_sat_v);
    } else {
      Note("%s: Plaits clips at %+.2f / %+.2f V, Plaitsy's ADC spans "
           "%+.2f..%+.2f V", kChannelName[ch], plo, phi, ylo, yhi);
    }
  }

  // The defaults the port boots with: Plaits' scales and thresholds, and
  // the offsets that read 0 V as 0 (Plaits' factory offsets assume its own
  // parts' errors; MODEL's would select the next model here).
  {
    FreshFlash();
    Settings settings;
    const bool loaded = settings.Init();
    bool same = !loaded;
    std::string offsets;
    for (int ch = 0; ch < CV_ADC_CHANNEL_LAST; ++ch) {
      const ChannelCalibrationData& c = settings.calibration_data(ch);
      same = same && fabs(c.offset - PlaitsNominalOffset(ch)) <=
          1e-5 * std::max(1.0, fabs(PlaitsNominalOffset(ch))) &&
          c.scale == kPlaitsDefaults[ch].scale &&
          c.normalization_detection_threshold == kPlaitsDefaults[ch].threshold;
      char cell[64];
      snprintf(cell, sizeof(cell), " %s %.4f (Plaits %.3f)", kChannelName[ch],
               c.offset, kPlaitsDefaults[ch].offset);
      offsets += cell;
    }
    Check("cv: an erased flash boots with Plaits 1.2's scales and thresholds "
          "and 0 V reading 0", same, "Init() returned %s; offsets:%s",
          loaded ? "true" : "false", offsets.c_str());
  }

  // Musical results with the default calibration, through Ui::Poll() and the
  // voice, everything else as main.cc runs it.
  fake::ResetBoard();
  FreshFlash();
  Rig rig(true);
  rig.Boot();
  rig.RunMs(50.0);
  struct Case {
    AdcInput input;
    int channel;
    double volts;
    const float* modulation;
    double tolerance;  // against Plaits through the same calibration
  };
  const Case cases[] = {
    { plaitsy::hal::ADC_FM, CV_ADC_CHANNEL_FM, 0.0, &rig.modulations.frequency, 0.01 },
    { plaitsy::hal::ADC_FM, CV_ADC_CHANNEL_FM, 1.0, &rig.modulations.frequency, 0.01 },
    { plaitsy::hal::ADC_TIMBRE, CV_ADC_CHANNEL_TIMBRE, 0.0, &rig.modulations.timbre, 0.001 },
    { plaitsy::hal::ADC_TIMBRE, CV_ADC_CHANNEL_TIMBRE, 5.0, &rig.modulations.timbre, 0.001 },
    { plaitsy::hal::ADC_MORPH, CV_ADC_CHANNEL_MORPH, 5.0, &rig.modulations.morph, 0.001 },
    { plaitsy::hal::ADC_MORPH, CV_ADC_CHANNEL_MORPH, -5.0, &rig.modulations.morph, 0.001 },
    { plaitsy::hal::ADC_HARMONICS, CV_ADC_CHANNEL_HARMONICS, 5.0, &rig.modulations.harmonics, 0.001 },
    { plaitsy::hal::ADC_HARMONICS, CV_ADC_CHANNEL_HARMONICS, -2.5, &rig.modulations.harmonics, 0.001 },
    { plaitsy::hal::ADC_MODEL, CV_ADC_CHANNEL_MODEL, 5.0, &rig.modulations.engine, 0.001 },
    { plaitsy::hal::ADC_TRIGGER, CV_ADC_CHANNEL_TRIGGER, 0.0, &rig.modulations.trigger, 0.002 },
    { plaitsy::hal::ADC_TRIGGER, CV_ADC_CHANNEL_TRIGGER, 5.0, &rig.modulations.trigger, 0.002 },
    { plaitsy::hal::ADC_LEVEL, CV_ADC_CHANNEL_LEVEL, 0.0, &rig.modulations.level, 0.002 },
    { plaitsy::hal::ADC_LEVEL, CV_ADC_CHANNEL_LEVEL, 5.0, &rig.modulations.level, 0.002 },
    { plaitsy::hal::ADC_LEVEL, CV_ADC_CHANNEL_LEVEL, 8.0, &rig.modulations.level, 0.002 },
  };
  for (const Case& c : cases) {
    fake::Patch(c.input, c.volts);
    rig.RunMs(40.0);
    const double got = *c.modulation;
    const double want = PlaitsDefaultTransform(c.channel, c.volts);
    char name[96];
    snprintf(name, sizeof(name), "cv default cal: %s at %+.1f V as on Plaits",
             kChannelName[c.channel], c.volts);
    Check(name, fabs(got - want) <= c.tolerance,
          "%.4f, Plaits %.4f", got, want);
    fake::Unpatch(c.input);
  }
  rig.RunMs(40.0);

  // V/OCT: the note, after Poll()'s low-pass.
  for (double v = 0.0; v <= 2.0; v += 1.0) {
    fake::Patch(plaitsy::hal::ADC_V_OCT, v);
    rig.RunMs(40.0);
    const double note = rig.modulations.note;
    char name[96];
    snprintf(name, sizeof(name), "cv default cal: V/OCT %.0f V -> %.0f "
             "semitones +- 0.3", v, 12.0 * v);
    Check(name, fabs(note - 12.0 * v) <= 0.3, "%.3f semitones (Plaits with "
          "the same calibration: %.3f)", note,
          PlaitsDefaultTransform(CV_ADC_CHANNEL_V_OCT, v));
  }
  fake::Unpatch(plaitsy::hal::ADC_V_OCT);
  rig.RunMs(40.0);
  Observe("default calibration: FM %.3f st at 0 V and %.3f st at +1 V "
          "(Plaits' defaults, before calibration), TIMBRE/MORPH %.4f at 5 V, "
          "HARMONICS %.3f at 5 V, LEVEL %.3f / %.3f / %.3f at 0 / 5 / 8 V",
          PlaitsDefaultTransform(CV_ADC_CHANNEL_FM, 0.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_FM, 1.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_TIMBRE, 5.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_HARMONICS, 5.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_LEVEL, 0.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_LEVEL, 5.0),
          PlaitsDefaultTransform(CV_ADC_CHANNEL_LEVEL, 8.0));

  // TRIG: the voice's trigger (threshold 0.3 rising, 0.1 falling).
  {
    fake::Patch(plaitsy::hal::ADC_TRIGGER, 0.0);
    rig.RunMs(40.0);
    const bool low = rig.voice->trigger_state_;
    fake::Patch(plaitsy::hal::ADC_TRIGGER, 5.0);
    rig.RunMs(5.0);
    const bool high = rig.voice->trigger_state_;
    Check("cv default cal: TRIG 0 V low, 5 V high in the voice",
          !low && high && rig.modulations.trigger_patched,
          "0 V: %s, 5 V: %s, trigger_patched %d", low ? "high" : "low",
          high ? "high" : "low", rig.modulations.trigger_patched);
    // Rising threshold: sweep up slowly.
    fake::Patch(plaitsy::hal::ADC_TRIGGER, 0.0);
    rig.RunMs(20.0);
    double rise = -1.0;
    for (int mv = 0; mv <= 3000 && rise < 0.0; mv += 5) {
      fake::Patch(plaitsy::hal::ADC_TRIGGER, mv * 0.001);
      rig.RunMs(2.0);
      if (rig.voice->trigger_state_) {
        rise = mv * 0.001;
      }
    }
    double fall = -1.0;
    for (int mv = 3000; mv >= -800 && fall < -0.5; mv -= 5) {
      fake::Patch(plaitsy::hal::ADC_TRIGGER, mv * 0.001);
      rig.RunMs(2.0);
      if (!rig.voice->trigger_state_) {
        fall = mv * 0.001;
      }
    }
    // Plaits: Transform = 0.3 and 0.1.
    double plaits_rise = 0.0, plaits_fall = 0.0;
    for (double v = 0.0; v < 5.0; v += 0.0005) {
      if (plaits_rise == 0.0 && PlaitsDefaultTransform(CV_ADC_CHANNEL_TRIGGER, v) > 0.3) {
        plaits_rise = v;
      }
      if (plaits_fall == 0.0 && PlaitsDefaultTransform(CV_ADC_CHANNEL_TRIGGER, v) >= 0.1) {
        plaits_fall = v;
      }
    }
    Check("cv default cal: TRIG thresholds as on Plaits",
          fabs(rise - plaits_rise) <= 0.01 && fabs(fall - plaits_fall) <= 0.01,
          "rises at %.3f V, falls at %.3f V (Plaits: %.3f / %.3f V)",
          rise, fall, plaits_rise, plaits_fall);
    fake::Unpatch(plaitsy::hal::ADC_TRIGGER);
    rig.RunMs(40.0);
  }

  // MODEL unpatched with the default calibration: the model the voice plays
  // and the LEDs at power-up.
  {
    fake::ResetBoard();
    FreshFlash();
    Rig boot(true);
    boot.Boot();
    LedObservation leds = ObserveLeds(&boot, 64.0);
    const int selected = boot.patch.engine;
    const int active = boot.voice->active_engine();
    Check("cv default cal: MODEL unpatched plays the selected model",
          active == selected,
          "selected %d, voice plays %d; modulations.engine %.4f (boot MODEL "
          "offset %.4f, Plaits' factory one %.3f, one model = %.4f, "
          "hysteresis 0.05 of one); LEDs at power-up %s",
          selected, active, boot.modulations.engine,
          boot.settings().calibration_data(CV_ADC_CHANNEL_MODEL).offset,
          kPlaitsDefaults[CV_ADC_CHANNEL_MODEL].offset, 1.0 / 23.0,
          leds.Pattern().c_str());
    // The same after calibrating MODEL's offset (what CalibrateC1 does).
    ChannelCalibrationData* c = boot.settings().mutable_calibration_data(
        CV_ADC_CHANNEL_MODEL);
    const float saved_offset = c->offset;
    c->offset = -boot.ui().cv_adc_.float_value(CV_ADC_CHANNEL_MODEL) * c->scale;
    boot.RunMs(20.0);
    Note("with MODEL's offset calibrated (%.4f instead of %.4f) the voice "
         "plays %d", c->offset, saved_offset, boot.voice->active_engine());
    // With 1 % bias errors (no calibration), how far MODEL's 0 V drifts.
    for (double e = -0.01; e <= 0.0101; e += 0.02) {
      SetBiasErrorOnNet("BIAS_A", e);
      c->offset = saved_offset;
      boot.RunMs(20.0);
      Note("bias A %+.0f %%, default calibration: modulations.engine %.4f, "
           "voice plays %d (selected %d)", e * 100.0,
           boot.modulations.engine, boot.voice->active_engine(),
           boot.patch.engine);
    }
  }
  // dsp.h: the sample rate libDaisy's "48 kHz" really is. libDaisy v9.0.0
  // system.cpp: HSE 16 MHz, PLL3 M 6 N 295 P 16 feeds SAI1; sai.cpp leaves
  // the master divider on (NODIV = 0) without oversampling; the HAL
  // (HAL_SAI_Init) picks MCKDIV = (f * 10 / (fs * 256)) / 10, rounded up
  // only when the tenths digit is 9.
  {
    const double pll3p = 16e6 / 6.0 * 295.0 / 16.0;
    const uint32_t f = static_cast<uint32_t>(pll3p);
    const uint32_t tmpval = f * 10u / (48000u * 256u);
    uint32_t mckdiv = tmpval / 10u;
    if (tmpval % 10u > 8u) {
      ++mckdiv;
    }
    const double fs = pll3p / mckdiv / 256.0;
    Check("dsp: kCorrectedSampleRate is the rate the Seed's 48 kHz runs at",
          fabs(fs - kCorrectedSampleRate) < 0.01,
          "PLL3P %.1f Hz, MCKDIV %u, fs %.2f Hz, dsp.h %.2f Hz; Plaits' "
          "47872.34 Hz would leave every model %.2f cents sharp",
          pll3p, mckdiv, fs, kCorrectedSampleRate,
          1200.0 * log2(fs / 47872.34));
  }
  Check("cv: no flash access from the audio callback",
        fake::flash_stats().violations == 0, "%d flash violations%s%s",
        fake::flash_stats().violations,
        fake::flash_stats().violations ? ": " : "",
        fake::flash_stats().violations
            ? fake::flash_stats().violation_log[0].c_str() : "");
}

// ====================================================================== 2
void TestNormalization() {
  Section("2. Normalization detection");
  const std::vector<Signal> signals = Signals(0x51u);
  struct Config {
    double latency_us;
    double noise_lsb;
  };
  const Config configs[] = { { 0.0, 0.0 }, { 100.0, 0.0 }, { 250.0, 0.0 },
                             { 250.0, 12.0 } };
  for (const Config& config : configs) {
    char tag[64];
    snprintf(tag, sizeof(tag), "latency %.0f us%s", config.latency_us,
             config.noise_lsb > 0.0 ? ", ADC noise 12 LSB rms" : "");
    std::string summary;
    char name[160];

    bool ok = DetectionRun(config.latency_us, config.noise_lsb, 0, signals, 0,
                           false, &summary);
    snprintf(name, sizeof(name), "norm (%s): nothing patched", tag);
    Check(name, ok, "%s", summary.c_str());

    ok = DetectionRun(config.latency_us, config.noise_lsb, 0, signals, 0,
                      true, &summary);
    snprintf(name, sizeof(name), "norm (%s): only MODEL, HARMONICS, V/OCT "
             "patched", tag);
    Check(name, ok, "%s", summary.c_str());

    for (int i = 0; i < kNumNormalizedChannels; ++i) {
      int bad = 0;
      std::string first_bad;
      for (size_t k = 0; k < signals.size(); ++k) {
        if (!DetectionRun(config.latency_us, config.noise_lsb, 1u << i,
                          signals, static_cast<int>(k), false, &summary)) {
          if (!bad) {
            first_bad = std::string(signals[k].name) + ": " + summary;
          }
          ++bad;
        }
      }
      snprintf(name, sizeof(name), "norm (%s): %s patched, alone", tag,
               kNormalizedName[i]);
      Check(name, bad == 0, "%zu signals (0 V, +5 V, -5 V, LFOs, noise, "
            "squares), %d wrong%s%s", signals.size(), bad,
            bad ? "; first: " : "", first_bad.c_str());
    }
    ok = DetectionRun(config.latency_us, config.noise_lsb, 0x1f, signals, 0,
                      true, &summary);
    snprintf(name, sizeof(name), "norm (%s): all eight inputs patched", tag);
    Check(name, ok, "%s", summary.c_str());
    ok = DetectionRun(config.latency_us, config.noise_lsb, 0x0a, signals, 4,
                      false, &summary);
    snprintf(name, sizeof(name), "norm (%s): TIMBRE and TRIG patched", tag);
    Check(name, ok, "%s", summary.c_str());
  }

  // Where it breaks: the latency at which an unpatched input stops
  // following the probe, or a patched one starts to look unpatched.
  double first_false_patched = -1.0, first_false_unpatched = -1.0;
  for (int l = 0; l <= 1500 && (first_false_patched < 0.0 ||
                                 first_false_unpatched < 0.0); l += 10) {
    if (first_false_patched < 0.0 &&
        !DetectionRun(l, 0.0, 0, signals, 0, false, nullptr)) {
      first_false_patched = l;
    }
    if (first_false_unpatched < 0.0 &&
        !DetectionRun(l, 0.0, 0x1f, signals, 0, false, nullptr)) {
      first_false_unpatched = l;
    }
  }
  Check("norm: detection holds up to 0.25 ms of ADC latency with margin",
        first_false_patched > 500.0 || first_false_patched < 0.0,
        "unpatched inputs first read as patched at %.0f us of latency; "
        "patched ones never read as unpatched up to 1.5 ms%s",
        first_false_patched,
        first_false_unpatched >= 0.0 ? " (they do, see observation)" : "");
  Observe("normalization: detection breaks when the ADC reading lags the "
          "probe by %.0f us or more (the probe changes once per ms; the "
          "model writes it 5 us into Poll(), Poll() reads the ADC at its "
          "start); patched inputs %s",
          first_false_patched,
          first_false_unpatched < 0.0 ? "were detected at every latency"
                                      : "fail too");
  Note("margin: %.2f ms beyond a 0.25 ms lag (more than a whole 0.2 ms ADC "
       "scan plus the 4 kHz poll period); with the conversions at the end of "
       "Poll(), as on Plaits, the limit would be 0.75 ms",
       (first_false_patched - 250.0) / 1000.0);
}

}  // namespace test
