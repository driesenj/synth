// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the screen on the Daisy Seed (the display half of hal.h, and
// hal::InitDisplay from hal_daisy.h).
//
// The panel is a Waveshare 1.9inch LCD Module: an ST7789V2 driving a 170 x
// 320 IPS glass, used in portrait. The controller's memory is 240 x 320 and
// the glass sits on its columns 35..204 (kColumnOffset); 240 - 170 - 35 is
// 35 too, so the offset stays the same when the picture is turned by 180
// degrees (MADCTL MX | MY mirror the columns about the middle of the 240).
//
// Wiring (side-fx/docs/design.md, "Daisy Seed pin map"):
//   D8  PG11  SCK    SPI1, mode 0, transmit only
//   D10 PB5   MOSI   SPI1
//   D7  PG10  CS     a GPIO (software NSS): low for a whole command or flush
//   D11 PB8   DC     low for a command byte, high for its parameters/pixels
//   D13 PB6   RST
//   D12 PB9   BL     TIM4 CH4 PWM, through the module's own transistor
//
// Speed: SPI1's kernel clock on the Seed is PLL2P = 25 MHz (libDaisy's
// system.cpp), so the fastest prescaler, /2, gives 12.5 MHz: a whole frame
// (108,800 bytes) in 70 ms, a 40-row strip in 9 ms. That is the default,
// because the lines run ~20 cm over two boards and a cable. Building with
// SIDEFX_LCD_SPI_FAST=1 clocks SPI1 (and SPI2/3, which share the selection
// and are unused on Side FXy) from PLL1Q instead: 16 MHz / 4 * 240 / 5 =
// 192 MHz with the CPU boosted to 480 MHz (160 MHz at 400 MHz), /8 = 24 MHz
// (20 MHz): a frame in 36 ms. Try it once the screen works at the default.
//
// Commands go out blocking. Pixels go by DMA (DMA2 stream 3, libDaisy's SPI
// DMA) straight from the frame in SDRAM, in chunks of whole rows below the
// 65,535-byte DMA limit, each chunk started from the previous one's end
// callback; CS goes high after the last. The frame sits in the D-cache, so
// the rows are cleaned to SDRAM before the DMA reads them.

#include "daisy_seed.h"
#include "hal.h"
#include "hal_daisy.h"

#ifndef SIDEFX_LCD_SPI_FAST
#define SIDEFX_LCD_SPI_FAST 0
#endif

