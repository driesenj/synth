// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: frames to PNG files (see png_writer.h). The PNG is
// 8-bit RGB, filter 0 on every row, and its zlib stream is a run of stored
// (uncompressed) blocks of at most 65535 bytes.

#include "png_writer.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace test {

namespace {

const uint32_t kStoredBlock = 65535;

class Writer {
 public:
  explicit Writer(FILE* f) : file_(f), ok_(true) { }

  void Bytes(const void* data, size_t size) {
    if (size && fwrite(data, 1, size, file_) != size) {
      ok_ = false;
    }
  }
  void U32(uint32_t v) {
    const uint8_t b[4] = { uint8_t(v >> 24), uint8_t(v >> 16),
                           uint8_t(v >> 8), uint8_t(v) };
    Bytes(b, 4);
  }
  // A chunk: length, type, data, CRC of type and data.
  void Chunk(const char* type, const uint8_t* data, uint32_t size) {
    U32(size);
    Bytes(type, 4);
    Bytes(data, size);
    uint32_t crc = Crc32(reinterpret_cast<const uint8_t*>(type), 4);
    crc = Crc32(data, size, crc);
    U32(crc);
  }
  bool ok() const { return ok_; }

 private:
  FILE* file_;
  bool ok_;
};

}  // namespace

uint32_t Crc32(const uint8_t* data, uint32_t size, uint32_t crc) {
  static uint32_t table[256];
  static bool ready = false;
  if (!ready) {
    for (uint32_t n = 0; n < 256; ++n) {
      uint32_t c = n;
      for (int k = 0; k < 8; ++k) {
        c = (c & 1) ? 0xedb88320u ^ (c >> 1) : c >> 1;
      }
      table[n] = c;
    }
    ready = true;
  }
  crc = ~crc;
  for (uint32_t i = 0; i < size; ++i) {
    crc = table[(crc ^ data[i]) & 0xff] ^ (crc >> 8);
  }
  return ~crc;
}

uint32_t Adler32(const uint8_t* data, uint32_t size, uint32_t adler) {
  uint32_t a = adler & 0xffff;
  uint32_t b = adler >> 16;
  for (uint32_t i = 0; i < size; ++i) {
    a = (a + data[i]) % 65521u;
    b = (b + a) % 65521u;
  }
  return (b << 16) | a;
}

bool WritePng(const char* path, const uint16_t* pixels, int width, int height,
              int stride, int scale) {
  if (!pixels || width <= 0 || height <= 0 || scale <= 0) {
    return false;
  }
  const uint32_t s = uint32_t(scale);
  const uint32_t out_w = uint32_t(width) * s;
  const uint32_t out_h = uint32_t(height) * s;
  const uint32_t row_bytes = 1 + 3 * out_w;
  const uint32_t raw_size = row_bytes * out_h;
  uint8_t* raw = static_cast<uint8_t*>(malloc(raw_size));
  if (!raw) {
    return false;
  }
  for (uint32_t y = 0; y < out_h; ++y) {
    uint8_t* row = raw + y * row_bytes;
    row[0] = 0;  // filter: none
    const uint16_t* src = pixels + (y / s) * uint32_t(stride);
    for (uint32_t x = 0; x < out_w; ++x) {
      const uint16_t p = src[x / s];
      const uint16_t c = uint16_t((p >> 8) | (p << 8));
      const uint32_t r = (c >> 11) & 0x1f;
      const uint32_t g = (c >> 5) & 0x3f;
      const uint32_t b = c & 0x1f;
      row[1 + 3 * x] = uint8_t((r << 3) | (r >> 2));
      row[2 + 3 * x] = uint8_t((g << 2) | (g >> 4));
      row[3 + 3 * x] = uint8_t((b << 3) | (b >> 2));
    }
  }

  // zlib: header, stored blocks, Adler-32 of the raw data.
  const uint32_t blocks = (raw_size + kStoredBlock - 1) / kStoredBlock;
  const uint32_t z_size = 2 + raw_size + 5 * blocks + 4;
  uint8_t* z = static_cast<uint8_t*>(malloc(z_size));
  if (!z) {
    free(raw);
    return false;
  }
  uint32_t n = 0;
  z[n++] = 0x78;  // deflate, 32 K window
  z[n++] = 0x01;  // no dictionary, "fastest"; 0x7801 is a multiple of 31
  for (uint32_t done = 0; done < raw_size; ) {
    const uint32_t len = raw_size - done < kStoredBlock ? raw_size - done
                                                        : kStoredBlock;
    z[n++] = (done + len == raw_size) ? 1 : 0;  // BFINAL, BTYPE 00
    z[n++] = uint8_t(len);
    z[n++] = uint8_t(len >> 8);
    z[n++] = uint8_t(~len);
    z[n++] = uint8_t(~len >> 8);
    memcpy(z + n, raw + done, len);
    n += len;
    done += len;
  }
  const uint32_t adler = Adler32(raw, raw_size);
  z[n++] = uint8_t(adler >> 24);
  z[n++] = uint8_t(adler >> 16);
  z[n++] = uint8_t(adler >> 8);
  z[n++] = uint8_t(adler);
  free(raw);

  FILE* f = fopen(path, "wb");
  if (!f) {
    free(z);
    return false;
  }
  Writer w(f);
  static const uint8_t kSignature[8] = { 0x89, 'P', 'N', 'G', '\r', '\n',
                                         0x1a, '\n' };
  w.Bytes(kSignature, 8);
  const uint8_t ihdr[13] = {
    uint8_t(out_w >> 24), uint8_t(out_w >> 16), uint8_t(out_w >> 8),
    uint8_t(out_w),
    uint8_t(out_h >> 24), uint8_t(out_h >> 16), uint8_t(out_h >> 8),
    uint8_t(out_h),
    8,       // bits per channel
    2,       // RGB
    0, 0, 0  // deflate, adaptive filtering, no interlace
  };
  w.Chunk("IHDR", ihdr, 13);
  w.Chunk("IDAT", z, n);
  w.Chunk("IEND", 0, 0);
  free(z);
  const bool ok = w.ok();
  return fclose(f) == 0 && ok;
}

}  // namespace test
