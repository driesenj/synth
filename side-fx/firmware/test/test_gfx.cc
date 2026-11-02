// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy host tests: the canvas, the fonts, the fake display and the PNG
// writer. The last test draws a specimen sheet of every font and shape into
// test/build/gfx_specimen.png, to look at.

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "check.h"
#include "display_fake.h"
#include "gfx/canvas.h"
#include "gfx/font.h"
#include "png_writer.h"

using sidefx::BlendColor;
using sidefx::Canvas;
using sidefx::Color;
using sidefx::Font;
using sidefx::Glyph;
using sidefx::Rgb;

namespace {

const int kPixels = Canvas::kWidth * Canvas::kHeight;

// A frame of exactly the screen's size from the heap, so that AddressSanitizer
// sees any write past it.
class Frame {
 public:
  Frame() {
    pixels_ = static_cast<uint16_t*>(malloc(kPixels * sizeof(uint16_t)));
    canvas_.Init(pixels_);
    canvas_.Clear(0);
    int y0, y1;
    canvas_.TakeDirty(&y0, &y1);
  }
  ~Frame() { free(pixels_); }
  Canvas& canvas() { return canvas_; }
  const uint16_t* pixels() const { return pixels_; }

 private:
  uint16_t* pixels_;
  Canvas canvas_;
};

int Red(Color c) { return (uint16_t((c >> 8) | (c << 8)) >> 11) & 0x1f; }
int Green(Color c) { return (uint16_t((c >> 8) | (c << 8)) >> 5) & 0x3f; }
int Blue(Color c) { return uint16_t((c >> 8) | (c << 8)) & 0x1f; }

// The coverage of a white-on-black pixel, 0..1, from its green channel.
float Coverage(const Canvas& c, int x, int y) {
  return float(Green(c.GetPixel(x, y))) / 63.0f;
}

int CountLit(const Canvas& c) {
  int n = 0;
  for (int i = 0; i < kPixels; ++i) {
    n += c.pixels()[i] != 0;
  }
  return n;
}

const Font* const kFonts[] = { &sidefx::kFontSmall, &sidefx::kFontMedium,
                               &sidefx::kFontLarge, &sidefx::kFontHuge };
const char* const kFontNames[] = { "small", "medium", "large", "huge" };

}  // namespace

TEST(gfx, colours) {
  CHECK(Rgb(255, 0, 0) == 0x00f8);
  CHECK(Rgb(0, 255, 0) == 0xe007);
  CHECK(Rgb(0, 0, 255) == 0x1f00);
  CHECK(Rgb(255, 255, 255) == 0xffff);
  const Color red = Rgb(255, 0, 0);
  const Color blue = Rgb(0, 0, 255);
  CHECK(BlendColor(red, blue, 0) == red);
  CHECK(BlendColor(red, blue, 255) == blue);
  const Color mid = BlendColor(red, blue, 128);
  CHECK(Red(mid) == 15 || Red(mid) == 16);
  CHECK(Blue(mid) == 15 || Blue(mid) == 16);
  CHECK(Green(mid) == 0);
  // Blending a colour with itself leaves it.
  const Color grey = Rgb(120, 130, 140);
  for (int a = 0; a < 256; a += 17) {
    CHECK(BlendColor(grey, grey, uint8_t(a)) == grey);
  }
  // Monotonic in alpha.
  int last = -1;
  for (int a = 0; a < 256; ++a) {
    const int g = Green(BlendColor(0, Rgb(255, 255, 255), uint8_t(a)));
    CHECK(g >= last);
    last = g;
  }
}

