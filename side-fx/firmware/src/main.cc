// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: start-up, the audio callback and the main loop on the Daisy Seed.
//
// Threads, by NVIC priority (0 = most urgent; HAL_Init's grouping 4: all
// preemption bits, no sub-priority). libDaisy sets every DMA stream, SPI,
// QSPI and UART interrupt to 0 and its timers to 15 when it starts them, so
// SetInterruptPriorities() puts them in order once everything is running:
//   0   USART1, MIDI bytes (each stamped with its arrival time), and EXTI
//       15..10, a CLOCK edge (hal_daisy.cc): a few hundred cycles at most,
//       above the audio so a byte or a short trigger is never held off by a
//       callback (a 0.4 ms callback at 60 % load is longer than a MIDI
//       byte's 320 us).
//   1   DMA1 stream 0/1 (SAI1, the audio callback): App::Process.
//   2   TIM3, the 4 kHz control scan: App::OnControlScan. Below the audio,
//       so a scan can be held off by up to one audio callback (~0.4 ms at
//       60 % load): harmless for debouncing, EC11 quadrature edges come
//       milliseconds apart, and CLOCK edges are counted by their EXTI.
//   3   SPI1 and its DMA (DMA2 stream 3): the display's chunk chaining,
//       started from the main loop. QUADSPI too, for order's sake: the
//       flash is driven by polling (no QSPI interrupt fires), and libDaisy's
//       HAL_QSPI_MspInit puts it back to 0 at every FlashErase and
//       FlashWrite (hal_daisy.cc re-initialises the peripheral), which is
//       harmless.
//   14  SysTick (libDaisy's TICK_INT_PRIORITY): Milliseconds().
//   -   the main loop: App::Poll, the UI, display flushes, flash writes.
// The ADC's DMA interrupt is off (hal_daisy.cc: it has nothing to do).
//
// Memory: libDaisy's STM32H750IB_sram.lds puts .data and .bss in the 128 kB
// DTCM, which the stack shares, and the program in the AXI SRAM. Its .heap
// section (NOLOAD) sits at the start of RAM_D2 (256 kB, cached), and
// newlib's sbrk starts after it (`end`), so a static array placed there is
// RAM_D2 for the internal arena. The frame is in the SDRAM's .sdram_bss
// (NOLOAD: never cleared), and the external arena is all of the SDRAM after
// that section's end (_esdram_bss): about 63.9 MB. GCC gives a named
// section like .sdram_bss file space in the object, so a 56 MB array there
// would make main.o 59 MB; the linker symbol costs nothing, and anything
// else declared DSY_SDRAM_BSS still gets its own place.

#include "daisy_seed.h"
#include "util/CpuLoadMeter.h"

#include "app/app.h"
#include "engine/config.h"
#include "engine/frame.h"
#include "engine/memory.h"
#include "engine/params.h"
#include "gfx/canvas.h"
#include "gfx/font.h"
#include "hal.h"
#include "hal_daisy.h"
#include "ui/ui.h"

// The end of .sdram_bss, from libDaisy's linker script.
extern "C" uint8_t _esdram_bss[];

using daisy::AudioHandle;
using daisy::CpuLoadMeter;
using daisy::DaisySeed;
using daisy::SaiHandle;
using daisy::System;

namespace {

const size_t kInternalArenaSize = 200 * 1024;
const uint32_t kSdramBase = 0xc0000000;
const uint32_t kSdramSize = 64 * 1024 * 1024;
const int kFrameSize = sidefx::Canvas::kWidth * sidefx::Canvas::kHeight;
// The backlight before the settings are read: bright enough to read the
// UPDATE and error screens.
const float kStartBacklight = 0.6f;

uint8_t internal_memory[kInternalArenaSize]
    __attribute__((section(".heap"), aligned(32)));
// 32-byte aligned: display_daisy.cc cleans the D-cache over whole lines of
// it before each DMA.
uint16_t DSY_SDRAM_BSS frame[kFrameSize] __attribute__((aligned(32)));

DaisySeed seed;
CpuLoadMeter load_meter;
sidefx::Arena internal_arena;
sidefx::Arena external_arena;
sidefx::Memory memory;
sidefx::App app;
sidefx::Canvas canvas;
sidefx::Ui ui;

const sidefx::Color kBlack = 0x0000;
const sidefx::Color kWhite = 0xffff;

// Denormals cost tens of cycles each on the M7 and show up in every
// decaying reverb tail and feedback loop: flush them to zero, and make
// every NaN the default one. FPDSCR is what each interrupt's FP context
// starts with, so the audio and control interrupts get the same.
void InitFpu() {
  const uint32_t bits = (1u << 24) | (1u << 25);  // FZ, DN
  __set_FPSCR(__get_FPSCR() | bits);
  FPU->FPDSCR |= FPU_FPDSCR_FZ_Msk | FPU_FPDSCR_DN_Msk;
}

void SetInterruptPriorities() {
  HAL_NVIC_SetPriority(USART1_IRQn, 0, 0);        // MIDI
  HAL_NVIC_SetPriority(EXTI15_10_IRQn, 0, 0);     // CLOCK edges
  HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, 1, 0);  // SAI1 A
  HAL_NVIC_SetPriority(DMA1_Stream1_IRQn, 1, 0);  // SAI1 B
  HAL_NVIC_SetPriority(TIM3_IRQn, 2, 0);          // control scan
  HAL_NVIC_SetPriority(DMA1_Stream2_IRQn, 2, 0);  // ADC (disabled)
  HAL_NVIC_SetPriority(SPI1_IRQn, 3, 0);          // display
  HAL_NVIC_SetPriority(DMA2_Stream2_IRQn, 3, 0);  // SPI1 RX (unused)
  HAL_NVIC_SetPriority(DMA2_Stream3_IRQn, 3, 0);  // SPI1 TX: display pixels
  HAL_NVIC_SetPriority(QUADSPI_IRQn, 3, 0);       // flash
}

