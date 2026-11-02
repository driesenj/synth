// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: small records in QSPI flash, wear-levelled (Plaitsy's
// RecordStore with slots up to 1 kB).

#include "app/storage.h"

#include <string.h>

#include "engine/crc32.h"
#include "hal.h"

namespace sidefx {

namespace {

uint32_t HeaderCrc(uint32_t sequence, uint32_t size, const void* payload) {
  uint32_t crc = Crc32(0, &sequence, sizeof(sequence));
  crc = Crc32(crc, &size, sizeof(size));
  return Crc32(crc, payload, size);
}

}  // namespace

void RecordStore::Init(uint32_t offset, uint32_t num_sectors,
                       uint32_t slot_size, uint32_t tag) {
  if (slot_size > kMaxSlotSize) {
    slot_size = kMaxSlotSize;
  }
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
  return HeaderCrc(header->sequence, header->size, payload) == header->crc;
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
  uint32_t best_sequence = 0;
  // The ring position follows the newest valid record of any size, so a
  // Load that finds nothing of this size does not send the next Save
  // back to slot 0 over newer records.
  bool any = false;
  uint32_t newest_slot = 0;
  uint32_t newest_sequence = 0;
  for (uint32_t slot = 0; slot < num_slots_; ++slot) {
    Header header;
    if (!ReadSlot(slot, &header, buffer)) {
      continue;
    }
    if (!any || header.sequence > newest_sequence) {
      any = true;
      newest_slot = slot;
      newest_sequence = header.sequence;
    }
    if (header.size == size && (!found || header.sequence > best_sequence)) {
      found = true;
      best_sequence = header.sequence;
      memcpy(payload, buffer, size);
    }
  }
  if (any) {
    next_slot_ = (newest_slot + 1) % num_slots_;
    sequence_ = newest_sequence + 1;
  } else {
    next_slot_ = 0;
    sequence_ = 1;
  }
  return found;
}

bool RecordStore::Save(const void* payload, uint32_t size) {
  if (num_slots_ == 0 || size > slot_size_ - sizeof(Header)) {
    return false;
  }
  uint32_t words[kMaxSlotSize / 4];
  uint8_t* buffer = reinterpret_cast<uint8_t*>(words);
  Header* header = reinterpret_cast<Header*>(words);
  header->tag = tag_;
  header->sequence = sequence_;
  header->size = size;
  memcpy(buffer + sizeof(Header), payload, size);
  header->crc = HeaderCrc(sequence_, size, payload);

  // A slot is written only once its sector has been erased on the way in.
  // A slot that is not blank anyway (an interrupted write, or a sector
  // whose erase was cut short) is skipped, so the previous save survives.
  for (uint32_t attempt = 0; attempt < num_slots_; ++attempt) {
    const uint32_t slot = next_slot_;
    next_slot_ = (next_slot_ + 1) % num_slots_;
    if (slot % slots_per_sector_ == 0) {
      if (!hal::FlashErase(slot_offset(slot), hal::kFlashSectorSize)) {
        return false;
      }
    } else if (!SlotBlank(slot)) {
      continue;
    }
    if (!hal::FlashWrite(slot_offset(slot), buffer, sizeof(Header) + size)) {
      return false;
    }
    // libDaisy's QSPIHandle::Write reports OK whatever its page programs
    // did: only a read-back shows the record is there. A slot that did
    // not take it is left for the next one.
    if (!SlotHolds(slot, buffer, sizeof(Header) + size)) {
      continue;
    }
    ++sequence_;
    return true;
  }
  return false;
}

bool RecordStore::SlotHolds(uint32_t slot, const uint8_t* data,
                            uint32_t size) {
  uint8_t chunk[256];
  for (uint32_t done = 0; done < size; done += sizeof(chunk)) {
    const uint32_t n = size - done < sizeof(chunk)
        ? size - done : uint32_t(sizeof(chunk));
    hal::FlashRead(slot_offset(slot) + done, chunk, n);
    if (memcmp(chunk, data + done, n) != 0) {
      return false;
    }
  }
  return true;
}

}  // namespace sidefx