TEST(gfx, dirty_rows) {
  Frame f;
  Canvas& c = f.canvas();
  int y0 = -1, y1 = -1;
  CHECK(!c.TakeDirty(&y0, &y1));
  c.FillRect(10, 20, 5, 5, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 20 && y1 == 24);
  CHECK(!c.TakeDirty(&y0, &y1));
  // Several draws far apart: one band each, top first; nothing between
  // them goes out.
  c.SetPixel(3, 100, 0xffff);
  c.DrawHLine(0, 40, 10, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 40 && y1 == 40);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 100 && y1 == 100);
  CHECK(!c.TakeDirty(&y0, &y1));
  // Bands closer than kDirtyMergeRows go as one; the next one further on
  // stays apart.
  const int merge = Canvas::kDirtyMergeRows;
  c.FillRect(0, 30, 10, 2, 0xffff);                 // 30..31
  c.FillRect(0, 32 + merge - 1, 10, 3, 0xffff);     // a gap of merge - 1
  c.FillRect(0, 34 + 2 * merge, 10, 1, 0xffff);     // a gap of merge
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 30 && y1 == 33 + merge);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 34 + 2 * merge && y1 == y0);
  CHECK(!c.TakeDirty(&y0, &y1));
  // Every row, across the bitmap's word boundaries.
  for (int y = 0; y < Canvas::kHeight; y += 2) {
    c.MarkDirty(y, y);
  }
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 0 && y1 == Canvas::kHeight - 2);
  CHECK(!c.TakeDirty(&y0, &y1));
  c.MarkDirty(31, 32);
  c.MarkDirty(63, 64);
  CHECK(c.TakeDirty(&y0, &y1) && y0 == 31 && y1 == 32);
  CHECK(c.TakeDirty(&y0, &y1) && y0 == 63 && y1 == 64);
  CHECK(!c.TakeDirty(&y0, &y1));
  // Nothing visible drawn, nothing dirty.
  c.FillRect(-20, 10, 10, 10, 0xffff);
  c.FillRect(10, 400, 10, 10, 0xffff);
  c.DrawText(200, 10, "X", sidefx::kFontMedium, 0xffff);
  c.BlendPixel(5, 5, 0xffff, 0);
  CHECK(!c.TakeDirty(&y0, &y1));
  // Text marks the rows its ink is on, inside its line box.
  c.DrawText(0, 50, "Ag", sidefx::kFontMedium, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 >= 50 && y1 < 50 + sidefx::kFontMedium.line_height && y1 > y0);
  // Clipped draws mark only the clipped rows; MarkDirty clamps.
  c.FillRect(0, 300, 10, 100, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 300 && y1 == Canvas::kHeight - 1);
  c.MarkDirty(-50, 5000);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 0 && y1 == Canvas::kHeight - 1);
  c.MarkDirty(9, 3);
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(y0 == 3 && y1 == 9);
  // Every primitive marks.
  c.DrawLine(5, 60, 100, 70, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 >= 60 && y1 <= 71);
  c.DrawArc(80, 150, 20, 3, 0.0f, 1.0f, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 >= 129 && y1 <= 171);
  c.FillCircle(80, 200, 10, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 == 190 && y1 == 210);
  c.DrawRoundRect(10, 220, 50, 20, 6, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 == 220 && y1 == 239);
  c.FillRoundRect(10, 250, 50, 20, 6, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 == 250 && y1 == 269);
  c.DrawCircle(80, 290, 8, 0xffff);
  CHECK(c.TakeDirty(&y0, &y1) && y0 >= 281 && y1 <= 299);
}

