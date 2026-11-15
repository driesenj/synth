#!/usr/bin/env python3
"""Bench kit for the mixer's mute PhotoMOS (test report M1): test signals, THD, IMD and a null test.

An off AQY212EH is a voltage-dependent capacitance on the channel's FI node. This kit measures what it
does to a signal: record a stand-in channel without and then with the part (README.md), and compare.

  python mute_test.py tones   [--rate 96000] [--out tones]
  python mute_test.py analyse REC.wav [--cal CAL.wav VRMS]
  python mute_test.py null    WITHOUT.wav WITH.wav [--floor WITHOUT2.wav] [--out DIR]
  python mute_test.py report  rec/without rec/with [--floor rec/without2] [--cal-vrms 3.54] [--out results]
  python mute_test.py selftest

numpy only (no scipy); Pillow, if present, draws the spectra.
"""
import argparse
import math
import struct
import sys
from pathlib import Path

import numpy as np

LEVEL_DBFS = -3.0          # peak of every test signal
SECONDS = 10.0             # steady part of every test signal
FADE = 0.02                # s, raised-cosine fade in and out
LEAD = 0.5                 # s of silence before and after
TONES = {                  # name: [(Hz, share of the peak)]
    "cal-50hz": [(50.0, 1.0)],
    "sine-1k": [(1000.0, 1.0)],
    "sine-10k": [(10000.0, 1.0)],
    "ccif-19k-20k": [(19000.0, 0.5), (20000.0, 0.5)],
    "smpte-60-7k": [(60.0, 0.8), (7000.0, 0.2)],
}
NOISE = "pink-noise"
BAND_EDGE = 0.45           # analysis stops at 0.45 fs, inside any interface's anti-alias filter
THDN_BAND = (20.0, 22000.0)

# Predicted for the stand-in of README.md (22k into the FI node, 10 V p-p, about 5 pF of strays), by the two
# C_off models of test_audio_ac.py (anti-series MOSFET pair .. one varactor); both mostly third order.
PREDICTED = {
    "sine-1k": "0.04-0.16 % (H3 -68..-56 dB)",
    "sine-10k": "0.39-1.55 % (H3 -48..-37 dB)",
    "ccif-19k-20k": "0.34-1.24 % (d3 at 18k / 21k -53..-41 dB; d2 negligible)",
    "smpte-60-7k": "0.26-1.0 % (f2+-2f1 -55..-43 dB; f2+-f1 negligible)",
}

# 7-term Blackman-Harris: side lobes below -180 dB, main lobe +-7 bins
BH7 = (0.27105140069342, -0.43329793923448, 0.21812299954311, -0.06592544638803,
       0.01081174209837, -0.00077658482522, 0.00001388721735)
LOBE = 10                  # bins summed each side of a tone's peak


# ----------------------------------------------------------------------------------------------- WAV files
def read_wav(path, channel=0):
    """(samples as float in -1..1, sample rate) of one channel; PCM 8/16/24/32-bit or float 32/64."""
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise SystemExit(f"{path}: not a WAV file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = body
        elif cid == b"data":
            raw = body
            if fmt is not None:
                break
        pos += 8 + size + (size & 1)
    if fmt is None or raw is None:
        raise SystemExit(f"{path}: no fmt or data chunk")
    tag, nch, fs, _, align, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == 0xFFFE:                                          # WAVE_FORMAT_EXTENSIBLE: the real tag is in the GUID
        tag = struct.unpack("<H", fmt[24:26])[0]
    width = align // nch
    n = len(raw) // align
    raw = raw[:n * align]
    if tag == 3:
        x = np.frombuffer(raw, {4: "<f4", 8: "<f8"}[width]).astype(float)
    elif tag == 1 and width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif tag == 1 and width in (1, 2, 4):
        dt = {1: np.uint8, 2: "<i2", 4: "<i4"}[width]
        x = np.frombuffer(raw, dt).astype(float)
        x = (x - 128) / 128 if width == 1 else x / float(1 << (8 * width - 1))
    else:
        raise SystemExit(f"{path}: unsupported WAV format (tag {tag}, {bits} bits)")
    x = x.reshape(-1, nch)
    if channel >= nch:
        raise SystemExit(f"{path}: has {nch} channel(s), channel {channel} asked for")
    return x[:, channel].copy(), fs


def write_wav(path, x, fs, channels=1):
    """24-bit PCM; x is clipped to -1..1 and written to every channel."""
    x = np.clip(np.asarray(x, float), -1.0, 1.0 - 2.0 ** -23)
    q = np.round(x * (1 << 23)).astype("<i4")
    q = np.repeat(q[:, None], channels, axis=1).ravel()
    body = np.ascontiguousarray(q).view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    fmt = struct.pack("<HHIIHH", 1, channels, int(fs), int(fs) * 3 * channels, 3 * channels, 24)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(body)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt)
        f.write(b"data" + struct.pack("<I", len(body)) + body)