namespace sidefx {
namespace hal {

namespace {

using daisy::GPIO;
using daisy::PWMHandle;
using daisy::SpiHandle;
using daisy::System;

const int kColumnOffset = 35;
const int kRowBytes = kDisplayWidth * 2;
// Whole rows per DMA chunk: 192 rows, 65,280 bytes.
const int kRowsPerChunk = 65535 / kRowBytes;

// Which way up MADCTL 0 shows the picture on the mounted module is not
// known yet (portrait, flex cable end up). If Side FXy's screen comes up
// upside down with SetDisplayFlip(false), set this to true.
const bool kPanelRotated180 = false;

// The backlight PWM: TIM4 counts at the timer clock (2 x APB1 = sysclk / 2
// on the Seed); a period of 9600 ticks gives 25 kHz at 480 MHz (20.8 kHz at
// 400 MHz), above hearing, with 9600 steps of brightness.
const uint32_t kBacklightPeriod = 9599;

// ST7789 commands.
const uint8_t kSwReset = 0x01;
const uint8_t kSleepOut = 0x11;
const uint8_t kInversionOn = 0x21;
const uint8_t kDisplayOn = 0x29;
const uint8_t kColumnAddress = 0x2a;
const uint8_t kRowAddress = 0x2b;
const uint8_t kMemoryWrite = 0x2c;
const uint8_t kMemoryAccess = 0x36;  // MADCTL
const uint8_t kPixelFormat = 0x3a;
const uint8_t kMadctlMY = 0x80;
const uint8_t kMadctlMX = 0x40;

// The init sequence of Waveshare's demo code for this module (LCD_1in9.c):
// porch, gate, VCOM and power settings and the gamma curves for its glass.
// Each entry: command, parameter count, parameters.
const uint8_t kInitSequence[] = {
  kPixelFormat, 1, 0x55,                          // 16 bits per pixel
  0xb2, 5, 0x0c, 0x0c, 0x00, 0x33, 0x33,          // PORCTRL
  0xb7, 1, 0x35,                                  // GCTRL
  0xbb, 1, 0x13,                                  // VCOMS
  0xc0, 1, 0x2c,                                  // LCMCTRL
  0xc2, 1, 0x01,                                  // VDVVRHEN
  0xc3, 1, 0x0b,                                  // VRHS
  0xc4, 1, 0x20,                                  // VDVS
  0xc6, 1, 0x0f,                                  // FRCTRL2: 60 Hz
  0xd0, 2, 0xa4, 0xa1,                            // PWCTRL1
  0xd6, 1, 0xa1,                                  // undocumented, as Waveshare
  0xe0, 14, 0x00, 0x03, 0x07, 0x08, 0x07, 0x15, 0x2a, 0x44, 0x42, 0x0a,
            0x17, 0x18, 0x25, 0x27,               // PVGAMCTRL
  0xe1, 14, 0x00, 0x03, 0x08, 0x07, 0x07, 0x23, 0x2a, 0x43, 0x42, 0x09,
            0x18, 0x17, 0x25, 0x27,               // NVGAMCTRL
  kInversionOn, 0,                                // IPS glass: inverted
};

SpiHandle spi;
GPIO cs;
GPIO dc;
GPIO rst;
PWMHandle backlight_pwm;
bool flipped = false;
// The frame of the last flush, for SetDisplayFlip to send again whole.
const uint16_t* last_frame = 0;

// The DMA chain, shared with the end callback (an interrupt).
volatile bool busy = false;
uint8_t* volatile next_chunk = 0;
volatile uint32_t bytes_left = 0;

// A row of black for clearing the panel's memory at start-up.
uint8_t black_row[kRowBytes];

void Command(uint8_t command) {
  dc.Write(false);
  spi.BlockingTransmit(&command, 1);
  dc.Write(true);
}

void Data(const uint8_t* data, size_t size) {
  if (size) {
    spi.BlockingTransmit(const_cast<uint8_t*>(data), size);
  }
}

void CommandWithData(uint8_t command, const uint8_t* data, size_t size) {
  cs.Write(false);
  Command(command);
  Data(data, size);
  cs.Write(true);
}

// Sets the window rows y0..y1 (all columns) and starts a memory write;
// leaves CS low and DC high for the pixels.
void BeginWrite(int y0, int y1) {
  const int x0 = kColumnOffset;
  const int x1 = kColumnOffset + kDisplayWidth - 1;
  const uint8_t columns[4] = { uint8_t(x0 >> 8), uint8_t(x0),
                               uint8_t(x1 >> 8), uint8_t(x1) };
  const uint8_t rows[4] = { uint8_t(y0 >> 8), uint8_t(y0),
                            uint8_t(y1 >> 8), uint8_t(y1) };
  cs.Write(false);
  Command(kColumnAddress);
  Data(columns, 4);
  Command(kRowAddress);
  Data(rows, 4);
  Command(kMemoryWrite);
}

void WriteMadctl() {
  const bool turned = flipped != kPanelRotated180;
  const uint8_t madctl = turned ? uint8_t(kMadctlMX | kMadctlMY) : 0;
  CommandWithData(kMemoryAccess, &madctl, 1);
}

void StartChunk();

void ChunkDone(void* context, SpiHandle::Result result) {
  (void)context;
  if (result != SpiHandle::Result::OK || bytes_left == 0) {
    bytes_left = 0;
    cs.Write(true);
    busy = false;
    return;
  }
  StartChunk();
}

void StartChunk() {
  const uint32_t chunk_limit = uint32_t(kRowsPerChunk) * kRowBytes;
  const uint32_t size = bytes_left < chunk_limit ? bytes_left : chunk_limit;
  uint8_t* data = next_chunk;
  next_chunk = data + size;
  bytes_left = bytes_left - size;
  if (spi.DmaTransmit(data, size, 0, ChunkDone, 0) != SpiHandle::Result::OK) {
    // libDaisy has already called ChunkDone with the error.
    bytes_left = 0;
  }
}

}  // namespace

void InitDisplay(float backlight) {
#if SIDEFX_LCD_SPI_FAST
  __HAL_RCC_SPI123_CONFIG(RCC_SPI123CLKSOURCE_PLL);
#endif

  cs.Init(daisy::seed::D7, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
          GPIO::Speed::MEDIUM);
  cs.Write(true);
  dc.Init(daisy::seed::D11, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
          GPIO::Speed::MEDIUM);
  dc.Write(true);
  rst.Init(daisy::seed::D13, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
           GPIO::Speed::LOW);
  rst.Write(true);

  SpiHandle::Config config;
  config.periph = SpiHandle::Config::Peripheral::SPI_1;
  config.mode = SpiHandle::Config::Mode::MASTER;
  config.direction = SpiHandle::Config::Direction::TWO_LINES_TX_ONLY;
  config.datasize = 8;
  config.clock_polarity = SpiHandle::Config::ClockPolarity::LOW;
  config.clock_phase = SpiHandle::Config::ClockPhase::ONE_EDGE;
  config.nss = SpiHandle::Config::NSS::SOFT;
  config.baud_prescaler = SIDEFX_LCD_SPI_FAST
      ? SpiHandle::Config::BaudPrescaler::PS_8
      : SpiHandle::Config::BaudPrescaler::PS_2;
  config.pin_config.sclk = daisy::seed::D8;
  config.pin_config.mosi = daisy::seed::D10;
  config.pin_config.miso = daisy::Pin();
  config.pin_config.nss = daisy::Pin();
  spi.Init(config);

  // The backlight stays off until the panel shows black.
  PWMHandle::Config pwm_config(PWMHandle::Config::Peripheral::TIM_4, 0,
                               kBacklightPeriod);
  backlight_pwm.Init(pwm_config);
  backlight_pwm.Channel4().Init(PWMHandle::Channel::Config(
      daisy::seed::D12, PWMHandle::Channel::Config::Polarity::HIGH));
  backlight_pwm.Channel4().SetRaw(0);

  // Hardware reset, then a software one for good measure: the ST7789 wants
  // 120 ms after either before it takes Sleep Out.
  rst.Write(true);
  System::Delay(5);
  rst.Write(false);
  System::Delay(10);
  rst.Write(true);
  System::Delay(120);
  CommandWithData(kSwReset, 0, 0);
  System::Delay(120);

  WriteMadctl();
  for (size_t i = 0; i < sizeof(kInitSequence); ) {
    const uint8_t command = kInitSequence[i];
    const uint8_t count = kInitSequence[i + 1];
    CommandWithData(command, &kInitSequence[i + 2], count);
    i += 2 + count;
  }
  CommandWithData(kSleepOut, 0, 0);
  System::Delay(120);

  // Black in the whole of the visible memory before the display goes on.
  for (int i = 0; i < kRowBytes; ++i) {
    black_row[i] = 0;
  }
  BeginWrite(0, kDisplayHeight - 1);
  for (int y = 0; y < kDisplayHeight; ++y) {
    Data(black_row, kRowBytes);
  }
  cs.Write(true);
  CommandWithData(kDisplayOn, 0, 0);
  System::Delay(20);

  SetBacklight(backlight);
}

void DisplayFlush(const uint16_t* frame, int y0, int y1) {
  if (y0 < 0) {
    y0 = 0;
  }
  if (y1 > kDisplayHeight - 1) {
    y1 = kDisplayHeight - 1;
  }
  if (!frame || y1 < y0) {
    return;
  }
  // One transfer at a time: a flush while the last is still going waits.
  while (busy) { }
  last_frame = frame;

  uint8_t* data = reinterpret_cast<uint8_t*>(
      const_cast<uint16_t*>(frame + y0 * kDisplayWidth));
  const uint32_t size = uint32_t(y1 - y0 + 1) * kRowBytes;

  // Write the rows back from the D-cache to SDRAM, in whole 32-byte lines.
  const uint32_t start = reinterpret_cast<uint32_t>(data) & ~31u;
  const uint32_t end = (reinterpret_cast<uint32_t>(data) + size + 31u) & ~31u;
  SCB_CleanDCache_by_Addr(reinterpret_cast<uint32_t*>(start),
                          int32_t(end - start));

  BeginWrite(y0, y1);
  busy = true;
  next_chunk = data;
  bytes_left = size;
  StartChunk();
}

bool DisplayBusy() { return busy; }

void SetBacklight(float level) {
  level = level < 0.0f ? 0.0f : (level > 1.0f ? 1.0f : level);
  // Square law: the eye's response to the LED's duty cycle is closer to a
  // power law than linear, so equal steps of `level` look like equal steps.
  const float duty = level * level;
  backlight_pwm.Channel4().SetRaw(
      uint32_t(duty * float(kBacklightPeriod) + 0.5f));
}

// MADCTL MX | MY change only how later memory writes are mapped, not what
// the panel's memory holds: without sending the frame again, only the rows
// the UI redraws would turn (and land at the other end of the glass), over
// the old picture still the old way up.
void SetDisplayFlip(bool flip) {
  if (flip == flipped) {
    return;
  }
  while (busy) { }
  flipped = flip;
  WriteMadctl();
  if (last_frame) {
    DisplayFlush(last_frame, 0, kDisplayHeight - 1);
  }
}

}  // namespace hal
}  // namespace sidefx
