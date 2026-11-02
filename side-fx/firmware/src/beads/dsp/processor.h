// Copyright 2017 Emilie Gillet.
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
// The whole FX chain.
//
// Side FXy: changed for BEADSY (lines marked "Side FXy"):
//   - ENABLE_HARDWARE_24K is not defined: the Seed's codec runs at a fixed
//     48014.32 Hz (kCodecSampleRate), so the tape media decimate by 2
//     internally (Beads' own non-24K path) and VINTAGE DIGITAL, which Beads
//     runs with its codec at 32 kHz, runs at the full codec rate here (its
//     12-bit buffer then holds 5.3 s instead of 8 s, and it aliases less);
//   - Init() and Configure() can skip clearing the delay buffer (BEADSY
//     clears it once on Reset, and in slices from the audio interrupt when
//     the quality changes, instead of Beads' nine passes over 768 kB);
//   - delay_mode(): the mode Process() runs in (after Beads' 1.5 s
//     transition), for BEADSY's seed clock and its readouts;
//   - the reverb is skipped once it has been at 0 long enough to have rung
//     out, which saves its CPU time without a glitch;
//   - no WasteCPUCycles().
//
// Running every medium at the codec rate also changes the DIRTY TAPE and
// VINTAGE DIGITAL sound beyond the buffer length: Beads (24K defined) runs
// DIRTY TAPE's reverb and wow and flutter at 24 kHz and VINTAGE DIGITAL's
// reverb at 32 kHz, and both are sized in samples. Here DIRTY TAPE's wow and flutter are half as deep (in time and
// in pitch) and its reverb half the size; VINTAGE DIGITAL's reverb is two
// thirds the size; both reverbs are a little brighter. (Doubling the wow
// depth would need a longer delay line than WowAndFlutter's 128 samples.)

#ifndef BEADS_DSP_PROCESSOR_H_
#define BEADS_DSP_PROCESSOR_H_

#include "stmlib/stmlib.h"

#include "beads/dsp/granular_processor.h"
#include "beads/dsp/modulated_parameter.h"
#include "beads/dsp/fx/reverb.h"
#include "beads/dsp/fx/wow_and_flutter.h"

// Setting this flag slows down the codec to 24kHz for the MEDIA_DIRTY_TAPE
// setting. The codec becomes very hissy at this sample rate, but this has
// a certain charm!
// 
// When this flag is not set, the codec is run at 48kHz and the wet signal is
// downsampled by a 0.5 factor before being processed. Low-pass filtering
// is also applied to the output signal within the wow and flutter code.
// Side FXy: not defined, see above.
// #define ENABLE_HARDWARE_24K

namespace beads {

// Side FXy: the Seed's codec rate (MCLK / 256), used where Beads says 48000.
const float kCodecSampleRate = 48014.32f;

// (512 + 256) * 1000 bytes, 48kHz 16-bit stereo = 4 seconds
const size_t kDelayBufferSizeBits = 768 * 1000 * 8;

class Processor {
 public:
  Processor() { }
  ~Processor() { }
  
  enum Media {
    MEDIA_DIRTY_TAPE,
    MEDIA_CLEAN_TAPE,
    MEDIA_VINTAGE_DIGITAL,
    MEDIA_DIGITAL
  };
  
  struct MixParameters {
    float feedback;
    float dry_wet;
    float reverb_amount;
    bool output_gate;
  };
  
  // Side FXy: clear false leaves the delay buffer as it is (the caller
  // clears it); only after a first Init with clear and the same buffers.
  void Init(uint8_t* buffers[], uint16_t* reverb_buffer, bool clear = true);
  void Configure(Media media, bool mono, bool clear = true);  // Side FXy
  
  inline Media media() const { return media_; }
  inline bool mono() const { return mono_; }
  // Side FXy: whether the next Process() runs in delay mode.
  inline bool delay_mode() const { return delay_mode_transition_ > 0.0f; }
  
  inline float sample_rate() const {
#ifdef ENABLE_HARDWARE_24K
    float sr[4] = { 24000.0f, 48000.0f, 32000.0f, 48000.0f };
#else
    // Side FXy: the codec rate for every medium (VINTAGE DIGITAL was 32 kHz).
    float sr[4] = {
        kCodecSampleRate, kCodecSampleRate, kCodecSampleRate, kCodecSampleRate
    };
#endif  // ENABLE_HARDWARE_24K
    return sr[media_];
  }
  
