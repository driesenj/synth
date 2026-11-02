// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: the seven ways the four slots connect, P(itch), D(elay),
// T(exture) and R(everb). "|" is parallel, ">" serial.
//
//   1 SERIAL    P > D > T > R
//   2 P|D>T>R   (P | D) > T > R
//   3 P>D|T>R   P > (D | T) > R
//   4 P|D|T>R   (P | D | T) > R          three effects into the reverb
//   5 PD|TR     (P > D) | (T > R)        two stereo chains side by side
//   6 PARALLEL  P | D | T | R            four send effects
//   7 DUAL MONO IN 1 > P > D > OUT 1,    two mono chains; IN 2 is
//               IN 2 > T > R > OUT 2     normalled to IN 1
//
// An algorithm is up to four stages in series; a stage holds up to four
// branches in parallel, each one slot or two in series. The order is part
// of the preset format: append, never reorder.

#ifndef SIDEFX_ENGINE_ALGORITHM_H_
#define SIDEFX_ENGINE_ALGORITHM_H_

#include <stdint.h>

namespace sidefx {

enum Algorithm {
  ALGORITHM_SERIAL,
  ALGORITHM_PD_T_R,
  ALGORITHM_P_DT_R,
  ALGORITHM_PDT_R,
  ALGORITHM_PD_TR,
  ALGORITHM_PARALLEL,
  ALGORITHM_DUAL_MONO,
  NUM_ALGORITHMS
};

struct Branch {
  uint8_t length;   // 1 or 2 slots
  uint8_t slot[2];  // SlotId, in signal order
};

struct Stage {
  uint8_t num_branches;  // 1..4
  Branch branch[4];
};

struct Topology {
  uint8_t num_stages;  // 1..4
  Stage stage[4];
  // DUAL MONO: the single stage's branch 0 runs IN 1 > OUT 1 and branch 1
  // runs IN 2 > OUT 2, each in mono.
  bool dual_mono;
};

extern const char* const kAlgorithmNames[NUM_ALGORITHMS];  // "SERIAL", "P|D>T>R", ...
const Topology& GetTopology(int algorithm);

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_ALGORITHM_H_
