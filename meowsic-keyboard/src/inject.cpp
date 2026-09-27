#include <Arduino.h>

#include "config.h"
#include "inject.h"

namespace inject {

static uint8_t curA = 0, curB = 0;
static bool isClosed = false;

void begin()
{
    // INH first, then the selects. The other order briefly closes an
    // arbitrary pair. The 10 k pull-up already held INH high through the
    // boot, while these GPIOs were still floating; this takes over from it.
    pinMode(PIN_MUX_INH, OUTPUT);
    digitalWrite(PIN_MUX_INH, HIGH);

    const int sel[] = {PIN_MUXA_S0, PIN_MUXA_S1, PIN_MUXA_S2,
                       PIN_MUXB_S0, PIN_MUXB_S1, PIN_MUXB_S2};
    for (int pin : sel)
    {
        pinMode(pin, OUTPUT);
        digitalWrite(pin, LOW);
    }
    curA = curB = 0;
    isClosed = false;
}

void selectRaw(uint8_t a, uint8_t b)
{
    digitalWrite(PIN_MUX_INH, HIGH);
    isClosed = false;

    a &= 7;
    b &= 7;
    digitalWrite(PIN_MUXA_S0, a & 1);
    digitalWrite(PIN_MUXA_S1, (a >> 1) & 1);
    digitalWrite(PIN_MUXA_S2, (a >> 2) & 1);
    digitalWrite(PIN_MUXB_S0, b & 1);
    digitalWrite(PIN_MUXB_S1, (b >> 1) & 1);
    digitalWrite(PIN_MUXB_S2, (b >> 2) & 1);
    delayMicroseconds(5); // the 4051 wants tens of ns of select set-up
    curA = a;
    curB = b;
}

void selectPos(uint8_t pos)
{
    if (pos >= N_POS)
        return;
    selectRaw(MUX_COL_OF[pos / N_ROWS], MUX_ROW_OF[pos % N_ROWS]);
}

void close()
{
    digitalWrite(PIN_MUX_INH, LOW);
    isClosed = true;
}

void open()
{
    digitalWrite(PIN_MUX_INH, HIGH);
    isClosed = false;
}

bool closed() { return isClosed; }
uint8_t rawA() { return curA; }
uint8_t rawB() { return curB; }

void press(uint8_t pos)
{
    selectPos(pos);
    close();
}

void tap(uint8_t pos, uint32_t holdMs)
{
    press(pos);
    delay(holdMs);
    open();
}

// ---- Tap queue --------------------------------------------------------------

struct Tap
{
    uint8_t pos, holdMs, gapMs;
};

static Tap queue[INJECT_QUEUE_LEN];
static uint8_t qHead, qTail;   // single producer, single consumer, both in loop()

enum Phase : uint8_t { IDLE, CLOSED, GAP };
static Phase phase = IDLE;
static uint32_t phaseEnd;      // millis() at which the current phase is over
static uint8_t curGap;

static_assert((INJECT_QUEUE_LEN & (INJECT_QUEUE_LEN - 1)) == 0,
              "INJECT_QUEUE_LEN must be a power of two");

void queueTap(uint8_t pos, uint8_t holdMs, uint8_t gapMs)
{
    if (pos >= N_POS)
        return;
    const uint8_t next = (uint8_t)((qHead + 1) & (INJECT_QUEUE_LEN - 1));
    if (next == qTail)
        return; // full - drop, better than a press arriving late
    queue[qHead] = {pos, holdMs, gapMs};
    qHead = next;
}

void service()
{
    const uint32_t now = millis();

    if (phase != IDLE)
    {
        if ((int32_t)(now - phaseEnd) < 0)
            return; // still holding, or still in the gap
        if (phase == CLOSED)
        {
            open();
            phase = GAP;
            phaseEnd = now + curGap;
            return;
        }
        phase = IDLE; // gap over
    }

    if (qTail == qHead)
        return;
    const Tap t = queue[qTail];
    qTail = (uint8_t)((qTail + 1) & (INJECT_QUEUE_LEN - 1));

    press(t.pos); // INH high, selects, INH low - in that order, see selectRaw
    phase = CLOSED;
    phaseEnd = now + t.holdMs;
    curGap = t.gapMs;
}

void flush()
{
    qHead = qTail = 0;
    phase = IDLE;
    open();
}

uint32_t backlogMs()
{
    uint32_t ms = 0;
    if (phase != IDLE)
    {
        const int32_t left = (int32_t)(phaseEnd - millis());
        if (left > 0)
            ms += (uint32_t)left;
        if (phase == CLOSED)
            ms += curGap;
    }
    for (uint8_t i = qTail; i != qHead; i = (uint8_t)((i + 1) & (INJECT_QUEUE_LEN - 1)))
        ms += (uint32_t)queue[i].holdMs + queue[i].gapMs;
    return ms;
}

}  // namespace inject
