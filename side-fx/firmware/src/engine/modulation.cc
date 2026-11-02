// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/modulation.h"

namespace sidefx {

const char* const kModSourceNames[NUM_MOD_SOURCES] = {
  "OFF", "CV1", "CV2", "CV3", "CV4", "LFO1", "LFO2", "RND", "ENV",
  "CC A", "CC B", "NOTE", "GATE",
};

const char* const kLfoShapeNames[NUM_LFO_SHAPES] = {
  "SINE", "TRI", "RAMP+", "RAMP-", "SQUARE", "S&H",
};

}  // namespace sidefx
