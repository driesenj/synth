// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: the board layer on the Daisy Seed (libDaisy 9.0.0).
//
// libDaisy sets up the pins, the ADC with its mux, the SPI peripheral, the
// RNG and the QSPI flash. What the 32 kHz interrupt does at every sample
// goes straight to the registers: the gate and clock pins, the chip selects
// and latches, and the SPI transfers, which run with TSIZE = 0 (an endless
// transfer started once) so that a frame is one write to TXDR and a wait for
// its echo in RXDR. The bus runs at 6.25 MHz in SPI mode 0 for all three
// kinds of device, so it never needs reconfiguring: the four DAC frames take
// about 11 us per sample, a third of the CPU.

#include "hal.h"

#include <string.h>

#include "daisy_seed.h"
#include "sys/dma.h"

namespace marblesy {
namespace hal {

using namespace daisy;

namespace {

// Seed pins, from circuit.py and design.md's Seed pin map.
constexpr Pin kCvPins[CV_INPUT_LAST] = {
  seed::A1, seed::A2, seed::A3, seed::A4, seed::A5, seed::A6, seed::A9
};
constexpr Pin kMuxOut = seed::A10;
constexpr Pin kMuxS0 = seed::D26;
constexpr Pin kMuxS1 = seed::D27;
constexpr Pin kMuxS2 = seed::D28;
constexpr Pin kClockT = seed::D0;     // PB12
constexpr Pin kClockX = seed::D1;     // PC11
constexpr Pin kGate1 = seed::D2;      // PC10
constexpr Pin kGate2 = seed::D3;      // PC9
constexpr Pin kGate3 = seed::D4;      // PC8
constexpr Pin kProbe = seed::D15;     // PC0
constexpr Pin kDacCs1 = seed::D7;     // PG10, U7
constexpr Pin kSpiSck = seed::D8;     // PG11, SPI1 SCK
constexpr Pin kSpiMiso = seed::D9;    // PB4, SPI1 MISO <- 74HC165 Q7
constexpr Pin kSpiMosi = seed::D10;   // PB5, SPI1 MOSI
constexpr Pin kDacCs2 = seed::D11;    // PB8, U8
constexpr Pin kDacLdac = seed::D12;   // PB9
constexpr Pin kLedLatch = seed::D13;  // PB6, 74HC595 RCLK
constexpr Pin kButtonLoad = seed::D14;  // PB7, 74HC165 /PL

// The registers below assume these ports and pins.
static_assert(kClockT.port == PORTB && kClockT.pin == 12, "D0");
static_assert(kClockX.port == PORTC && kClockX.pin == 11, "D1");
static_assert(kGate1.port == PORTC && kGate1.pin == 10, "D2");
static_assert(kGate2.port == PORTC && kGate2.pin == 9, "D3");
static_assert(kGate3.port == PORTC && kGate3.pin == 8, "D4");
static_assert(kProbe.port == PORTC && kProbe.pin == 0, "D15");
static_assert(kDacCs1.port == PORTG && kDacCs1.pin == 10, "D7");
static_assert(kDacCs2.port == PORTB && kDacCs2.pin == 8, "D11");
static_assert(kDacLdac.port == PORTB && kDacLdac.pin == 9, "D12");
static_assert(kLedLatch.port == PORTB && kLedLatch.pin == 6, "D13");
static_assert(kButtonLoad.port == PORTB && kButtonLoad.pin == 7, "D14");

const uint32_t kClockTMask = 1 << 12;  // GPIOB
const uint32_t kClockXMask = 1 << 11;  // GPIOC
const uint32_t kGateMask[3] = { 1 << 10, 1 << 9, 1 << 8 };  // GPIOC
const uint32_t kProbeMask = 1 << 0;   // GPIOC
const uint32_t kCs1Mask = 1 << 10;    // GPIOG
const uint32_t kCs2Mask = 1 << 8;     // GPIOB
const uint32_t kLdacMask = 1 << 9;    // GPIOB
const uint32_t kLatchMask = 1 << 6;   // GPIOB
const uint32_t kLoadMask = 1 << 7;    // GPIOB

// 8x oversampling: a scan of the eight channels takes about 0.2 ms, so each
// CV is read about every 0.2 ms and each pot every 1.6 ms.
constexpr AdcHandle::OverSampling kOversampling = AdcHandle::OVS_8;

// TIM7 runs from the APB1 timer clock (2 x PCLK1, 240 MHz at 480 MHz).
const uint32_t kIoPriority = 0;
const uint32_t kAdcDmaPriority = 1;  // below the I/O interrupt
const uint32_t kDspPriority = 15;    // the lowest

DaisySeed* seed_ = nullptr;
AdcHandle adc;
bool adc_started = false;
bool gpio_ready = false;
bool bus_ready = false;
IWDG_HandleTypeDef watchdog;
GPIO clock_t_pin;
GPIO clock_x_pin;
GPIO gate_pins[3];
GPIO probe_pin;
GPIO dac_cs1;
GPIO dac_cs2;
GPIO dac_ldac;
GPIO led_latch;
GPIO button_load;
SpiHandle spi;

Callback io_callback = nullptr;
Callback dsp_callback = nullptr;

// About `ns` nanoseconds at 480 MHz (a few cycles per iteration, so at
// least that long).
inline void Wait(uint32_t ns) {
  for (volatile uint32_t i = 0; i < (ns + 4) / 5; ++i) { }
}

// The data registers take 16-bit accesses for 16-bit frames (a 32-bit write
// would queue two frames).
volatile uint16_t* const spi_txdr = reinterpret_cast<volatile uint16_t*>(
    reinterpret_cast<uintptr_t>(&SPI1->TXDR));
volatile uint16_t* const spi_rxdr = reinterpret_cast<volatile uint16_t*>(
    reinterpret_cast<uintptr_t>(&SPI1->RXDR));

// (Re)starts the endless transfer: TSIZE = 0, CSTART once, so a frame is
// one write to TXDR. Disabling first flushes both FIFOs.
void StartEndlessTransfer() {
  SPI1->CR1 &= ~SPI_CR1_SPE;
  SPI1->CFG1 &= ~SPI_CFG1_FTHLV;  // one frame per FIFO event
  SPI1->CR2 = 0;
  SPI1->IFCR = 0xff8;
  SPI1->CR1 |= SPI_CR1_SPE;
  SPI1->CR1 |= SPI_CR1_CSTART;
}

// One 16-bit frame out and its echo in, one frame in flight at a time.
// With a timeout, so that a stuck peripheral costs a wrong frame, not the
// module; the transfer then restarts, so that a late echo cannot leave
// every later frame one behind.
inline uint16_t Transfer(uint16_t word) {
  *spi_txdr = word;
  for (uint32_t timeout = 4000; timeout; --timeout) {
    if (SPI1->SR & SPI_SR_RXP) {
      return *spi_rxdr;
    }
  }
  StartEndlessTransfer();
  return 0xffff;
}

}  // namespace

void Init(DaisySeed* seed) {
  seed_ = seed;
}

uint32_t Milliseconds() {
  return System::GetNow();
}

void Delay(uint32_t ms) {
  System::Delay(ms);
}

void StartInterrupts(Callback io, Callback dsp) {
  io_callback = io;
  dsp_callback = dsp;

  HAL_NVIC_SetPriority(PendSV_IRQn, kDspPriority, 0);

  __HAL_RCC_TIM7_CLK_ENABLE();
  const uint32_t timer_clock = 2 * HAL_RCC_GetPCLK1Freq();
  TIM7->CR1 = 0;
  TIM7->PSC = 0;
  TIM7->ARR = timer_clock / kIoRate - 1;
  TIM7->CNT = 0;
  TIM7->EGR = TIM_EGR_UG;
  TIM7->SR = 0;
  TIM7->DIER = TIM_DIER_UIE;
  HAL_NVIC_SetPriority(TIM7_IRQn, kIoPriority, 0);
  HAL_NVIC_EnableIRQ(TIM7_IRQn);
  TIM7->CR1 = TIM_CR1_CEN;
}

void PendDsp() {
  SCB->ICSR = SCB_ICSR_PENDSVSET_Msk;
}

void StartWatchdog() {
  // Stopped while a debugger halts the core, so a breakpoint does not reset.
  __HAL_DBGMCU_FREEZE_IWDG1();
  // LSI (32 kHz) / 64, 1000 counts: about 2 s. Marbles' is about 4 s.
  IWDG_HandleTypeDef handle;
  handle.Instance = IWDG1;
  handle.Init.Prescaler = IWDG_PRESCALER_64;
  handle.Init.Reload = 1000;
  handle.Init.Window = IWDG_WINDOW_DISABLE;
  if (HAL_IWDG_Init(&handle) == HAL_OK) {
    watchdog = handle;  // from now on every DSP pass feeds it
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
  AdcChannelConfig config[CV_INPUT_LAST + 1];
  for (int i = 0; i < CV_INPUT_LAST; ++i) {
    config[i].InitSingle(kCvPins[i]);
  }
  // Last in the sequence: libDaisy moves the mux address when a scan ends,
  // so the pot being read has a whole scan to settle.
  config[CV_INPUT_LAST].InitMux(kMuxOut, POT_LAST, kMuxS0, kMuxS1, kMuxS2);
  adc.Init(config, CV_INPUT_LAST + 1, kOversampling);
  HAL_NVIC_SetPriority(DMA1_Stream2_IRQn, kAdcDmaPriority, 0);
  adc.Start();
  adc_started = true;
  // Every pot read at least once before the first block is rendered.
  System::Delay(5);
}

uint16_t ReadCv(CvInput input) {
  return adc.Get(input);
}

uint16_t ReadPot(Pot pot) {
  return adc.GetMux(CV_INPUT_LAST, pot);
}

void InitGpio() {
  if (gpio_ready) {
    return;
  }
  // The clock stages have their own 10k pull-ups to 3V3D.
  clock_t_pin.Init(kClockT, GPIO::Mode::INPUT, GPIO::Pull::NOPULL);
  clock_x_pin.Init(kClockX, GPIO::Mode::INPUT, GPIO::Pull::NOPULL);
  gate_pins[0].Init(kGate1, GPIO::Mode::OUTPUT);
  gate_pins[1].Init(kGate2, GPIO::Mode::OUTPUT);
  gate_pins[2].Init(kGate3, GPIO::Mode::OUTPUT);
  probe_pin.Init(kProbe, GPIO::Mode::OUTPUT);
  WriteGates(0);
  WriteProbe(false);
  gpio_ready = true;
}

uint32_t ReadClockPins() {
  uint32_t pins = 0;
  if (GPIOB->IDR & kClockTMask) {
    pins |= 1;
  }
  if (GPIOC->IDR & kClockXMask) {
    pins |= 2;
  }
  return pins;
}

void WriteProbe(bool high) {
  GPIOC->BSRR = high ? kProbeMask : kProbeMask << 16;
}

void WriteGates(uint32_t gates) {
  uint32_t bsrr = 0;
  for (int i = 0; i < 3; ++i) {
    bsrr |= (gates & (1 << i)) ? kGateMask[i] : kGateMask[i] << 16;
  }
  GPIOC->BSRR = bsrr;
}

void InitBus() {
  if (bus_ready) {
    return;
  }
  // Chip selects and LDAC idle high, the latch low, /PL high (shift).
  dac_cs1.Init(kDacCs1, GPIO::Mode::OUTPUT);
  dac_cs2.Init(kDacCs2, GPIO::Mode::OUTPUT);
  dac_ldac.Init(kDacLdac, GPIO::Mode::OUTPUT);
  led_latch.Init(kLedLatch, GPIO::Mode::OUTPUT);
  button_load.Init(kButtonLoad, GPIO::Mode::OUTPUT);
  dac_cs1.Write(true);
  dac_cs2.Write(true);
  dac_ldac.Write(true);
  led_latch.Write(false);
  button_load.Write(true);

  SpiHandle::Config config;
  config.periph = SpiHandle::Config::Peripheral::SPI_1;
  config.mode = SpiHandle::Config::Mode::MASTER;
  config.direction = SpiHandle::Config::Direction::TWO_LINES;
  config.datasize = 16;
  config.clock_polarity = SpiHandle::Config::ClockPolarity::LOW;
  config.clock_phase = SpiHandle::Config::ClockPhase::ONE_EDGE;
  config.nss = SpiHandle::Config::NSS::SOFT;
  // SPI1 runs from PLL2P (25 MHz): 6.25 MHz. Fast enough for the MCP4922s
  // (20 MHz) and slow enough for the 74HC595 / 74HC165 at 3.3 V over the
  // board-to-board header.
  config.baud_prescaler = SpiHandle::Config::BaudPrescaler::PS_4;
  config.pin_config.sclk = kSpiSck;
  config.pin_config.miso = kSpiMiso;
  config.pin_config.mosi = kSpiMosi;
  config.pin_config.nss = Pin();
  spi.Init(config);
  // MISO pulled up (libDaisy leaves it floating): with the faceplate
  // unplugged or its header open, the buttons then read as released.
  GPIOB->PUPDR = (GPIOB->PUPDR & ~(3u << (4 * 2))) | (1u << (4 * 2));

  StartEndlessTransfer();
  bus_ready = true;
}

void WriteDacs(const uint16_t words[4]) {
  for (int i = 0; i < 4; ++i) {
    volatile uint32_t* bsrr = i < 2 ? &GPIOG->BSRR : &GPIOB->BSRR;
    const uint32_t cs = i < 2 ? kCs1Mask : kCs2Mask;
    *bsrr = cs << 16;
    Transfer(words[i]);
    Wait(20);  // CS hold after the last clock
    *bsrr = cs;
    Wait(50);  // CS high time; after U8, CS to LDAC setup (40 ns)
  }
  // LDAC low at least 100 ns: the four input registers go to the outputs.
  GPIOB->BSRR = kLdacMask << 16;
  Wait(150);
  GPIOB->BSRR = kLdacMask;
}

void WriteLeds(uint16_t bits) {
  // U10 is last in the chain, so its byte goes out first: MSB first, bit
  // 15 ends in U10 QH.
  Transfer(bits);
  Wait(50);
  GPIOB->BSRR = kLatchMask;
  Wait(100);
  GPIOB->BSRR = kLatchMask << 16;
}

uint8_t ReadButtons() {
  // /PL low loads the eight inputs; then Q7 shifts out D7 first, sampled
  // at each rising edge before the 74HC165 moves on (SPI mode 0).
  GPIOB->BSRR = kLoadMask << 16;
  Wait(200);
  GPIOB->BSRR = kLoadMask;
  Wait(100);
  return static_cast<uint8_t>(Transfer(0) >> 8);
}

void InitRng() {
  Random::Init();
}

bool RngReady() {
  // A seed or clock error leaves stale data: Marbles then falls back on
  // its own generator, as it does when the stream runs dry.
  const uint32_t sr = RNG->SR;
  return (sr & RNG_SR_DRDY) && !(sr & (RNG_SR_SECS | RNG_SR_CECS));
}

uint32_t RngData() {
  return RNG->DR;
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

void ResetToBootloader() {
  System::ResetToBootloader(System::BootloaderMode::DAISY_INFINITE_TIMEOUT);
}

}  // namespace hal
}  // namespace marblesy

extern "C" {

void TIM7_IRQHandler(void) {
  TIM7->SR = ~TIM_SR_UIF;
  marblesy::hal::io_callback();
}

void PendSV_Handler(void) {
  marblesy::hal::dsp_callback();
}

}
