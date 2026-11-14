// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: calibration of the four CV outputs. Marbles calibrates its DAC
// on the factory test rig only; here the module measures its own outputs
// with the X SPREAD CV input, which Marbles' calibration has just set from
// two exact voltages. For each output in turn, patched into X SPREAD, the
// calibrator sets the code Marbles' factory test uses for each of its two
// points (about +4.1 V and -2.1 V here), averages what X SPREAD reads at
// each, and fits that channel's dac_scale and dac_offset through the two.
// A fit more than 10 % from the nominal output stage (the margin Marbles'
// settings check allows) fails, which is also what an unpatched input
// gives.
//
// The reading is the jack voltage under X SPREAD's load: the output's 1k
// into the input's 100k, whose summing node sits at the 1.57 V bias, so
// the jack reads (100 V_out + 1.57 V) / 101. Into a usual 1V/oct input,
// 100k to ground, the same output gives 100 V_out / 101: the same slope,
// 16 mV lower. The fit is made for that load, so the outputs are right
// into such inputs (and, as any output behind 1k, about 1 % wide into a
// high-impedance one).

#ifndef MARBLESY_OUTPUT_CALIBRATOR_H_
#define MARBLESY_OUTPUT_CALIBRATOR_H_

#include <math.h>

#include "marbles/drivers/dac.h"
#include "marbles/settings.h"

namespace marblesy {

class OutputCalibrator {
 public:
  enum Status {
    STATUS_IDLE,
    STATUS_MEASURING,
    STATUS_DONE,
    STATUS_FAILED
  };

  // Marbles' factory test points (ui.cc: 0x1d98 and 0xaf35), on the 12-bit
  // grid so the DAC outputs exactly these codes.
  static const uint16_t kHighCode = 0x1d90;
  static const uint16_t kLowCode = 0xaf30;
  // In blocks of 5 samples at 32 kHz: 50 ms to settle, 0.32 s to average.
  static const uint32_t kSettleBlocks = 320;
  static const uint32_t kAverageBlocks = 2048;
  // X SPREAD's calibrated reading is 0.2 per volt (cv_reader.h).
  static constexpr float kVoltsPerSpreadUnit = 5.0f;
  // circuit.py: R73/R77/R81/R85 1k after each output stage; R33 100k into
  // X SPREAD's stage, its + input at 3V3A * 10k / 21k, R46 / (R45 + R46).
  static constexpr float kOutputResistor = 1.0e3f;
  static constexpr float kSpreadInputResistor = 100.0e3f;
  static constexpr float kSpreadBias = 3.3f * 10.0e3f / 21.0e3f;
  static constexpr float kLoadOffset = kSpreadBias * kOutputResistor / \
      (kOutputResistor + kSpreadInputResistor);  // 15.56 mV

  OutputCalibrator() { }
  ~OutputCalibrator() { }

  void Init(marbles::CalibrationData* calibration_data) {
    calibration_data_ = calibration_data;
    channel_ = 0;
    status_ = STATUS_IDLE;
  }

  // Selects DAC channel `channel` (0 = Y, 1..3 = X1..X3), idle.
  void Select(size_t channel) {
    channel_ = channel;
    status_ = STATUS_IDLE;
  }

  // Measures the selected channel.
  void Start() {
    point_ = 0;
    count_ = 0;
    sum_ = 0.0f;
    status_ = STATUS_MEASURING;
  }

  // Once per block, from the DSP, with X SPREAD's calibrated reading
  // (CvReaderChannel::scaled_raw_cv()) for that block.
  void Process(float spread) {
    if (status_ != STATUS_MEASURING) {
      return;
    }
    ++count_;
    if (count_ > kSettleBlocks) {
      sum_ += spread;
    }
    if (count_ == kSettleBlocks + kAverageBlocks) {
      volts_[point_] = sum_ / static_cast<float>(kAverageBlocks) * \
          kVoltsPerSpreadUnit - kLoadOffset;
      sum_ = 0.0f;
      count_ = 0;
      ++point_;
      if (point_ == 2) {
        Fit();
      }
    }
  }

  // What DAC channel `channel` outputs meanwhile: the point being measured
  // on the selected channel, 0 V everywhere else.
  uint16_t code(size_t channel) const {
    if (status_ == STATUS_MEASURING && channel == channel_) {
      return point_ == 0 ? kHighCode : kLowCode;
    }
    float zero = calibration_data_->dac_offset[channel];
    CONSTRAIN(zero, 0.0f, 65535.0f);
    return static_cast<uint16_t>(zero);
  }

  inline size_t channel() const { return channel_; }
  inline Status status() const { return status_; }
  inline float volts(int point) const { return volts_[point]; }

  // A fit is kept only within 10 % of the nominal stage.
  static bool Plausible(float scale, float offset) {
    return fabsf(scale / marbles::kDacScale - 1.0f) <= 0.1f &&
        fabsf(offset / marbles::kDacOffset - 1.0f) <= 0.1f;
  }

 private:
  void Fit() {
    const float delta = volts_[1] - volts_[0];
    if (fabsf(delta) < 0.1f) {
      status_ = STATUS_FAILED;
      return;
    }
    const float scale = (static_cast<float>(kLowCode) - \
        static_cast<float>(kHighCode)) / delta;
    const float offset = static_cast<float>(kHighCode) - scale * volts_[0];
    if (!Plausible(scale, offset)) {
      status_ = STATUS_FAILED;
      return;
    }
    calibration_data_->dac_scale[channel_] = scale;
    calibration_data_->dac_offset[channel_] = offset;
    status_ = STATUS_DONE;
  }

  marbles::CalibrationData* calibration_data_;
  size_t channel_;
  Status status_;
  int point_;
  uint32_t count_;
  float sum_;
  float volts_[2];

  DISALLOW_COPY_AND_ASSIGN(OutputCalibrator);
};

}  // namespace marblesy

#endif  // MARBLESY_OUTPUT_CALIBRATOR_H_
