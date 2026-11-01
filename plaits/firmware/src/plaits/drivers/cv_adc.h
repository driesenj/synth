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
// Plaitsy port of plaits/drivers/cv_adc.h.
//
// Plaits reads its eight CV inputs with the STM32F373's 16-bit SDADC, behind
// MCP6004 stages of its own; Plaitsy reads them with the Seed's ADC behind
// TL074 stages with other gains. Convert() turns each Seed reading back into
// the jack voltage and then into the value Plaits' SDADC would have returned
// for that voltage, clipped where Plaits' stage clips. So value() and
// float_value() mean exactly what they mean on Plaits, and Plaits'
// calibration data, thresholds and UI code apply unchanged.

#ifndef PLAITS_DRIVERS_CV_ADC_H_
#define PLAITS_DRIVERS_CV_ADC_H_

#include "stmlib/stmlib.h"

namespace plaits {

enum CvAdcChannel {
  CV_ADC_CHANNEL_MODEL,
  CV_ADC_CHANNEL_V_OCT,
  CV_ADC_CHANNEL_FM,
  CV_ADC_CHANNEL_HARMONICS,
  CV_ADC_CHANNEL_TIMBRE,
  CV_ADC_CHANNEL_MORPH,
  CV_ADC_CHANNEL_TRIGGER,
  CV_ADC_CHANNEL_LEVEL,
  CV_ADC_CHANNEL_LAST
};

class CvAdc {
 public:
  CvAdc() { }
  ~CvAdc() { }

  void Init();
  void DeInit() { }
  // Takes the latest readings (the Seed's ADC scans continuously).
  void Convert();

  inline int16_t value(CvAdcChannel channel) const {
    return values_[channel];
  }

  inline float float_value(CvAdcChannel channel) const {
    return static_cast<float>(value(channel)) / 32768.0f;
  }

  // Plaitsy: what float_value() reads above its 0 V value on an input with
  // nothing patched while the probe is held low (during calibration). Zero
  // for the inputs without a probe.
  float probe_low_offset(CvAdcChannel channel) const;

  // Plaitsy: what float_value() reads at 0 V on Plaits' nominal circuit, so
  // what Plaits' calibration would measure there.
  static float zero_volt_value(CvAdcChannel channel);

 private:
  int16_t values_[CV_ADC_CHANNEL_LAST];

  DISALLOW_COPY_AND_ASSIGN(CvAdc);
};

}  // namespace plaits

#endif  // PLAITS_DRIVERS_CV_ADC_H_
