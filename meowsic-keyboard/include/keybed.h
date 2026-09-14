#pragma once
#include <stdint.h>

struct KeyEvent {
    uint8_t pos;    // col * 6 + row
    bool    down;
};

namespace keybed {

bool begin();

// One full 8-column frame. Pushes debounced, ghost-filtered edges into the
// event queue. Returns false if the I2C transaction failed, in which case no
// state is updated and no events are produced.
bool scan();

// Pop one event. Returns false when the queue is empty.
bool nextEvent(KeyEvent &e);

bool held(uint8_t pos);

// Forget all held state without emitting release events. Used by panic and by
// I2C recovery, where the caller sends the note-offs itself.
void reset();

}  // namespace keybed
