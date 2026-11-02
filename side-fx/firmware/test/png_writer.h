// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: frames to PNG files, so a test can leave a picture of
// the screen to look at. Uncompressed (zlib stored blocks) and without a
// library: the files are a few MB at most and only for people to view.

#ifndef SIDEFX_TEST_PNG_WRITER_H_
#define SIDEFX_TEST_PNG_WRITER_H_

#include <stdint.h>

namespace test {

// Writes a width x height image of byte-swapped RGB565 pixels (as in the
// frame buffer, see gfx/canvas.h), `stride` pixels from one row to the
// next, each pixel blown up to scale x scale. False when the file could not
// be written.
bool WritePng(const char* path, const uint16_t* pixels, int width, int height,
              int stride, int scale);

// The CRC-32 (PNG chunks) and Adler-32 (zlib) checksums, for the tests.
uint32_t Crc32(const uint8_t* data, uint32_t size, uint32_t crc = 0);
uint32_t Adler32(const uint8_t* data, uint32_t size, uint32_t adler = 1);

}  // namespace test

#endif  // SIDEFX_TEST_PNG_WRITER_H_
