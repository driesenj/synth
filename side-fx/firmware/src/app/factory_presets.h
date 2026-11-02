// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the factory presets, built in code from the blocks' parameter
// lists (so they follow any change of defaults), written to the bank on the
// first power-up and by RESTORE FACTORY.

#ifndef SIDEFX_APP_FACTORY_PRESETS_H_
#define SIDEFX_APP_FACTORY_PRESETS_H_

#include "engine/preset.h"

namespace sidefx {

int NumFactoryPresets();
// Fills *preset (sealed). Needs InitBlocks() first.
void GetFactoryPreset(int index, Preset* preset);

// How many block, parameter or note names the presets asked for and did not
// find, since power-up (the host test requires 0).
int FactoryPresetMisses();

}  // namespace sidefx

#endif  // SIDEFX_APP_FACTORY_PRESETS_H_
