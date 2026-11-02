// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: bringing the board up (Daisy Seed only; the host tests have no
// equivalent). main.cc calls these once, in this order, after
// DaisySeed::Init().

#ifndef SIDEFX_HAL_DAISY_H_
#define SIDEFX_HAL_DAISY_H_

namespace daisy {
class DaisySeed;
}

namespace sidefx {
namespace hal {

// hal_daisy.cc: GPIO, the shift-register chain's pins, ADC, MIDI UART,
// QSPI handle, cycle counter. Does not start the control interrupt
// (StartControls) or the audio.
void Init(daisy::DaisySeed* seed);

// display_daisy.cc: SPI1, the ST7789's reset and init sequence, a black
// screen, the backlight PWM (TIM4 CH4 on PB9) at `backlight`.
void InitDisplay(float backlight);

}  // namespace hal
}  // namespace sidefx

#endif  // SIDEFX_HAL_DAISY_H_
