#include <Arduino.h>
#include <Preferences.h>

#include "config.h"
#include "settings.h"

namespace settings {

Settings current;

static const Settings DEFAULTS = {
    /* quantLoop  */ true,
    /* quantPitch */ true,
    /* auxWave    */ AUX_SAW_UP,
    /* auxRate    */ AUX_PER_LOOP,
    /* gateMode   */ GATE_RETRIG,
    /* glide      */ GLIDE_OFF,
    /* arpOn      */ false,
    /* arpOrder   */ ARP_UP,
    /* arpDiv     */ ARP_16TH,
    /* toyNotes   */ true,
    /* bpm        */ 120,
};

// Bumped whenever the struct's layout or an enum's meaning changes, so a
// blob from an older firmware is ignored rather than misread.
static constexpr uint8_t SETTINGS_VERSION = 2;

static Preferences prefs;
static bool     dirty = false;
static uint32_t changedMs = 0;

// A blob from flash is only trusted within the ranges the firmware knows.
static bool valid(const Settings &s)
{
    return s.auxWave < AUX_WAVE_N && s.auxRate < AUX_RATE_N && s.gateMode < GATE_MODE_N &&
           s.glide < GLIDE_N && s.arpOrder < ARP_ORDER_N && s.arpDiv < ARP_DIV_N &&
           s.bpm >= BPM_MIN && s.bpm <= BPM_MAX;
}

void begin()
{
    current = DEFAULTS;
    if (!prefs.begin("meowsic", false))
        return;   // no NVS: the defaults, every boot
    Settings stored;
    if (prefs.getUChar("ver", 0) == SETTINGS_VERSION &&
        prefs.getBytes("settings", &stored, sizeof stored) == sizeof stored &&
        valid(stored))
        current = stored;
    dirty = false;
}

void changed()
{
    dirty = true;
    changedMs = millis();
}

// The write waits until the panel has been quiet for a while, so a knob
// cycled through its options costs one flash write, not five. A write
// blocks for a few milliseconds - one scan frame - which is why it is not
// done on the change itself.
void service()
{
    if (!dirty || millis() - changedMs < SETTINGS_SAVE_DELAY_MS)
        return;
    dirty = false;
    prefs.putUChar("ver", SETTINGS_VERSION);
    prefs.putBytes("settings", &current, sizeof current);
}

}  // namespace settings
