// Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
//
// Side FXy: drawing into the screen's frame buffer (see canvas.h).
//
// Everything works on whole pixels with the pixel (x, y) centred on the
// integer point (x, y): a disc of radius r around (cx, cy) covers 2r + 1
// pixels across, its edge r + 1/2 from the centre like the outer edges of
// those pixels, and a rounded rectangle is exactly as wide as the plain one.
// The anti-aliased shapes compute a coverage per pixel from the distance to
// the shape's edge (a ramp over the pixel's width across it) and blend; solid interiors go through the plain fills, which write whole runs
// of 32-bit words where they can.

#include "gfx/canvas.h"

#include <math.h>

namespace sidefx {

namespace {

const float kTwoPi = 6.28318530718f;

inline int Min(int a, int b) { return a < b ? a : b; }
inline int Max(int a, int b) { return a > b ? a : b; }

inline float Clamp01(float x) {
  return x < 0.0f ? 0.0f : (x > 1.0f ? 1.0f : x);
}

// x / 255 rounded, exact for 0 <= x <= 255 * 255 + 127.
inline uint32_t Div255(uint32_t x) {
  x += 128;
  return (x + (x >> 8)) >> 8;
}

inline uint8_t Alpha(float coverage) {
  return uint8_t(coverage * 255.0f + 0.5f);
}

// Pairs of pixels written as one word: the frame is uint16_t.
typedef uint32_t __attribute__((__may_alias__)) PixelPair;

// The byte swap is its own inverse.
inline uint16_t Swap(uint16_t c) { return uint16_t((c >> 8) | (c << 8)); }

// A frame row of `count` pixels from `p` set to `color`, word-wide where
// the row is word-aligned.
inline void FillRun(uint16_t* p, int count, Color color) {
  if (count <= 0) {
    return;
  }
  if (reinterpret_cast<uintptr_t>(p) & 2) {
    *p++ = color;
    --count;
  }
  PixelPair* w = reinterpret_cast<PixelPair*>(p);
  const uint32_t pair = uint32_t(color) | (uint32_t(color) << 16);
  int words = count >> 1;
  while (words >= 4) {
    w[0] = pair;
    w[1] = pair;
    w[2] = pair;
    w[3] = pair;
    w += 4;
    words -= 4;
  }
  while (words--) {
    *w++ = pair;
  }
  if (count & 1) {
    p += (count & ~1);
    *p = color;
  }
}

// One bitmap row from the 4-bit glyph data: the coverage of pixel i.
inline uint8_t Nibble(const uint8_t* row, int i) {
  const uint8_t b = row[i >> 1];
  return (i & 1) ? (b & 0x0f) : (b >> 4);
}

}  // namespace

Color BlendColor(Color a, Color b, uint8_t alpha) {
  if (alpha == 0) {
    return a;
  }
  if (alpha == 255) {
    return b;
  }
  const uint32_t ca = Swap(a);
  const uint32_t cb = Swap(b);
  const uint32_t ia = 255u - alpha;
  const uint32_t r = Div255(((ca >> 11) & 0x1f) * ia + ((cb >> 11) & 0x1f) * alpha);
  const uint32_t g = Div255(((ca >> 5) & 0x3f) * ia + ((cb >> 5) & 0x3f) * alpha);
  const uint32_t bl = Div255((ca & 0x1f) * ia + (cb & 0x1f) * alpha);
  return Swap(uint16_t((r << 11) | (g << 5) | bl));
}

void Canvas::Init(uint16_t* pixels) {
  pixels_ = pixels;
  ResetClip();
  for (int i = 0; i < kDirtyWords; ++i) {
    dirty_[i] = 0;
  }
}

// --- clipping and dirty rows -------------------------------------------------

void Canvas::SetClip(int x, int y, int w, int h) {
  clip_x0_ = Max(x, 0);
  clip_y0_ = Max(y, 0);
  clip_x1_ = Min(x + w, kWidth);
  clip_y1_ = Min(y + h, kHeight);
  if (clip_x1_ < clip_x0_) {
    clip_x1_ = clip_x0_;
  }
  if (clip_y1_ < clip_y0_) {
    clip_y1_ = clip_y0_;
  }
}

void Canvas::ResetClip() {
  clip_x0_ = 0;
  clip_y0_ = 0;
  clip_x1_ = kWidth;
  clip_y1_ = kHeight;
}

void Canvas::MarkDirty(int y0, int y1) {
  if (y1 < y0) {
    const int t = y0;
    y0 = y1;
    y1 = t;
  }
  y0 = Max(y0, 0);
  y1 = Min(y1, kHeight - 1);
  if (y0 > y1) {
    return;
  }
  // Whole words where the span covers them: every glyph and fill comes
  // through here.
  for (int w = y0 >> 5; w <= y1 >> 5; ++w) {
    const int lo = Max(y0 - (w << 5), 0);
    const int hi = Min(y1 - (w << 5), 31);
    const uint32_t upper = hi == 31 ? 0xffffffffu : (2u << hi) - 1u;
    dirty_[w] |= upper & ~((1u << lo) - 1u);
  }
}

namespace {

inline bool RowBit(const uint32_t* bits, int y) {
  return (bits[y >> 5] >> (y & 31)) & 1u;
}

}  // namespace

bool Canvas::TakeDirty(int* y0, int* y1) {
  int first = -1;
  for (int i = 0; i < kDirtyWords; ++i) {
    if (dirty_[i]) {
      first = (i << 5) + __builtin_ctz(dirty_[i]);
      break;
    }
  }
  if (first < 0) {
    return false;
  }
  // The band runs on over clean gaps shorter than kDirtyMergeRows.
  int last = first;
  int clean = 0;
  for (int y = first + 1; y < kHeight && clean < kDirtyMergeRows; ++y) {
    if (RowBit(dirty_, y)) {
      last = y;
      clean = 0;
    } else {
      ++clean;
    }
  }
  for (int y = first; y <= last; ++y) {
    dirty_[y >> 5] &= ~(1u << (y & 31));
  }
  *y0 = first;
  *y1 = last;
  return true;
}

// --- pixels ------------------------------------------------------------------

void Canvas::Clear(Color color) {
  FillRect(clip_x0_, clip_y0_, clip_x1_ - clip_x0_, clip_y1_ - clip_y0_,
           color);
}

void Canvas::SetPixel(int x, int y, Color color) {
  if (x < clip_x0_ || x >= clip_x1_ || y < clip_y0_ || y >= clip_y1_) {
    return;
  }
  pixels_[y * kWidth + x] = color;
  MarkDirty(y, y);
}

Color Canvas::GetPixel(int x, int y) const {
  if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) {
    return 0;
  }
  return pixels_[y * kWidth + x];
}