TEST(gfx, clipping) {
  Frame f;
  Canvas& c = f.canvas();
  const Color w = 0xffff;
  // Shapes far off every edge: nothing lands, nothing is written out of the
  // frame (ASan would see it).
  c.FillRect(-1000, -1000, 3000, 3000, w);
  CHECK(CountLit(c) == kPixels);
  c.Clear(0);
  c.DrawLine(-500, -300, 700, 900, w);
  c.DrawLine(-10, 5, 400, 5, w);
  c.DrawLine(5, -10, 5, 400, w);
  c.DrawArc(0, 0, 40, 10, -3.0f, 3.0f, w);
  c.DrawArc(169, 319, 40, 10, 0.0f, 7.0f, w);
  c.FillCircle(-5, 160, 30, w);
  c.FillCircle(175, 160, 30, w);
  c.FillRoundRect(-20, 300, 250, 50, 10, w);
  c.DrawRoundRect(-20, -20, 250, 50, 10, w);
  c.DrawText(150, 310, "WWWWW", sidefx::kFontHuge, w);
  c.DrawText(-30, -10, "WWWWW", sidefx::kFontHuge, w);
  c.DrawTextRight(10, 100, "ggg", sidefx::kFontLarge, w);
  CHECK(CountLit(c) > 0);

  // A clip rectangle: nothing outside it changes.
  c.Clear(0);
  c.SetClip(20, 30, 40, 50);
  c.Clear(w);
  c.DrawLine(0, 0, 169, 319, Rgb(255, 0, 0));
  c.FillCircle(20, 30, 25, Rgb(0, 255, 0));
  c.DrawText(10, 60, "Hello", sidefx::kFontLarge, Rgb(0, 0, 255));
  c.DrawArc(40, 55, 30, 4, 0.0f, 6.0f, Rgb(255, 0, 255));
  c.SetPixel(5, 5, w);
  c.BlendPixel(100, 100, w, 255);
  int outside = 0, inside = 0;
  for (int y = 0; y < Canvas::kHeight; ++y) {
    for (int x = 0; x < Canvas::kWidth; ++x) {
      const bool in = x >= 20 && x < 60 && y >= 30 && y < 80;
      if (in) {
        inside += c.GetPixel(x, y) != 0;
      } else {
        outside += c.GetPixel(x, y) != 0;
      }
    }
  }
  CHECK(outside == 0);
  CHECK(inside == 40 * 50);
  // A clip partly off the frame is cut to it; an empty one draws nothing.
  c.SetClip(-10, -10, 15, 15);
  c.Clear(0x1234);
  CHECK(c.GetPixel(4, 4) == 0x1234 && c.GetPixel(5, 5) != 0x1234);
  c.SetClip(50, 50, -5, 10);
  c.FillRect(0, 0, 170, 320, 0x4321);
  int y0, y1;
  c.TakeDirty(&y0, &y1);
  c.FillRect(0, 0, 170, 320, 0x4321);
  CHECK(!c.TakeDirty(&y0, &y1));
  c.ResetClip();
  c.Clear(0);
  CHECK(CountLit(c) == 0);
  CHECK(c.GetPixel(-1, 0) == 0 && c.GetPixel(0, 320) == 0);
}

TEST(gfx, fills) {
  Frame f;
  Canvas& c = f.canvas();
  // Every alignment and width of a run: exactly the pixels asked for.
  for (int x = 0; x < 6; ++x) {
    for (int w = 0; w < 12; ++w) {
      c.Clear(0);
      c.FillRect(x, 7, w, 1, 0xabcd);
      int n = 0;
      for (int i = 0; i < kPixels; ++i) {
        n += c.pixels()[i] != 0;
      }
      CHECK(n == w);
      CHECK(w == 0 || (c.GetPixel(x, 7) == 0xabcd &&
                       c.GetPixel(x + w - 1, 7) == 0xabcd));
      CHECK(c.GetPixel(x + w, 7) == 0);
    }
  }
  c.Clear(0);
  c.DrawRect(10, 10, 20, 10, 0xffff);
  CHECK(CountLit(c) == 2 * 20 + 2 * 8);
  CHECK(c.GetPixel(15, 15) == 0 && c.GetPixel(10, 10) == 0xffff &&
        c.GetPixel(29, 19) == 0xffff);
  // Filled round rect: solid inside, corners cut, area about right.
  c.Clear(0);
  c.FillRoundRect(10, 10, 60, 40, 8, 0xffff);
  CHECK(c.GetPixel(40, 30) == 0xffff);
  CHECK(c.GetPixel(10, 10) == 0 && c.GetPixel(69, 49) == 0);
  CHECK(c.GetPixel(10, 30) == 0xffff && c.GetPixel(40, 10) == 0xffff);
  float area = 0.0f;
  for (int y = 0; y < 60; ++y) {
    for (int x = 0; x < 80; ++x) {
      area += Coverage(c, x, y);
    }
  }
  const float expected = 60.0f * 40.0f - (4.0f - float(M_PI)) * 8.5f * 8.5f;
  CHECK(fabsf(area - expected) < 0.01f * expected);
  test::Note("round rect area %.1f, expected %.1f", area, expected);
}

