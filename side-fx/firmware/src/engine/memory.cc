// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.

#include "engine/memory.h"

namespace sidefx {

void Arena::Init(void* base, size_t size) {
  base_ = static_cast<uint8_t*>(base);
  size_ = size;
  used_ = 0;
  failed_ = false;
}

void* Arena::Allocate(size_t size, size_t alignment) {
  if (alignment < 4) {
    alignment = 4;
  }
  uintptr_t start = reinterpret_cast<uintptr_t>(base_) + used_;
  uintptr_t aligned = (start + alignment - 1) & ~(uintptr_t(alignment) - 1);
  size_t offset = aligned - reinterpret_cast<uintptr_t>(base_);
  if (!base_ || offset + size > size_) {
    failed_ = true;
    return NULL;
  }
  used_ = offset + size;
  return base_ + offset;
}

}  // namespace sidefx
