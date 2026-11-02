// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the fake blocks behind test/fake_registry.cc.

#ifndef SIDEFX_TEST_FAKE_REGISTRY_H_
#define SIDEFX_TEST_FAKE_REGISTRY_H_

#include "engine/block.h"
#include "engine/registry.h"

namespace sidefx {

class FakeBlock : public Block {
 public:
  enum Kind {
    KIND_GAIN,
    KIND_ECHO,
    KIND_NAN,
    KIND_FREEZE,
  };

  static const int kEchoLength = 64;

  FakeBlock() : resets(0), process_calls(0) { }

  void Configure(const BlockInfo& info, Kind kind) {
    info_ = info;
    kind_ = kind;
  }

  const BlockInfo& info() const { return info_; }
  bool Init(Memory* memory);
  void Reset();
  void Process(const ProcessContext& context, const float* params,
               const Frame* in, Frame* out, size_t size);
  void Format(int param, float value, const ProcessContext& context,
              char* text, size_t size) const;

  int resets;
  int process_calls;
  ProcessContext last_context;
  float last_params[kNumSlotValues];

 private:
  BlockInfo info_;
  Kind kind_;
  Frame* echo_;
  int echo_index_;
  Frame held_;
};

FakeBlock* GetFakeBlock(int slot, int type);

}  // namespace sidefx

#endif  // SIDEFX_TEST_FAKE_REGISTRY_H_
