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
// Side FXy: changed for BEADSY, see processor.h (lines marked "Side FXy").

// Side FXy: host tests use stmlib's portable code (see src/fx/beadsy.cc).
#if defined(SIDEFX_HOST_TEST) && !defined(TEST)
#define TEST
#endif

#include "beads/dsp/processor.h"

#include <algorithm>

#include "beads/dsp/mu_law.h"

namespace beads {

const float kDelayModeTransitionTime = 1.5f;  // seconds
const float kDelayModeFadeTime = 0.75f;  // seconds

// Side FXy: at REVERB 0 the tank's loop gain is at most 0.45 per pass
// (~0.1 s): after 5 s it is more than 100 dB down and can be stopped.
const int kReverbIdleSamples = int(5.0f * kCodecSampleRate);

using namespace std;
using namespace stmlib;

void Processor::Init(
    uint8_t* buffers[],
    uint16_t* reverb_buffer,
    bool clear) {  // Side FXy
  // Side FXy: the codec rate (Beads: 48000, 32000, 24000, 24000).
  processor_digital_.Init(kCodecSampleRate, buffers, clear);
  processor_vintage_digital_.Init(kCodecSampleRate, buffers, clear);
  processor_clean_tape_.Init(kCodecSampleRate * 0.5f, buffers, clear);
  processor_dirty_tape_.Init(kCodecSampleRate * 0.5f, buffers, clear);
  
  dry_ = 0.0f;
  wet_ = 0.0f;
  reverb_idle_ = 0;  // Side FXy
  
  reverb_.Init(reverb_buffer, kCodecSampleRate);  // Side FXy: was 48000
#ifdef ENABLE_HARDWARE_24K
  wow_and_flutter_.Init(24000.0f);
  wow_and_flutter_.set_lp(0.95f);
#else
  wow_and_flutter_.Init(kCodecSampleRate);  // Side FXy: was 48000
  wow_and_flutter_.set_lp(0.6f);
#endif  // ENABLE_HARDWARE_24K

  Configure(MEDIA_DIGITAL, false, clear);  // Side FXy
  
  // Used for the timing of the delay to granular transition.
  delay_mode_transition_ = -kDelayModeTransitionTime;
}

void Processor::Configure(Media media, bool mono, bool clear) {  // Side FXy
  media_ = media;
  mono_ = mono;
  
  int max_delay = 0;

  switch (media_) {
    case MEDIA_DIGITAL:
      processor_digital_.Reset(clear);  // Side FXy
      max_delay = processor_digital_.max_delay_times_ratio();
      break;
    case MEDIA_VINTAGE_DIGITAL:
      processor_vintage_digital_.Reset(clear);  // Side FXy
      max_delay = processor_vintage_digital_.max_delay_times_ratio();
      break;
    case MEDIA_CLEAN_TAPE:
      processor_clean_tape_.Reset(clear);  // Side FXy
      max_delay = processor_clean_tape_.max_delay_times_ratio();
      break;
    case MEDIA_DIRTY_TAPE:
      processor_dirty_tape_.Reset(clear);  // Side FXy
      max_delay = processor_dirty_tape_.max_delay_times_ratio();
      break;
  }
  
  float sr = sample_rate();
  pre_reverb_limiter_.Init(1.0f / (sr * 4.0f), 0.9f);
  output_limiter_.Init(1.0f / (sr * 6.0f), 0.9f);
  trigger_generator_.Init(sr);
  delay_controller_.Init(sr, max_delay * (mono ? 2 : 1));
  reverb_.Reset(sr);
  reverb_idle_ = 0;  // Side FXy
}

void Processor::Process(
    SeedButtonState seed_button_state,
    const stmlib::GateFlags* seed_input,
    const bool* freeze,
    const ModulatedParameter& density,
    const Parameters& parameters,
    const MixParameters& mix_parameters,
    const FloatFrame* in,
    FloatFrame* out,
    size_t size) {
  const float delay_mode = delay_mode_transition_ > 0.0f;
  const float threshold = delay_mode ? 0.98f : 0.99f;
  const float direction = parameters.size.base > threshold ? 1.0f : -1.0f;
  delay_mode_transition_ += direction * float(size) / sample_rate();
  
  CONSTRAIN(delay_mode_transition_,
            -kDelayModeTransitionTime,
            +kDelayModeTransitionTime);
  
  float expo_fm_amount = 20.0f * (fabsf(density.base - 0.5f) - 0.225f);
  CONSTRAIN(expo_fm_amount, 0.0f, 1.0f);

  TriggerGenerator::Output triggers_buffer[size];
  DelayController::Output taps_buffer[size];
  bool gate_out[size];

  TriggerGenerator::Output* triggers = &triggers_buffer[0];
  DelayController::Output* taps = &taps_buffer[0];
  
  // Extract grain triggers.
  if (delay_mode) {
    triggers = NULL;
    delay_controller_.Render(
        seed_button_state,
        seed_input,
        freeze,
        density.base,
        (1.0f - expo_fm_amount) * density.cv,
        expo_fm_amount * density.cv,
        parameters.time,
        parameters.shape,
        taps,
        size);
    for (size_t i = 0; i < size; ++i) {
      gate_out[i] = taps[i].gate;
    }
  } else {
    taps = NULL;
    trigger_generator_.Render(
        seed_button_state,
        seed_input,
        density.base,
        (1.0f - expo_fm_amount) * density.cv,
        expo_fm_amount * density.cv,
        triggers,
        size);
    for (size_t i = 0; i < size; ++i) {
      gate_out[i] = triggers[i].gate;
    }
  }
  
  FloatFrame dry_signal[size];
  
  // Granular processing.
  const float feedback = mix_parameters.feedback;
  switch (media_) {
    case MEDIA_DIGITAL:
      processor_digital_.Process(
          triggers, taps, freeze, parameters, feedback, mono_, in, out, size);
      copy(&in[0], &in[size], &dry_signal[0]);
      break;
    
    case MEDIA_VINTAGE_DIGITAL:
      processor_vintage_digital_.Process(
          triggers, taps, freeze, parameters, feedback, mono_, in, out, size);
      for (size_t i = 0; i < size; ++i) {
        dry_signal[i].l = static_cast<int32_t>(in[i].l * 4096.0f) / 4096.0f;
        dry_signal[i].r = static_cast<int32_t>(in[i].r * 4096.0f) / 4096.0f;
      }
      break;
    
    case MEDIA_CLEAN_TAPE:
      processor_clean_tape_.Process(
          triggers, taps, freeze, parameters, feedback, mono_, in, out,
          size);
      copy(&in[0], &in[size], &dry_signal[0]);
      break;
    
    case MEDIA_DIRTY_TAPE:
      processor_dirty_tape_.Process(
          triggers, taps, freeze, parameters, feedback, mono_, in, out,
          size);
      for (size_t i = 0; i < size; ++i) {
        dry_signal[i].l = MuLaw2Lin(
            Lin2MuLaw(
                stmlib::Clip16(static_cast<int32_t>(in[i].l * 32768.0f))));
        dry_signal[i].r = MuLaw2Lin(
            Lin2MuLaw(
                stmlib::Clip16(static_cast<int32_t>(in[i].r * 32768.0f))));
      }
      break;
  }
  
  // Fade-out / Fade-in the dry signal when switching between granular and
  // Delay mode.
  const float wet_fade = SmoothStep(
      std::min(1.0f, fabsf(delay_mode_transition_) / kDelayModeFadeTime));
  
  // Dry/wet balance.
  const float post_gain_dry = 0.75f;
  const float post_gain_wet = 1.5f;
  const float dry_wet = mix_parameters.dry_wet;
  const float dry = (1.0f - dry_wet) * (1.0f + dry_wet) * post_gain_dry;
  const float wet = dry_wet * (2.0f - dry_wet) * post_gain_wet * wet_fade;

  stmlib::ParameterInterpolator dry_modulation(&dry_, dry, size);
  stmlib::ParameterInterpolator wet_modulation(&wet_, wet, size);

  for (size_t i = 0; i < size; ++i) {
    out[i] = dry_modulation.Next() * dry_signal[i] + \
        wet_modulation.Next() * out[i];
  }
  
  // Wow and flutter simulation.
  if (media_ == MEDIA_DIRTY_TAPE) {
    wow_and_flutter_.Process(out, size);
  }
  
  pre_reverb_limiter_.Process(out, size);
  
  // Reverb.
  const bool caveman = media_ != MEDIA_DIGITAL;
  const float reverb = mix_parameters.reverb_amount;
  const float reverb_mix = reverb * reverb * 0.9f;
  const float reverb_time = reverb * reverb * reverb;
  // Side FXy: skip the reverb once it has been at 0 for kReverbIdleSamples.
  // At 0 it only lets its tail ring out (dry 1, send 0), so by then it
  // passes the signal unchanged and stopping or restarting it is silent.
  if (reverb > 0.0f) {
    reverb_idle_ = 0;
  } else if (reverb_idle_ < kReverbIdleSamples) {
    reverb_idle_ += int(size);
  }
  if (reverb_idle_ < kReverbIdleSamples) {
    reverb_.set_mix(reverb_mix);
    reverb_.set_time(caveman
        ? (0.45f + 0.5f * reverb_time)
        : (0.3f + 0.6f * reverb_time));
    reverb_.set_lp(
        caveman ? 0.4f : (media_ == MEDIA_VINTAGE_DIGITAL ? 0.75f : 0.6f));
    reverb_.Process(out, size);
  }
  
  // Final clipping/limiting
  output_limiter_.Process(out, size);
  
  if (mix_parameters.output_gate) {
    for (size_t i = 0; i < size; ++i) {
      out[i].l = (out[i].l + out[i].r) * 0.5f;
      out[i].r = gate_out[i] ? -0.8f : 0.0f;
    }
  }
}

}  // namespace beads