TEST(gfx, circles_and_arcs) {
  Frame f;
  Canvas& c = f.canvas();
  const Color w = 0xffff;
  // A filled disc's coverage adds up to pi r^2 (its edge is r + 1/2 from
  // the centre pixel's centre, so (r + 1/2)^2).
  for (int r = 3; r < 40; r += 6) {
    c.Clear(0);
    c.FillCircle(85, 160, r, w);
    float area = 0.0f;
    for (int i = 0; i < kPixels; ++i) {
      area += float(Green(c.pixels()[i])) / 63.0f;
    }
    const float expected = float(M_PI) * (r + 0.5f) * (r + 0.5f);
    CHECK(fabsf(area - expected) < 0.03f * expected);
    CHECK(c.GetPixel(85 + r, 160) != 0 && c.GetPixel(85 + r + 1, 160) == 0);
  }
  // A full ring is symmetric and has area 2 pi r t.
  c.Clear(0);
  c.DrawArc(85, 160, 30, 4, 0.0f, 7.0f, w);
  CHECK(c.GetPixel(85, 130) == c.GetPixel(85, 190));
  CHECK(c.GetPixel(55, 160) == c.GetPixel(115, 160));
  CHECK(c.GetPixel(85, 130) == c.GetPixel(115, 160));
  CHECK(c.GetPixel(85, 160) == 0 && c.GetPixel(85, 140) == 0);
  float area = 0.0f;
  for (int i = 0; i < kPixels; ++i) {
    area += float(Green(c.pixels()[i])) / 63.0f;
  }
  const float ring = float(M_PI) * (30.5f * 30.5f - 26.5f * 26.5f);
  CHECK(fabsf(area - ring) < 0.03f * ring);
  // The right half (0 = up, clockwise): lit right of the centre, dark left.
  c.Clear(0);
  c.DrawArc(85, 160, 30, 4, 0.0f, float(M_PI), w);
  CHECK(c.GetPixel(114, 160) == w);
  CHECK(c.GetPixel(56, 160) == 0);
  CHECK(c.GetPixel(86 + 20, 160 - 20) != 0);   // up right
  CHECK(c.GetPixel(84 - 20, 160 - 20) == 0);   // up left
  CHECK(c.GetPixel(86 + 20, 160 + 20) != 0);   // down right
  // The ends are half covered on the cut: the top pixel of the ring.
  CHECK(Coverage(c, 85, 131) > 0.3f && Coverage(c, 85, 131) < 0.7f);
  // A knob arc from -135 to +45 degrees: the order of the angles does not
  // matter, and the arc passes through the top.
  c.Clear(0);
  c.DrawArc(85, 160, 30, 4, 0.785f, -2.356f, w);
  CHECK(c.GetPixel(85, 131) == w);
  CHECK(c.GetPixel(114, 160) == 0);
  CHECK(c.GetPixel(85, 189) == 0);
  // A thin circle: one pixel ring, cardinal points fully lit.
  c.Clear(0);
  c.DrawCircle(85, 160, 10, w);
  CHECK(c.GetPixel(85, 150) == w && c.GetPixel(95, 160) == w &&
        c.GetPixel(75, 160) == w && c.GetPixel(85, 170) == w);
  CHECK(c.GetPixel(85, 160) == 0);
}

