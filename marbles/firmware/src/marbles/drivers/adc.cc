// Copyright 2015 Emilie Gillet.
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
// Driver for ADC. ADC1 is used for the 8 pots ; ADC2 for the 8 CV inputs.
//
// Marblesy port: the readings come from hal.h (see adc.h).

#include "marbles/drivers/adc.h"

#include "hal.h"

namespace marbles {

using namespace marblesy;

namespace {

// Marblesy's CV input stage (circuit.py): an inverting TL074 stage, Rin 100k,
// Rf 27k, its + input on 3V3A * 10k / (15k + 10k), into the Seed's ADC,
// whose reference is 3V3A too. So reading / full scale =
// kZeroReading - jack voltage / kVoltsPerFullScale.
const float kRin = 100.0e3f;
const float kRf = 27.0e3f;
const float kBiasRatio = 10.0e3f / (15.0e3f + 10.0e3f);
const float kAdcReference = 3.3f;
const float kZeroReading = kBiasRatio * (1.0f + kRf / kRin);
const float kVoltsPerFullScale = kAdcReference * kRin / kRf;

// Marbles' input stage reads 0.5 - V / 10 of full scale: its default
// calibration (scale -2, offset +1, so +-5 V is +-1) and the 0.4 / 0.2
// readings its calibration expects at 1 V and 3 V.
const float kMarblesZeroReading = 0.5f;
const float kMarblesVoltsPerFullScale = 10.0f;

const hal::Pot kPot[ADC_CHANNEL_LAST] = {
  hal::POT_DEJA_VU,         // ADC_CHANNEL_DEJA_VU_AMOUNT
  hal::POT_DEJA_VU_LENGTH,  // ADC_CHANNEL_DEJA_VU_LENGTH
  hal::POT_T_RATE,          // ADC_CHANNEL_T_RATE
  hal::POT_T_BIAS,          // ADC_CHANNEL_T_BIAS
  hal::POT_T_JITTER,        // ADC_CHANNEL_T_JITTER
  hal::POT_X_SPREAD,        // ADC_CHANNEL_X_SPREAD
  hal::POT_X_BIAS,          // ADC_CHANNEL_X_BIAS
  hal::POT_X_STEPS,         // ADC_CHANNEL_X_STEPS
};

// LENGTH has no CV input; its slot holds Marbles' second X SPREAD reading.
const hal::CvInput kCv[ADC_CHANNEL_LAST] = {
  hal::CV_DEJA_VU,   // ADC_CHANNEL_DEJA_VU_AMOUNT
  hal::CV_X_SPREAD,  // ADC_CHANNEL_X_SPREAD_2
  hal::CV_T_RATE,    // ADC_CHANNEL_T_RATE
  hal::CV_T_BIAS,    // ADC_CHANNEL_T_BIAS
  hal::CV_T_JITTER,  // ADC_CHANNEL_T_JITTER
  hal::CV_X_SPREAD,  // ADC_CHANNEL_X_SPREAD
  hal::CV_X_BIAS,    // ADC_CHANNEL_X_BIAS
  hal::CV_X_STEPS,   // ADC_CHANNEL_X_STEPS
};

}  // namespace

/* static */
float Adc::JackVoltage(uint16_t seed_reading) {
  const float reading = static_cast<float>(seed_reading) / 65536.0f;
  return (kZeroReading - reading) * kVoltsPerFullScale;
}

/* static */
uint16_t Adc::MarblesReading(float jack_voltage) {
  float reading = kMarblesZeroReading - \
      jack_voltage / kMarblesVoltsPerFullScale;
  CONSTRAIN(reading, 0.0f, 65535.0f / 65536.0f);
  return static_cast<uint16_t>(reading * 65536.0f + 0.5f);
}

void Adc::Init(bool single_channel) {
  hal::InitAdc();
  Convert();
}

void Adc::DeInit() { }

void Adc::Convert() {
  uint16_t cv[hal::CV_INPUT_LAST];
  for (int i = 0; i < hal::CV_INPUT_LAST; ++i) {
    cv[i] = MarblesReading(JackVoltage(hal::ReadCv(hal::CvInput(i))));
  }
  for (int i = 0; i < ADC_CHANNEL_LAST; ++i) {
    values_[ADC_GROUP_POT + i] = hal::ReadPot(kPot[i]);
    values_[ADC_GROUP_CV + i] = cv[kCv[i]];
  }
}

}  // namespace marbles