# ---------------------------------------------------------------------------------------------- signals
def envelope(n, fs):
    e = np.ones(n)
    m = int(FADE * fs)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(m) / m)
    e[:m], e[n - m:] = ramp, ramp[::-1]
    return e


def make_signal(name, fs, seconds=SECONDS, level_dbfs=LEVEL_DBFS):
    n = int(round(seconds * fs))
    t = np.arange(n) / fs
    peak = 10 ** (level_dbfs / 20)
    if name == NOISE:
        rng = np.random.default_rng(1)
        spec = rng.normal(size=n // 2 + 1) + 1j * rng.normal(size=n // 2 + 1)
        f = np.fft.rfftfreq(n, 1 / fs)
        spec *= np.where((f >= 20) & (f <= 20000), 1 / np.sqrt(np.maximum(f, 1.0)), 0.0)
        x = np.fft.irfft(spec, n)
        x *= peak / np.max(np.abs(x))
    else:
        x = sum(share * peak * np.sin(2 * np.pi * f0 * t) for f0, share in TONES[name])
    x = x * envelope(n, fs)
    gap = np.zeros(int(LEAD * fs))
    return np.concatenate([gap, x, gap])


def cmd_tones(args):
    out = Path(args.out)
    for name in list(TONES) + [NOISE]:
        if max(f for f, _ in TONES.get(name, [(0, 0)])) > BAND_EDGE * args.rate:
            print(f"skipped {name}: above {BAND_EDGE} fs at {args.rate} Hz")
            continue
        write_wav(out / f"{name}.wav", make_signal(name, args.rate), args.rate, channels=2)
        print(f"wrote {out / (name + '.wav')}")
    print(f"{args.rate} Hz, 24-bit stereo (the same on both channels), peak {LEVEL_DBFS:.0f} dBFS, "
          f"{SECONDS:.0f} s each. Set your DAW project to {args.rate} Hz so nothing is resampled.")


# --------------------------------------------------------------------------------------------- spectrum
def bh7(n):
    t = 2 * np.pi * np.arange(n) / n
    return sum(c * np.cos(k * t) for k, c in enumerate(BH7))


def steady(x, fs, guard=0.3):
    """The part of a recording where the test signal is on, less `guard` seconds at each end."""
    blk = max(int(0.05 * fs), 1)
    nb = len(x) // blk
    if nb < 8:
        return x
    r = np.sqrt(np.mean(x[:nb * blk].reshape(nb, blk) ** 2, axis=1))
    loud = np.nonzero(r > 0.5 * r.max())[0]
    a, b = loud[0] * blk + int(guard * fs), (loud[-1] + 1) * blk - int(guard * fs)
    return x[a:b] if b - a > 8 * blk else x


class Spectrum:
    """Averaged power spectrum, scaled so that a tone's bins sum to its mean square (rms^2)."""

    def __init__(self, x, fs, seconds=0.7):
        n = 2 ** int(round(math.log2(fs * seconds)))
        while n > len(x) and n > 1024:
            n //= 2
        w = bh7(n)
        acc, m = 0.0, 0
        for i in range(0, len(x) - n + 1, n // 2):
            seg = x[i:i + n]
            acc = acc + np.abs(np.fft.rfft((seg - seg.mean()) * w)) ** 2
            m += 1
        self.p = 2 * acc / max(m, 1) / (n * np.sum(w ** 2))
        self.p[0] = 0.0
        self.df, self.fs, self.n, self.segments = fs / n, fs, n, m
        self.enbw = n * np.sum(w ** 2) / np.sum(w) ** 2          # bins; a tone's peak bin is p / enbw

    def k(self, f):
        return int(round(f / self.df))

    def tone(self, f, search=3):
        """(mean square, refined frequency, noise mean square in the same bins) of the tone near f."""
        k = self.k(f)
        lo, hi = max(k - search, 1), min(k + search, len(self.p) - 1)
        k = lo + int(np.argmax(self.p[lo:hi + 1]))
        a, b = max(k - LOBE, 1), min(k + LOBE, len(self.p) - 1)
        pw = float(self.p[a:b + 1].sum())
        side = np.r_[self.p[max(k - 60, 1):max(k - 20, 1)], self.p[k + 20:k + 60]]
        noise = float(np.median(side)) * (b - a + 1) if len(side) else 0.0
        fr = float((np.arange(a, b + 1) * self.p[a:b + 1]).sum() / max(pw, 1e-300) * self.df)
        return pw, fr, noise

    def peaks(self, count=2, fmin=10.0):
        p = self.p.copy()
        p[:self.k(fmin)] = 0
        found = []
        for _ in range(count):
            k = int(np.argmax(p))
            found.append(k * self.df)
            p[max(k - 3 * LOBE, 0):k + 3 * LOBE + 1] = 0
        return found


def db(power_ratio):
    return 10 * math.log10(max(power_ratio, 1e-30))


def kind_of(spec):
    """'sine', 'ccif' or 'smpte' from the two biggest peaks."""
    f1, f2 = spec.peaks(2)
    p1, f1, _ = spec.tone(f1)
    p2, f2, _ = spec.tone(f2)
    lo, hi = min(f1, f2), max(f1, f2)
    near_harmonic = abs(hi / lo - round(hi / lo)) * lo < 3 * spec.df
    if db(p2 / p1) < -30 or near_harmonic:
        return "sine"
    return "ccif" if abs(db(p2 / p1)) < 6 else "smpte"


def measure_thd(spec):
    f0 = spec.peaks(1)[0]
    p1, f1, _ = spec.tone(f0)
    rows = []
    for h in range(2, 11):
        if h * f1 > BAND_EDGE * spec.fs:
            break
        pw, _, nz = spec.tone(h * f1)
        rows.append((f"H{h}", h * f1, max(pw - nz, 0.0), pw < 2 * nz, pw))
    thd = math.sqrt(sum(r[2] for r in rows) / p1)
    lo, hi = spec.k(THDN_BAND[0]), spec.k(min(THDN_BAND[1], BAND_EDGE * spec.fs))
    k1 = spec.k(f1)
    band = np.r_[spec.p[lo:max(k1 - LOBE, lo)], spec.p[k1 + LOBE + 1:hi + 1]]
    return {"kind": "sine", "f": f1, "ref": p1, "rows": rows, "total": thd,
            "thdn": math.sqrt(float(band.sum()) / p1)}


def measure_imd(spec, kind):
    fa, fb = spec.peaks(2)
    (pa, fa, _), (pb, fb, _) = spec.tone(fa), spec.tone(fb)
    if kind == "ccif":
        (p1, f1), (p2, f2) = sorted([(pa, fa), (pb, fb)], key=lambda t: t[1])
        ref, fref = p2, f2
        prods = [("d2 f2-f1", f2 - f1), ("d3 2f1-f2", 2 * f1 - f2), ("d3 2f2-f1", 2 * f2 - f1),
                 ("d5 3f1-2f2", 3 * f1 - 2 * f2), ("d5 3f2-2f1", 3 * f2 - 2 * f1)]
    else:
        (pl, fl), (ph, fh) = sorted([(pa, fa), (pb, fb)], key=lambda t: t[1])
        ref, fref = ph, fh
        prods = [(f"f2{'-' if s < 0 else '+'}{n if n > 1 else ''}f1", fh + s * n * fl)
                 for n in (1, 2, 3, 4) for s in (-1, 1)]
    rows = []
    for label, f in prods:
        if 10 < f < BAND_EDGE * spec.fs:
            pw, _, nz = spec.tone(f, search=2)
            rows.append((label, f, max(pw - nz, 0.0), pw < 2 * nz, pw))
    return {"kind": kind, "f": fref, "ref": ref, "rows": rows,
            "total": math.sqrt(sum(r[2] for r in rows) / ref), "tones": (fa, fb)}


def measure(x, fs):
    spec = Spectrum(steady(x, fs), fs)
    kind = kind_of(spec)
    m = measure_thd(spec) if kind == "sine" else measure_imd(spec, kind)
    m["spec"] = spec
    return m


def volts_scale(cal_path, vrms, channel=0):
    """Volts rms per unit rms of the recording, from a recorded 50 Hz tone and the meter's reading."""
    x, fs = read_wav(cal_path, channel)
    spec = Spectrum(steady(x, fs), fs)
    p, _, _ = spec.tone(spec.peaks(1)[0])
    return vrms / math.sqrt(p)


def level_text(p, vscale):
    s = f"{db(2 * p):6.1f} dBFS"
    if vscale:
        s += f", {2 * math.sqrt(2 * p) * vscale:.2f} V p-p"
    return s


def product_text(row, ref):
    """A product's level re the tone, or an upper bound when it is not above the noise."""
    _, _, pw, floor, raw = row
    return f"< {db(raw / ref):.0f} dB" if floor else f"{db(pw / ref):.1f} dB"


def thdn_label(fs):
    hi = min(THDN_BAND[1], BAND_EDGE * fs)
    return f"THD+N {THDN_BAND[0]:.0f} Hz-{hi / 1e3:.1f} kHz, harmonics above that left out"


def describe(m, vscale=None):
    head = {"sine": "THD", "ccif": "IMD, CCIF twin tone", "smpte": "IMD, SMPTE 4:1"}[m["kind"]]
    lines = [f"  {head}: tone {m['f']:.1f} Hz at {level_text(m['ref'], vscale)}"]
    for row in m["rows"]:
        label, f, pw, floor, raw = row
        lines.append(f"    {label:<11} {f:8.1f} Hz  {product_text(row, m['ref']):>9}"
                     + (f"  < {100 * math.sqrt(raw / m['ref']):.4f} %, not above the noise" if floor else
                        f"  {100 * math.sqrt(pw / m['ref']):8.4f} %"))
    lines.append(f"    total       {100 * m['total']:.4f} %  ({db(m['total'] ** 2):.1f} dB)")
    if m["kind"] == "sine":
        lines.append(f"    {thdn_label(m['spec'].fs)}: {100 * m['thdn']:.4f} %")
    return "\n".join(lines)


def cmd_analyse(args):
    vscale = volts_scale(args.cal[0], float(args.cal[1]), args.channel) if args.cal else None
    for path in args.files:
        x, fs = read_wav(path, args.channel)
        print(f"{path} ({fs} Hz)")
        print(describe(measure(x, fs), vscale))


def compare_text(name, ma, mb, vscale=None):
    rows = [f"{name}: {ma['kind']}, {ma['f']:.1f} Hz"]
    rows.append(f"  {'':<13}{'without':>14}{'with':>14}{'change':>10}")
    rows.append(f"  {'level':<13}{db(2 * ma['ref']):>9.2f} dBFS{db(2 * mb['ref']):>9.2f} dBFS"
                f"{db(mb['ref'] / ma['ref']):>+8.2f} dB")
    if vscale:
        rows.append(f"  {'':<13}{2 * math.sqrt(2 * ma['ref']) * vscale:>9.2f} V pp{2 * math.sqrt(2 * mb['ref']) * vscale:>9.2f} V pp")
    lb = {r[0]: r for r in mb["rows"]}
    for row in ma["rows"]:
        if row[0] not in lb:
            continue
        rb = lb[row[0]]
        da, dbb = db(row[4 if row[3] else 2] / ma["ref"]), db(rb[4 if rb[3] else 2] / mb["ref"])
        change = "" if rb[3] else (f"> {dbb - da:+.0f} dB" if row[3] else f"{dbb - da:+.1f} dB")
        rows.append(f"  {row[0]:<13}{product_text(row, ma['ref']):>14}{product_text(rb, mb['ref']):>14}{change:>10}")
    rows.append(f"  {'total':<13}{100 * ma['total']:>12.4f} %{100 * mb['total']:>12.4f} %")
    if ma["kind"] == "sine":
        rows.append(f"  {'THD+N':<13}{100 * ma['thdn']:>12.4f} %{100 * mb['thdn']:>12.4f} %   ({thdn_label(ma['spec'].fs)})")
    if name in PREDICTED:
        rows.append(f"  predicted for the stand-in at 10 V p-p: {PREDICTED[name]}")
    if any(r[3] for r in ma["rows"] + mb["rows"]):
        rows.append("  < : not above the noise floor; the figure is an upper bound")
    return "\n".join(rows)


# ----------------------------------------------------------------------------------------------- plots
def plot_spectra(path, title, curves):
    """curves: [(label, Spectrum, ref power, (r, g, b))]; dB re ref, log frequency. Needs Pillow."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    W, H, L, R, T, B = 1100, 560, 64, 16, 34, 44
    fs = curves[0][1].fs
    fmin, fmax, ymin, ymax = 20.0, BAND_EDGE * fs, -160.0, 10.0
    lf0, lf1 = math.log10(fmin), math.log10(fmax)
    X = lambda f: L + (math.log10(f) - lf0) / (lf1 - lf0) * (W - L - R)
    Y = lambda d: T + (ymax - d) / (ymax - ymin) * (H - T - B)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for dec in (10, 100, 1000, 10000):
        for m in range(1, 10):
            f = dec * m
            if fmin <= f <= fmax:
                d.line([(X(f), T), (X(f), H - B)], fill=(225, 225, 225) if m > 1 else (190, 190, 190))
                if m in (1, 2, 5):
                    d.text((X(f) - 10, H - B + 6), f"{f / 1000:g}k" if f >= 1000 else f"{f:g}", fill=(80, 80, 80))
    for v in range(-160, 1, 20):
        d.line([(L, Y(v)), (W - R, Y(v))], fill=(225, 225, 225) if v else (160, 160, 160))
        d.text((8, Y(v) - 6), f"{v} dB", fill=(80, 80, 80))
    d.text((L, 10), title, fill=(0, 0, 0))
    for i, (label, spec, ref, colour) in enumerate(curves):
        f = np.arange(len(spec.p)) * spec.df
        sel = (f >= fmin) & (f <= fmax)
        cols = np.array([X(v) for v in f[sel]]).astype(int)
        vals = 10 * np.log10(np.maximum(spec.p[sel] * spec.enbw / ref, 1e-30))   # tones at their true level
        top = {}
        for c, v in zip(cols, vals):                     # peak per pixel column, so every tone shows
            top[c] = max(v, top.get(c, -1e9))
        pts = [(c, Y(min(max(v, ymin), ymax))) for c, v in sorted(top.items())]
        d.line(pts, fill=colour, width=1)
        d.text((W - R - 200, T + 8 + 16 * i), f"--  {label}", fill=colour)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return True


# ------------------------------------------------------------------------------------------- null test
def fft_conv(x, h):
    n = len(x) + len(h) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(h, N), N)[:n]


def frac_delay(x, d):
    """x delayed by d samples (any real d), by a phase ramp; x is padded so nothing wraps."""
    N = 1 << (len(x) + 4096).bit_length()
    k = np.fft.rfftfreq(N)
    return np.fft.irfft(np.fft.rfft(x, N) * np.exp(-2j * np.pi * k * d), N)[:len(x)]


def coarse_lag(a, b, fs, span=30.0):
    """Lag d (samples, fractional) with b[n] ~ a[n - d], from the first `span` seconds of each."""
    a, b = a[:int(span * fs)], b[:int(span * fs)]
    N = 1 << (len(a) + len(b)).bit_length()
    r = np.fft.irfft(np.fft.rfft(b, N) * np.conj(np.fft.rfft(a, N)), N)
    k = int(np.argmax(np.abs(r)))
    y0, y1, y2 = r[k - 1], r[k], r[(k + 1) % N]
    den = y0 - 2 * y1 + y2
    d = k + (0.5 * (y0 - y2) / den if den else 0.0)
    return d - N if k > N // 2 else d


def welch_cross(a, b, nseg):
    w = np.hanning(nseg)
    saa = sbb = sab = 0.0
    for i in range(0, len(a) - nseg + 1, nseg // 2):
        A = np.fft.rfft(w * a[i:i + nseg])
        B = np.fft.rfft(w * b[i:i + nseg])
        saa, sbb, sab = saa + np.abs(A) ** 2, sbb + np.abs(B) ** 2, sab + np.conj(A) * B
    return saa, sbb, sab


def psd(x, nseg):
    _, s, _ = welch_cross(x, x, nseg)
    return s


def align(a, b, fs):
    """a and b cut to their overlap and a shifted so that b[n] ~ g a[n]; returns (a, b, lag in samples)."""
    lag = coarse_lag(a, b, fs)
    di = int(math.floor(lag))
    if di >= 0:
        b = b[di:]
    else:
        a = a[-di:]
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    total = lag - di
    a = frac_delay(a, total)
    nseg = 1 << int(round(math.log2(fs * 0.085)))
    for _ in range(2):                                   # refine by the phase slope where coherence is high
        saa, sbb, sab = welch_cross(a, b, nseg)
        f = np.fft.rfftfreq(nseg, 1 / fs)
        coh = np.abs(sab) ** 2 / np.maximum(saa * sbb, 1e-300)
        sel = (coh > 0.98) & (f > 50) & (f < 0.4 * fs)
        if sel.sum() < 10:
            break
        x = 2 * np.pi * f[sel] / fs
        wt = coh[sel] * saa[sel]
        tau = -float(np.sum(wt * np.angle(sab[sel]) * x) / np.sum(wt * x * x))
        a = frac_delay(a, tau)
        total += tau
    return a, b, di + total


def null(a, b, fs, taps=1024):
    """Plain null (gain and delay only) and matched null (after the best linear filter)."""
    a, b, lag = align(a, b, fs)
    edge = max(taps, int(0.1 * fs))
    g = float(np.dot(a, b) / np.dot(a, a))
    plain = b - g * a
    nseg = 1 << int(round(math.log2(fs * 0.085)))
    saa, sbb, sab = welch_cross(a, b, nseg)
    # Where the signal has no energy (below 20 Hz, above 20 kHz, gaps in a loop) the estimate is noise and
    # a sharp edge to it rings longer than the taps: pull H to the plain gain there.
    lam = 1e-7 * saa.max()
    H = (sab + lam * g) / (saa + lam)
    h = np.fft.irfft(H, nseg)
    kern = np.r_[h[-taps // 2:], h[:taps // 2]]
    taper = np.ones(taps)
    q = taps // 4
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(q) / q)
    taper[:q], taper[-q:] = ramp, ramp[::-1]
    y = fft_conv(a, kern * taper)[taps // 2:taps // 2 + len(a)]
    matched = b - y
    sl = slice(edge, len(b) - edge)
    f = np.fft.rfftfreq(nseg, 1 / fs)
    coh = np.abs(sab) ** 2 / np.maximum(saa * sbb, 1e-300)
    resp = {}
    i1k = int(np.argmin(np.abs(f - 1000)))
    for fr in (100, 1000, 5000, 10000, 15000, 20000):
        i = int(np.argmin(np.abs(f - fr)))
        if fr < BAND_EDGE * fs and coh[i] > 0.9:
            resp[fr] = 20 * math.log10(abs(H[i]) / abs(H[i1k]))
    return {"b": b[sl], "plain": plain[sl], "matched": matched[sl], "lag": lag, "gain": g, "resp": resp,
            "nseg": nseg, "fs": fs}


OCTAVES = [31.5 * 2 ** i for i in range(10)]          # 31.5 Hz .. 16 kHz


def band_table(r, fs):
    """Signal and residual power per octave band, dB re the whole signal."""
    nseg = r["nseg"]
    f = np.fft.rfftfreq(nseg, 1 / fs)
    total = float(psd(r["b"], nseg).sum())
    out = {}
    for key in ("b", "matched"):
        s = psd(r[key], nseg)
        out[key] = [db(float(s[(f >= c / 2 ** 0.5) & (f < c * 2 ** 0.5)].sum()) / total)
                    for c in OCTAVES if c * 2 ** 0.5 < BAND_EDGE * fs]
    return out


def cmd_null(args):
    a, fs = read_wav(args.without, args.channel)
    b, fsb = read_wav(args.with_, args.channel)
    if fs != fsb:
        raise SystemExit("the two recordings have different sample rates")
    floor = None
    if args.floor:
        a2, fs2 = read_wav(args.floor, args.channel)
        floor = null(a, a2, fs)
    print(null_text(Path(args.with_).stem, null(a, b, fs), floor, Path(args.out)))


def null_text(name, r, floor, out):
    fs = r["fs"]
    pb = float(np.mean(r["b"] ** 2))
    lv = lambda x: db(float(np.mean(x ** 2)) / pb)
    rows = [f"{name}: null test, lag {r['lag']:+.2f} samples, gain {db(r['gain'] ** 2):+.3f} dB, "
            f"{len(r['b']) / fs:.1f} s compared"]
    rows.append(f"  {'residual, dB re the signal':<32}{'with':>9}" + (f"{'floor':>9}{'above':>9}" if floor else ""))
    for key, label in (("plain", "gain and delay matched"), ("matched", "after the best linear filter")):
        t = f"  {label:<32}{lv(r[key]):>9.1f}"
        if floor:
            pf = db(float(np.mean(floor[key] ** 2)) / float(np.mean(floor['b'] ** 2)))
            t += f"{pf:>9.1f}{lv(r[key]) - pf:>+9.1f}"
        rows.append(t)
    if r["resp"]:
        rows.append("  linear change with the part, re 1 kHz: " +
                    ", ".join(f"{k / 1000:g}k {v:+.2f} dB" for k, v in r["resp"].items()))
    bt = band_table(r, fs)
    bf = band_table(floor, fs) if floor else None
    rows.append(f"  octave band  {'signal':>8}{'residual':>10}" + (f"{'floor':>8}{'above':>8}" if floor else "")
                + "   (dB re the whole signal)")
    for i, c in enumerate(OCTAVES[:len(bt['b'])]):
        t = f"  {c:>8.0f} Hz {bt['b'][i]:>8.1f}{bt['matched'][i]:>10.1f}"
        if bf:
            t += f"{bf['matched'][i]:>8.1f}{bt['matched'][i] - bf['matched'][i]:>+8.1f}"
        rows.append(t)
    peak = max(np.max(np.abs(r["matched"])), np.max(np.abs(floor["matched"])) if floor else 0.0)
    gain = 10 ** (-1 / 20) / max(peak, 1e-12)
    write_wav(out / f"{name}-residual.wav", r["matched"] * gain, fs)
    written = [f"{name}-residual.wav"]
    if floor:
        write_wav(out / f"{name}-floor-residual.wav", floor["matched"] * gain, fs)
        written.append(f"{name}-floor-residual.wav")
    rows.append(f"  wrote {', '.join(str(out / w) for w in written)}: the residual after the linear filter, "
                f"boosted {20 * math.log10(gain):+.0f} dB (the same boost on both). Turn the monitors down first.")
    return "\n".join(rows)


# ------------------------------------------------------------------------------------------------ report
def cmd_report(args):
    da, dbb = Path(args.without), Path(args.with_)
    df = Path(args.floor) if args.floor else None
    out = Path(args.out)
    names = sorted(p.stem for p in da.glob("*.wav") if (dbb / p.name).exists())
    if not names:
        raise SystemExit(f"no recording has the same file name in {da} and {dbb}")
    vscale = None
    cal = next((n for n in names if n.startswith("cal")), None)
    if cal and args.cal_vrms:
        vscale = volts_scale(da / f"{cal}.wav", args.cal_vrms, args.channel)
    order = ["cal", "sine-1k", "sine-10k", "sine", "ccif", "smpte"]
    rank = lambda n: next((i for i, o in enumerate(order) if n.startswith(o)), len(order))
    for name in sorted(names, key=lambda n: (rank(n), n)):
        a, fs = read_wav(da / f"{name}.wav", args.channel)
        b, fsb = read_wav(dbb / f"{name}.wav", args.channel)
        if fs != fsb:
            print(f"{name}: different sample rates ({fs} / {fsb} Hz), skipped\n")
            continue
        if name.startswith("cal"):
            ma, mb = measure(a, fs), measure(b, fs)
            change = db(mb["ref"] / ma["ref"])
            print(f"{name}: {level_text(ma['ref'], vscale)} without, {level_text(mb['ref'], vscale)} with, "
                  f"{change:+.3f} dB" + ("" if abs(change) < 0.05 else
                                         "   <- the level moved between the runs: check knobs and cables"))
            print()
        elif name.split("-")[0] in ("sine", "ccif", "smpte"):
            ma, mb = measure(a, fs), measure(b, fs)
            print(compare_text(name, ma, mb, vscale))
            png = out / f"{name}.png"
            if plot_spectra(png, f"{name}: without (blue) and with (orange) the PhotoMOS, dB re the tone",
                            [("without", ma["spec"], ma["ref"], (40, 90, 200)),
                             ("with", mb["spec"], mb["ref"], (230, 120, 20))]):
                print(f"  spectra: {png}")
            print()
        else:
            floor = None
            if df and (df / f"{name}.wav").exists():
                a2, _ = read_wav(df / f"{name}.wav", args.channel)
                floor = null(a, a2, fs)
            print(null_text(name, null(a, b, fs), floor, out))
            print()


# ---------------------------------------------------------------------------------------------- selftest
def cmd_selftest(_args):
    """Known answers: injected harmonics, IMD products and a non-linear term must come back as put in."""
    rng = np.random.default_rng(7)
    fails = []

    def check(label, got, want, tol):
        ok = abs(got - want) <= tol
        print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got:.3f} (want {want:.3f} +- {tol})")
        if not ok:
            fails.append(label)

    fs = 96000
    t = np.arange(int(6 * fs)) / fs
    noise = lambda lvl: rng.normal(size=len(t)) * 10 ** (lvl / 20)
    path = Path(__file__).resolve().parent / "selftest-tmp.wav"
    x = 0.5 * np.sin(2 * np.pi * 1000.37 * t) + 0.3 * np.sin(2 * np.pi * 3333.3 * t)
    write_wav(path, x, fs)
    y, _ = read_wav(path)
    path.unlink()
    check("24-bit WAV round trip, worst error in LSBs", float(np.max(np.abs(y - x)) * (1 << 23)), 0.25, 0.25)

    print("THD, 1000.37 Hz at -6 dBFS with H2 -70 dB, H3 -80 dB, H5 -100 dB, noise -120 dBFS rms:")
    f0, a0 = 1000.37, 0.5
    x = (a0 * np.sin(2 * np.pi * f0 * t) + a0 * 10 ** (-70 / 20) * np.sin(2 * np.pi * 2 * f0 * t + 0.3)
         + a0 * 10 ** (-80 / 20) * np.sin(2 * np.pi * 3 * f0 * t + 1.1)
         + a0 * 10 ** (-100 / 20) * np.sin(2 * np.pi * 5 * f0 * t) + noise(-120))
    m = measure(x, fs)
    h = {r[0]: db(r[2] / m["ref"]) for r in m["rows"]}
    check("kind is sine", float(m["kind"] == "sine"), 1.0, 0)
    check("fundamental, Hz", m["f"], f0, 0.05)
    check("level, dBFS", db(2 * m["ref"]), -6.02, 0.02)
    check("H2, dB", h["H2"], -70, 0.1)
    check("H3, dB", h["H3"], -80, 0.1)
    check("H5, dB", h["H5"], -100, 0.3)
    check("THD, %", 100 * m["total"], 100 * math.sqrt(1e-7 + 1e-8 + 1e-10), 0.0005)

    print("CCIF 19 + 20 kHz, each -12 dBFS, d2 -80 dB, d3 at 18 k -70 dB and 21 k -75 dB:")
    x = (0.25 * np.sin(2 * np.pi * 19000 * t) + 0.25 * np.sin(2 * np.pi * 20000 * t)
         + 0.25 * 10 ** (-80 / 20) * np.sin(2 * np.pi * 1000 * t) + 0.25 * 10 ** (-70 / 20) * np.sin(2 * np.pi * 18000 * t)
         + 0.25 * 10 ** (-75 / 20) * np.sin(2 * np.pi * 21000 * t) + noise(-120))
    m = measure(x, fs)
    p = {r[0]: db(r[2] / m["ref"]) for r in m["rows"]}
    check("kind is ccif", float(m["kind"] == "ccif"), 1.0, 0)
    check("d2 f2-f1, dB", p["d2 f2-f1"], -80, 0.2)
    check("d3 2f1-f2, dB", p["d3 2f1-f2"], -70, 0.1)
    check("d3 2f2-f1, dB", p["d3 2f2-f1"], -75, 0.1)

    print("SMPTE 60 Hz + 7 kHz 4:1, sidebands +-60 Hz at -60 dB and +-120 Hz at -70 dB:")
    x = 0.4 * np.sin(2 * np.pi * 60 * t) + 0.1 * np.sin(2 * np.pi * 7000 * t) + noise(-120)
    for n, lvl in ((1, -60), (2, -70)):
        for s in (-1, 1):
            x = x + 0.1 * 10 ** (lvl / 20) * np.sin(2 * np.pi * (7000 + s * n * 60) * t + n)
    m = measure(x, fs)
    check("kind is smpte", float(m["kind"] == "smpte"), 1.0, 0)
    check("IMD total, %", 100 * m["total"], 100 * math.sqrt(2e-6 + 2e-7), 0.002)

    print("Null: pink noise, 'with' = 0.9 x a 3-tap low-pass, 1234.37 samples late, plus a non-linear term "
          "orthogonal to the signal (Hermite) at -60 dB, noise -110 dB:")
    pn = make_signal(NOISE, fs, seconds=8.0)[int(LEAD * fs):-int(LEAD * fs)]
    sd = float(np.std(pn))
    u = pn / sd
    nl = (u ** 3 - 3 * u) / math.sqrt(6) * sd * 10 ** (-60 / 20)        # He3, unit variance -> -60 dB re pn
    lp = np.convolve(pn, [0.05, 0.9, 0.05], mode="same") * 0.9
    tail = lambda v: np.r_[np.zeros(3000), v, np.zeros(3000)]
    a = tail(pn) + rng.normal(size=len(pn) + 6000) * sd * 10 ** (-110 / 20)
    b = frac_delay(tail(lp + nl * 0.9), 1234.37) + rng.normal(size=len(pn) + 6000) * sd * 10 ** (-110 / 20)
    r = null(a, b, fs)
    want = db(float(np.mean((nl * 0.9) ** 2)) / float(np.mean(lp ** 2)))
    check("lag, samples", r["lag"], 1234.37, 0.02)
    check("matched null, dB re signal", db(float(np.mean(r["matched"] ** 2)) / float(np.mean(r["b"] ** 2))), want, 0.5)
    a2 = tail(pn) + rng.normal(size=len(pn) + 6000) * sd * 10 ** (-110 / 20)
    rf = null(a, a2, fs)
    check("floor null (two takes, noise only), dB", db(float(np.mean(rf["matched"] ** 2)) / float(np.mean(rf["b"] ** 2))),
          -107.0, 1.5)
    print("selftest:", "all passed" if not fails else f"{len(fails)} FAILED: {', '.join(fails)}")
    return 1 if fails else 0


# -------------------------------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--channel", type=int, default=0, help="channel of the recordings to analyse (0 = left)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("tones", help="write the test signals")
    s.add_argument("--rate", type=int, default=96000)
    s.add_argument("--out", default="tones")
    s = sub.add_parser("analyse", parents=[common], help="THD or IMD of recordings")
    s.add_argument("files", nargs="+")
    s.add_argument("--cal", nargs=2, metavar=("CAL.wav", "VRMS"), help="recorded 50 Hz tone and the meter's V rms")
    s = sub.add_parser("null", parents=[common], help="subtract two recordings of the same signal")
    s.add_argument("without")
    s.add_argument("with_", metavar="with")
    s.add_argument("--floor", help="a second recording without the part: the floor of the method")
    s.add_argument("--out", default="results")
    s = sub.add_parser("report", parents=[common], help="compare every recording in two folders")
    s.add_argument("without")
    s.add_argument("with_", metavar="with")
    s.add_argument("--floor", help="folder with a second take without the part")
    s.add_argument("--cal-vrms", type=float, help="the meter's V rms on the 50 Hz tone at the follower's output")
    s.add_argument("--out", default="results")
    sub.add_parser("selftest", help="check the analysis against known answers")
    args = ap.parse_args(argv)
    return {"tones": cmd_tones, "analyse": cmd_analyse, "null": cmd_null, "report": cmd_report,
            "selftest": cmd_selftest}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