void Canvas::BlendPixel(int x, int y, Color color, uint8_t alpha) {
  if (alpha == 0 || x < clip_x0_ || x >= clip_x1_ || y < clip_y0_ ||
      y >= clip_y1_) {
    return;
  }
  uint16_t* p = &pixels_[y * kWidth + x];
  *p = BlendColor(*p, color, alpha);
  MarkDirty(y, y);
}

// --- rectangles and lines ----------------------------------------------------

void Canvas::FillRect(int x, int y, int w, int h, Color color) {
  int x0 = Max(x, clip_x0_);
  int y0 = Max(y, clip_y0_);
  int x1 = Min(x + w, clip_x1_);
  int y1 = Min(y + h, clip_y1_);
  if (x0 >= x1 || y0 >= y1) {
    return;
  }
  MarkDirty(y0, y1 - 1);
  if (x0 == 0 && x1 == kWidth) {
    // Whole rows are one contiguous run.
    FillRun(&pixels_[y0 * kWidth], (y1 - y0) * kWidth, color);
    return;
  }
  for (int row = y0; row < y1; ++row) {
    FillRun(&pixels_[row * kWidth + x0], x1 - x0, color);
  }
}

void Canvas::DrawRect(int x, int y, int w, int h, Color color) {
  if (w <= 0 || h <= 0) {
    return;
  }
  DrawHLine(x, y, w, color);
  if (h > 1) {
    DrawHLine(x, y + h - 1, w, color);
  }
  if (h > 2) {
    DrawVLine(x, y + 1, h - 2, color);
    if (w > 1) {
      DrawVLine(x + w - 1, y + 1, h - 2, color);
    }
  }
}

