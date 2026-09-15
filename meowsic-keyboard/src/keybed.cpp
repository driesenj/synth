#include <Arduino.h>

#include "config.h"
#include "keybed.h"
#include "mcp23017.h"

namespace keybed
{

    static uint8_t rawCols[N_COLS];    // this frame
    static uint8_t stableCols[N_COLS]; // accepted state
    static uint32_t lastEdgeUs[N_POS];

    // Event ring. Single producer (scan) and single consumer (main loop) today;
    // the looper will read from the same queue later.
    static constexpr uint8_t QUEUE_LEN = 32; // power of two
    static KeyEvent queue[QUEUE_LEN];
    static volatile uint8_t qHead, qTail;

    static void push(uint8_t pos, bool down)
    {
        uint8_t next = (uint8_t)((qHead + 1) & (QUEUE_LEN - 1));
        if (next == qTail)
            return; // full - drop, better than blocking
        queue[qHead] = {pos, down};
        qHead = next;
    }

    bool nextEvent(KeyEvent &e)
    {
        if (qTail == qHead)
            return false;
        e = queue[qTail];
        qTail = (uint8_t)((qTail + 1) & (QUEUE_LEN - 1));
        return true;
    }

    bool held(uint8_t pos)
    {
        if (pos >= N_POS)
            return false;
        return stableCols[pos / N_ROWS] & (1u << (pos % N_ROWS));
    }

    void reset()
    {
        for (uint8_t c = 0; c < N_COLS; ++c)
            stableCols[c] = 0;
        qHead = qTail = 0;
    }

    bool begin()
    {
        for (uint8_t c = 0; c < N_COLS; ++c)
            rawCols[c] = stableCols[c] = 0;
        for (uint8_t i = 0; i < N_POS; ++i)
            lastEdgeUs[i] = 0;
        qHead = qTail = 0;
        return mcp::begin();
    }

    // ---------------------------------------------------------------------------
    //  Ghost rejection (design doc 9.3)
    //
    //  With no diodes in the membrane, three closed contacts forming an L produce a
    //  phantom fourth at the corner that completes the rectangle. A new closure at
    //  (c, r) is a phantom exactly when some other column c2 holds both row r and
    //  some row r2 that column c also holds.
    //
    //  Because (c, r) is not stable yet, its own bit is still clear in stableCols,
    //  so no self-exclusion is needed.
    // ---------------------------------------------------------------------------
    static bool isGhost(uint8_t c, uint8_t r)
    {
        const uint8_t colMask = stableCols[c];
        if (colMask == 0)
            return false; // nothing else held here

        const uint8_t rowBit = (uint8_t)(1u << r);
        for (uint8_t c2 = 0; c2 < N_COLS; ++c2)
        {
            if (c2 == c)
                continue;
            if (!(stableCols[c2] & rowBit))
                continue; // c2 does not share the row
            if (stableCols[c2] & colMask)
                return true; // and it shares a row with c
        }
        return false;
    }

    bool scan()
    {
        // Read the whole frame first, then process. Keeps the I2C burst tight.
        for (uint8_t c = 0; c < N_COLS; ++c)
        {
            // Assert column c by making it the only output. The latch is 0, so
            // it drives low. Selection is by the direction register, never by
            // the port register.
            if (!mcp::writeReg(REG_COL_IODIR, mcp::colStrobe(c)))
                return false;

            uint8_t rows;
            if (!mcp::readReg(REG_ROW_GPIO, rows))
                return false;
            rawCols[c] = mcp::packRows(rows); // keybed order from here on
        }
        if (!mcp::writeReg(REG_COL_IODIR, 0xFF))
            return false; // release the matrix

        const uint32_t now = micros();

        for (uint8_t c = 0; c < N_COLS; ++c)
        {
            uint8_t changed = (uint8_t)(rawCols[c] ^ stableCols[c]);
            while (changed)
            {
                const uint8_t r = (uint8_t)__builtin_ctz(changed);
                const uint8_t bit = (uint8_t)(1u << r);
                const uint8_t pos = POS(c, r);
                const bool closed = rawCols[c] & bit;
                changed &= (uint8_t)~bit;

                // Guard window. The edge that opened it was already emitted, so
                // this only ever swallows contact bounce.
                if ((uint32_t)(now - lastEdgeUs[pos]) < DEBOUNCE_US)
                    continue;

                // Do not stamp lastEdgeUs on a rejected ghost - the position is
                // re-tested next frame, so it comes through the moment one of the
                // other three keys is lifted.
                if (closed && isGhost(c, r))
                    continue;

                lastEdgeUs[pos] = now;
                if (closed)
                    stableCols[c] |= bit;
                else
                    stableCols[c] &= (uint8_t)~bit;
                push(pos, closed);
            }
        }
        return true;
    }

} // namespace keybed
