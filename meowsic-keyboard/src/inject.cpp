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

}  // namespace inject
