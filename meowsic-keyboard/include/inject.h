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

// press, wait, open. Blocking; for buttons, which are one-shot to the blob.
void tap(uint8_t pos, uint32_t holdMs);

}  // namespace inject
