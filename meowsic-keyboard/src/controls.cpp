#include <Arduino.h>
#include <math.h>

#include "config.h"
#include "controls.h"
#include "led.h"
#include "midi_out.h"
#include "router.h"
#include "settings.h"

namespace controls {

// ---- Commands out -----------------------------------------------------------

static constexpr uint8_t CMD_QUEUE_LEN = 8;   // power of two
static Cmd cmdQueue[CMD_QUEUE_LEN];
static uint8_t cmdHead, cmdTail;

static void push(Cmd c)
{
    const uint8_t next = (uint8_t)((cmdHead + 1) & (CMD_QUEUE_LEN - 1));
    if (next == cmdTail)
        return;
    cmdQueue[cmdHead] = c;
    cmdHead = next;
}

bool nextCommand(Cmd &c)
{
    if (cmdTail == cmdHead)
        return false;
    c = cmdQueue[cmdTail];
    cmdTail = (uint8_t)((cmdTail + 1) & (CMD_QUEUE_LEN - 1));
    return true;
}

// ---- Buttons ----------------------------------------------------------------

static constexpr uint8_t N_BUTTONS = CC_LAST - CC_PIANO + 1;

// Held state for the buttons with a long-press function.
struct Hold
{
    bool     down;
    bool     longFired;
    uint32_t downAt;
};
static Hold hold[N_BUTTONS];

static inline bool isPerf(uint8_t cc)
{
    return (cc >= CC_PIANO && cc <= CC_BANJO) || cc == CC_CATFACE;
}

// ---- Settings ---------------------------------------------------------------
// The blinks: blue, two pulses for on, one for off; n + 1 for the n-th entry
// of a cycle, so the first entry is one pulse.
static void blinkOnOff(bool on) { led::blink(0, 0, 255, on ? 2 : 1); }
static void blinkIndex(uint8_t ix) { led::blink(0, 0, 255, (uint8_t)(ix + 1)); }

static void pushPitch();

void setQuantLoop(bool on)
{
    settings::current.quantLoop = on;
    settings::changed();
    blinkOnOff(on);
}

void setQuantPitch(bool on)
{
    settings::current.quantPitch = on;
    settings::changed();
    blinkOnOff(on);
    pushPitch();   // the pot's reading changes meaning at once
}

void setGateMode(uint8_t mode)
{
    if (mode >= GATE_MODE_N) return;
    settings::current.gateMode = mode;
    settings::changed();
    blinkOnOff(mode == GATE_RETRIG);
}

void setGlide(uint8_t glide)
{
    if (glide >= GLIDE_N) return;
    settings::current.glide = glide;
    settings::changed();
    blinkIndex(glide);
}

void setAuxWave(uint8_t wave)
{
    if (wave >= AUX_WAVE_N) return;
    settings::current.auxWave = wave;
    settings::changed();
    blinkIndex(wave);
}

void setAuxRate(uint8_t rate)
{
    if (rate >= AUX_RATE_N) return;
    settings::current.auxRate = rate;
    settings::changed();
    blinkIndex(rate);
}

void setArp(bool on)
{
    settings::current.arpOn = on;
    settings::changed();
    blinkOnOff(on);
}

void setArpOrder(uint8_t order)
{
    if (order >= ARP_ORDER_N) return;
    settings::current.arpOrder = order;
    settings::changed();
    blinkIndex(order);
}

void setArpDiv(uint8_t div)
{
    if (div >= ARP_DIV_N) return;
    settings::current.arpDiv = div;
    settings::changed();
    blinkIndex(div);
}

void setToyNotes(bool on)
{
    settings::current.toyNotes = on;
    settings::changed();
    blinkOnOff(on);
}

// ---- The buttons' functions ------------------------------------------------

static const uint8_t RHYTHMS[] = {CC_ROCK, CC_BLUES, CC_SAMBA, CC_TECHNO, CC_DISCO};
static uint8_t rhythmIx = 0xFF;   // none yet: the first press is rock

static inline uint8_t next(uint8_t v, uint8_t n) { return (uint8_t)((v + 1) % n); }

static void shortPress(uint8_t cc)
{
    const Settings &s = settings::current;
    switch (cc)
    {
    case CC_MUSIC:
        led::flash(0, 0, 255, 60);
        push(CMD_TAP_TEMPO);
        break;
    case CC_STOP:
        router::tapToy(CC_STOP);   // the toy's rhythm or song stops too
        push(CMD_STOP);
        break;
    case CC_RECORD:
        push(CMD_RECORD);
        break;
    case CC_PLAY:
        push(CMD_PLAY);
        break;
    case CC_ROCK:
        rhythmIx = next(rhythmIx, sizeof(RHYTHMS) / sizeof(RHYTHMS[0]));
        router::tapToy(RHYTHMS[rhythmIx]);
        break;
    case CC_BLUES:  setQuantLoop(!s.quantLoop); break;
    case CC_SAMBA:  setQuantPitch(!s.quantPitch); break;
    case CC_TECHNO: setAuxWave(next(s.auxWave, AUX_WAVE_N)); break;
    case CC_DISCO:  setArp(!s.arpOn); break;
    default:
        break;
    }
}

static void longPress(uint8_t cc)
{
    const Settings &s = settings::current;
    switch (cc)
    {
    case CC_MUSIC:
        router::tapToy(CC_MUSIC);   // the demo song, the button's old function
        break;
    case CC_STOP:
        push(CMD_PANIC);
        break;
    case CC_RECORD:
        push(CMD_UNDO);
        break;
    case CC_PLAY:
        push(CMD_CLEAR);
        break;
    case CC_ROCK:
        router::tapToy(CC_STOP);    // the rhythm only; the loop keeps going
        break;
    case CC_CATFACE:
        setToyNotes(!s.toyNotes);   // hold the cat's face: the cat stops singing
        break;
    case CC_BLUES:  setGateMode(next(s.gateMode, GATE_MODE_N)); break;
    case CC_SAMBA:  setGlide(next(s.glide, GLIDE_N)); break;
    case CC_TECHNO: setAuxRate(next(s.auxRate, AUX_RATE_N)); break;
    case CC_DISCO:  setArpOrder(next(s.arpOrder, ARP_ORDER_N)); break;
    default:
        break;
    }
}

void onButton(uint8_t cc, bool down)
{
    if (cc < CC_PIANO || cc > CC_LAST)
        return;

    if (isPerf(cc))
    {
        // Acts on the press, as the toy did. Catface also has a long
        // function, which costs it nothing: the tap has already gone.
        router::button(cc, down);
        if (cc != CC_CATFACE)
            return;
        Hold &h = hold[cc - CC_PIANO];
        h.down = down;
        h.longFired = false;
        h.downAt = millis();
        return;
    }

    // Every physical button still reports itself on MIDI out, whatever it
    // does here, so a DAW can record the panel.
    midi::cc(CTRL_CHANNEL, cc, down ? 127 : 0);

    Hold &h = hold[cc - CC_PIANO];
    if (down)
    {
        h.down = true;
        h.longFired = false;
        h.downAt = millis();
        return;
    }
    h.down = false;
    if (!h.longFired)
        shortPress(cc);
}

static void serviceHolds()
{
    const uint32_t now = millis();
    for (uint8_t i = 0; i < N_BUTTONS; ++i)
    {
        Hold &h = hold[i];
        if (!h.down || h.longFired || now - h.downAt < LONG_PRESS_MS)
            continue;
        h.longFired = true;
        longPress((uint8_t)(CC_PIANO + i));
    }
}

// ---- Pots -------------------------------------------------------------------

struct Pot
{
    int     pin;
    bool    reversed;
    int32_t smooth;   // reading x16
    bool    primed;
};
static Pot potBase = {PIN_POT_BASE, POT_BASE_REVERSED != 0, 0, false};
static Pot potTune = {PIN_POT_TUNE, POT_TUNE_REVERSED != 0, 0, false};
static uint32_t lastPotMs;

static float quantBase = 0.0f;   // whole semitones, with hysteresis
static float contBase  = 0.0f;   // semitones, continuous
static float tuneSemis = 0.0f;

// 0.0 at one end of the travel to 1.0 at the other, the ADC's dead ends
// clipped away.
static float readPot(Pot &p)
{
    const int raw = analogRead(p.pin);
    if (!p.primed)
    {
        p.smooth = raw * 16;
        p.primed = true;
    }
    else
        p.smooth += (raw * 16 - p.smooth) >> 3;

    float v = ((float)(p.smooth / 16) - (float)POT_ADC_LO) / (float)(POT_ADC_HI - POT_ADC_LO);
    if (v < 0.0f) v = 0.0f;
    if (v > 1.0f) v = 1.0f;
    return p.reversed ? 1.0f - v : v;
}

float basePitch() { return settings::current.quantPitch ? quantBase : contBase; }
float tune() { return tuneSemis; }

static void pushPitch() { router::setPitch(basePitch(), tuneSemis); }

static void servicePots()
{
    const uint32_t now = millis();
    if (now - lastPotMs < POT_SAMPLE_MS)
        return;
    lastPotMs = now;

    bool changed = false;

    const float x = (readPot(potBase) - 0.5f) * 2.0f * BASE_PITCH_SEMIS;
    // Quantised: the step only moves once the reading is clear of the
    // boundary by POT_STEP_HYST, so noise straddling it cannot flicker.
    if (fabsf(x - quantBase) > 0.5f + POT_STEP_HYST)
    {
        quantBase = roundf(x);
        changed = settings::current.quantPitch;
    }
    // Continuous: a DAC code is ~0.015 semitone; anything smaller is noise.
    if (fabsf(x - contBase) > 0.02f)
    {
        contBase = x;
        changed |= !settings::current.quantPitch;
    }

    const float t = (readPot(potTune) - 0.5f) * 2.0f * TUNE_SEMIS;
    if (fabsf(t - tuneSemis) > 0.01f)
    {
        tuneSemis = t;
        changed = true;
    }

    if (changed)
        pushPitch();
}

// ---- CV select switch -------------------------------------------------------

static bool swLevel, swCandidate;
static uint32_t swSince;
static constexpr uint32_t SW_DEBOUNCE_MS = 20;

static inline uint8_t channelOf(bool level) { return level ? 0 : 1; }   // open = high = A

uint8_t cvChannel() { return channelOf(swLevel); }

static void serviceSwitch()
{
    const bool level = digitalRead(PIN_CV_SELECT);
    const uint32_t now = millis();
    if (level != swCandidate)
    {
        swCandidate = level;
        swSince = now;
        return;
    }
    if (level == swLevel || now - swSince < SW_DEBOUNCE_MS)
        return;
    swLevel = level;
    router::setKeysChannel(channelOf(level));
}

// ---- Setup / service --------------------------------------------------------

void begin()
{
    // GPIO34/36/39 are input-only with no internal pull-ups; the switch has
    // its 10k on the board, the pots are dividers.
    pinMode(PIN_CV_SELECT, INPUT);
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_POT_BASE, ADC_11db);
    analogSetPinAttenuation(PIN_POT_TUNE, ADC_11db);

    for (auto &h : hold)
        h = {false, false, 0};
    cmdHead = cmdTail = 0;
    rhythmIx = 0xFF;

    swLevel = swCandidate = digitalRead(PIN_CV_SELECT);
    swSince = millis();
    router::setKeysChannel(channelOf(swLevel));

    // Settle the smoothing before the first pitch goes out, so power-up does
    // not sweep the CV from 0 to wherever the knobs are.
    for (uint8_t i = 0; i < 16; ++i)
    {
        readPot(potBase);
        readPot(potTune);
    }
    const float x = (readPot(potBase) - 0.5f) * 2.0f * BASE_PITCH_SEMIS;
    quantBase = roundf(x);
    contBase = x;
    tuneSemis = (readPot(potTune) - 0.5f) * 2.0f * TUNE_SEMIS;
    lastPotMs = millis();
    pushPitch();
}

void service()
{
    serviceHolds();
    servicePots();
    serviceSwitch();
}

}  // namespace controls
