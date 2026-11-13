// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the board half of hal.h on the Daisy Seed (libDaisy v9.0.0):
// time, the shift-register chain, SHIFT and CLOCK, the CV ADC, MIDI in,
// QSPI flash, watchdog, critical sections, the bootloader. The display half
// is display_daisy.cc. tools/check_pins.py checks the pins and the chain's
// bit order below against side-fx/hardware/tools/circuit.py.
//
// Timers. libDaisy's System runs TIM2 (its tick); the display's backlight
// PWM is TIM4. That leaves TIM3 and TIM5:
//   TIM5 (32 bit)  free-running at 1 MHz: Microseconds(). System::GetUs()
//                  is TIM2's 240 MHz count divided by 240, which wraps
//                  after 17.9 s at a value that is not 2^32, so differences
//                  across its wrap come out wrong; TIM5's wrap is 2^32 us.
//   TIM3 (16 bit)  the 4 kHz control interrupt: 240 MHz / 60,000.
//
// The chain (side-fx/docs/design.md, "Encoders, buttons and LEDs on one
// chain"): two 74HC165s on the faceplate (U1's Q7 is SR_DIN, U2's Q7 feeds
// U1's DS) and the main board's 74HC595, sharing SR_CLK; SR_LOAD is both the
// 165s' /PL and the 595's RCLK. One scan:
//   SR_LOAD low: the 165s load their 16 inputs.
//   SR_LOAD high: the 595 latches the LED byte the previous scan shifted in.
//   16 clocks: before each rising SR_CLK edge, read SR_DIN and set SR_DOUT.
// The 165 shifts out D7 first, so the 16 bits arrive as U1 D7..D0, then
// U2 D7..D0; shifted into a word MSB first that is raw bit 8 + n = U1 Dn,
// raw bit n = U2 Dn. With circuit.py's SR_INPUTS:
//   raw bit  15 14 13 12 11 10  9  8 | 7   6   5   4   3  2  1  0
//   U1 / U2  D7 ..           ..    D0| D7  ..                    D0
//   net      4B 4A 3B 3A 2B 2A 1B 1A | REV TEX DEL PIT K4 K3 K2 K1
// (nB / nA: ENCn phase B / A). Every input has a pull-up, so a closed
// switch or a phase at ground reads 0; ControlScan has 1 for those.
// The 595: each rising SR_CLK edge moves QA->QB->..->QH and takes SR_DOUT
// into QA, so of the 16 bits sent the last lands in QA and the 9th in QH.
// Sending the word (LED byte & 0x1f) MSB first puts Led n in Q(A+n):
// PITCH, DELAY, TEXTURE, REVERB, SHIFT in QA..QE (circuit.py's LED_ORDER),
// zeros in QF..QH, and the first 8 bits fall out of QH' unused.
//
// SR_CLK and SR_LOAD run about 19 cm over two boards and a header: the pins
// are at GPIO speed LOW (slow edges ring less) and every edge gets
// kSettleCycles before the next. A scan is then about 2,300 cycles
// (~5 us, two settles per bit), 1.9 % of the CPU at 4 kHz; the hook
// (Controls::OnScan) comes on top.
//
// MIDI: USART1 RX on PB7 (D14), receive only. libDaisy's UartHandler would
// skip an unset TX pin, but it only receives by DMA, and its IDLE-line
// callback stamps a whole burst at once (and stops listening for good after
// a framing error, e.g. a cable plugged in mid-byte). Here USART1 is set up
// on the registers with an interrupt per byte, so each byte carries its own
// arrival time. The interrupt is the most urgent of all (priority 0, above
// the audio: main.cc), so the stamp is the arrival within a few us, and the
// 8-byte receive FIFO is on, so a byte waits there rather than overrun the
// one before when the interrupt is held off (by a critical section, say):
// 2.5 ms of solid MIDI before anything is lost. The handler drains the FIFO.
// libDaisy's uart.cpp is always linked (System::Init calls its
// dsy_uart_global_init) and defines USART1_IRQHandler for its own handle, so
// a second definition would not link; instead InitMidi() writes
// MidiInterrupt() into USART1's slot of the vector table, which a BOOT_SRAM
// program has in the AXI SRAM (SCB->VTOR = 0x24000000), before it enables
// the interrupt. Nothing else may use USART1 through libDaisy.
// PB6 (D13, USART1 TX's pin) stays the display's reset GPIO.
//
// CLOCK: PB12 (D0) is read by every control scan, and an EXTI on its
// falling edge (the jack rising, after the NPN) counts edges between scans,
// so a trigger shorter than a scan period (250 us, longer while the audio
// holds the scan off) still shows as one scan with the clock high. Its
// vector (EXTI15_10, the startup file's weak breakpoint) is written the same
// way as MIDI's.
//
// QSPI flash: libDaisy's QSPIHandle::Erase and ::Write switch the chip to
// indirect mode and back on every call, and each switch re-runs its whole
// Init, which always rewrites the IS25LP064A's non-volatile status register
// (QuadEnable's WRSR, without reading it first): two status-register writes
// per erase or write, which no wear levelling of the records can spread.
// Write also ignores the result of every page it programs. FlashErase and
// FlashWrite here drive the QUADSPI themselves through the HAL, with
// what libDaisy's mode switch does minus that write, once per call: the
// peripheral re-initialised, the reset libDaisy's Init sends (its first
// command also ends the chip's continuous-read mode) and the read
// parameters it sets; a status read, rewriting the register only if QE is
// ever found clear; the erase or the page programs; libDaisy's
// memory-mapped read set up again. Every step is checked and the range is
// read back, so true means the flash holds what was asked.