// Sends every dirty row and waits for it: for the screens drawn before (or
// instead of) the UI.
void FlushNow() {
  int y0, y1;
  if (canvas.TakeDirty(&y0, &y1)) {
    sidefx::hal::DisplayFlush(frame, y0, y1);
  }
  while (sidefx::hal::DisplayBusy()) { }
}

void DrawCentredScreen(const char* line1, const char* line2,
                       const char* line3) {
  const int x = sidefx::Canvas::kWidth / 2;
  canvas.Clear(kBlack);
  canvas.DrawTextCentered(x, 120, line1, sidefx::kFontLarge, kWhite);
  if (line2) {
    canvas.DrawTextCentered(x, 160, line2, sidefx::kFontSmall, kWhite);
  }
  if (line3) {
    canvas.DrawTextCentered(x, 180, line3, sidefx::kFontSmall, kWhite);
  }
  FlushNow();
}

// SHIFT held at power-up, or pressed on the error screen: say so, then wait
// in the Daisy bootloader for an upload. The ST7789 keeps its picture
// through the reset as long as nothing pulls its RST low.
void EnterBootloader() {
  DrawCentredScreen("UPDATE", "waiting for", "new firmware");
  sidefx::hal::ResetToBootloader();
}

float CpuLoad() {
  return load_meter.GetAvgCpuLoad();
}

uint8_t OnControlScan(const sidefx::hal::ControlScan& scan) {
  return app.OnControlScan(scan);
}

void AudioCallback(AudioHandle::InputBuffer in, AudioHandle::OutputBuffer out,
                   size_t size) {
  load_meter.OnBlockStart();
  sidefx::hal::FeedWatchdog();
  sidefx::Frame input[sidefx::kBlockSize];
  sidefx::Frame output[sidefx::kBlockSize];
  // libDaisy's buffers are one array per channel; the engine takes frames.
  for (size_t done = 0; done < size; ) {
    const size_t n = size - done < sidefx::kBlockSize
        ? size - done : sidefx::kBlockSize;
    for (size_t i = 0; i < n; ++i) {
      input[i].l = in[0][done + i];
      input[i].r = in[1][done + i];
    }
    app.Process(input, output, n);
    for (size_t i = 0; i < n; ++i) {
      out[0][done + i] = output[i].l;
      out[1][done + i] = output[i].r;
    }
    done += n;
  }
  load_meter.OnBlockEnd();
}

// App::Init failed (an arena too small for the blocks, or a block's Init):
// no audio; the screen says which arena ran out, and SHIFT still reaches
// the bootloader.
void ErrorLoop() {
  char text[32];
  const sidefx::Arena* full = internal_arena.failed()
      ? &internal_arena
      : (external_arena.failed() ? &external_arena : NULL);
  if (full) {
    const size_t prefix = sidefx::FormatNumber(
        text, sizeof(text), float(full->used() / 1024), 0, false, " kB of ");
    sidefx::FormatNumber(text + prefix, sizeof(text) - prefix,
                         float(full->size() / 1024), 0, false, " kB");
    DrawCentredScreen(full == &internal_arena ? "SRAM FULL" : "SDRAM FULL",
                      text, "SHIFT: update");
  } else {
    DrawCentredScreen("INIT FAILED", NULL, "SHIFT: update");
  }
  while (true) {
    if (sidefx::hal::ShiftPressedNow()) {
      EnterBootloader();
    }
  }
}

}  // namespace

int main(void) {
  seed.Init(true);  // 480 MHz
  InitFpu();
  sidefx::hal::Init(&seed);

  // The screen first: the UPDATE and error screens need it, and App::Init
  // may set the backlight.
  sidefx::hal::InitDisplay(kStartBacklight);
  canvas.Init(frame);
  canvas.Clear(kBlack);

  // Checked before App::Init, so a firmware that crashes there can still be
  // replaced without opening the case for the Seed's BOOT button.
  if (sidefx::hal::ShiftPressedNow()) {
    EnterBootloader();
  }

  internal_arena.Init(internal_memory, sizeof(internal_memory));
  const uint32_t sdram_free =
      (reinterpret_cast<uint32_t>(_esdram_bss) + 31u) & ~31u;
  external_arena.Init(reinterpret_cast<void*>(sdram_free),
                      kSdramBase + kSdramSize - sdram_free);
  memory.internal = &internal_arena;
  memory.external = &external_arena;
  if (!app.Init(&memory)) {
    ErrorLoop();
  }

  ui.Init(&app, &canvas, CpuLoad);
  // The stored brightness, flip, encoder and MIDI settings to the engine,
  // the controls and the board.
  app.SettingsChanged();

  seed.SetAudioSampleRate(SaiHandle::Config::SampleRate::SAI_48KHZ);
  seed.SetAudioBlockSize(sidefx::kBlockSize);
  load_meter.Init(seed.AudioSampleRate(), int(sidefx::kBlockSize));
  seed.StartAudio(AudioCallback);
  sidefx::hal::StartControls(OnControlScan);
  SetInterruptPriorities();
  sidefx::hal::StartWatchdog();

  while (true) {
    const uint32_t now = sidefx::hal::Milliseconds();
    app.Poll(now);
    sidefx::Event event;
    while (app.controls.PopEvent(&event)) {
      ui.OnEvent(event);
    }
    ui.Poll(now);
    if (!sidefx::hal::DisplayBusy()) {
      int y0, y1;
      if (canvas.TakeDirty(&y0, &y1)) {
        sidefx::hal::DisplayFlush(frame, y0, y1);
      }
    }
  }
}
