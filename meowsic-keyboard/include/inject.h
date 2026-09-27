#pragma once
#include <stdint.h>

// One virtual key press into the blob through the two 74HCT4051s. Mux A picks
// a column, mux B a row, their COM pins are tied, so together they are one
// switch between one blob column line and one blob row line - exactly what a
// keybed contact is. One closure at a time, by construction.
//
// The rule every caller inherits: INH is raised before the selects move and
// stays high until asked. Changing selects with a channel closed briefly joins
// wrong pairs, and the blob may latch those as presses.
namespace inject {

// Park: INH high first, then the selects. Nothing is injected until close().
void begin();

// Raw mux channels, for bring-up: Y<a> of the column chip to Y<b> of the row
// chip, whatever blob lines those pins were wired to. Opens the switch first.
void selectRaw(uint8_t a, uint8_t b);

// A keybed position (col * N_ROWS + row), translated through MUX_COL_OF and
// MUX_ROW_OF in config.h. Opens the switch first. Out-of-range is ignored.
void selectPos(uint8_t pos);

void close();  // INH low: the selected pair is connected
void open();   // INH high: everything open
bool closed();

uint8_t rawA();
uint8_t rawB();

// selectPos + close. Hold for >= 30 ms - the blob polls every 10-20 ms.
void press(uint8_t pos);

// press, wait, open. Blocking; for the bring-up tools and the demo.
void tap(uint8_t pos, uint32_t holdMs);

// ---- Tap queue --------------------------------------------------------------
// The non-blocking face of the injector, for the firmware, which has to keep
// scanning while a tap plays out. queueTap() files a press; service(), called
// from the loop, closes the switch for holdMs, opens it for gapMs, then takes
// the next. One switch, so taps go out in the order they were queued; a full
// queue drops the newest. Every press is one-shot to the blob, so this is the
// whole of what a key does to it - there is no release to send.
void queueTap(uint8_t pos, uint8_t holdMs, uint8_t gapMs);
void service();

// Drop everything queued and open the switch. Panic, and I2C recovery.
void flush();

// How long a tap queued now would wait before its switch closes: the rest
// of the tap in progress plus everything queued ahead of it. The looper
// drops toy taps that would be late by more than LOOP_TAP_LATE_MS.
uint32_t backlogMs();

}  // namespace inject
