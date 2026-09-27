#include <Arduino.h>

#include "clock.h"
#include "config.h"
#include "looper.h"
#include "router.h"
#include "settings.h"

namespace looper {

enum Kind : uint8_t { EV_ON, EV_OFF, EV_BUTTON };

struct Event
{
    uint16_t tick;    // raw, as played, within the loop
    uint8_t  kind;
    uint8_t  data;    // note or button CC
    uint8_t  layer;
};

static constexpr uint16_t TICKS_PER_16TH = TICKS_PER_BEAT / 4;
static constexpr uint32_t MAX_TICKS = (uint32_t)LOOP_MAX_BEATS * TICKS_PER_BEAT;

static inline bool has(const uint8_t *set, uint8_t k) { return set[k >> 3] & (1u << (k & 7)); }
static inline void setBit(uint8_t *set, uint8_t k, bool v)
{
    if (v) set[k >> 3] |= (uint8_t)(1u << (k & 7));
    else   set[k >> 3] &= (uint8_t)~(1u << (k & 7));
}
static inline void clearSet(uint8_t *set) { for (uint8_t i = 0; i < 16; ++i) set[i] = 0; }

static bool anyRunningBut(uint8_t ch);

// ============================================================================
//  One loop
// ============================================================================

struct Loop
{
    uint8_t  ch;              // the CV/gate pair this loop plays on

    Event    ev[LOOP_MAX_EVENTS];
    uint16_t n = 0;
    uint16_t len = 0;         // loop length in ticks
    uint8_t  curLayer = 0;
    State    st = EMPTY;

    // Playback: the events in the order they play, with the tick each plays
    // at (raw, or snapped to the 16th grid when quantise loop is on).
    uint16_t order[LOOP_MAX_EVENTS];
    uint16_t playTick[LOOP_MAX_EVENTS];
    bool     orderDirty = false;
    bool     orderQuant = false;
    uint16_t cursor = 0;
    uint32_t startTick = 0;   // absolute tick of the current pass's tick 0
    int32_t  lastPos = -1;
    uint32_t pendingStart = 0; // absolute tick playback waits for (quantised start); 0 = none
    bool     pendingOverdub = false;

    // Notes the playback has turned on; notes the recording has turned on
    // and not yet off, with the layer each one's note-on went into, so the
    // note-off always lands in the same layer - whenever the key comes up.
    uint8_t loopOn[16];
    uint8_t recOn[16];
    uint8_t recLayer[128];

    // ---- The store ----------------------------------------------------------

    void add(uint16_t tick, uint8_t kind, uint8_t data, uint8_t layer)
    {
        if (n >= LOOP_MAX_EVENTS)
            return;   // full: the newest is what gets lost
        ev[n++] = {tick, kind, data, layer};
        orderDirty = true;
    }

    // Sort key: play tick, then note-offs before note-ons on the same tick
    // so a repeated note that quantises onto itself still retriggers.
    inline uint32_t keyOf(uint16_t i) const
    {
        return ((uint32_t)playTick[i] << 2) | (ev[i].kind == EV_OFF ? 0u : 1u);
    }

    void rebuildOrder()
    {
        orderQuant = settings::current.quantLoop;
        for (uint16_t i = 0; i < n; ++i)
        {
            uint16_t t = ev[i].tick;
            if (orderQuant)
            {
                t = (uint16_t)(((uint32_t)t + TICKS_PER_16TH / 2) / TICKS_PER_16TH * TICKS_PER_16TH);
                if (t >= len)
                    t = 0;   // the last 16th snaps onto the next pass's first
            }
            playTick[i] = t;
        }
        // Insertion sort: the events arrive nearly in order, so this is
        // quick, and it only runs when the store or the setting changed.
        for (uint16_t i = 0; i < n; ++i)
        {
            const uint32_t k = keyOf(i);
            uint16_t j = i;
            while (j > 0 && keyOf(order[j - 1]) > k)
            {
                order[j] = order[j - 1];
                --j;
            }
            order[j] = i;
        }
        orderDirty = false;
    }

    // The first event in play order after position pos.
    void seek(int32_t pos)
    {
        cursor = 0;
        while (cursor < n && (int32_t)playTick[order[cursor]] <= pos)
            ++cursor;
    }

    // ---- Playback -----------------------------------------------------------

    void fire(const Event &e)
    {
        switch (e.kind)
        {
        case EV_ON:
            router::noteOn(e.data, router::SRC_LOOP, ch);
            setBit(loopOn, e.data, true);
            break;
        case EV_OFF:
            router::noteOff(e.data, router::SRC_LOOP, ch);
            setBit(loopOn, e.data, false);
            break;
        case EV_BUTTON:
            router::loopButton(e.data);
            break;
        }
    }

