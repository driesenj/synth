// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: CRC-32 (IEEE 802.3, reflected, as zlib's crc32()). Bitwise:
// it only runs on presets and settings records, never per sample.

#ifndef SIDEFX_ENGINE_CRC32_H_
#define SIDEFX_ENGINE_CRC32_H_

#include <stddef.h>
#include <stdint.h>

namespace sidefx {

// Start with crc = 0; feed the result back in to continue over more data.
inline uint32_t Crc32(uint32_t crc, const void* data, size_t size) {
  const uint8_t* p = static_cast<const uint8_t*>(data);
  crc = ~crc;
  while (size--) {
    crc ^= *p++;
    for (int k = 0; k < 8; ++k) {
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
  }
  return ~crc;
}

}  // namespace sidefx

#endif  // SIDEFX_ENGINE_CRC32_H_