TEST(gfx, lines) {
  Frame f;
  Canvas& c = f.canvas();
  const Color w = 0xffff;
  c.DrawLine(10, 10, 60, 10, w);
  CHECK(CountLit(c) == 51);
  c.Clear(0);
  c.DrawLine(60, 20, 60, 10, w);
  CHECK(CountLit(c) == 11);
  // A diagonal: each column's coverage sums to one, the end points are lit.
  c.Clear(0);
  c.DrawLine(10, 10, 110, 47, w);
  CHECK(c.GetPixel(10, 10) == w && c.GetPixel(110, 47) == w);
  for (int x = 10; x <= 110; x += 7) {
    float sum = 0.0f;
    for (int y = 0; y < 60; ++y) {
      sum += Coverage(c, x, y);
    }
    CHECK(fabsf(sum - 1.0f) < 0.05f);
  }
  // Steep and backwards.
  c.Clear(0);
  c.DrawLine(50, 200, 30, 100, w);
  CHECK(c.GetPixel(50, 200) == w && c.GetPixel(30, 100) == w);
  for (int y = 100; y <= 200; y += 9) {
    float sum = 0.0f;
    for (int x = 0; x < 70; ++x) {
      sum += Coverage(c, x, y);
    }
    CHECK(fabsf(sum - 1.0f) < 0.05f);
  }
}

TEST(gfx, fonts) {
  for (int i = 0; i < 4; ++i) {
    const Font& font = *kFonts[i];
    CHECK(font.first <= 0x01 && font.last >= 0x7e);
    CHECK(font.ascent < font.line_height);
    int max_advance = 0;
    for (int code = 0x20; code <= 0x7e; ++code) {
      const Glyph& g = font.glyphs[code - font.first];
      // The ink stays in the line box, horizontally near the pen.
      CHECK(g.y_offset >= 0);
      CHECK(g.y_offset + g.height <= font.line_height);
      CHECK(g.x_offset > -4 && g.x_offset + g.width <= g.advance + 4);
      max_advance = g.advance > max_advance ? g.advance : max_advance;
    }
    for (int code = 0x01; code <= 0x05; ++code) {
      const Glyph& g = font.glyphs[code - font.first];
      CHECK(g.width > 0 && g.height > 0 && g.advance > g.width);
      CHECK(g.y_offset >= 0 && g.y_offset + g.height <= font.line_height);
    }
    // Digits share one width, so changing values do not jitter.
    const int digit = font.glyphs['0' - font.first].advance;
    for (int code = '1'; code <= '9'; ++code) {
      CHECK(font.glyphs[code - font.first].advance == digit);
    }
    test::Note("%s: line height %d, ascent %d, digit %d, space %d, max %d",
               kFontNames[i], font.line_height, font.ascent, digit,
               font.glyphs[' ' - font.first].advance, max_advance);
  }
  // Sizes grow.
  CHECK(sidefx::kFontSmall.line_height < sidefx::kFontMedium.line_height);
  CHECK(sidefx::kFontMedium.line_height < sidefx::kFontLarge.line_height);
  CHECK(sidefx::kFontLarge.line_height < sidefx::kFontHuge.line_height);
}

