// Copyright 2026 the Marblesy authors. MIT licence, see marbles/firmware/LICENSE.
//
// Marblesy: small records in QSPI flash, wear-levelled.

#include "storage.h"

#include <string.h>

#include "hal.h"

namespace marblesy {

uint32_t Crc32(uint32_t crc, const void* data, size_t size) {
  const uint8_t* p = static_cast<const uint8_t*>(data);
  crc = ~crc;
  while (size--) {
    crc ^= *p++;
    for (int k = 0; k < 8; ++k) {
      crc = (crc >> 1) ^ (0xedb88320 & (0 - (crc & 1)));
    }
  }
  return ~crc;
}

void RecordStore::Init(
    uint32_t offset,
    uint32_t num_sectors,
    uint32_t slot_size,
    uint32_t tag) {
  offset_ = offset;
  slot_size_ = slot_size;
  slots_per_sector_ = hal::kFlashSectorSize / slot_size;
  num_slots_ = num_sectors * slots_per_sector_;
  tag_ = tag;
  next_slot_ = 0;
  sequence_ = 1;
}

bool RecordStore::ReadSlot(uint32_t slot, Header* header, uint8_t* payload) {
  hal::FlashRead(slot_offset(slot), header, sizeof(Header));
  if (header->tag != tag_ ||
      header->size > slot_size_ - sizeof(Header) ||
      header->sequence == 0xffffffff) {
    return false;
  }
  hal::FlashRead(slot_offset(slot) + sizeof(Header), payload, header->size);
  uint32_t crc = Crc32(0, &header->sequence, sizeof(header->sequence));
  crc = Crc32(crc, &header->size, sizeof(header->size));
  crc = Crc32(crc, payload, header->size);
  return crc == header->crc;
}

bool RecordStore::SlotBlank(uint32_t slot) {
  uint32_t words[kMaxSlotSize / 4];
  hal::FlashRead(slot_offset(slot), words, slot_size_);
  for (uint32_t i = 0; i < slot_size_ / 4; ++i) {
    if (words[i] != 0xffffffff) {
      return false;
    }
  }
  return true;
}

bool RecordStore::Load(void* payload, uint32_t size) {
  uint8_t buffer[kMaxSlotSize];
  bool found = false;
  uint32_t best_slot = 0;
  uint32_t best_sequence = 0;
  for (uint32_t slot = 0; slot < num_slots_; ++slot) {
    Header header;
    if (ReadSlot(slot, &header, buffer) &&
        header.size == size &&
        (!found || header.sequence > best_sequence)) {
      found = true;
      best_slot = slot;
      best_sequence = header.sequence;
      memcpy(payload, buffer, size);
    }
  }
  if (found) {
    next_slot_ = (best_slot + 1) % num_slots_;
    sequence_ = best_sequence + 1;
  } else {
    next_slot_ = 0;
    sequence_ = 1;
  }
  return found;
}

bool RecordStore::Save(const void* payload, uint32_t size) {
  if (size > slot_size_ - sizeof(Header)) {
    return false;
  }
  uint32_t words[kMaxSlotSize / 4];
  uint8_t* buffer = reinterpret_cast<uint8_t*>(words);
  Header* header = reinterpret_cast<Header*>(words);
  header->tag = tag_;
  header->size = size;
  memcpy(buffer + sizeof(Header), payload, size);

  // A slot is written only once its sector has been erased on the way in. A
  // slot that is not blank anyway (an interrupted write) is skipped. A write
  // that fails, or reads back wrong (libDaisy's QSPI Write() can report
  // success after a failed page), is tried once more in the next slot.
  // Every attempt takes a new sequence number, so a slot reported bad that
  // turns out valid can never tie with a later one.
  const int kMaxWrites = 2;
  int writes = 0;
  for (uint32_t attempt = 0; attempt < num_slots_ && writes < kMaxWrites;
       ++attempt) {
    const uint32_t slot = next_slot_;
    next_slot_ = (next_slot_ + 1) % num_slots_;
    if (slot % slots_per_sector_ == 0) {
      if (!hal::FlashErase(slot_offset(slot), hal::kFlashSectorSize)) {
        return false;
      }
    } else if (!SlotBlank(slot)) {
      continue;
    }
    header->sequence = sequence_++;
    uint32_t crc = Crc32(0, &header->sequence, sizeof(header->sequence));
    crc = Crc32(crc, &header->size, sizeof(header->size));
    header->crc = Crc32(crc, payload, size);
    ++writes;
    if (!hal::FlashWrite(slot_offset(slot), buffer, sizeof(Header) + size)) {
      continue;
    }
    Header check;
    uint32_t back[kMaxSlotSize / 4];
    uint8_t* back_payload = reinterpret_cast<uint8_t*>(back);
    if (ReadSlot(slot, &check, back_payload) &&
        check.sequence == header->sequence &&
        memcmp(back_payload, payload, size) == 0) {
      return true;
    }
  }
  return false;
}

}  // namespace marblesy
