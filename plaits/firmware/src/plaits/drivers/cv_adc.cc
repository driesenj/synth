// Copyright 2016 Emilie Gillet.
//
// Author: Emilie Gillet (emilie.o.gillet@gmail.com)
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// 
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// 
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.
// 
// See http://creativecommons.org/licenses/MIT/ for more information.
//
// -----------------------------------------------------------------------------
//
// Plaitsy port of plaits/drivers/cv_adc.cc: the Seed's ADC, rescaled to
// Plaits' SDADC.

#include "plaits/drivers/cv_adc.h"

#include "hal.h"

namespace plaits {

using namespace plaitsy;

namespace {

// Both modules feed the ADC from an inverting stage, V_adc = v0 - g * V_jack,
// with the ADC spanning 0 .. 3.3 V.
struct Stage {
  float g;
  float v0;
};

const float kVdd = 3.3f;

// Plaitsy (plaits/docs/design.md, "CV inputs"): TL074, Rin 100k, the (+)
// input on a divider from 3V3A, so v0 = bias * (1 + Rf / Rin).
const float kBiasWide = kVdd * 12.0f / (15.0f + 12.0f);  // R46 / (R45 + R46)
const float kBiasVOct = kVdd * 15.0f / (13.0f + 15.0f);  // R48 / (R47 + R48)
const Stage kPlaitsyWide = { 13.0f / 100.0f, kBiasWide * (1.0f + 13.0f / 100.0f) };
// V/OCT: R43 30k (33k until 2026-11-14), so the stage reads -3.3 .. +7.7 V
// and Plaits' own -2.86 .. +7.14 V fits at every tolerance corner; the
// conversion below clips to Plaits' range, as Plaits' op-amps do.
const Stage kPlaitsyVOct = { 30.0f / 100.0f, kBiasVOct * (1.0f + 30.0f / 100.0f) };

// Plaits (plaits_v50 schematic, sheet 3 "CV inputs"): MCP6004 on 0 .. 3.3 V,
// Rin 100k, (+) at ground, an offset from the -10 V reference through Rref,
// so g = Rf / Rin and v0 = 10 V * Rf / Rref.
inline Stage PlaitsStage(float rf, float rref) {
  return { rf / 100.0f, 10.0f * rf / rref };
}

struct ChannelDefinition {
  hal::AdcInput input;
  bool plaitsy_v_oct_stage;
  float plaits_rf;
  float plaits_rref;
  bool normalized;  // switch lug fed by the probe
};

// In CvAdcChannel order.
const ChannelDefinition kChannels[CV_ADC_CHANNEL_LAST] = {
  { hal::ADC_MODEL, false, 33.0f, 200.0f, false },      // R31, R30
  { hal::ADC_V_OCT, true, 33.0f, 140.0f, false },       // R34, R29
  { hal::ADC_FM, false, 20.0f, 120.0f, true },          // R19, R23
  { hal::ADC_HARMONICS, false, 33.0f, 200.0f, false },  // R20, R27
  { hal::ADC_TIMBRE, false, 20.0f, 120.0f, true },      // R32, R33
  { hal::ADC_MORPH, false, 20.0f, 120.0f, true },       // R35, R36
  { hal::ADC_TRIGGER, false, 56.0f, 200.0f, true },     // R17, R25
  { hal::ADC_LEVEL, false, 33.0f, 110.0f, true },       // R18, R26
};

// With the probe pin low, an unpatched normalized jack sits on a divider
// between the probe (0 V, through 10k) and the stage's virtual ground (the
// bias, through Rin 100k). On Plaits that ground is 0 V, here it is not.
const float kProbeLowJackVoltage = kBiasWide * 10.0f / (10.0f + 100.0f);

// Plaits' SDADC value = gain * (Seed ADC value) + offset, before clipping.
float gain_[CV_ADC_CHANNEL_LAST];
float offset_[CV_ADC_CHANNEL_LAST];

}  // namespace

void CvAdc::Init() {
  for (int i = 0; i < CV_ADC_CHANNEL_LAST; ++i) {
    const ChannelDefinition& d = kChannels[i];
    const Stage s = d.plaitsy_v_oct_stage ? kPlaitsyVOct : kPlaitsyWide;
    const Stage p = PlaitsStage(d.plaits_rf, d.plaits_rref);
    // V_jack = (s.v0 - V_adc) / s.g; Plaits' V_adc = p.v0 - p.g * V_jack;
    // its SDADC returns V_adc / kVdd * 65536 - 32768.
    gain_[i] = p.g / s.g;
    offset_[i] = (p.v0 - p.g * s.v0 / s.g) / kVdd * 65536.0f - 32768.0f;
  }
  hal::InitAdc();
  Convert();
}

void CvAdc::Convert() {
  for (int i = 0; i < CV_ADC_CHANNEL_LAST; ++i) {
    float v = gain_[i] * static_cast<float>(hal::ReadAdc(kChannels[i].input)) + \
        offset_[i];
    // Plaits' op-amps stop at the rails: that is where its inputs clip.
    CONSTRAIN(v, -32768.0f, 32767.0f);
    values_[i] = static_cast<int16_t>(v);
  }
}

/* static */
float CvAdc::zero_volt_value(CvAdcChannel channel) {
  const ChannelDefinition& d = kChannels[channel];
  const Stage p = PlaitsStage(d.plaits_rf, d.plaits_rref);
  return p.v0 / kVdd * 2.0f - 1.0f;
}

float CvAdc::probe_low_offset(CvAdcChannel channel) const {
  const ChannelDefinition& d = kChannels[channel];
  if (!d.normalized) {
    return 0.0f;
  }
  const Stage p = PlaitsStage(d.plaits_rf, d.plaits_rref);
  return -p.g * kProbeLowJackVoltage / kVdd * 2.0f;
}

}  // namespace plaits