void Canvas::DrawHLine(int x, int y, int w, Color color) {
  FillRect(x, y, w, 1, color);
}

void Canvas::DrawVLine(int x, int y, int h, Color color) {
  FillRect(x, y, 1, h, color);
}

void Canvas::DrawLine(int x0, int y0, int x1, int y1, Color color) {
  if (y0 == y1) {
    DrawHLine(Min(x0, x1), y0, (x1 > x0 ? x1 - x0 : x0 - x1) + 1, color);
    return;
  }
  if (x0 == x1) {
    DrawVLine(x0, Min(y0, y1), (y1 > y0 ? y1 - y0 : y0 - y1) + 1, color);
    return;
  }
  // Xiaolin Wu: step along the major axis one pixel at a time and split the
  // line's position on the minor axis between the two pixels it falls in.
  const int dx = x1 - x0;
  const int dy = y1 - y0;
  const bool steep = (dy < 0 ? -dy : dy) > (dx < 0 ? -dx : dx);
  if (steep) {
    if (y0 > y1) {
      int t = x0; x0 = x1; x1 = t;
      t = y0; y0 = y1; y1 = t;
    }
    // Only the rows in the clip matter.
    const int start = Max(y0, clip_y0_);
    const int end = Min(y1, clip_y1_ - 1);
    const float gradient = float(x1 - x0) / float(y1 - y0);
    for (int y = start; y <= end; ++y) {
      const float fx = float(x0) + gradient * float(y - y0);
      const float base = floorf(fx);
      const float frac = fx - base;
      const int x = int(base);
      BlendPixel(x, y, color, Alpha(1.0f - frac));
      BlendPixel(x + 1, y, color, Alpha(frac));
    }
  } else {
    if (x0 > x1) {
      int t = x0; x0 = x1; x1 = t;
      t = y0; y0 = y1; y1 = t;
    }
    const int start = Max(x0, clip_x0_);
    const int end = Min(x1, clip_x1_ - 1);
    const float gradient = float(y1 - y0) / float(x1 - x0);
    for (int x = start; x <= end; ++x) {
      const float fy = float(y0) + gradient * float(x - x0);
      const float base = floorf(fy);
      const float frac = fy - base;
      const int y = int(base);
      BlendPixel(x, y, color, Alpha(1.0f - frac));
      BlendPixel(x, y + 1, color, Alpha(frac));
    }
  }
}

// --- round shapes -------------------------------------------------------------

void Canvas::FillRoundRect(int x, int y, int w, int h, int radius,
                           Color color) {
  if (w <= 0 || h <= 0) {
    return;
  }
  radius = Min(radius, Min(w, h) / 2);
  if (radius <= 0) {
    FillRect(x, y, w, h, color);
    return;
  }
  // The straight middle band, then the rows holding the corners: each a
  // solid span between the corners' anti-aliased quarter discs, centred on
  // (x + r, y + r) and its mirror images.
  FillRect(x, y + radius, w, h - 2 * radius, color);
  const float r = float(radius);
  for (int j = 0; j < radius; ++j) {
    const int dy = radius - j;
    const int top = y + j;
    const int bottom = y + h - 1 - j;
    if ((top < clip_y0_ || top >= clip_y1_) &&
        (bottom < clip_y0_ || bottom >= clip_y1_)) {
      continue;
    }
    // The leftmost fully covered column of this row: everything from it to
    // the mirror column is one solid span.
    int solid = radius;
    for (int i = 0; i < radius; ++i) {
      const int dx = radius - i;
      const float d = sqrtf(float(dx * dx + dy * dy));
      const float coverage = Clamp01(r + 1.0f - d);
      if (coverage >= 1.0f) {
        solid = i;
        break;
      }
      const uint8_t a = Alpha(coverage);
      BlendPixel(x + i, top, color, a);
      BlendPixel(x + w - 1 - i, top, color, a);
      BlendPixel(x + i, bottom, color, a);
      BlendPixel(x + w - 1 - i, bottom, color, a);
    }
    DrawHLine(x + solid, top, w - 2 * solid, color);
    DrawHLine(x + solid, bottom, w - 2 * solid, color);
  }
}