TEST(gfx, text) {
  Frame f;
  Canvas& c = f.canvas();
  const Font& m = sidefx::kFontMedium;
  CHECK(c.TextWidth("", m) == 0);
  const int a = m.glyphs['A' - m.first].advance;
  const int b = m.glyphs['B' - m.first].advance;
  CHECK(c.TextWidth("AB", m) == a + b);
  CHECK(c.DrawText(10, 10, "AB", m, 0xffff) == 10 + a + b);
  CHECK(c.DrawTextRight(150, 40, "AB", m, 0xffff) == 150);
  CHECK(c.DrawTextCentered(85, 70, "AB", m, 0xffff) ==
        85 - (a + b) / 2 + a + b);
  // A character outside the font draws as '?'.
  CHECK(c.TextWidth("\x7f", m) == c.TextWidth("?", m));
  CHECK(c.TextWidth("\xe9", m) == c.TextWidth("?", m));

  // Anti-aliased: white on black gives greys between black and white.
  c.Clear(0);
  c.DrawText(10, 100, "Sync 1/8 \x01", m, 0xffff);
  int full = 0, partial = 0;
  for (int i = 0; i < kPixels; ++i) {
    const Color p = c.pixels()[i];
    if (p == 0xffff) {
      ++full;
    } else if (p) {
      ++partial;
      CHECK(Red(p) * 2 >= Green(p) - 2 && Red(p) * 2 <= Green(p) + 2);
    }
  }
  CHECK(full > 20 && partial > 20);
  // Over a red background the edges are blends of red and white: red stays
  // full, green and blue rise together.
  const Color red = Rgb(255, 0, 0);
  c.Clear(red);
  c.DrawText(10, 100, "Sync", m, 0xffff);
  int blended = 0;
  for (int i = 0; i < kPixels; ++i) {
    const Color p = c.pixels()[i];
    if (p != red && p != 0xffff) {
      ++blended;
      CHECK(Red(p) == 31);
      CHECK(Green(p) > 0 && Blue(p) > 0);
    }
  }
  CHECK(blended > 20);
  // Every byte of every glyph is read in range (ASan on the bitmaps).
  char all[0x80];
  int n = 0;
  for (int code = 1; code < 0x7f; ++code) {
    all[n++] = char(code);
  }
  all[n] = 0;
  for (int i = 0; i < 4; ++i) {
    c.Clear(0);
    for (int start = 0; start < n; start += 6) {
      char chunk[7];
      memcpy(chunk, all + start, 6);
      chunk[6] = 0;
      c.DrawText(0, 0, chunk, *kFonts[i], 0xffff);
    }
  }
}

TEST(gfx, display_fake) {
  test::ResetDisplay();
  Frame f;
  Canvas& c = f.canvas();
  c.FillRect(0, 10, 170, 5, Rgb(0, 255, 0));
  int y0, y1;
  CHECK(c.TakeDirty(&y0, &y1));
  CHECK(!sidefx::hal::DisplayBusy());
  sidefx::hal::DisplayFlush(c.pixels(), y0, y1);
  const test::DisplayState& d = test::Display();
  CHECK(d.flushes == 1 && d.rows_sent == 5);
  CHECK(d.last_y0 == 10 && d.last_y1 == 14 && d.last_frame == c.pixels());
  CHECK(d.panel[12 * 170 + 3] == Rgb(0, 255, 0));
  CHECK(d.panel[9 * 170 + 3] == 0);
  CHECK(!sidefx::hal::DisplayBusy());
  sidefx::hal::SetBacklight(1.5f);
  CHECK(d.backlight == 1.0f);
  sidefx::hal::SetBacklight(0.25f);
  CHECK(d.backlight == 0.25f);
  // A flip sends the last frame again, whole, turned by 180 degrees.
  sidefx::hal::SetDisplayFlip(true);
  CHECK(d.flip);
  CHECK(d.flushes == 2 && d.last_y0 == 0 && d.last_y1 == 319);
  CHECK(d.panel[(319 - 12) * 170 + (169 - 3)] == Rgb(0, 255, 0));
  CHECK(d.panel[12 * 170 + 3] == 0);
  sidefx::hal::SetDisplayFlip(true);
  CHECK(d.flushes == 2);  // no change, nothing sent
  test::ResetDisplay();
  CHECK(d.flushes == 0 && d.last_y0 == -1 && !d.flip);
}

TEST(gfx, png_checksums) {
  const uint8_t text[] = "123456789";
  CHECK(test::Crc32(text, 9) == 0xcbf43926u);
  CHECK(test::Adler32(text, 9) == 0x091e01deu);
  // Chunks: crc of "IEND".
  CHECK(test::Crc32(reinterpret_cast<const uint8_t*>("IEND"), 4) ==
        0xae426082u);
}

// --- the specimen sheet ---------------------------------------------------------

