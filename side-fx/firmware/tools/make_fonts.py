# Copyright 2026 the Side FXy authors. MIT licence, see side-fx/firmware/LICENSE.
#
# Side FXy: renders the screen's anti-aliased bitmap fonts into
# src/gfx/fonts.cc (see src/gfx/font.h for the format).
#
#   python tools/make_fonts.py <dir with DejaVuSans.ttf, DejaVuSans-Bold.ttf>
#
# Needs Pillow (FreeType). The glyphs are FreeType's hinted, anti-aliased
# rendering at the target pixel size (hinting keeps small text sharp on a
# 170 px wide screen), cropped to their ink, with 4-bit coverage. The
# symbols on \x01..\x05 are drawn here, 8x supersampled and box-filtered,
# from the font's own cap height, x-height and stem width, so they sit with
# the letters.

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "src", "gfx", "fonts.cc")

# (C name, file, pixel size, description)
FONTS = [
    ("Small", "DejaVuSans.ttf", 11, "DejaVu Sans"),
    ("Medium", "DejaVuSans.ttf", 15, "DejaVu Sans"),
    ("Large", "DejaVuSans-Bold.ttf", 22, "DejaVu Sans Bold"),
    ("Huge", "DejaVuSans-Bold.ttf", 32, "DejaVu Sans Bold"),
]

FIRST = 0x01
LAST = 0x7E
SYMBOLS = range(0x01, 0x06)
SS = 8  # supersampling of the drawn symbols

LICENSE = """\
Glyphs rendered from the DejaVu fonts (https://dejavu-fonts.github.io/),
a derivative of Bitstream Vera. Their licence:

Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved. Bitstream Vera
is a trademark of Bitstream, Inc. DejaVu changes are in public domain.

Permission is hereby granted, free of charge, to any person obtaining a copy
of the fonts accompanying this license ("Fonts") and associated
documentation files (the "Font Software"), to reproduce and distribute the
Font Software, including without limitation the rights to use, copy, merge,
publish, distribute, and/or sell copies of the Font Software, and to permit
persons to whom the Font Software is furnished to do so, subject to the
following conditions:

The above copyright and trademark notices and this permission notice shall
be included in all copies of one or more of the Font Software typefaces.

The Font Software may be modified, altered, or added to, and in particular
the designs of glyphs or characters in the Fonts may be modified and
additional glyphs or characters may be added to the Fonts, only if the fonts
are renamed to names not containing either the words "Bitstream" or the word
"Vera".

This License becomes null and void to the extent applicable to Fonts or Font
Software that has been modified and is distributed under the "Bitstream
Vera" names.

The Font Software may be sold as part of a larger software package but no
copy of one or more of the Font Software typefaces may be sold by itself.

THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT OF COPYRIGHT, PATENT,
TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL BITSTREAM OR THE GNOME
FOUNDATION BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, INCLUDING
ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL DAMAGES,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF
THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM OTHER DEALINGS IN THE
FONT SOFTWARE.

Except as contained in this notice, the names of Gnome, the Gnome
Foundation, and Bitstream Inc., shall not be used in advertising or
otherwise to promote the sale, use or other dealings in this Font Software
without prior written authorization from the Gnome Foundation or Bitstream
Inc., respectively. For further information, contact: fonts at gnome dot
org."""


class Bitmap(object):
  """A glyph's ink: coverage rows (0..255) and its place on the baseline."""

  def __init__(self, image, left, top, advance):
    # image: 'L', already cropped; left/top: of its top-left pixel relative
    # to the pen on the baseline (top negative above the baseline).
    self.image = image
    self.left = left
    self.top = top
    self.advance = advance


def crop(image, left, top, advance):
  box = image.getbbox()
  if box is None:
    return Bitmap(Image.new("L", (0, 0)), 0, 0, advance)
  return Bitmap(image.crop(box), left + box[0], top + box[1], advance)


def render_char(font, ch):
  l, t, r, b = font.getbbox(ch, anchor="ls")
  advance = int(round(font.getlength(ch)))
  w, h = max(r - l, 1) + 2, max(b - t, 1) + 2
  image = Image.new("L", (w, h), 0)
  ImageDraw.Draw(image).text((1 - l, 1 - t), ch, font=font, fill=255,
                             anchor="ls")
  return crop(image, l - 1, t - 1, advance)