void Canvas::DrawRoundRect(int x, int y, int w, int h, int radius,
                           Color color) {
  if (w <= 0 || h <= 0) {
    return;
  }
  radius = Min(radius, Min(w, h) / 2);
  if (radius <= 0) {
    DrawRect(x, y, w, h, color);
    return;
  }
  DrawHLine(x + radius, y, w - 2 * radius, color);
  DrawHLine(x + radius, y + h - 1, w - 2 * radius, color);
  DrawVLine(x, y + radius, h - 2 * radius, color);
  DrawVLine(x + w - 1, y + radius, h - 2 * radius, color);
  // The corners: a one-pixel ring of radius r, coverage falling off over a
  // pixel either side of it. The axis pixels belong to the straight edges.
  const float r = float(radius);
  for (int dy = 1; dy <= radius; ++dy) {
    for (int dx = 1; dx <= radius; ++dx) {
      const float d = sqrtf(float(dx * dx + dy * dy));
      const float coverage = Clamp01(1.0f - fabsf(d - r));
      if (coverage <= 0.0f) {
        continue;
      }
      const uint8_t a = Alpha(coverage);
      const int left = x + radius - dx;
      const int right = x + w - 1 - radius + dx;
      const int top = y + radius - dy;
      const int bottom = y + h - 1 - radius + dy;
      BlendPixel(left, top, color, a);
      BlendPixel(right, top, color, a);
      BlendPixel(left, bottom, color, a);
      BlendPixel(right, bottom, color, a);
    }
  }
}

void Canvas::FillCircle(int cx, int cy, int radius, Color color) {
  if (radius < 0) {
    return;
  }
  if (radius == 0) {
    SetPixel(cx, cy, color);
    return;
  }
  const float r = float(radius);
  const int y_start = Max(cy - radius, clip_y0_);
  const int y_end = Min(cy + radius, clip_y1_ - 1);
  for (int py = y_start; py <= y_end; ++py) {
    const int dy = py - cy;
    // Per row: anti-aliased pixels from the outside in until one is fully
    // covered, then a solid span to its mirror.
    int solid = radius + 1;
    for (int dx = radius; dx >= 0; --dx) {
      const float d = sqrtf(float(dx * dx + dy * dy));
      const float coverage = Clamp01(r + 1.0f - d);
      if (coverage >= 1.0f) {
        solid = dx;
        break;
      }
      const uint8_t a = Alpha(coverage);
      BlendPixel(cx - dx, py, color, a);
      if (dx) {
        BlendPixel(cx + dx, py, color, a);
      }
    }
    if (solid <= radius) {
      DrawHLine(cx - solid, py, 2 * solid + 1, color);
    }
  }
}

void Canvas::DrawCircle(int cx, int cy, int radius, Color color) {
  DrawArc(cx, cy, radius, 1, 0.0f, kTwoPi, color);
}

