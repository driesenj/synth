// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: what the Marbles drivers, the settings store and the app need
// from the board. hal_daisy.cc implements it on the Daisy Seed with libDaisy
// and a few registers; the host tests implement it with a model of the board
// (test/hal_fake.cc).
//
// Pins, channel orders and bit orders follow marbles/hardware/tools/circuit.py
// and the tables in marbles/docs/design.md (the routed boards).

#ifndef MARBLESY_HAL_H_
#define MARBLESY_HAL_H_

#include <stddef.h>
#include <stdint.h>

namespace daisy {
class DaisySeed;
}

namespace marblesy {
namespace hal {

// Called once, after DaisySeed::Init(): the flash store uses its QSPI handle.
void Init(daisy::DaisySeed* seed);

// Milliseconds since power-up. Readable from any context.
uint32_t Milliseconds();

// Busy-waits; for the start-up, before the interrupts run.
void Delay(uint32_t ms);

// The I/O interrupt calls `io` at exactly kIoRate (TIM7, the highest
// priority). PendDsp(), called from `io`, makes `dsp` run once the I/O
// interrupt returns (PendSV, the lowest priority: the I/O interrupt
// preempts it, and it preempts the main loop).
const uint32_t kIoRate = 32000;
typedef void (*Callback)();
void StartInterrupts(Callback io, Callback dsp);
void PendDsp();

// The independent watchdog: started once the interrupts run, fed by every
// DSP pass, so a stalled interrupt restarts the module after about 2 s.
void StartWatchdog();
void FeedWatchdog();

// CV inputs, in the order of the Seed's ADC sequence (A1..A6, A9).
enum CvInput {
  CV_T_RATE,
  CV_T_BIAS,
  CV_T_JITTER,
  CV_DEJA_VU,
  CV_X_SPREAD,
  CV_X_BIAS,
  CV_X_STEPS,
  CV_INPUT_LAST
};

// The 74HC4051's channels Y0..Y7 (on A10, address on D26, D27, D28), as
// routed: not the panel order.
enum Pot {
  POT_T_RATE,
  POT_T_JITTER,
  POT_DEJA_VU,
  POT_T_BIAS,
  POT_X_STEPS,
  POT_DEJA_VU_LENGTH,
  POT_X_BIAS,
  POT_X_SPREAD,
  POT_LAST
};

void InitAdc();  // Starts the ADC; later calls do nothing.
uint16_t ReadCv(CvInput input);  // 16-bit, 0 V .. 3V3A at the Seed pin
uint16_t ReadPot(Pot pot);       // 16-bit, 0 V .. 3V3A

// Clock inputs, normalization probe and gate outputs.
void InitGpio();  // Later calls do nothing.
// Pin levels: bit 0 = T CLOCK (D0), bit 1 = X CLOCK (D1). The input stages
// invert, so a high clock reads 0.
uint32_t ReadClockPins();
void WriteProbe(bool high);  // D15, into the clock jacks' switch lugs
// Bit 0 = t1 (D2), bit 1 = t2 (D3), bit 2 = t3 (D4).
void WriteGates(uint32_t gates);

// The SPI bus (SPI1): two MCP4922s, the 74HC595 chain and the 74HC165. Only
// one context may use it: the startup code, then the I/O interrupt.
void InitBus();  // Later calls do nothing.
// MCP4922 command words for U7 DAC A, U7 DAC B, U8 DAC A, U8 DAC B, each
// sent with its own chip select, then one LDAC pulse updates all four.
void WriteDacs(const uint16_t words[4]);
// Bit n drives output n of the 74HC595 chain: 0..7 = U9 QA..QH,
// 8..15 = U10 QA..QH. Latched at once.
void WriteLeds(uint16_t bits);
// Bit n = the level on the 74HC165's input Dn (pulled up: 0 = pressed).
uint8_t ReadButtons();

// The STM32's hardware random number generator.
void InitRng();
bool RngReady();
uint32_t RngData();

// The Seed's QSPI flash. Offsets from the start of the chip; erasing works on
// whole 4 kB sectors, at most one per call (libDaisy's 64 kB block erase
// does not return the chip to memory-mapped mode). Main loop only: the chip
// leaves memory-mapped mode during a write or an erase.
const uint32_t kFlashSectorSize = 0x1000;
void FlashRead(uint32_t offset, void* destination, uint32_t size);
bool FlashErase(uint32_t offset, uint32_t size);
bool FlashWrite(uint32_t offset, const void* data, uint32_t size);

// Masks interrupts, so the main loop can copy what the interrupts write.
uint32_t EnterCritical();
void ExitCritical(uint32_t state);

// Restarts into the Daisy bootloader, which then waits for a firmware upload.
void ResetToBootloader();

}  // namespace hal
}  // namespace marblesy

#endif  // MARBLESY_HAL_H_
