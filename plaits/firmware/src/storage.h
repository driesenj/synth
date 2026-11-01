// Copyright 2026 the Plaitsy authors. MIT licence, see plaits/firmware/LICENSE.
//
// Plaitsy: small records in QSPI flash, wear-levelled.
//
// Plaits keeps its settings in the F373's internal flash with stmlib's
// ChunkStorage. Here a region of whole 4 kB sectors holds a ring of slots;
// each save goes to the next slot, and a sector is erased only when the ring
// enters it again, so a 64 kB region takes 256 saves per erase. A load picks
// the valid slot with the highest sequence number, so an interrupted write
// or erase falls back to the previous save.

#ifndef PLAITSY_STORAGE_H_
#define PLAITSY_STORAGE_H_

#include <stddef.h>
#include <stdint.h>

namespace plaitsy {

class RecordStore {
 public:
  RecordStore() { }
  ~RecordStore() { }

  // Region [offset, offset + num_sectors * 4 kB), slots of slot_size bytes
  // (a power of two dividing 4 kB, at most 256: one flash page).
  void Init(uint32_t offset, uint32_t num_sectors, uint32_t slot_size,
            uint32_t tag);

  // Copies the newest valid record of exactly `size` bytes into `payload`.
  bool Load(void* payload, uint32_t size);
  bool Save(const void* payload, uint32_t size);

 private:
  struct Header {
    uint32_t tag;
    uint32_t sequence;
    uint32_t size;
    uint32_t crc;
  };

  static const uint32_t kMaxSlotSize = 256;

  uint32_t slot_offset(uint32_t slot) const {
    return offset_ + slot * slot_size_;
  }
  bool ReadSlot(uint32_t slot, Header* header, uint8_t* payload);
  bool SlotBlank(uint32_t slot);

  uint32_t offset_;
  uint32_t num_slots_;
  uint32_t slots_per_sector_;
  uint32_t slot_size_;
  uint32_t tag_;
  uint32_t next_slot_;
  uint32_t sequence_;
};

uint32_t Crc32(uint32_t crc, const void* data, size_t size);

}  // namespace plaitsy

#endif  // PLAITSY_STORAGE_H_
