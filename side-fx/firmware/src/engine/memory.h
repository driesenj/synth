// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: where blocks get their memory.
//
// Nothing is allocated after start-up. At boot the engine creates every
// block type and calls its Init(), which takes what it needs from two
// arenas:
//
// - internal: on-chip SRAM (the H750's 256 kB D2 RAM, cached), for the
//   block objects themselves and small buffers read every sample (filter
//   states, short allpass lines). Keep a block's share under 8 kB.
// - external: the Seed's 64 MB SDRAM (cached), for delay lines, grain
//   buffers and reverb tanks. Slower than SRAM on a cache miss, so read it
//   sequentially where possible.
//
// Arena memory is not cleared: on the Seed it holds whatever the SDRAM
// powered up with. Blocks clear their buffers in Reset().

#ifndef SIDEFX_ENGINE_MEMORY_H_
#define SIDEFX_ENGINE_MEMORY_H_

#include <stddef.h>
#include <stdint.h>

#include <new>

namespace sidefx {

class Arena {
 public:
  Arena() : base_(NULL), size_(0), used_(0), failed_(false) { }

  void Init(void* base, size_t size);

  // NULL (and failed() true from then on) when the arena is full.
  void* Allocate(size_t size, size_t alignment = 32);

  template<typename T>
  T* AllocateArray(size_t count) {
    return static_cast<T*>(Allocate(sizeof(T) * count, alignof(T) > 4 ? alignof(T) : 4));
  }

  // Constructs one T in the arena (placement new).
  template<typename T>
  T* Create() {
    void* p = Allocate(sizeof(T), alignof(T) > 4 ? alignof(T) : 4);
    return p ? new (p) T() : NULL;
  }

  size_t size() const { return size_; }
  size_t used() const { return used_; }
  bool failed() const { return failed_; }

 private:
  uint8_t* base_;
  size_t size_;
  size_t used_;
  bool failed_;
};

struct Memory {
  Arena* internal;
  Arena* external;
};

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_MEMORY_H_