void Canvas::DrawArc(int cx, int cy, int radius, int thickness, float a0,
                     float a1, Color color) {
  if (radius <= 0 || thickness <= 0) {
    return;
  }
  if (a1 < a0) {
    const float t = a0;
    a0 = a1;
    a1 = t;
  }
  float sweep = a1 - a0;
  const bool full = sweep >= kTwoPi;
  if (sweep <= 0.0f) {
    return;
  }
  a0 = fmodf(a0, kTwoPi);
  if (a0 < 0.0f) {
    a0 += kTwoPi;
  }
  // The ring's edges sit on the outer radius r + 0.5 and the inner radius
  // r + 0.5 - thickness (so a thickness of 1 is the pixel ring at r); the
  // ends are cut square to the radius.
  const float outer = float(radius) + 0.5f;
  const float inner = outer - float(thickness);
  const float outer_sq = (outer + 0.5f) * (outer + 0.5f);
  const float inner_sq = inner > 0.5f ? (inner - 0.5f) * (inner - 0.5f) : 0.0f;
  const int extent = radius + 1;
  const int y_start = Max(cy - extent, clip_y0_);
  const int y_end = Min(cy + extent, clip_y1_ - 1);
  const int x_start = Max(cx - extent, clip_x0_);
  const int x_end = Min(cx + extent, clip_x1_ - 1);
  for (int py = y_start; py <= y_end; ++py) {
    const float dy = float(py - cy);
    for (int px = x_start; px <= x_end; ++px) {
      const float dx = float(px - cx);
      const float d_sq = dx * dx + dy * dy;
      if (d_sq >= outer_sq || d_sq < inner_sq) {
        continue;
      }
      const float d = sqrtf(d_sq);
      // How much of a pixel-wide radial window around d lies in the band.
      const float hi = d + 0.5f < outer ? d + 0.5f : outer;
      const float lo = d - 0.5f > inner ? d - 0.5f : inner;
      float coverage = Clamp01(hi - lo);
      if (coverage <= 0.0f) {
        continue;
      }
      if (!full) {
        // 0 = up, clockwise on the screen (y grows downwards).
        float angle = atan2f(dx, -dy);
        if (angle < 0.0f) {
          angle += kTwoPi;
        }
        float rel = angle - a0;
        if (rel < 0.0f) {
          rel += kTwoPi;
        }
        // Distances to the end edges along the circle, in pixels (at the
        // centre itself every angle is "inside").
        const float arc = d > 0.5f ? d : 0.5f;
        float angular;
        if (rel <= sweep) {
          const float in = rel < sweep - rel ? rel : sweep - rel;
          angular = Clamp01(in * arc + 0.5f);
        } else {
          const float past = rel - sweep;
          const float before = kTwoPi - rel;
          const float out = past < before ? past : before;
          angular = Clamp01(0.5f - out * arc);
        }
        coverage *= angular;
        if (coverage <= 0.0f) {
          continue;
        }
      }
      BlendPixel(px, py, color, Alpha(coverage));
    }
  }
}

// --- text ----------------------------------------------------------------------

namespace {

inline const Glyph* GlyphOf(const Font& font, char c) {
  uint8_t code = uint8_t(c);
  if (code < font.first || code > font.last) {
    code = (uint8_t('?') >= font.first && uint8_t('?') <= font.last)
        ? uint8_t('?')
        : font.first;
  }
  return &font.glyphs[code - font.first];
}

}  // namespace

int Canvas::TextWidth(const char* text, const Font& font) const {
  int width = 0;
  for (const char* c = text; *c; ++c) {
    width += GlyphOf(font, *c)->advance;
  }
  return width;
}

int Canvas::DrawText(int x, int y, const char* text, const Font& font,
                     Color color) {
  for (const char* c = text; *c; ++c) {
    const Glyph& g = *GlyphOf(font, *c);
    const int gx = x + g.x_offset;
    const int gy = y + g.y_offset;
    const int stride = (g.width + 1) >> 1;
    const int row0 = Max(0, clip_y0_ - gy);
    const int row1 = Min(int(g.height), clip_y1_ - gy);
    const int col0 = Max(0, clip_x0_ - gx);
    const int col1 = Min(int(g.width), clip_x1_ - gx);
    if (row0 < row1 && col0 < col1) {
      MarkDirty(gy + row0, gy + row1 - 1);
      const uint8_t* bits = font.bitmap + g.offset;
      for (int row = row0; row < row1; ++row) {
        const uint8_t* src = bits + row * stride;
        uint16_t* dst = &pixels_[(gy + row) * kWidth + gx];
        for (int col = col0; col < col1; ++col) {
          const uint8_t coverage = Nibble(src, col);
          if (coverage == 15) {
            dst[col] = color;
          } else if (coverage) {
            dst[col] = BlendColor(dst[col], color, uint8_t(coverage * 17));
          }
        }
      }
    }
    x += g.advance;
  }
  return x;
}

int Canvas::DrawTextRight(int right, int y, const char* text,
                          const Font& font, Color color) {
  return DrawText(right - TextWidth(text, font), y, text, font, color);
}

int Canvas::DrawTextCentered(int center, int y, const char* text,
                             const Font& font, Color color) {
  return DrawText(center - TextWidth(text, font) / 2, y, text, font, color);
}

}  // namespace sidefx
