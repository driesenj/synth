// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/algorithm.h"

#include "engine/config.h"

namespace sidefx {

const char* const kAlgorithmNames[NUM_ALGORITHMS] = {
  "SERIAL", "P|D>T>R", "P>D|T>R", "P|D|T>R", "PD|TR", "PARALLEL", "DUAL MONO",
};

namespace {

const uint8_t P = SLOT_PITCH;
const uint8_t D = SLOT_DELAY;
const uint8_t T = SLOT_TEXTURE;
const uint8_t R = SLOT_REVERB;

// Branch: { length, { slots } }; Stage: { branches, { ... } }.
const Topology kTopologies[NUM_ALGORITHMS] = {
  // 1 SERIAL: P > D > T > R
  { 4, { { 1, { { 1, { P } } } }, { 1, { { 1, { D } } } },
         { 1, { { 1, { T } } } }, { 1, { { 1, { R } } } } }, false },
  // 2 (P | D) > T > R
  { 3, { { 2, { { 1, { P } }, { 1, { D } } } }, { 1, { { 1, { T } } } },
         { 1, { { 1, { R } } } } }, false },
  // 3 P > (D | T) > R
  { 3, { { 1, { { 1, { P } } } }, { 2, { { 1, { D } }, { 1, { T } } } },
         { 1, { { 1, { R } } } } }, false },
  // 4 (P | D | T) > R
  { 2, { { 3, { { 1, { P } }, { 1, { D } }, { 1, { T } } } },
         { 1, { { 1, { R } } } } }, false },
  // 5 (P > D) | (T > R)
  { 1, { { 2, { { 2, { P, D } }, { 2, { T, R } } } } }, false },
  // 6 P | D | T | R
  { 1, { { 4, { { 1, { P } }, { 1, { D } }, { 1, { T } }, { 1, { R } } } } },
    false },
  // 7 DUAL MONO: IN 1 > P > D > OUT 1, IN 2 > T > R > OUT 2
  { 1, { { 2, { { 2, { P, D } }, { 2, { T, R } } } } }, true },
};

}  // namespace

const Topology& GetTopology(int algorithm) {
  if (algorithm < 0 || algorithm >= NUM_ALGORITHMS) {
    algorithm = ALGORITHM_SERIAL;
  }
  return kTopologies[algorithm];
}

}  // namespace sidefx