namespace {

const Color kBlack = 0;
const Color kWhite = 0xffff;

Color Accent(int slot) {
  // Pitch, delay, texture, reverb.
  static const uint8_t kRgb[4][3] = {
    { 255, 170, 40 }, { 60, 200, 255 }, { 190, 110, 255 }, { 80, 230, 140 } };
  return Rgb(kRgb[slot][0], kRgb[slot][1], kRgb[slot][2]);
}

// Pages 1 and 2: every font, every character.
void DrawFonts(Canvas& c, int first_font, int fonts) {
  c.Clear(kBlack);
  int y = 2;
  for (int i = first_font; i < first_font + fonts; ++i) {
    const Font& font = *kFonts[i];
    // The line box, faint, behind the first line, and the baseline.
    c.FillRect(0, y, 170, font.line_height, Rgb(30, 30, 50));
    c.DrawHLine(0, y + font.ascent, 170, Rgb(70, 40, 40));
    char line[40];
    int n = 0;
    int code = 0x20;
    while (code <= 0x7e) {
      // Fill lines up to the width.
      n = 0;
      int width = 0;
      while (code <= 0x7e) {
        const int adv = font.glyphs[code - font.first].advance;
        if (width + adv > 168 || n == 38) {
          break;
        }
        line[n++] = char(code);
        width += adv;
        ++code;
      }
      line[n] = 0;
      c.DrawText(1, y, line, font, kWhite);
      y += font.line_height;
    }
    const char symbols[] = "\x01 \x02 \x03 \x04 \x05 120\x05 \x02Play";
    c.DrawText(1, y, symbols, font, Accent(i));
    y += font.line_height + 3;
  }
}

// Page 2: shapes.
void DrawShapes(Canvas& c) {
  c.Clear(Rgb(8, 8, 12));
  // Knob rings: a dark track and a value arc from -135 degrees.
  const float kStart = -2.356f;
  for (int i = 0; i < 4; ++i) {
    const int cx = 22 + i * 42;
    const int cy = 26;
    c.DrawArc(cx, cy, 17, 4, kStart, -kStart, Rgb(45, 45, 55));
    c.DrawArc(cx, cy, 17, 4, kStart, kStart + (i + 1) * 1.178f, Accent(i));
    char v[4] = { char('1' + i), '0', 0, 0 };
    c.DrawTextCentered(cx, cy - sidefx::kFontSmall.ascent / 2 - 1, v,
                       sidefx::kFontSmall, kWhite);
  }
  // Thin and thick arcs, a bipolar one from the top.
  c.DrawArc(30, 80, 22, 1, 0.0f, 6.3f, kWhite);
  c.DrawArc(30, 80, 16, 2, -1.2f, 1.9f, Accent(1));
  c.DrawArc(85, 80, 22, 6, 0.0f, 1.3f, Accent(0));
  c.DrawArc(85, 80, 22, 6, -0.6f, 0.0f, Accent(2));
  c.DrawLine(85, 80, 85, 56, Rgb(90, 90, 90));
  c.DrawArc(140, 80, 22, 22, 0.5f, 2.5f, Accent(3));  // a pie
  // Circles.
  for (int r = 0; r <= 6; ++r) {
    c.FillCircle(10 + r * 24 - (r * r) / 2 + r, 125, r + 1, kWhite);
  }
  c.DrawCircle(30, 160, 14, Accent(1));
  c.FillCircle(30, 160, 8, Accent(0));
  c.DrawCircle(70, 160, 4, kWhite);
  c.DrawCircle(90, 160, 9, kWhite);
  c.FillCircle(135, 160, 18, Accent(2));
  c.FillCircle(145, 168, 10, BlendColor(Accent(2), kWhite, 160));
  // Round rects.
  c.FillRoundRect(4, 185, 76, 24, 6, Accent(1));
  c.DrawText(10, 190, "DELAY", sidefx::kFontMedium, kBlack);
  c.DrawRoundRect(88, 185, 78, 24, 6, Accent(3));
  c.DrawText(94, 190, "REVERB", sidefx::kFontMedium, Accent(3));
  c.FillRoundRect(4, 214, 40, 12, 3, Rgb(60, 60, 70));
  c.DrawRoundRect(50, 214, 40, 12, 12, kWhite);
  c.FillRoundRect(96, 214, 70, 12, 12, Accent(0));
  c.DrawRect(4, 230, 162, 6, Rgb(80, 80, 80));
  c.FillRect(5, 231, 100, 4, Accent(3));
  // A line fan, every slope.
  for (int i = 0; i <= 16; ++i) {
    const float a = float(i) / 16.0f * 3.14159f;
    c.DrawLine(85, 318, 85 + int(78.0f * cosf(a)), 318 - int(78.0f * sinf(a)),
               i & 1 ? Accent(1) : kWhite);
  }
}

// Page 3: a mock of a parameter page, text over colours.
void DrawMock(Canvas& c) {
  c.Clear(kBlack);
  c.FillRect(0, 0, 170, 40, Rgb(20, 22, 30));
  c.DrawText(6, 4, "07", sidefx::kFontHuge, Accent(1));
  c.DrawText(52, 4, "Dub Throw", sidefx::kFontMedium, kWhite);
  c.DrawText(52, 22, "P\x02" "D\x02" "T\x02" "R  120.0 BPM \x01",
             sidefx::kFontSmall, Rgb(150, 150, 160));
  const char* const names[4] = { "PITCH", "DELAY", "TEXTURE", "REVERB" };
  const char* const values[4] = { "+12 st", "3/16", "62%", "8.4 s" };
  for (int i = 0; i < 4; ++i) {
    const int y = 46 + i * 64;
    c.FillRoundRect(2, y, 166, 58, 8, BlendColor(kBlack, Accent(i), 40));
    c.DrawText(10, y + 4, names[i], sidefx::kFontSmall, Accent(i));
    c.DrawTextRight(160, y + 4, "K" "\x04", sidefx::kFontSmall,
                    Rgb(120, 120, 130));
    c.DrawText(10, y + 22, values[i], sidefx::kFontLarge, kWhite);
    c.DrawArc(138, y + 36, 16, 3, -2.356f, 2.356f, Rgb(50, 50, 60));
    c.DrawArc(138, y + 36, 16, 3, -2.356f, -2.356f + 1.2f * (i + 1),
              Accent(i));
  }
  c.DrawTextCentered(85, 318 - sidefx::kFontSmall.line_height,
                     "SHIFT: algorithm", sidefx::kFontSmall,
                     Rgb(110, 110, 120));
}

}  // namespace