    void fireUpTo(int32_t pos)
    {
        while (cursor < n && (int32_t)playTick[order[cursor]] <= pos)
            fire(ev[order[cursor++]]);
    }

    void silence()
    {
        for (uint8_t note = 0; note < 128; ++note)
            if (has(loopOn, note))
                router::noteOff(note, router::SRC_LOOP, ch);
        clearSet(loopOn);
    }

    // Keys the recording still holds get their note-off here, at pos.
    void closePending(int32_t pos)
    {
        if (pos < 0) pos = 0;
        for (uint8_t note = 0; note < 128; ++note)
            if (has(recOn, note))
                add((uint16_t)pos, EV_OFF, note, recLayer[note]);
        clearSet(recOn);
    }

    // Playback from the top at absolute tick t.
    void startAt(uint32_t t, bool overdub)
    {
        startTick = t;
        lastPos = -1;
        if (orderDirty)
            rebuildOrder();
        cursor = 0;
        clearSet(loopOn);
        if (overdub)
            ++curLayer;
        st = overdub ? OVERDUB : PLAYING;
        clk::sendStart();
    }

    void stopPlayback()
    {
        closePending(lastPos < 0 ? 0 : lastPos);
        silence();
        pendingStart = 0;
        st = STOPPED;
        clk::sendStop();
    }

    // Ask for playback: now, or on the next beat when quantised. The beat
    // grid is moved here only if no other loop is already on it.
    void requestStart(bool overdub)
    {
        if (settings::current.quantLoop)
        {
            const uint32_t t = clk::nextBeatTick();
            if (t == clk::tick())
                startAt(t, overdub);
            else
            {
                pendingStart = t;
                pendingOverdub = overdub;
            }
        }
        else
        {
            if (!anyRunningBut(ch))
                clk::resetPhase();   // the loop is the beat now
            startAt(clk::tick(), overdub);
        }
    }

    // ---- Recording ----------------------------------------------------------

    // At the end of a pass, notes the recording still holds get their
    // note-off on the last tick and a fresh note-on on the first tick of the
    // next pass, in the given layer; the key stays pending, so its release
    // records the off later. Every on thus has its off in its own layer,
    // and undoing a layer can never leave a note sounding.
    void closeHeld(uint8_t layerForOn)
    {
        for (uint8_t note = 0; note < 128; ++note)
        {
            if (!has(recOn, note))
                continue;
            add((uint16_t)(len - 1), EV_OFF, note, recLayer[note]);
            add(0, EV_ON, note, layerForOn);
            recLayer[note] = layerForOn;
        }
    }

    // The first pass ends: fix the length, close held notes, play.
    void closeRecording()
    {
        const uint32_t now = clk::tick();
        uint32_t elapsed = now - startTick;
        if (settings::current.quantLoop)
        {
            elapsed = (elapsed + TICKS_PER_BEAT / 2) / TICKS_PER_BEAT * TICKS_PER_BEAT;
            if (elapsed < TICKS_PER_BEAT)
                elapsed = TICKS_PER_BEAT;
        }
        else if (elapsed < TICKS_PER_16TH)
            elapsed = TICKS_PER_16TH;
        if (elapsed > MAX_TICKS)
            elapsed = MAX_TICKS;
        len = (uint16_t)elapsed;

        // Rounded down: whatever was played past the new end belongs to the
        // start of the next pass.
        for (uint16_t i = 0; i < n; ++i)
            if (ev[i].tick >= len)
                ev[i].tick = (uint16_t)(ev[i].tick % len);

        closeHeld(curLayer);
        rebuildOrder();

        // Keep playing from where we are. If the length was rounded down
        // the pass has already wrapped: move the origin on, or service()
        // would replay the end of the first pass over what was just played.
        while (now - startTick >= len)
            startTick += len;
        st = PLAYING;
        clearSet(loopOn);
        const int32_t pos = (int32_t)(now - startTick);
        seek(pos);
        lastPos = pos;
    }

    // Overdubbing ends; keys still held record their note-off on release.
    void finishOverdub() { st = PLAYING; }

    uint16_t recordPos() const
    {
        int32_t pos = (int32_t)(clk::tick() - startTick);
        if (pos < 0) pos = 0;
        if (st != RECORDING && pos >= (int32_t)len)
            pos = len - 1;
        return (uint16_t)pos;
    }