def metrics(font):
  cap = -font.getbbox("H", anchor="ls")[1]
  xh = -font.getbbox("x", anchor="ls")[1]
  # The stem: the ink width of "l" (a single vertical stroke).
  l = render_char(font, "l")
  row = [l.image.getpixel((x, l.image.height // 2)) for x in range(l.image.width)]
  stem = max(1.0, sum(row) / 255.0)
  return cap, xh, stem


def draw_symbol(code, font):
  """The symbol on `code`, as a Bitmap, drawn supersampled."""
  cap, xh, stem = metrics(font)
  size = font.size
  # The canvas: from one cap height above the baseline to a quarter below,
  # one em wide plus margins, everything in supersampled pixels.
  w = int(size * 1.5) * SS
  above = int(cap + 2) * SS
  h = above + int(size * 0.5) * SS
  image = Image.new("L", (w, h), 0)
  d = ImageDraw.Draw(image)
  base = above          # baseline, in supersampled rows
  x0 = 2 * SS           # left of the ink
  s = stem * SS
  c = cap * SS
  bearing = max(1, int(round(size * 0.08)))

  if code == 0x01:      # an eighth note
    head_w = 0.62 * c
    head_h = 0.42 * c
    cx = x0 + head_w / 2
    cy = base - head_h / 2
    pts = []
    tilt = math.radians(-22)
    for i in range(64):
      a = 2 * math.pi * i / 64
      ex = head_w / 2 * math.cos(a)
      ey = head_h / 2 * math.sin(a)
      pts.append((cx + ex * math.cos(tilt) - ey * math.sin(tilt),
                  cy + ex * math.sin(tilt) + ey * math.cos(tilt)))
    d.polygon(pts, fill=255)
    stem_x = cx + head_w / 2 - s * 0.9
    top = base - c * 1.02
    d.rectangle([stem_x, top, stem_x + s, cy], fill=255)
    # The flag: a band falling right from the stem's top, then curling down.
    fw = 0.42 * c
    flag = [(stem_x + s * 0.5, top), (stem_x + s, top),
            (stem_x + s + fw * 0.55, top + 0.25 * c),
            (stem_x + s + fw, top + 0.55 * c),
            (stem_x + s + fw * 0.8, top + 0.72 * c),
            (stem_x + s + fw * 0.75, top + 0.52 * c),
            (stem_x + s + fw * 0.3, top + 0.38 * c),
            (stem_x + s, top + 0.36 * c)]
    d.polygon(flag, fill=255)
  elif code in (0x02, 0x03):  # right and left triangles
    th = 0.86 * c
    tw = 0.78 * th
    mid = base - c / 2
    if code == 0x02:
      pts = [(x0, mid - th / 2), (x0 + tw, mid), (x0, mid + th / 2)]
    else:
      pts = [(x0 + tw, mid - th / 2), (x0, mid), (x0 + tw, mid + th / 2)]
    d.polygon(pts, fill=255)
  elif code == 0x04:    # a dot, centred on the x-height like a bullet
    r = max(0.26 * xh * SS, s * 0.9)
    mid = base - xh * SS / 2
    d.ellipse([x0, mid - r, x0 + 2 * r, mid + r], fill=255)
  else:                 # 0x05, a degree ring at the cap height
    ro = 0.24 * c
    ri = ro - max(s * 0.85, 0.75 * SS)
    cx = x0 + ro
    cy = base - c + ro
    d.ellipse([cx - ro, cy - ro, cx + ro, cy + ro], fill=255)
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=0)

  small = image.resize((w // SS, h // SS), Image.BOX)
  bm = crop(small, 0, -(above // SS), 0)
  # Pen advance: a bearing either side of the ink.
  bm.left = bearing
  bm.advance = bm.image.width + 2 * bearing
  return bm


def quantize(bm):
  w, h = bm.image.size
  data = []
  px = bm.image.load()
  for y in range(h):
    row = [(px[x, y] * 15 + 127) // 255 for x in range(w)]
    if len(row) % 2:
      row.append(0)
    for i in range(0, len(row), 2):
      data.append((row[i] << 4) | row[i + 1])
  return data


def char_comment(code):
  if code in SYMBOLS:
    return "\\x%02x" % code
  ch = chr(code)
  if ch == "\\":
    return "backslash"
  return "'%s'" % ch


def build(name, path, size, description):
  font = ImageFont.truetype(path, size)
  glyphs = {}
  for code in range(0x20, LAST + 1):
    glyphs[code] = render_char(font, chr(code))
  for code in SYMBOLS:
    glyphs[code] = draw_symbol(code, font)
  # The line box: from the highest ink of printable ASCII to the lowest.
  ascii_ink = [g for c, g in glyphs.items() if c > 0x20 and g.image.width]
  ascent = -min(g.top for g in ascii_ink)
  descent = max(g.top + g.image.height for g in ascii_ink)
  line_height = ascent + descent

  bitmap = []
  entries = []
  offsets = {}
  for code in range(FIRST, LAST + 1):
    if code not in glyphs:
      entries.append(None)  # filled with '?' below
      continue
    g = glyphs[code]
    offsets[code] = len(bitmap)
    data = quantize(g)
    bitmap.extend(data)
    assert -128 <= g.left <= 127 and -128 <= ascent + g.top <= 127
    assert g.image.width < 256 and g.image.height < 256 and g.advance < 256
    entries.append((offsets[code], g.image.width, g.image.height, g.left,
                    ascent + g.top, g.advance, char_comment(code)))
  q = entries[ord("?") - FIRST]
  entries = [e if e is not None else q[:6] + ("unused, as '?'",)
             for e in entries]

  out = []
  out.append("// %s, %d px: line height %d, ascent %d, cap height %d."
             % (description, size, line_height, ascent,
                -font.getbbox("H", anchor="ls")[1]))
  out.append("const uint8_t k%sBitmap[%d] = {" % (name, len(bitmap)))
  for i in range(0, len(bitmap), 16):
    out.append("  " + ", ".join("0x%02x" % b for b in bitmap[i:i + 16]) + ",")
  out.append("};")
  out.append("")
  out.append("const Glyph k%sGlyphs[%d] = {" % (name, len(entries)))
  for e in entries:
    out.append("  { %d, %d, %d, %d, %d, %d },  // %s" % e)
  out.append("};")
  out.append("")
  font_def = ("const Font kFont%s = {\n  0x%02x, 0x%02x, %d, %d, k%sGlyphs, "
              "k%sBitmap\n};" % (name, FIRST, LAST, line_height, ascent,
                                 name, name))
  return out, font_def, len(bitmap) + 12 * len(entries)


def main():
  if len(sys.argv) != 2:
    sys.exit(__doc__ if __doc__ else "usage: make_fonts.py <font dir>")
  font_dir = sys.argv[1]
  body = []
  defs = []
  total = 0
  for name, file_name, size, description in FONTS:
    lines, font_def, nbytes = build(name, os.path.join(font_dir, file_name),
                                    size, description)
    body.extend(lines)
    defs.append(font_def)
    total += nbytes
    print("%-6s %2d px: %6d bytes" % (name, size, nbytes))
  print("total %d bytes" % total)

  head = [
      "// Copyright 2026 the Side FXy authors. MIT licence, see "
      "side-fx/firmware/LICENSE.",
      "//",
      "// Side FXy: the screen's fonts (see gfx/font.h). Generated by",
      "// tools/make_fonts.py from DejaVu Sans and DejaVu Sans Bold; do not",
      "// edit. The symbols on \\x01..\\x05 are drawn by the script.",
      "//",
  ]
  head += ["// " + line if line else "//" for line in LICENSE.split("\n")]
  head += ["", '#include "gfx/font.h"', "", "namespace sidefx {", "",
           "namespace {", ""]
  text = "\n".join(head + body + ["}  // namespace", ""] + defs +
                   ["", "}  // namespace sidefx", ""])
  with open(OUT, "w", newline="\n", encoding="ascii") as f:
    f.write(text)
  print("wrote", OUT)


if __name__ == "__main__":
  main()
