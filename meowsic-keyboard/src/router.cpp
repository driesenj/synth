#include <Arduino.h>
#include <math.h>

#include "arp.h"
#include "auxout.h"
#include "config.h"
#include "cv.h"
#include "inject.h"
#include "looper.h"
#include "midi_out.h"
#include "router.h"
#include "settings.h"

namespace router {

static constexpr uint8_t NONE = 0xFF;

// Reverse maps out of POSITION_MAP, built once.
static uint8_t posOfNoteTab[128];
static uint8_t posOfCCTab[CC_LAST - CC_PIANO + 1];
static uint8_t lowestNote = NONE, highestNote = 0;

// MIDI note actually sent per note played, so note-off matches note-on even
// if the base pitch pot moved while the key was down.
static uint8_t sentNote[128];

static uint8_t keysCh = 0;
static float base = 0.0f, tune = 0.0f;

void begin()
{
    for (auto &p : posOfNoteTab) p = NONE;
    for (auto &p : posOfCCTab) p = NONE;
    for (auto &s : sentNote) s = NONE;

    for (uint8_t pos = 0; pos < N_POS; ++pos)
    {
        const PosMap &m = POSITION_MAP[pos];
        if (m.kind == K_NOTE && m.data < 128)
        {
            posOfNoteTab[m.data] = pos;
            if (m.data < lowestNote) lowestNote = m.data;
            if (m.data > highestNote) highestNote = m.data;
        }
        else if (m.kind == K_CC && m.data >= CC_PIANO && m.data <= CC_LAST)
            posOfCCTab[m.data - CC_PIANO] = pos;
    }

    keysCh = 0;
    looper::setActive(keysCh);
    cv::setOffset(0, 0.0f);
    cv::setOffset(1, 0.0f);
}

// The key that plays this note on the toy. Notes off the keybed are folded
// by octaves onto it (MIDI_IN_FOLD), or get no tap.
static uint8_t toyPos(uint8_t note)
{
    if (lowestNote == NONE)
        return NONE;
    if (note < lowestNote || note > highestNote)
    {
#if MIDI_IN_FOLD
        if (highestNote - lowestNote < 11)
            return NONE;   // a placeholder map - no octave to fold into
        int n = note;
        while (n < lowestNote) n += 12;
        while (n > highestNote) n -= 12;
        note = (uint8_t)n;
#else
        return NONE;
#endif
    }
    return posOfNoteTab[note];
}

void setKeysChannel(uint8_t ch)
{
    ch &= 1;
    if (ch == keysCh)
        return;
    // Both pairs change hands, so both start empty: notes the keys hold
    // cannot follow, and notes a DAW holds on the other pair would otherwise
    // be stuck in a stack their note-offs no longer reach. A loop's sounding
    // note returns at its next event. MIDI out is untouched.
    cv::allOff(0);
    cv::allOff(1);
    cv::setBend(0, 0.0f);
    cv::setBend(1, 0.0f);
    keysCh = ch;
    looper::setActive(keysCh);
}

uint8_t keysChannel() { return keysCh; }
uint8_t otherChannel() { return keysCh ^ 1; }

void setPitch(float baseSemis, float tuneSemis)
{
    base = baseSemis;
    tune = tuneSemis;
    cv::setOffset(0, base + tune);   // both pairs; cv applies it per note
    cv::setOffset(1, base + tune);
}

void noteOn(uint8_t note, Source src, uint8_t pair)
{
    if (note > 127)
        return;
    const uint8_t target = pair == KEYS_PAIR ? keysCh : (uint8_t)(pair & 1);

    // The keys and MIDI feed the arp; while it is on, it is what sounds.
    if (src == SRC_KEYS || src == SRC_MIDI)
    {
        arp::noteOn(note);
        if (settings::current.arpOn)
            return;
    }
    if (src != SRC_LOOP)
        looper::noteOn(note);

    // The toy first: it plays its own pitch for this key whatever the pot
    // does to MIDI and CV - unless its notes are switched off (catface
    // held), which leaves the keys to the jacks and MIDI. The loop's taps
    // are dropped when the toy is already this far behind - a dense loop
    // arpeggiates, it does not lag.
    const uint8_t pos = toyPos(note);
    if (pos != NONE && settings::current.toyNotes &&
        !(src == SRC_LOOP && inject::backlogMs() > LOOP_TAP_LATE_MS))
        inject::queueTap(pos, INJECT_NOTE_HOLD_MS, INJECT_NOTE_GAP_MS);

    // MIDI, unless the note came in over MIDI. A note already on is
    // retriggered, off then on, so a loop hitting a key the player holds
    // still sounds.
    if (src != SRC_MIDI)
    {
        if (sentNote[note] != NONE)
            midi::noteOff(NOTE_CHANNEL, sentNote[note]);
        int out = (int)note + (int)lroundf(base);
        if (out < 0) out = 0;
        if (out > 127) out = 127;
        sentNote[note] = (uint8_t)out;
        midi::noteOn(NOTE_CHANNEL, (uint8_t)out, NOTE_VELOCITY);
    }

    cv::noteOn(target, note, true);
    if (target == keysCh)
        aux::trigger();   // the envelope shape follows the keys' pair
}

void noteOff(uint8_t note, Source src, uint8_t pair)
{
    if (note > 127)
        return;
    const uint8_t target = pair == KEYS_PAIR ? keysCh : (uint8_t)(pair & 1);
    if (src == SRC_KEYS || src == SRC_MIDI)
    {
        arp::noteOff(note);
        if (settings::current.arpOn)
            return;
    }
    if (src != SRC_LOOP)
        looper::noteOff(note);

    if (src != SRC_MIDI && sentNote[note] != NONE)
    {
        midi::noteOff(NOTE_CHANNEL, sentNote[note]);
        sentNote[note] = NONE;
    }
    cv::noteOff(target, note);
}

uint8_t posOfCC(uint8_t cc)
{
    return (cc >= CC_PIANO && cc <= CC_LAST) ? posOfCCTab[cc - CC_PIANO] : NONE;
}

void tapToyPos(uint8_t pos)
{
    if (pos < N_POS)
        inject::queueTap(pos, INJECT_BUTTON_HOLD_MS, INJECT_BUTTON_GAP_MS);
}

void tapToy(uint8_t cc) { tapToyPos(posOfCC(cc)); }

void button(uint8_t cc, bool down)
{
    if (down)
    {
        looper::button(cc);
        tapToy(cc);
    }
    midi::cc(CTRL_CHANNEL, cc, down ? 127 : 0);
}

void loopButton(uint8_t cc)
{
    if (inject::backlogMs() <= LOOP_TAP_LATE_MS)
        tapToy(cc);
    midi::cc(CTRL_CHANNEL, cc, 127);
    midi::cc(CTRL_CHANNEL, cc, 0);
}

void releaseKeysPath()
{
    for (uint8_t n = 0; n < 128; ++n)
    {
        if (sentNote[n] == NONE)
            continue;
        midi::noteOff(NOTE_CHANNEL, sentNote[n]);
        sentNote[n] = NONE;
    }
    cv::allOff(keysCh);
}

void allNotesOff()
{
    for (uint8_t n = 0; n < 128; ++n)
    {
        if (sentNote[n] == NONE)
            continue;
        midi::noteOff(NOTE_CHANNEL, sentNote[n]);
        sentNote[n] = NONE;
    }
    cv::allOff(0);
    cv::allOff(1);
}

void panic()
{
    allNotesOff();
    midi::allSoundOff(NOTE_CHANNEL);
    if (CTRL_CHANNEL != NOTE_CHANNEL)
        midi::allSoundOff(CTRL_CHANNEL);
}

}  // namespace router