    void noteOn(uint8_t note)
    {
        if (st == ARMED)
        {
            // The first note is beat 1. With the internal clock and nothing
            // else running, the beat grid moves to it; otherwise - another
            // loop on the grid, or an external clock - it snaps to the grid.
            uint32_t t = clk::tick();
            if (clk::source() == clk::SRC_INTERNAL && !anyRunningBut(ch))
                clk::resetPhase();
            else
            {
                const uint32_t r = (t - clk::origin()) % TICKS_PER_16TH;
                t = r < TICKS_PER_16TH / 2 ? t - r : t + (TICKS_PER_16TH - r);
            }
            n = 0;
            curLayer = 0;
            startTick = t;
            clearSet(recOn);
            clearSet(loopOn);
            st = RECORDING;
            clk::sendStart();
        }
        if (st != RECORDING && st != OVERDUB)
            return;
        add(recordPos(), EV_ON, note, curLayer);
        setBit(recOn, note, true);
        recLayer[note] = curLayer;
    }

    void noteOff(uint8_t note)
    {
        // A recorded note-on gets its off whenever the key comes up - also
        // after the recording closed or the overdub ended, so a note held
        // across either is as long in the loop as it was played.
        if (st != RECORDING && st != OVERDUB && st != PLAYING)
            return;
        if (!has(recOn, note))
            return;   // its on was never recorded (pressed before, or undone)
        add(recordPos(), EV_OFF, note, recLayer[note]);
        setBit(recOn, note, false);
    }

    void button(uint8_t cc)
    {
        if (st != RECORDING && st != OVERDUB)
            return;
        add(recordPos(), EV_BUTTON, cc, curLayer);
    }

    // ---- Transport ----------------------------------------------------------

    void record()
    {
        switch (st)
        {
        case EMPTY:     st = ARMED; break;
        case ARMED:     st = EMPTY; break;
        case RECORDING: closeRecording(); break;
        case PLAYING:
            ++curLayer;   // keys still pending keep their own layer
            st = OVERDUB;
            break;
        case OVERDUB:   finishOverdub(); break;
        case STOPPED:
            if (pendingStart == 0)
                requestStart(true);
            break;
        }
    }

    void play()
    {
        switch (st)
        {
        case EMPTY:
        case ARMED:     break;
        case RECORDING: closeRecording(); break;
        case OVERDUB:   finishOverdub(); break;
        case PLAYING:   stopPlayback(); break;
        case STOPPED:
            if (pendingStart != 0)
                pendingStart = 0;   // a second press cancels the wait
            else
                requestStart(false);
            break;
        }
    }

    void stop()
    {
        switch (st)
        {
        case EMPTY:     break;
        case ARMED:     st = EMPTY; break;
        case RECORDING: closeRecording(); stopPlayback(); break;
        case OVERDUB:   finishOverdub(); stopPlayback(); break;
        case PLAYING:   stopPlayback(); break;
        case STOPPED:   pendingStart = 0; break;
        }
    }

    // Drop every event of the newest layer. Keys still held whose note-on
    // was in it are forgotten too, or their release would record an off
    // into a layer that no longer exists.
    void dropLayer(uint8_t layer)
    {
        uint16_t w = 0;
        for (uint16_t i = 0; i < n; ++i)
            if (ev[i].layer != layer)
                ev[w++] = ev[i];
        n = w;
        for (uint8_t note = 0; note < 128; ++note)
            if (has(recOn, note) && recLayer[note] == layer)
                setBit(recOn, note, false);
        orderDirty = true;
    }

    void undo()
    {
        switch (st)
        {
        case EMPTY:     break;
        case ARMED:     st = EMPTY; break;
        case RECORDING:            // the first pass is cancelled outright
            n = 0;
            clearSet(recOn);
            st = EMPTY;
            break;
        case OVERDUB:
            // What this pass has recorded so far goes; overdubbing continues
            // in the same layer, and the notes it is holding start over.
            dropLayer(curLayer);
            silence();
            rebuildOrder();
            seek(lastPos);
            break;
        case PLAYING:
        case STOPPED:
            if (curLayer == 0)
                break;   // only the first pass is left; clear is explicit
            dropLayer(curLayer);
            --curLayer;
            if (st == PLAYING)
            {
                silence();
                rebuildOrder();
                seek(lastPos);
            }
            break;
        }
    }

    void clear()
    {
        if (st == PLAYING || st == OVERDUB || st == RECORDING)
            return;   // only while stopped, so a slip cannot take a running loop
        n = 0;
        len = 0;
        curLayer = 0;
        clearSet(recOn);
        clearSet(loopOn);
        pendingStart = 0;
        st = EMPTY;
    }

