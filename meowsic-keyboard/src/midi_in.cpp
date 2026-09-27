#include <Arduino.h>

#include "auxout.h"
#include "clock.h"
#include "config.h"
#include "controls.h"
#include "cv.h"
#include "inject.h"
#include "looper.h"
#include "midi_in.h"
#include "router.h"
#include "settings.h"

namespace midi_in {

// ---- Dispatch ---------------------------------------------------------------

// Which CV/gate pair a MIDI channel speaks to, or -1.
static int cvChannelOf(uint8_t midiCh)
{
    if (midiCh == MIDI_IN_KEYS_CH)  return router::keysChannel();
    if (midiCh == MIDI_IN_OTHER_CH) return router::otherChannel();
    return -1;
}

static void noteOn(uint8_t midiCh, uint8_t note)
{
    if (midiCh == MIDI_IN_KEYS_CH)
        router::noteOn(note, router::SRC_MIDI);       // toy, keys' CV pair, the loop
    else if (midiCh == MIDI_IN_OTHER_CH)
        cv::noteOn(router::otherChannel(), note, false);   // the other pair, straight, no pots
}

static void noteOff(uint8_t midiCh, uint8_t note)
{
    if (midiCh == MIDI_IN_KEYS_CH)
        router::noteOff(note, router::SRC_MIDI);
    else if (midiCh == MIDI_IN_OTHER_CH)
        cv::noteOff(router::otherChannel(), note);
}

// The four toy buttons that never scan, by keybed position.
static uint8_t posOfInjectOnly(uint8_t cc)
{
    switch (cc)
    {
    case CC_TEMPO_UP:   return POS_TEMPO_UP;
    case CC_TEMPO_DOWN: return POS_TEMPO_DOWN;
    case CC_VOL_UP:     return POS_VOL_UP;
    case CC_VOL_DOWN:   return POS_VOL_DOWN;
    default:            return 0xFF;
    }
}

static void control(uint8_t midiCh, uint8_t cc, uint8_t v)
{
    const bool on = v >= 64;

    // The toy's buttons, on any channel: a press (>= 64) taps, a release
    // does nothing. The same numbers the panel sends out, so a recorded
    // panel plays back onto the toy.
    if (cc >= CC_PIANO && cc <= CC_LAST)
    {
        if (on)
            router::tapToy(cc);
        return;
    }
    if (cc >= CC_TEMPO_UP && cc <= CC_VOL_DOWN)
    {
        if (on)
            router::tapToyPos(posOfInjectOnly(cc));
        return;
    }

    switch (cc)
    {
    case 1:   // mod wheel -> AUX, when that waveform is selected
        if (midiCh == MIDI_IN_KEYS_CH)
            aux::setModWheel(v);
        break;

    case 64:  // sustain, per channel
    {
        const int ch = cvChannelOf(midiCh);
        if (ch >= 0)
            cv::setSustain((uint8_t)ch, on);
        break;
    }

    // Settings, as the buttons would set them - same state, same blink.
    // On/off is the usual >= 64; the cycles take the entry's number.
    case CC_SET_QUANT_LOOP:  controls::setQuantLoop(on); break;
    case CC_SET_QUANT_PITCH: controls::setQuantPitch(on); break;
    case CC_SET_AUX_WAVE:    controls::setAuxWave(v); break;
    case CC_SET_AUX_RATE:    controls::setAuxRate(v); break;
    case CC_SET_GATE_MODE:   controls::setGateMode(on ? GATE_RETRIG : GATE_LEGATO); break;
    case CC_SET_GLIDE:       controls::setGlide(v); break;
    case CC_SET_ARP:         controls::setArp(on); break;
    case CC_SET_ARP_ORDER:   controls::setArpOrder(v); break;
    case CC_SET_ARP_DIV:     controls::setArpDiv(v); break;
    case CC_SET_TOY_NOTES:   controls::setToyNotes(on); break;

    case 120:  // all sound off
    case 123:  // all notes off
        // Everything off - MIDI out, both CV pairs, the toy's queue - but
        // without the CC 120 / 123 echo panic sends, since this came in
        // over MIDI and the DAW would get its own message back.
        router::allNotesOff();
        inject::flush();
        break;

    default:
        break;
    }
}

static void channelMessage(uint8_t status, uint8_t d1, uint8_t d2)
{
    const uint8_t kind = status & 0xF0, midiCh = status & 0x0F;
    switch (kind)
    {
    case 0x90:
        if (d2 == 0) noteOff(midiCh, d1); else noteOn(midiCh, d1);
        break;
    case 0x80:
        noteOff(midiCh, d1);
        break;
    case 0xB0:
        control(midiCh, d1, d2);
        break;
    case 0xC0:   // program change 0-4: piano, bells, meow, organ, banjo
        if (midiCh == MIDI_IN_KEYS_CH && d1 <= CC_BANJO - CC_PIANO)
            router::tapToy((uint8_t)(CC_PIANO + d1));
        break;
    case 0xE0:   // pitch bend, per channel
    {
        const int ch = cvChannelOf(midiCh);
        if (ch >= 0)
        {
            const int raw = ((int)d2 << 7 | d1) - 8192;   // -8192 .. +8191
            cv::setBend((uint8_t)ch, (float)raw / 8192.0f * MIDI_BEND_SEMIS);
        }
        break;
    }
    default:     // aftertouch, either kind
        break;
    }
}

// Clock ticks drive the transport clock; start / stop / continue drive the
// loop, and a start is the DAW's beat 1.
static void realtime(uint8_t b)
{
    switch (b)
    {
    case 0xF8: clk::midiTick(); break;
    case 0xFA: clk::resetPhase(); looper::restartAll(); break;
    case 0xFB: looper::resumeAll(); break;
    case 0xFC: looper::stopAll(); break;
    default:   break;   // reset (0xFF), undefined
    }
}

// ---- Parser -----------------------------------------------------------------

struct Parser
{
    uint8_t status = 0;      // running status; 0 = none
    uint8_t data[2];
    uint8_t count = 0;
    bool    inSysex = false;

