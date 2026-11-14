// Copyright 2026 the Plaitsy authors. MIT licence, see plaits/firmware/LICENSE.
//
// Plaitsy: the board layer on the Daisy Seed (libDaisy).

#include "hal.h"

#include <string.h>

#include "daisy_seed.h"
#include "sys/dma.h"

namespace plaitsy {
namespace hal {

using namespace daisy;

namespace {

// Seed pins, from circuit.py's SEED_PINS.
constexpr Pin kAdcPins[ADC_INPUT_LAST] = {
  seed::A0, seed::A1, seed::A2, seed::A3, seed::A4, seed::A5, seed::A6, seed::A9
};
constexpr Pin kMuxOut = seed::A10;
constexpr Pin kMuxS0 = seed::D26;
constexpr Pin kMuxS1 = seed::D27;
constexpr Pin kMuxS2 = seed::D28;
constexpr Pin kButtonPins[2] = { seed::D0, seed::D1 };
constexpr Pin kButtonLedA = seed::D2;
constexpr Pin kButtonLedB = seed::D3;
constexpr Pin kSpiSck = seed::D8;    // SPI1 SCK  -> 74HC595 SRCLK
constexpr Pin kSpiMosi = seed::D10;  // SPI1 MOSI -> U9 SER
constexpr Pin kLedLatch = seed::D13; // -> 74HC595 RCLK
constexpr Pin kProbe = seed::D14;

// 8x oversampling keeps a full scan of the nine channels near 0.21 ms, so the
// reading the normalization detector compares with the probe is always taken
// well after the probe last changed (it changes once per millisecond).
constexpr AdcHandle::OverSampling kOversampling = AdcHandle::OVS_8;

DaisySeed* seed_ = nullptr;
AdcHandle adc;
bool adc_started = false;
bool leds_ready = false;
IWDG_HandleTypeDef watchdog;
GPIO buttons[2];
GPIO probe;
GPIO button_led_a;
GPIO button_led_b;
GPIO led_latch;
SpiHandle spi;

volatile uint16_t led_bits = 0;
volatile bool led_bits_pending = false;

}  // namespace

void Init(DaisySeed* seed) {
  seed_ = seed;
}

uint32_t Milliseconds() {
  return System::GetNow();
}

void StartWatchdog() {
  // Stopped while a debugger halts the core, so a breakpoint does not reset.
  __HAL_DBGMCU_FREEZE_IWDG1();
  // LSI (32 kHz) / 64, 1000 counts: about 2 s. Plaits' is about 1.6 s.
  IWDG_HandleTypeDef handle;
  handle.Instance = IWDG1;
  handle.Init.Prescaler = IWDG_PRESCALER_64;
  handle.Init.Reload = 1000;
  handle.Init.Window = IWDG_WINDOW_DISABLE;
  if (HAL_IWDG_Init(&handle) == HAL_OK) {
    watchdog = handle;  // from now on the audio callback feeds it
  }
}

void FeedWatchdog() {
  if (watchdog.Instance) {
    HAL_IWDG_Refresh(&watchdog);
  }
}

void InitAdc() {
  if (adc_started) {
    return;
  }
  AdcChannelConfig config[ADC_INPUT_LAST + 1];
  for (int i = 0; i < ADC_INPUT_LAST; ++i) {
    config[i].InitSingle(kAdcPins[i]);
  }
  // Last in the sequence: libDaisy moves the mux address when a scan ends,
  // so the pot being read has a whole scan to settle. Sampled for 16.5 ADC
  // cycles, not the default 8.5: the wiper (up to 2.5k), the 74HC4051's
  // on-resistance at 3.3 V and its common capacitance (no series resistor)
  // need about 1.5 us; 8.5 cycles is 1.4 us. The scan grows from about 0.20
  // to 0.21 ms. Not 32.5 cycles: that would make the scan about 0.23 ms,
  // close to the 0.245 ms where the host tests lose a TIMBRE data transfer.
  config[ADC_INPUT_LAST].InitMux(
      kMuxOut, kNumMuxChannels, kMuxS0, kMuxS1, kMuxS2,
      AdcChannelConfig::SPEED_16CYCLES_5);
  adc.Init(config, ADC_INPUT_LAST + 1, kOversampling);
  adc.Start();
  adc_started = true;
}

uint16_t ReadAdc(AdcInput input) {
  return adc.Get(input);
}

uint16_t ReadMux(int channel) {
  return adc.GetMux(ADC_INPUT_LAST, channel);
}

void InitButtons() {
  for (int i = 0; i < 2; ++i) {
    buttons[i].Init(kButtonPins[i], GPIO::Mode::INPUT, GPIO::Pull::PULLUP);
  }
}

bool ButtonPressed(Button button) {
  return !buttons[button].Read();
}

void InitProbe() {
  probe.Init(kProbe, GPIO::Mode::OUTPUT);
}

void WriteProbe(bool high) {
  probe.Write(high);
}

void InitLeds() {
  if (leds_ready) {
    return;
  }
  button_led_a.Init(kButtonLedA, GPIO::Mode::OUTPUT);
  button_led_b.Init(kButtonLedB, GPIO::Mode::OUTPUT);
  led_latch.Init(kLedLatch, GPIO::Mode::OUTPUT);
  led_latch.Write(false);

  SpiHandle::Config config;
  config.periph = SpiHandle::Config::Peripheral::SPI_1;
  config.mode = SpiHandle::Config::Mode::MASTER;
  config.direction = SpiHandle::Config::Direction::TWO_LINES_TX_ONLY;
  config.datasize = 8;
  config.clock_polarity = SpiHandle::Config::ClockPolarity::LOW;
  config.clock_phase = SpiHandle::Config::ClockPhase::ONE_EDGE;
  config.nss = SpiHandle::Config::NSS::SOFT;
  // SPI1 runs from PLL2P (25 MHz): 1.6 MHz, 10 us for the 16 bits.
  config.baud_prescaler = SpiHandle::Config::BaudPrescaler::PS_16;
  config.pin_config.sclk = kSpiSck;
  config.pin_config.mosi = kSpiMosi;
  config.pin_config.miso = Pin();
  config.pin_config.nss = Pin();
  spi.Init(config);

  led_bits = 0;
  led_bits_pending = true;
  leds_ready = true;
}

void SetLedShiftRegisters(uint16_t bits) {
  if (bits != led_bits) {
    led_bits = bits;
    led_bits_pending = true;
  }
}

void WriteButtonLeds(bool a, bool b) {
  button_led_a.Write(a);
  button_led_b.Write(b);
}

void Service() {
  if (!led_bits_pending) {
    return;
  }
  led_bits_pending = false;
  const uint16_t bits = led_bits;
  // U10 (the greens) is last in the chain, so its byte goes out first.
  uint8_t bytes[2] = {
    static_cast<uint8_t>(bits >> 8),
    static_cast<uint8_t>(bits & 0xff)
  };
  spi.BlockingTransmit(bytes, 2);
  // RCLK pulse; the 74HC595 wants it at least ~50 ns wide at 3.3 V.
  led_latch.Write(true);
  System::DelayTicks(100);
  led_latch.Write(false);
}

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  uint8_t* source = static_cast<uint8_t*>(seed_->qspi.GetData(offset));
  // The data cache may still hold lines from before the last erase or write.
  dsy_dma_invalidate_cache_for_buffer(source, size);
  memcpy(destination, source, size);
}

bool FlashErase(uint32_t offset, uint32_t size) {
  return seed_->qspi.Erase(offset, offset + size) == QSPIHandle::Result::OK;
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  return seed_->qspi.Write(
      offset, size,
      static_cast<uint8_t*>(const_cast<void*>(data))) == QSPIHandle::Result::OK;
}

uint32_t EnterCritical() {
  uint32_t state = __get_PRIMASK();
  __disable_irq();
  return state;
}

void ExitCritical(uint32_t state) {
  __set_PRIMASK(state);
}

}  // namespace hal
}  // namespace plaitsy
