// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: small records in QSPI flash, wear-levelled. Plaitsy's
// RecordStore (plaits/firmware/src/storage.h), with slots up to 1 kB.
//
// A region of whole 4 kB sectors holds a ring of slots; each save goes to
// the next slot, and a sector is erased only when the ring enters it again,
// so a 64 kB region of 1 kB slots takes 64 saves per erase of each sector. A load
// picks the valid slot with the highest sequence number, so an interrupted
// write or erase falls back to the previous save. A save reads its slot
// back, and moves on to the next slot when the flash did not take it.

#ifndef SIDEFX_APP_STORAGE_H_
#define SIDEFX_APP_STORAGE_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {

class RecordStore {
 public:
  RecordStore() { }
  ~RecordStore() { }

  // Region [offset, offset + num_sectors * 4 kB), slots of slot_size bytes
  // (a power of two dividing 4 kB, at most 1 kB).
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

  static const uint32_t kMaxSlotSize = 1024;

  uint32_t slot_offset(uint32_t slot) const {
    return offset_ + slot * slot_size_;
  }
  bool ReadSlot(uint32_t slot, Header* header, uint8_t* payload);
  bool SlotBlank(uint32_t slot);
  // The slot reads back as `data`.
  bool SlotHolds(uint32_t slot, const uint8_t* data, uint32_t size);

  uint32_t offset_;
  uint32_t num_slots_;
  uint32_t slots_per_sector_;
  uint32_t slot_size_;
  uint32_t tag_;
  uint32_t next_slot_;
  uint32_t sequence_;
};

}  // namespace sidefx

#endif  // SIDEFX_APP_STORAGE_H_
