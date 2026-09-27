#include <Arduino.h>

#include "config.h"
#include "keybed.h"
#include "mcp23017.h"

namespace keybed
{

    static uint8_t rawCols[N_COLS];       // this frame
    static uint8_t stableCols[N_COLS];    // accepted state
    static uint8_t releasingCols[N_COLS]; // held keys currently reading open
    static uint32_t lastEdgeUs[N_POS];
    static uint32_t openSinceUs[N_POS];   // when a releasing key last went open

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
            stableCols[c] = releasingCols[c] = 0;
        qHead = qTail = 0;
    }

    bool begin()
    {
        for (uint8_t c = 0; c < N_COLS; ++c)
            rawCols[c] = stableCols[c] = releasingCols[c] = 0;
        for (uint8_t i = 0; i < N_POS; ++i)
            lastEdgeUs[i] = openSinceUs[i] = 0;
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
            for (uint8_t r = 0; r < N_ROWS; ++r)
            {
                const uint8_t bit = (uint8_t)(1u << r);
                const uint8_t pos = POS(c, r);
                const bool raw = rawCols[c] & bit;
                const bool stable = stableCols[c] & bit;

                if (raw == stable)
                {
                    // A held key reading closed again: the open was chatter.
                    releasingCols[c] &= (uint8_t)~bit;
                    continue;
                }

                if (raw)
                {
                    // Press: emitted on the first frame that sees it, after the
                    // guard window. The edge that opened the window was already
                    // emitted, so this only ever swallows contact bounce.
                    if ((uint32_t)(now - lastEdgeUs[pos]) < DEBOUNCE_US)
                        continue;

                    // Do not stamp lastEdgeUs on a rejected ghost - the position
                    // is re-tested next frame, so it comes through the moment one
                    // of the other three keys is lifted.
                    if (isGhost(c, r))
                        continue;

                    lastEdgeUs[pos] = now;
                    stableCols[c] |= bit;
                    push(pos, true);
                    continue;
                }

                // Release: only once the contact has read open for RELEASE_US
                // without a closed frame in between (config.h). Until then the
                // key counts as held, which is what a flickering contact is.
                if (!(releasingCols[c] & bit))
                {
                    releasingCols[c] |= bit;
                    openSinceUs[pos] = now;
                    continue;
                }
                if ((uint32_t)(now - openSinceUs[pos]) < RELEASE_US)
                    continue;

                releasingCols[c] &= (uint8_t)~bit;
                lastEdgeUs[pos] = now;
                stableCols[c] &= (uint8_t)~bit;
                push(pos, false);
            }
        }
        return true;
    }

} // namespace keybed