TEST(gfx, specimen) {
  const int kPages = 4;
  const int kGap = 4;
  const int sheet_w = kPages * Canvas::kWidth + (kPages - 1) * kGap;
  const int sheet_h = Canvas::kHeight;
  uint16_t* sheet = static_cast<uint16_t*>(
      malloc(sizeof(uint16_t) * size_t(sheet_w) * size_t(sheet_h)));
  for (int i = 0; i < sheet_w * sheet_h; ++i) {
    sheet[i] = Rgb(255, 0, 255);
  }
  Frame f;
  Canvas& c = f.canvas();
  for (int page = 0; page < kPages; ++page) {
    if (page == 0) {
      DrawFonts(c, 0, 2);
    } else if (page == 1) {
      DrawFonts(c, 2, 2);
    } else if (page == 2) {
      DrawShapes(c);
    } else {
      DrawMock(c);
    }
    for (int y = 0; y < Canvas::kHeight; ++y) {
      memcpy(&sheet[y * sheet_w + page * (Canvas::kWidth + kGap)],
             &c.pixels()[y * Canvas::kWidth],
             sizeof(uint16_t) * Canvas::kWidth);
    }
  }
  const char* path = "test/build/gfx_specimen.png";
  CHECK(test::WritePng(path, sheet, sheet_w, sheet_h, sheet_w, 2));
  test::Note("wrote %s (%d x %d, x2)", path, sheet_w, sheet_h);
  // The small fonts close up: the top of page 1, four times.
  const char* zoom = "test/build/gfx_specimen_zoom.png";
  CHECK(test::WritePng(zoom, sheet, Canvas::kWidth, 130, sheet_w, 4));
  test::Note("wrote %s", zoom);
  free(sheet);
}