#include "hal.h"
#include "hal_daisy.h"

#include <string.h>

#include "daisy_seed.h"
#include "dev/flash_IS25LP064A.h"
#include "sys/dma.h"
#include "util/hal_map.h"

namespace sidefx {
namespace hal {

using daisy::AdcChannelConfig;
using daisy::AdcHandle;
using daisy::DaisySeed;
using daisy::GPIO;
using daisy::Pin;
using daisy::System;
using daisy::TimerHandle;

namespace {

// --- pins (circuit.py's SEED; checked by tools/check_pins.py) ---------------

constexpr Pin kPinClock = daisy::seed::D0;     // CLK: low while the jack is high
constexpr Pin kPinMidiRx = daisy::seed::D14;   // MIDI_RX: USART1 RX, PB7
constexpr Pin kPinShift = daisy::seed::D20;    // BTN_SHIFT: to ground
constexpr Pin kPinSrClk = daisy::seed::D26;    // SR_CLK
constexpr Pin kPinSrLoad = daisy::seed::D27;   // SR_LOAD
constexpr Pin kPinSrDout = daisy::seed::D29;   // SR_DOUT
constexpr Pin kPinSrDin = daisy::seed::D30;    // SR_DIN
constexpr Pin kPinCv[kNumCvInputs] = {         // ADC_CV1..ADC_CV4
  daisy::seed::A0, daisy::seed::A1, daisy::seed::A2, daisy::seed::A3
};

// --- the chain's bit order (see the table above) -----------------------------

// Raw bits of each encoder's phases.
const uint8_t kEncoderBitA[kNumEncoders] = { 8, 10, 12, 14 };
const uint8_t kEncoderBitB[kNumEncoders] = { 9, 11, 13, 15 };
// Raw bit of each Switch; kNotOnChain for SHIFT, which has its own pin.
const uint8_t kNotOnChain = 0xff;
const uint8_t kSwitchBit[NUM_SWITCHES] = {
  4, 5, 6, 7,    // PITCH, DELAY, TEXTURE, REVERB: U2 D4..D7
  kNotOnChain,   // SHIFT
  0, 1, 2, 3     // K1..K4: U2 D0..D3
};
// The 595 output of each Led, 0 = QA.
const uint8_t kLedOutput[NUM_LEDS] = { 0, 1, 2, 3, 4 };
const int kChainBits = 16;

// 125 ns at 480 MHz per half clock: the 165 and 595 need ~60 ns at 3.3 V
// (TI's 100 ns at 2 V and 20 ns at 4.5 V, interpolated), the rest is for
// the edges on the long lines to settle. About 90 covers TI's 2 V figures.
const uint32_t kSettleCycles = 60;

// --- MIDI ---------------------------------------------------------------------

const uint32_t kMidiBaud = 31250;
// MIDI and CLOCK edges: above the audio DMA (main.cc's priorities).
const uint32_t kEdgePriority = 0;
const uint32_t kMidiRingSize = 256;  // a power of two; 82 ms of solid MIDI

// The ADC's oversampling: 4 channels x 16 at ~2.8 us per conversion is a
// fresh set every ~0.18 ms, several per audio block (0.67 ms), with ~2 bits
// less noise than a single conversion.
const AdcHandle::OverSampling kOversampling = AdcHandle::OVS_16;

DaisySeed* seed_ = NULL;

GPIO shift_in;
GPIO sr_clk;
GPIO sr_load;
GPIO sr_dout;
GPIO sr_din;

// Direct register access for the bit-banged chain (GPIO::Write is out of
// line in libDaisy).
GPIO_TypeDef* sr_clk_port;
GPIO_TypeDef* sr_load_port;
GPIO_TypeDef* sr_dout_port;
GPIO_TypeDef* sr_din_port;
GPIO_TypeDef* shift_port;
GPIO_TypeDef* clock_port;
uint32_t sr_clk_mask;
uint32_t sr_load_mask;
uint32_t sr_dout_mask;
uint32_t sr_din_mask;
uint32_t shift_mask;
uint32_t clock_mask;

AdcHandle adc;
bool adc_ready = false;

TimerHandle control_timer;  // TIM3
TimerHandle us_timer;       // TIM5
ControlHook control_hook = NULL;
uint8_t led_bits = 0;       // control interrupt only

// CLOCK edges, counted by ClockEdgeInterrupt; the scan keeps the count it
// saw last (a count, not a flag, so no edge is lost between read and clear).
volatile uint32_t clock_edges = 0;
uint32_t clock_edges_seen = 0;  // control interrupt only

IWDG_HandleTypeDef watchdog;

struct MidiByte {
  uint32_t time_us;
  uint8_t byte;
};
MidiByte midi_ring[kMidiRingSize];
volatile uint32_t midi_head = 0;  // written by the UART interrupt
volatile uint32_t midi_tail = 0;  // written by the main loop

inline void SetHigh(GPIO_TypeDef* port, uint32_t mask) {
  port->BSRR = mask;
}

inline void SetLow(GPIO_TypeDef* port, uint32_t mask) {
  port->BSRR = mask << 16;
}

inline void Settle() {
  const uint32_t start = DWT->CYCCNT;
  while (DWT->CYCCNT - start < kSettleCycles) { }
}

// One pass over the chain: returns the 16 raw bits (U1 D7 at bit 15) and
// leaves `leds` (bit n = Led n) in the 595's shift register for the next
// pass to latch.
uint16_t ShiftChain(uint8_t leds) {
  uint16_t out = 0;
  for (int i = 0; i < NUM_LEDS; ++i) {
    if (leds & (1 << i)) {
      out = uint16_t(out | (1 << kLedOutput[i]));
    }
  }

  SetLow(sr_load_port, sr_load_mask);
  Settle();
  SetHigh(sr_load_port, sr_load_mask);
  Settle();

  uint16_t in = 0;
  for (int i = 0; i < kChainBits; ++i) {
    if (out & 0x8000) {
      SetHigh(sr_dout_port, sr_dout_mask);
    } else {
      SetLow(sr_dout_port, sr_dout_mask);
    }
    out = uint16_t(out << 1);
    Settle();
    in = uint16_t((in << 1) | ((sr_din_port->IDR & sr_din_mask) ? 1 : 0));
    SetHigh(sr_clk_port, sr_clk_mask);
    Settle();
    SetLow(sr_clk_port, sr_clk_mask);
  }
  return in;
}

void ControlInterrupt(void* context) {
  (void)context;
  const uint16_t pressed = uint16_t(~ShiftChain(led_bits));

  ControlScan scan;
  for (int k = 0; k < kNumEncoders; ++k) {
    scan.encoder[k] = uint8_t(((pressed >> kEncoderBitA[k]) & 1) |
                              (((pressed >> kEncoderBitB[k]) & 1) << 1));
  }
  uint16_t switches = 0;
  for (int s = 0; s < NUM_SWITCHES; ++s) {
    const bool on = kSwitchBit[s] == kNotOnChain
        ? !(shift_port->IDR & shift_mask)
        : ((pressed >> kSwitchBit[s]) & 1) != 0;
    if (on) {
      switches = uint16_t(switches | (1 << s));
    }
  }
  scan.switches = switches;
  // High now, or a pulse rose (and perhaps fell) since the last scan.
  const uint32_t edges = clock_edges;
  scan.clock = !(clock_port->IDR & clock_mask) || edges != clock_edges_seen;
  clock_edges_seen = edges;
  scan.time_us = Microseconds();

  if (control_hook) {
    led_bits = control_hook(scan);
  }
}

void InitChain() {
  // Outputs at speed LOW for the long lines; SR_LOAD idles high, so the
  // 165s shift and the 595's RCLK edge comes only at a scan's start.
  sr_load.Init(kPinSrLoad, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
               GPIO::Speed::LOW);
  sr_load.Write(true);
  sr_clk.Init(kPinSrClk, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
              GPIO::Speed::LOW);
  sr_clk.Write(false);
  sr_dout.Init(kPinSrDout, GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL,
               GPIO::Speed::LOW);
  sr_dout.Write(false);
  // The 165's Q7 drives SR_DIN; a pull-up keeps it defined while the
  // faceplate is unplugged (then every input reads released).
  sr_din.Init(kPinSrDin, GPIO::Mode::INPUT, GPIO::Pull::PULLUP);

  sr_clk_port = daisy::GetHALPort(kPinSrClk);
  sr_load_port = daisy::GetHALPort(kPinSrLoad);
  sr_dout_port = daisy::GetHALPort(kPinSrDout);
  sr_din_port = daisy::GetHALPort(kPinSrDin);
  sr_clk_mask = daisy::GetHALPin(kPinSrClk);
  sr_load_mask = daisy::GetHALPin(kPinSrLoad);
  sr_dout_mask = daisy::GetHALPin(kPinSrDout);
  sr_din_mask = daisy::GetHALPin(kPinSrDin);

  // The 595 powers up with random outputs: two passes with no LEDs, the
  // second latching the first's zeros.
  ShiftChain(0);
  ShiftChain(0);
}

void InitMicroseconds() {
  TimerHandle::Config config;
  config.periph = TimerHandle::Config::Peripheral::TIM_5;
  config.dir = TimerHandle::Config::CounterDir::UP;
  config.period = 0xffffffff;
  config.enable_irq = false;
  us_timer.Init(config);
  // GetFreq() is 2 x PCLK1 / (PSC + 1) with PSC still 0: 240 MHz boosted.
  us_timer.SetPrescaler(us_timer.GetFreq() / 1000000 - 1);
  // PSC is buffered until an update event: force one (it also zeroes CNT).
  TIM5->EGR = TIM_EGR_UG;
  us_timer.Start();
}

void InitCycleCounter() {
  CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  DWT->LAR = 0xc5acce55;  // the M7's DWT is locked after reset
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

void InitAdc() {
  AdcChannelConfig config[kNumCvInputs];
  for (int i = 0; i < kNumCvInputs; ++i) {
    config[i].InitSingle(kPinCv[i]);
  }
  adc.Init(config, kNumCvInputs, kOversampling);
  adc.Start();
  // With no multiplexer, libDaisy's ADC DMA interrupt does nothing but clear
  // flags (twice per scan, ~11,000 a second); the circular DMA runs on
  // without it.
  HAL_NVIC_DisableIRQ(DMA1_Stream2_IRQn);
  adc_ready = true;
}

// USART1: every MIDI byte waiting in the receive FIFO, each stamped as it
// is read (its arrival, unless the interrupt was held off). With the FIFO
// on, the framing, noise and parity flags belong to the byte at the FIFO's
// head: they are cleared before that byte is read, so the next byte's own
// flags are not wiped, and a byte with an error is dropped (a cable plugged
// in mid-byte cannot inject garbage). An overrun (the FIFO was full) is
// cleared too, or it would keep the interrupt pending.
void MidiInterrupt() {
  const uint32_t errors = USART_ISR_FE | USART_ISR_NE | USART_ISR_PE;
  while (true) {
    const uint32_t isr = USART1->ISR;
    if (isr & USART_ISR_ORE) {
      USART1->ICR = USART_ICR_ORECF;
    }
    if (isr & errors) {
      USART1->ICR = USART_ICR_FECF | USART_ICR_NECF | USART_ICR_PECF;
    }
    if (!(isr & USART_ISR_RXNE_RXFNE)) {
      return;
    }
    const uint8_t byte = uint8_t(USART1->RDR);
    if (isr & errors) {
      continue;
    }
    const uint32_t head = midi_head;
    if (head - midi_tail >= kMidiRingSize) {
      continue;  // full: the main loop is stalled; newest bytes are dropped
    }
    MidiByte& entry = midi_ring[head & (kMidiRingSize - 1)];
    entry.byte = byte;
    entry.time_us = Microseconds();
    __DMB();  // the entry is written before the main loop can see it
    midi_head = head + 1;
  }
}

// A falling edge on PB12: the CLOCK jack rose.
void ClockEdgeInterrupt() {
  __HAL_GPIO_EXTI_CLEAR_IT(clock_mask);
  clock_edges = clock_edges + 1;
}

// Points an interrupt's vector at `handler` (see the top of the file).
void InstallVector(IRQn_Type irq, void (*handler)()) {
  volatile uint32_t* vectors = reinterpret_cast<volatile uint32_t*>(SCB->VTOR);
  volatile uint32_t* slot = &vectors[16 + irq];
  *slot = reinterpret_cast<uint32_t>(handler);
  // The core reads vectors through the D-side; clean the line anyway, so
  // the table in SRAM itself is right too.
  SCB_CleanDCache_by_Addr(
      reinterpret_cast<uint32_t*>(reinterpret_cast<uint32_t>(slot) & ~31u), 32);
  __DSB();
  __ISB();
}

void InitMidi() {
  GPIO_InitTypeDef gpio;
  memset(&gpio, 0, sizeof(gpio));
  daisy::GPIOClockEnable(kPinMidiRx);
  gpio.Pin = daisy::GetHALPin(kPinMidiRx);
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLUP;  // idle high with no cable (the H11L1 also pulls up)
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  gpio.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(daisy::GetHALPort(kPinMidiRx), &gpio);

  // USART1's kernel clock is PCLK2 (libDaisy's system.cpp selects
  // RCC_USART16CLKSOURCE_D2PCLK2): 120 MHz boosted, BRR 3840.
  __HAL_RCC_USART1_CLK_ENABLE();
  USART1->CR1 = 0;
  USART1->CR2 = 0;
  USART1->CR3 = 0;
  USART1->PRESC = 0;
  USART1->BRR = (HAL_RCC_GetPCLK2Freq() + kMidiBaud / 2) / kMidiBaud;
  USART1->ICR = 0xffffffff;
  // 8N1, oversampling by 16, the FIFO on (FIFOEN can change only while UE
  // is 0), an interrupt while the FIFO holds a byte.
  USART1->CR1 = USART_CR1_FIFOEN;
  USART1->CR1 = USART_CR1_FIFOEN | USART_CR1_RE | USART_CR1_RXNEIE_RXFNEIE |
                USART_CR1_UE;
  InstallVector(USART1_IRQn, &MidiInterrupt);
  HAL_NVIC_SetPriority(USART1_IRQn, kEdgePriority, 0);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

// PB12 as an input with an EXTI (line 12) on its falling edge. The clock
// stage has its own pull-up to 3V3D on the main board.
void InitClock() {
  clock_port = daisy::GetHALPort(kPinClock);
  clock_mask = daisy::GetHALPin(kPinClock);
  daisy::GPIOClockEnable(kPinClock);
  GPIO_InitTypeDef gpio;
  memset(&gpio, 0, sizeof(gpio));
  gpio.Pin = clock_mask;
  gpio.Mode = GPIO_MODE_IT_FALLING;
  gpio.Pull = GPIO_NOPULL;
  gpio.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(clock_port, &gpio);  // also SYSCFG's EXTICR and the mask
  __HAL_GPIO_EXTI_CLEAR_IT(clock_mask);
  InstallVector(EXTI15_10_IRQn, &ClockEdgeInterrupt);
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, kEdgePriority, 0);
  HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);
}

}  // namespace

// --- bring-up -----------------------------------------------------------------

void Init(DaisySeed* seed) {
  seed_ = seed;
  InitCycleCounter();
  InitMicroseconds();

  shift_in.Init(kPinShift, GPIO::Mode::INPUT, GPIO::Pull::PULLUP);
  shift_port = daisy::GetHALPort(kPinShift);
  shift_mask = daisy::GetHALPin(kPinShift);

  InitClock();
  InitChain();
  InitAdc();
  InitMidi();
  // The pull-ups (SHIFT's ~40k into the button's wiring) settle well
  // within this, before main.cc reads SHIFT for the bootloader.
  System::Delay(2);
}

// --- time ---------------------------------------------------------------------

uint32_t Milliseconds() {
  return System::GetNow();
}

uint32_t Microseconds() {
  return TIM5->CNT;
}

uint32_t CycleCount() {
  return DWT->CYCCNT;
}

// --- controls -----------------------------------------------------------------

void StartControls(ControlHook hook) {
  control_hook = hook;
  TimerHandle::Config config;
  config.periph = TimerHandle::Config::Peripheral::TIM_3;
  config.dir = TimerHandle::Config::CounterDir::UP;
  config.period = 0xffff;
  config.enable_irq = true;
  control_timer.Init(config);
  // 2 x PCLK1 = 240 MHz boosted (200 MHz at 400): 60,000 (50,000) ticks,
  // inside TIM3's 16 bits either way.
  control_timer.SetPeriod(control_timer.GetFreq() / kControlRate - 1);
  control_timer.SetCallback(ControlInterrupt, NULL);
  // Below MIDI and CLOCK (0) and the audio DMA (1), above the display (3);
  // libDaisy gives its timers 15.
  HAL_NVIC_SetPriority(TIM3_IRQn, 2, 0);
  control_timer.Start();
}

bool ShiftPressedNow() {
  return !shift_in.Read();
}

// --- CV inputs ----------------------------------------------------------------

float ReadCv(int channel) {
  if (!adc_ready || channel < 0 || channel >= kNumCvInputs) {
    return 0.502f;  // what 0 V reads
  }
  return adc.GetFloat(uint8_t(channel));
}

// --- MIDI ---------------------------------------------------------------------

bool ReadMidiByte(uint8_t* byte, uint32_t* time_us) {
  const uint32_t tail = midi_tail;
  if (tail == midi_head) {
    return false;
  }
  const MidiByte& entry = midi_ring[tail & (kMidiRingSize - 1)];
  *byte = entry.byte;
  *time_us = entry.time_us;
  __DMB();  // the entry is read before the interrupt may reuse its slot
  midi_tail = tail + 1;
  return true;
}

// --- QSPI flash ---------------------------------------------------------------

void FlashRead(uint32_t offset, void* destination, uint32_t size) {
  uint8_t* source = static_cast<uint8_t*>(seed_->qspi.GetData(offset));
  // The D-cache may still hold lines from before the last erase or write.
  dsy_dma_invalidate_cache_for_buffer(source, size);
  memcpy(destination, source, size);
}

namespace {

// The IS25LP064A's commands, as libDaisy's qspi.cpp sends them (all on one
// line except the memory-mapped quad read).
const uint8_t kCmdResetEnable = 0x66;
const uint8_t kCmdReset = 0x99;
const uint8_t kCmdSetReadParams = 0xc0;   // volatile
const uint8_t kCmdReadStatus = 0x05;
const uint8_t kCmdWriteStatus = 0x01;     // non-volatile: worn by each write
const uint8_t kCmdWriteEnable = 0x06;
const uint8_t kCmdSectorErase = 0xd7;     // 4 kB
const uint8_t kCmdPageProgram = 0x02;
const uint8_t kCmdQuadIoRead = 0xeb;
const uint8_t kStatusWip = 0x01;
const uint8_t kStatusWel = 0x02;
const uint8_t kStatusQe = 0x40;
// libDaisy's read parameters for the 064A: 8-byte bursts, no wrap, its
// dummy-cycle setting for the 6 cycles below, drive strength 50 %.
const uint8_t kReadParams = 0xf0;
const uint32_t kFlashPageSize = IS25LP064A_PAGE_SIZE;
const uint32_t kFlashProgramStart = 0x40000;  // the bootloader's program
const uint32_t kFlashTimeoutMs = HAL_QSPI_TIMEOUT_DEFAULT_VALUE;
const uint32_t kVerifyChunk = 64;

// A handle of our own on the QUADSPI, set up with libDaisy's values
// (qspi.cpp's Init); libDaisy's handle is private to qspi.cpp, which keeps
// believing the chip is memory-mapped, as it is whenever a call here
// returns. HAL_QSPI_Init and _DeInit call libDaisy's HAL_QSPI_MspInit and
// _MspDeInit, which take any handle on QUADSPI.
QSPI_HandleTypeDef flash;

QSPI_CommandTypeDef FlashCommand(uint8_t instruction, uint32_t data_mode,
                                 uint32_t size) {
  QSPI_CommandTypeDef c;
  memset(&c, 0, sizeof(c));
  c.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  c.Instruction = instruction;
  c.AddressMode = QSPI_ADDRESS_NONE;
  c.AddressSize = QSPI_ADDRESS_24_BITS;
  c.AlternateByteMode = QSPI_ALTERNATE_BYTES_NONE;
  c.DummyCycles = 0;
  c.DataMode = data_mode;
  c.NbData = size;
  c.DdrMode = QSPI_DDR_MODE_DISABLE;
  c.DdrHoldHalfCycle = QSPI_DDR_HHC_ANALOG_DELAY;
  c.SIOOMode = QSPI_SIOO_INST_EVERY_CMD;
  return c;
}

// Polls the status register until (status & mask) == match.
bool FlashPoll(uint8_t mask, uint8_t match, uint32_t interval) {
  QSPI_CommandTypeDef c = FlashCommand(kCmdReadStatus, QSPI_DATA_1_LINE, 1);
  QSPI_AutoPollingTypeDef poll;
  memset(&poll, 0, sizeof(poll));
  poll.Match = match;
  poll.Mask = mask;
  poll.MatchMode = QSPI_MATCH_MODE_AND;
  poll.StatusBytesSize = 1;
  poll.Interval = interval;
  poll.AutomaticStop = QSPI_AUTOMATIC_STOP_ENABLE;
  return HAL_QSPI_AutoPolling(&flash, &c, &poll, kFlashTimeoutMs) == HAL_OK;
}

bool FlashReady() {
  return FlashPoll(kStatusWip, 0, 0x10);
}

bool FlashSimple(uint8_t instruction) {
  QSPI_CommandTypeDef c = FlashCommand(instruction, QSPI_DATA_NONE, 0);
  return HAL_QSPI_Command(&flash, &c, kFlashTimeoutMs) == HAL_OK;
}

bool FlashSend(uint8_t instruction, const uint8_t* data, uint32_t size) {
  QSPI_CommandTypeDef c = FlashCommand(instruction, QSPI_DATA_1_LINE, size);
  return HAL_QSPI_Command(&flash, &c, kFlashTimeoutMs) == HAL_OK &&
         HAL_QSPI_Transmit(&flash, const_cast<uint8_t*>(data),
                           kFlashTimeoutMs) == HAL_OK;
}

bool FlashWriteEnable() {
  return FlashSimple(kCmdWriteEnable) &&
         FlashPoll(kStatusWel, kStatusWel, 0x10);
}

bool FlashReadStatus(uint8_t* status) {
  QSPI_CommandTypeDef c = FlashCommand(kCmdReadStatus, QSPI_DATA_1_LINE, 1);
  return HAL_QSPI_Command(&flash, &c, kFlashTimeoutMs) == HAL_OK &&
         HAL_QSPI_Receive(&flash, status, kFlashTimeoutMs) == HAL_OK;
}

// The peripheral re-initialised (out of memory-mapped mode, or out of a
// command that failed half-way), then the chip reset, as every one of
// libDaisy's mode switches does: reset enable and reset (in continuous-read
// mode the chip takes the first as a read with other mode bits and leaves
// that mode), then the read parameters the reset cleared. No status write.
bool FlashIndirect() {
  // DeInit disables the peripheral and its pins and clock (libDaisy's
  // MspDeInit), memory-mapped or not; Init's MspInit resets it.
  flash.Instance = QUADSPI;
  HAL_QSPI_DeInit(&flash);
  memset(&flash, 0, sizeof(flash));
  flash.Instance = QUADSPI;
  flash.Init.ClockPrescaler = 1;
  flash.Init.FifoThreshold = 1;
  flash.Init.SampleShifting = QSPI_SAMPLE_SHIFTING_NONE;
  flash.Init.FlashSize = POSITION_VAL(IS25LP064A_FLASH_SIZE) - 1;
  flash.Init.ChipSelectHighTime = QSPI_CS_HIGH_TIME_2_CYCLE;
  flash.Init.FlashID = QSPI_FLASH_ID_1;
  flash.Init.DualFlash = QSPI_DUALFLASH_DISABLE;
  if (HAL_QSPI_Init(&flash) != HAL_OK) {
    return false;
  }
  if (!FlashSimple(kCmdResetEnable) || !FlashSimple(kCmdReset)) {
    return false;
  }
  System::DelayUs(100);  // the reset's recovery time, before any command
  return FlashReady() && FlashSend(kCmdSetReadParams, &kReadParams, 1) &&
         FlashReady();
}

// Memory-mapped to indirect mode, the chip ready for erases and programs.
bool BeginFlash() {
  if (!FlashIndirect()) {
    return false;
  }
  // QE is set at every boot (libDaisy's PreInit and Init) and nothing here
  // clears it; rewrite the register only if it ever reads clear.
  uint8_t status = 0;
  if (!FlashReadStatus(&status)) {
    return false;
  }
  if (!(status & kStatusQe)) {
    if (!FlashWriteEnable() || !FlashSend(kCmdWriteStatus, &kStatusQe, 1) ||
        !FlashPoll(kStatusQe | kStatusWel | kStatusWip, kStatusQe, 0x8000)) {
      return false;
    }
  }
  return true;
}

// Back to libDaisy's memory-mapped read (EnableMemoryMappedMode): quad I/O
// fast read, mode bits 0xA0 (continuous read), 6 dummy cycles. After a
// failure (`clean` false: a step timed out or the chip did not answer),
// the peripheral and the chip start over first, so that FlashRead and the
// rest of the program find the chip mapped whatever went wrong.
bool EndFlash(bool clean) {
  if ((!clean || flash.State != HAL_QSPI_STATE_READY) && !FlashIndirect()) {
    return false;
  }
  QSPI_CommandTypeDef c;
  memset(&c, 0, sizeof(c));
  c.InstructionMode = QSPI_INSTRUCTION_1_LINE;
  c.Instruction = kCmdQuadIoRead;
  c.AddressMode = QSPI_ADDRESS_4_LINES;
  c.AddressSize = QSPI_ADDRESS_24_BITS;
  c.AlternateByteMode = QSPI_ALTERNATE_BYTES_4_LINES;
  c.AlternateBytesSize = QSPI_ALTERNATE_BYTES_8_BITS;
  c.AlternateBytes = 0xa0;
  c.DummyCycles = 6;
  c.DataMode = QSPI_DATA_4_LINES;
  c.DdrMode = QSPI_DDR_MODE_DISABLE;
  c.DdrHoldHalfCycle = QSPI_DDR_HHC_ANALOG_DELAY;
  c.SIOOMode = QSPI_SIOO_INST_ONLY_FIRST_CMD;
  QSPI_MemoryMappedTypeDef mapped;
  memset(&mapped, 0, sizeof(mapped));
  mapped.TimeOutActivation = QSPI_TIMEOUT_COUNTER_DISABLE;
  mapped.TimeOutPeriod = 0;
  return HAL_QSPI_MemoryMapped(&flash, &c, &mapped) == HAL_OK;
}

// Only Side FXy's records, never the program; and not while running from
// the chip (memory-mapped mode is the code's; libDaisy refuses this too).
bool FlashAllowed(uint32_t offset, uint32_t size) {
  return offset < kFlashProgramStart && size <= kFlashProgramStart - offset &&
         System::GetProgramMemoryRegion() != System::MemoryRegion::QSPI;
}

// Reads the range back (through the memory map, after EndFlash): true when
// it holds `data`, or only 0xff when `data` is NULL.
bool FlashVerify(uint32_t offset, const uint8_t* data, uint32_t size) {
  uint8_t chunk[kVerifyChunk];
  for (uint32_t done = 0; done < size; ) {
    const uint32_t n = size - done < kVerifyChunk ? size - done : kVerifyChunk;
    FlashRead(offset + done, chunk, n);
    for (uint32_t i = 0; i < n; ++i) {
      if (chunk[i] != (data ? data[done + i] : 0xff)) {
        return false;
      }
    }
    done += n;
  }
  return true;
}

}  // namespace

bool FlashErase(uint32_t offset, uint32_t size) {
  if (!size) {
    return true;
  }
  if (!FlashAllowed(offset, size)) {
    return false;
  }
  const uint32_t start = offset & ~(kFlashSectorSize - 1);
  const uint32_t end = offset + size;
  bool ok = BeginFlash();
  for (uint32_t sector = start; ok && sector < end;
       sector += kFlashSectorSize) {
    QSPI_CommandTypeDef c = FlashCommand(kCmdSectorErase, QSPI_DATA_NONE, 0);
    c.AddressMode = QSPI_ADDRESS_1_LINE;
    c.Address = sector;
    // Up to 400 ms a sector (the datasheet's maximum): inside the timeout.
    ok = FlashWriteEnable() &&
         HAL_QSPI_Command(&flash, &c, kFlashTimeoutMs) == HAL_OK &&
         FlashReady();
  }
  ok = EndFlash(ok) && ok;
  return ok && FlashVerify(start, NULL, end - start);
}

bool FlashWrite(uint32_t offset, const void* data, uint32_t size) {
  if (!size) {
    return true;
  }
  if (!data || !FlashAllowed(offset, size)) {
    return false;
  }
  const uint8_t* bytes = static_cast<const uint8_t*>(data);
  bool ok = BeginFlash();
  for (uint32_t done = 0; ok && done < size; ) {
    // A page program stays inside one 256-byte page.
    const uint32_t address = offset + done;
    const uint32_t room = kFlashPageSize - address % kFlashPageSize;
    const uint32_t n = size - done < room ? size - done : room;
    QSPI_CommandTypeDef c = FlashCommand(kCmdPageProgram, QSPI_DATA_1_LINE, n);
    c.AddressMode = QSPI_ADDRESS_1_LINE;
    c.Address = address;
    ok = FlashWriteEnable() &&
         HAL_QSPI_Command(&flash, &c, kFlashTimeoutMs) == HAL_OK &&
         HAL_QSPI_Transmit(&flash, const_cast<uint8_t*>(bytes + done),
                           kFlashTimeoutMs) == HAL_OK &&
         FlashReady();
    done += n;
  }
  ok = EndFlash(ok) && ok;
  return ok && FlashVerify(offset, bytes, size);
}

// --- system -------------------------------------------------------------------

void StartWatchdog() {
  // Stopped while a debugger halts the core, so a breakpoint does not reset.
  __HAL_DBGMCU_FREEZE_IWDG1();
  // LSI (32 kHz) / 64, 1000 counts: about 2 s, longer than a sector erase
  // (the audio, which feeds it, keeps running through one anyway).
  IWDG_HandleTypeDef handle;
  memset(&handle, 0, sizeof(handle));
  handle.Instance = IWDG1;
  handle.Init.Prescaler = IWDG_PRESCALER_64;
  handle.Init.Reload = 1000;
  handle.Init.Window = IWDG_WINDOW_DISABLE;
  // HAL_IWDG_Init starts the watchdog (KR = 0xCCCC) before it waits for
  // the prescaler and reload to reach the LSI domain, so even when that
  // wait times out the watchdog runs (at its reset values, ~0.5 s, if they
  // did not arrive): the audio callback feeds it whatever Init returns.
  HAL_IWDG_Init(&handle);
  watchdog = handle;  // from now on the audio callback feeds it
}

void FeedWatchdog() {
  if (watchdog.Instance) {
    HAL_IWDG_Refresh(&watchdog);
  }
}

uint32_t EnterCritical() {
  const uint32_t state = __get_PRIMASK();
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
}  // namespace sidefx