  inline int ratio() const {
#ifdef ENABLE_HARDWARE_24K
    int ratio[4] = { 1, 2, 1, 1 };
#else
    int ratio[4] = { 2, 2, 1, 1 };
#endif  // ENABLE_HARDWARE_24K
    return ratio[media_];
  }
  
  inline uint8_t* delay_buffer_raw_bytes(size_t offset) {
    // Independently of the quality settings, we're writing in the same
    // bytes anyway!
    return processor_vintage_digital_.delay_buffer_raw_bytes(mono_, offset);
  }
  
  inline int* mutable_delay_write_ptr() {
    switch (media_) {
      case MEDIA_DIRTY_TAPE:
        return processor_dirty_tape_.mutable_delay_write_ptr(mono_);
      case MEDIA_CLEAN_TAPE:
        return processor_clean_tape_.mutable_delay_write_ptr(mono_);
      case MEDIA_VINTAGE_DIGITAL:
        return processor_vintage_digital_.mutable_delay_write_ptr(mono_);
      case MEDIA_DIGITAL:
      default:
        return processor_digital_.mutable_delay_write_ptr(mono_);
    }
  }
  
  inline float overwrite_reserve() const {
    float reserve = float(remaining());
    float fade_duration = sample_rate() * 0.15f / float(ratio());
    return reserve >= fade_duration ? 1.0f : reserve / fade_duration;
  }
  
  inline int remaining() const {
    switch (media_) {
      case MEDIA_DIRTY_TAPE:
        return processor_dirty_tape_.remaining(mono_);
      case MEDIA_CLEAN_TAPE:
        return processor_clean_tape_.remaining(mono_);
      case MEDIA_VINTAGE_DIGITAL:
        return processor_vintage_digital_.remaining(mono_);
      case MEDIA_DIGITAL:
      default:
        return processor_digital_.remaining(mono_);
    }
  }

  inline void Trim() {
    switch (media_) {
      case MEDIA_DIRTY_TAPE:
        processor_dirty_tape_.Trim(mono_);
      case MEDIA_CLEAN_TAPE:
        processor_clean_tape_.Trim(mono_);
      case MEDIA_VINTAGE_DIGITAL:
        processor_vintage_digital_.Trim(mono_);
      case MEDIA_DIGITAL:
      default:
        processor_digital_.Trim(mono_);
    }
  }
  
  // Side FXy: WasteCPUCycles() removed.

  void Process(
      SeedButtonState seed_button_state,
      const stmlib::GateFlags* seed_input,
      const bool* freeze,
      const ModulatedParameter& density,
      const Parameters& parameters,
      const MixParameters& mix_parameters,
      const FloatFrame* in,
      FloatFrame* out,
      size_t size);
  
 private:
  GranularProcessor<
      RESOLUTION_16_BIT,
      kDelayBufferSizeBits / (16 * 2),
      1> processor_digital_;
  GranularProcessor<
      RESOLUTION_12_BIT,
      kDelayBufferSizeBits / (12 * 2),
      1> processor_vintage_digital_;
  GranularProcessor<
      RESOLUTION_12_BIT,
      kDelayBufferSizeBits / (12 * 2),
      2> processor_clean_tape_;
#ifdef ENABLE_HARDWARE_24K
  GranularProcessor<
      RESOLUTION_8_BIT,
      kDelayBufferSizeBits / (8 * 2),
      1> processor_dirty_tape_;
#else
  GranularProcessor<
      RESOLUTION_8_BIT,
      kDelayBufferSizeBits / (8 * 2),
      2> processor_dirty_tape_;
#endif  // ENABLE_HARDWARE_24K

  TriggerGenerator trigger_generator_;
  DelayController delay_controller_;
  
  Media media_;
  bool process_dry_;
  bool mono_;
  
  float delay_mode_transition_;

  float dry_;
  float wet_;

  int reverb_idle_;  // Side FXy: samples since the reverb amount went to 0.
  
  WowAndFlutter wow_and_flutter_;
  Reverb reverb_;
  Limiter pre_reverb_limiter_;
  Limiter output_limiter_;
  
  DISALLOW_COPY_AND_ASSIGN(Processor);
};

}  // namespace beads

#endif  // BEADS_DSP_PROCESSOR_H_
