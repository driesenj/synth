#pragma once
#include <stdint.h>

namespace midi {

// Opens UART2 at 31250 for the DIN socket, and UART0 at USB_BAUD. UART0 only
// carries MIDI when USB_MIDI is 1; otherwise it is a text console.
void begin();

void noteOn(uint8_t ch, uint8_t note, uint8_t vel);
void noteOff(uint8_t ch, uint8_t note);
void cc(uint8_t ch, uint8_t num, uint8_t val);

// CC 120 / 123. A courtesy message only - receivers are inconsistent about
// honouring it, so send real note-offs for anything you know is sounding.
void allSoundOff(uint8_t ch);

}  // namespace midi
