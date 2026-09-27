#pragma once
#include <stdint.h>

// The settings a player changes from the panel or over MIDI CC 102-110
// (docs/firmware.md sections 2 and 3.4), and the tapped tempo. One struct,
// one instance, read by whoever acts on a setting and written by
// controls.cpp, midi_in.cpp and clock.cpp. Kept in NVS: loaded at boot,
// written SETTINGS_SAVE_DELAY_MS after the last change.

enum GateMode : uint8_t { GATE_LEGATO = 0, GATE_RETRIG, GATE_MODE_N };
enum Glide    : uint8_t { GLIDE_OFF = 0, GLIDE_SHORT, GLIDE_LONG, GLIDE_N };

// The AUX waveform table, in the order the techno button cycles them.
enum AuxWave : uint8_t {
    AUX_SAW_UP = 0, AUX_SAW_DOWN, AUX_TRI, AUX_SINE, AUX_SQUARE, AUX_RANDOM,
    AUX_CLOCK, AUX_RESET, AUX_ENV, AUX_MODWHEEL, AUX_OFF, AUX_WAVE_N
};
enum AuxRate  : uint8_t { AUX_PER_LOOP = 0, AUX_PER_BAR, AUX_PER_BEAT, AUX_RATE_N };

enum ArpOrder : uint8_t { ARP_UP = 0, ARP_DOWN, ARP_UPDOWN, ARP_PLAYED, ARP_ORDER_N };
enum ArpDiv   : uint8_t { ARP_16TH = 0, ARP_8TH, ARP_QUARTER, ARP_DIV_N };

struct Settings {
    bool     quantLoop;
    bool     quantPitch;
    uint8_t  auxWave;    // AuxWave
    uint8_t  auxRate;    // AuxRate
    uint8_t  gateMode;   // GateMode
    uint8_t  glide;      // Glide
    bool     arpOn;
    uint8_t  arpOrder;   // ArpOrder
    uint8_t  arpDiv;     // ArpDiv
    bool     toyNotes;   // notes reach the toy (buttons always do)
    uint16_t bpm;        // the internal clock's tempo
};

namespace settings {

extern Settings current;

void begin();     // the defaults, then whatever NVS holds if it is sane
void changed();   // call after writing a field; schedules the write
void service();   // the write itself, once the panel has been quiet

}  // namespace settings
