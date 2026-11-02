// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: drawing into the screen's frame buffer.
//
// The frame is 170 x 320 RGB565 pixels, row by row, each pixel stored high
// byte first (as the ST7789 takes them over SPI), so a Color is the
// byte-swapped 565 value: build them with Rgb(). Every drawing call clips
// to the frame (and to the clip rectangle) and marks the rows it touched
// dirty; the main loop sends the dirty rows (TakeDirty) when the display is
// free, one band of them at a time, so two small changes far apart do not
// send everything between them. Text is anti-aliased: glyphs carry 4-bit coverage and blend over
// whatever is already in the frame.

#ifndef SIDEFX_GFX_CANVAS_H_
#define SIDEFX_GFX_CANVAS_H_

#include <stddef.h>
#include <stdint.h>

#include "gfx/font.h"

namespace sidefx {

typedef uint16_t Color;

inline Color Rgb(uint8_t r, uint8_t g, uint8_t b) {
  const uint16_t c = uint16_t(((r & 0xf8) << 8) | ((g & 0xfc) << 3) | (b >> 3));
  return uint16_t((c >> 8) | (c << 8));
}

// a + (b - a) * alpha / 255, per channel, on byte-swapped colours.
Color BlendColor(Color a, Color b, uint8_t alpha);

class Canvas {
 public:
  static const int kWidth = 170;
  static const int kHeight = 320;

  Canvas() { }
  ~Canvas() { }

  void Init(uint16_t* pixels);  // kWidth * kHeight

  void Clear(Color color);
  void SetPixel(int x, int y, Color color);
  Color GetPixel(int x, int y) const;
  void BlendPixel(int x, int y, Color color, uint8_t alpha);

  void FillRect(int x, int y, int w, int h, Color color);
  void DrawRect(int x, int y, int w, int h, Color color);
  void FillRoundRect(int x, int y, int w, int h, int radius, Color color);
  void DrawRoundRect(int x, int y, int w, int h, int radius, Color color);
  void DrawHLine(int x, int y, int w, Color color);
  void DrawVLine(int x, int y, int h, Color color);
  void DrawLine(int x0, int y0, int x1, int y1, Color color);  // anti-aliased
  void FillCircle(int cx, int cy, int radius, Color color);
  void DrawCircle(int cx, int cy, int radius, Color color);
  // An arc of `thickness` pixels from angle a0 to a1 (radians, 0 = up,
  // clockwise), anti-aliased: a knob ring.
  void DrawArc(int cx, int cy, int radius, int thickness, float a0, float a1,
               Color color);

  // Text with its line box's top-left at (x, y); returns the x after it.
  int DrawText(int x, int y, const char* text, const Font& font,
               Color color);
  int DrawTextRight(int right, int y, const char* text, const Font& font,
                    Color color);
  int DrawTextCentered(int center, int y, const char* text, const Font& font,
                       Color color);
  int TextWidth(const char* text, const Font& font) const;

  void SetClip(int x, int y, int w, int h);
  void ResetClip();

  void MarkDirty(int y0, int y1);
  // The first band of changed rows, which is then clean again; false when
  // none is left. Bands closer than kDirtyMergeRows go out as one (a flush
  // costs a few commands and a pass of the main loop). Call it again for
  // the next band.
  bool TakeDirty(int* y0, int* y1);

  static const int kDirtyMergeRows = 6;

  const uint16_t* pixels() const { return pixels_; }
  uint16_t* mutable_pixels() { return pixels_; }

 private:
  uint16_t* pixels_;
  int clip_x0_;
  int clip_y0_;
  int clip_x1_;  // exclusive
  int clip_y1_;
  static const int kDirtyWords = (kHeight + 31) / 32;
  uint32_t dirty_[kDirtyWords];  // bit y % 32 of word y / 32: row y
};

}  // namespace sidefx

#endif  // SIDEFX_GFX_CANVAS_H_
