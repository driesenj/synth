// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: what the portable code (engine, app, UI) needs from the board.
// hal_daisy.cc and display_daisy.cc implement it on the Daisy Seed with
// libDaisy; the host tests implement it with a model of the board
// (test/hal_fake.cc, test/display_fake.cc).
//
// Pins follow side-fx/hardware/tools/circuit.py and the "Daisy Seed pin
// map" in side-fx/docs/design.md:
//   D0  PB12  CLK        clock input, after the NPN: low while the jack is high
//   D7  PG10  LCD_CS     SPI1 (software NSS)
//   D8  PG11  LCD_SCK    SPI1 SCK
//   D10 PB5   LCD_MOSI   SPI1 MOSI
//   D11 PB8   LCD_DC
//   D12 PB9   LCD_BL     TIM4_CH4 PWM
//   D13 PB6   LCD_RST
//   D14 PB7   MIDI_RX    USART1 RX, 31250 baud
//   A0..A3    PC0 PA3 PB1 PA7   CV 1..4 (inverting stage: 0 V reads ~0.502)
//   D20 PC1   BTN_SHIFT  to ground, internal pull-up
//   D26 PD11  SR_CLK     74HC165 CP and 74HC595 SRCLK
//   D27 PG9   SR_LOAD    165 /PL and 595 RCLK
//   D29 PB14  SR_DOUT    595 SER
//   D30 PB15  SR_DIN     U1 (74HC165) Q7

#ifndef SIDEFX_HAL_H_
#define SIDEFX_HAL_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {
namespace hal {

// --- time ---------------------------------------------------------------------

uint32_t Milliseconds();   // since power-up
uint32_t Microseconds();   // wraps; use differences
uint32_t CycleCount();     // CPU cycles, wraps every 8.9 s at 480 MHz
const float kCyclesPerSecond = 480.0e6f;

// --- controls ---------------------------------------------------------------

enum Switch {
  SWITCH_PITCH,    // the four send buttons, left to right
  SWITCH_DELAY,
  SWITCH_TEXTURE,
  SWITCH_REVERB,
  SWITCH_SHIFT,
  SWITCH_K1,       // encoder pushes, K1 at the top
  SWITCH_K2,
  SWITCH_K3,
  SWITCH_K4,
  NUM_SWITCHES
};

enum Led {
  LED_PITCH,       // in the send buttons (74HC595 QA..QD)
  LED_DELAY,
  LED_TEXTURE,
  LED_REVERB,
  LED_SHIFT,       // QE
  NUM_LEDS
};

const int kNumEncoders = 4;

// One pass over the shift-register chain, raw (no debouncing).
struct ControlScan {
  uint8_t encoder[kNumEncoders];  // bit 0 = phase A, bit 1 = phase B; 1 = at ground
  uint16_t switches;              // bit n = Switch n pressed
  bool clock;                     // the CLOCK jack is high
  uint32_t time_us;               // Microseconds() at the scan
};

// The control interrupt (4 kHz) scans the chain and calls the hook; the
// hook returns the LED bits (bit n = Led n lit) for the next scan to latch.
typedef uint8_t (*ControlHook)(const ControlScan& scan);
const uint32_t kControlRate = 4000;
void StartControls(ControlHook hook);

// SHIFT read straight from its pin, for the power-up check.
bool ShiftPressedNow();

// --- CV inputs ----------------------------------------------------------------

const int kNumCvInputs = 4;
// The raw ADC reading of CV n, 0..1 of 3V3A, inverted by the input stage
// (+5 V at the jack reads about 0.305, 0 V about 0.502, -5 V about 0.699;
// +-12 V stays within 0..1).
// Callable from the audio interrupt.
float ReadCv(int channel);

// --- MIDI -------------------------------------------------------------------

// The next received MIDI byte and its arrival time; false when none is
// waiting. Main loop.
bool ReadMidiByte(uint8_t* byte, uint32_t* time_us);

// --- display ------------------------------------------------------------------

const int kDisplayWidth = 170;
const int kDisplayHeight = 320;

// Starts sending rows y0..y1 (inclusive) of a kDisplayWidth x
// kDisplayHeight frame of RGB565 pixels stored high byte first, as the
// ST7789 takes them. Returns at once; the frame must not change until
// DisplayBusy() is false.
void DisplayFlush(const uint16_t* frame, int y0, int y1);
bool DisplayBusy();
void SetBacklight(float level);  // 0..1
// Turns the picture by 180 degrees (a module mounted the other way up).
// The panel turns only what it is sent afterwards, so a change also starts
// sending the whole of the last flushed frame again (as DisplayFlush, the
// display is then busy for a frame's time); before the first flush the
// panel holds InitDisplay's black, which needs no turning. Main loop.
void SetDisplayFlip(bool flip);

// --- QSPI flash -------------------------------------------------------------

// Offsets from the start of the chip. The Daisy bootloader keeps the
// program from 0x40000 on; Side FXy's records live below it. Erasing works
// on whole 4 kB sectors. Not from the audio interrupt; a sector erase can
// take 400 ms (the audio keeps running: the program runs from SRAM).
// FlashErase and FlashWrite read the range back: true means the flash now
// holds 0xff (erase) or the data (write); false on any failure, and for any
// range reaching 0x40000.
const uint32_t kFlashSectorSize = 0x1000;
void FlashRead(uint32_t offset, void* destination, uint32_t size);
bool FlashErase(uint32_t offset, uint32_t size);
bool FlashWrite(uint32_t offset, const void* data, uint32_t size);

// --- system -------------------------------------------------------------------

// The independent watchdog: started once the audio runs, fed by every audio
// callback, so a stalled callback restarts the module.
void StartWatchdog();
void FeedWatchdog();

// Masks interrupts, so the main loop can copy what an interrupt writes.
uint32_t EnterCritical();
void ExitCritical(uint32_t state);

// Restarts into the Daisy bootloader and waits there for a firmware update.
void ResetToBootloader();

}  // namespace hal
}  // namespace sidefx

#endif  // SIDEFX_HAL_H_