    void feed(uint8_t b)
    {
        // Real-time bytes can land anywhere, even inside a message, and
        // never disturb running status.
        if (b >= 0xF8)
        {
            if (b != 0xFE)   // active sensing is just a heartbeat
                realtime(b);
            return;
        }

        if (b >= 0x80)
        {
            if (b >= 0xF0)
            {
                // System common. SysEx (F0) swallows data until EOX (F7);
                // the rest carry data we do not want. Either way running
                // status is cancelled, so their data bytes fall through
                // the `status == 0` check below.
                inSysex = (b == 0xF0);
                status = 0;
                count = 0;
                return;
            }
            inSysex = false;
            status = b;
            count = 0;
            return;
        }

        if (inSysex || status == 0)
            return;   // SysEx payload, or data with no status to belong to

        data[count++] = b;
        const uint8_t kind = status & 0xF0;
        const uint8_t needed = (kind == 0xC0 || kind == 0xD0) ? 1 : 2;
        if (count < needed)
            return;
        channelMessage(status, data[0], needed == 2 ? data[1] : 0);
        count = 0;   // status stays: running status
    }
};

static Parser din;
#if USB_MIDI
static Parser usb;
#endif

void begin()
{
    // midi::begin() opened both UARTs; nothing to do but start clean.
    din = Parser();
#if USB_MIDI
    usb = Parser();
#endif
}

void service()
{
    // Everything waiting on each port. The buffers are 256 bytes, which is
    // 80 ms at 31250 baud and 22 ms at 115200; the loop comes round every
    // ~3 ms, so nothing is lost.
    while (Serial2.available())
        din.feed((uint8_t)Serial2.read());
#if USB_MIDI
    while (Serial.available())
        usb.feed((uint8_t)Serial.read());
#endif
}

}  // namespace midi_in