    void restart()
    {
        if (st == EMPTY || st == ARMED || st == RECORDING)
            return;
        if (st == OVERDUB)
            finishOverdub();
        silence();
        startAt(clk::tick(), false);
    }

    void resume()
    {
        if (st == STOPPED && pendingStart == 0)
            startAt(clk::tick(), false);
    }

    bool running() const { return st == PLAYING || st == OVERDUB; }

    // ---- Service ------------------------------------------------------------

    void begin(uint8_t channel)
    {
        ch = channel;
        n = 0;
        len = 0;
        curLayer = 0;
        st = EMPTY;
        orderDirty = false;
        cursor = 0;
        lastPos = -1;
        pendingStart = 0;
        clearSet(loopOn);
        clearSet(recOn);
    }

    void service()
    {
        const uint32_t now = clk::tick();

        if (pendingStart != 0 && (int32_t)(now - pendingStart) >= 0)
        {
            const bool od = pendingOverdub;
            pendingStart = 0;
            startAt(now, od);
        }

        if (st == RECORDING)
        {
            if (now - startTick >= MAX_TICKS)
                closeRecording();   // the longest loop allowed closes itself
            return;
        }
        if (st != PLAYING && st != OVERDUB)
            return;

        if (settings::current.quantLoop != orderQuant)
            orderDirty = true;

        int32_t pos = (int32_t)(now - startTick);
        if (pos < 0)
            pos = 0;

        while (pos >= (int32_t)len)
        {
            // End of the pass: the rest of its events, then round again.
            fireUpTo((int32_t)len - 1);
            if (st == OVERDUB)
            {
                closeHeld((uint8_t)(curLayer + 1));
                ++curLayer;
            }
            else
                closeHeld(curLayer);   // a key held on after the recording closed
            startTick += len;
            pos -= len;
            if (orderDirty)
                rebuildOrder();
            cursor = 0;
            lastPos = -1;
        }

        if (orderDirty && lastPos < 0)
        {
            rebuildOrder();   // a quantise flip lands at the next pass; a wrap just happened
            cursor = 0;
        }

        fireUpTo(pos);
        lastPos = pos;
    }
};

// ============================================================================
//  The two, and the active one
// ============================================================================

static Loop loops[N_LOOPS];
static uint8_t activeIx = 0;

static bool anyRunningBut(uint8_t ch)
{
    for (uint8_t i = 0; i < N_LOOPS; ++i)
        if (i != ch && loops[i].running())
            return true;
    return false;
}

static inline Loop &at(uint8_t ch) { return loops[ch == ACTIVE ? activeIx : (ch & 1)]; }

void begin()
{
    for (uint8_t i = 0; i < N_LOOPS; ++i)
        loops[i].begin(i);
    activeIx = 0;
}

void service()
{
    for (auto &l : loops)
        l.service();
}

void setActive(uint8_t ch) { activeIx = ch & 1; }
uint8_t active() { return activeIx; }

State state(uint8_t ch) { return at(ch).st; }
uint16_t lengthTicks(uint8_t ch) { return at(ch).len; }
uint16_t eventCount(uint8_t ch) { return at(ch).n; }
uint8_t layer(uint8_t ch) { return at(ch).curLayer; }
uint32_t positionTicks(uint8_t ch)
{
    const Loop &l = at(ch);
    return l.running() && l.lastPos >= 0 ? (uint32_t)l.lastPos : 0;
}
uint32_t passStart(uint8_t ch) { return at(ch).startTick; }
bool anyRunning() { return anyRunningBut(0xFF); }

void record() { at(ACTIVE).record(); }
void play()   { at(ACTIVE).play(); }
void stop()   { at(ACTIVE).stop(); }
void undo()   { at(ACTIVE).undo(); }
void clear()  { at(ACTIVE).clear(); }

void restartAll() { for (auto &l : loops) l.restart(); }
void resumeAll()  { for (auto &l : loops) l.resume(); }
void stopAll()    { for (auto &l : loops) l.stop(); }

bool recording() { return at(ACTIVE).st == ARMED || at(ACTIVE).st == RECORDING || at(ACTIVE).st == OVERDUB; }
void noteOn(uint8_t note)  { at(ACTIVE).noteOn(note); }
void noteOff(uint8_t note) { at(ACTIVE).noteOff(note); }
void button(uint8_t cc)    { at(ACTIVE).button(cc); }

}  // namespace looper
