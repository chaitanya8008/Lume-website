"""Render Lume Reels (1080x1920 MP4, H.264 + AAC) from site photos and workshop clips.

usage: python reels.py render r1 [r2 ...]
       python reels.py preview r1 0.8 4.2 ...   (writes JPG stills to scratch/reels/)
"""
import math
import os
import subprocess
import sys
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SITE = r'C:\Users\CHAITANYA\Downloads\lume-website-updated'
OUT = os.path.join(SITE, 'marketing', 'ads', 'reels')
SCRATCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reels')
FF = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1080, 1920, 30
FD = r'C:\Windows\Fonts'

INK = (11, 13, 15)
PAPER = (238, 241, 244)
DIM = (165, 174, 184)
LED = (223, 233, 245)
GREEN = (37, 211, 102)
WARM = (255, 186, 112)
NEUTRAL = (255, 236, 208)
COOL = (205, 226, 255)

VID = {
    'closeup': os.path.join(SITE, 'videos', 'lume-laser-frosting-closeup.mp4'),
    'machine': os.path.join(SITE, 'videos', 'lume-laser-machine-workshop.mp4'),
    'fibre': os.path.join(SITE, 'videos', 'lume-fibre-laser-frosting-workshop.mp4'),
}

_fonts = {}


def F(name, size):
    k = (name, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(os.path.join(FD, name), size)
    return _fonts[k]


SERIF = lambda s: F('GARA.TTF', s)
SERIF_I = lambda s: F('GARAIT.TTF', s)
SANS = lambda s: F('segoeui.ttf', s)
SANS_L = lambda s: F('segoeuil.ttf', s)
MONO = lambda s: F('consola.ttf', s)
MONO_B = lambda s: F('consolab.ttf', s)
LOGO = lambda s: F('Bodoni Bd BT Bold.ttf', s)


def c01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def eo(x):
    x = c01(x)
    return 1 - (1 - x) ** 3


def eio(x):
    x = c01(x)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- drawing helpers

class TL:
    """A pre-rendered text layer (RGBA uint8) with its padding and visible size."""

    def __init__(self, arr, pad, w, h):
        self.arr, self.pad, self.w, self.h = arr, pad, w, h


def text_layer(text, font, fill=PAPER, spacing=0.0, shadow=0.6, align='center', gap=0.12):
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))

    def lw(s):
        if not spacing:
            return probe.textlength(s, font=font)
        return sum(probe.textlength(c, font=font) for c in s) + font.size * spacing * (len(s) - 1)

    lines = text.split('\n')
    asc, desc = font.getmetrics()
    step = int((asc + desc) * (1 + gap))
    widths = [lw(s) for s in lines]
    tw = int(max(widths)) + 2
    th = step * (len(lines) - 1) + asc + desc
    pad = int(font.size * 0.7) if shadow else 6
    mask = Image.new('L', (tw + 2 * pad, th + 2 * pad), 0)
    d = ImageDraw.Draw(mask)
    for i, s in enumerate(lines):
        if align == 'center':
            x = pad + (tw - widths[i]) / 2
        elif align == 'right':
            x = pad + tw - widths[i]
        else:
            x = pad
        y = pad + i * step
        if spacing:
            for ch in s:
                d.text((x, y), ch, font=font, fill=255)
                x += probe.textlength(ch, font=font) + font.size * spacing
        else:
            d.text((x, y), s, font=font, fill=255)
    m = np.asarray(mask, np.float32) / 255
    if shadow:
        sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(6, font.size * 0.28))), np.float32) / 255
        sh = np.clip(sh * 1.6, 0, 1) * shadow
        a = m + sh * (1 - m)
    else:
        a = m
    rgb = np.zeros(m.shape + (3,), np.float32)
    k = np.divide(m, a, out=np.zeros_like(m), where=a > 1e-4)
    for c in range(3):
        rgb[..., c] = fill[c] * k
    arr = np.dstack([rgb, a * 255]).astype(np.uint8)
    return TL(arr, pad, tw, th)


def blit(dst, src, x, y, op=1.0):
    """Alpha-composite an RGBA uint8 array onto a float32 RGB frame at (x, y)."""
    if op <= 0.003:
        return
    h, w = src.shape[:2]
    x, y = int(round(x)), int(round(y))
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dst.shape[1], x + w), min(dst.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x].astype(np.float32)
    a = s[..., 3:4] * (op / 255.0)
    d = dst[y0:y1, x0:x1]
    d *= 1 - a
    d += s[..., :3] * a


def place(dst, tl, cx, y, op=1.0, dy=0.0, align='center'):
    """Draw text layer so its visible block is horizontally centred on cx with top at y."""
    if align == 'center':
        x = cx - tl.w / 2 - tl.pad
    elif align == 'left':
        x = cx - tl.pad
    else:
        x = cx - tl.w - tl.pad
    blit(dst, tl.arr, x, y - tl.pad + dy, op)


def vgrad(h, a0, a1, power=1.4):
    t = np.linspace(0, 1, h, dtype=np.float32) ** power
    return (a0 + (a1 - a0) * t)[:, None, None]


SCRIM_TOP = vgrad(int(H * 0.28), 0.55, 0.0)
SCRIM_BOT = vgrad(int(H * 0.62), 0.0, 0.88, 1.2)


_yy = np.linspace(0, 1, H, dtype=np.float32)
TEXT_BAND = (np.exp(-((_yy - 0.60) / 0.13) ** 2) * 0.55)[:, None, None]


def scrim(dst, strength=1.0):
    ht = SCRIM_TOP.shape[0]
    dst[:ht] *= 1 - SCRIM_TOP * strength
    hb = SCRIM_BOT.shape[0]
    dst[H - hb:] *= 1 - SCRIM_BOT * strength
    dst *= 1 - TEXT_BAND * strength


def radial(cx, cy, r, color, alpha):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 0.85) ** 2) / r
    a = np.clip(1 - d, 0, 1) ** 2 * alpha
    return np.dstack([np.full((H, W), color[0]), np.full((H, W), color[1]), np.full((H, W), color[2]), a * 255]).astype(np.uint8)


def rounded_mask(w, h, r, scale=3):
    m = Image.new('L', (w * scale, h * scale), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), r * scale, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def load(name):
    return Image.open(os.path.join(SITE, 'images', name)).convert('RGB')


def cover(im, w, h, fx=0.5, fy=0.5):
    s = max(w / im.width, h / im.height)
    r = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    x = int((r.width - w) * fx)
    y = int((r.height - h) * fy)
    return r.crop((x, y, x + w, y + h))


def blurred_bg(im, darkness=0.30):
    bg = cover(im, W // 4, H // 4).filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BILINEAR)
    a = np.asarray(bg, np.float32) * darkness + np.array(INK, np.float32) * (1 - darkness) * 0.6
    return a.astype(np.uint8)


def led_line(dst, cx, y, width, color=LED, op=1.0):
    """A glowing horizontal LED strip."""
    if width < 2:
        return
    w = int(width)
    pad = 40
    m = Image.new('L', (w + 2 * pad, 2 * pad + 4), 0)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, pad + w, pad + 3), 2, fill=255)
    core = np.asarray(m, np.float32) / 255
    glow = np.asarray(m.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
    a = np.clip(core + glow * 2.2, 0, 1)
    arr = np.dstack([np.full(a.shape, color[0]), np.full(a.shape, color[1]), np.full(a.shape, color[2]), a * 255]).astype(np.uint8)
    blit(dst, arr, cx - w / 2 - pad, y - pad, op)


# ---------------------------------------------------------------- animated text

class Txt:
    def __init__(self, tl, cx, y, t_in=0.0, t_out=None, rise=34, dur=0.55, align='center'):
        self.tl, self.cx, self.y, self.t_in, self.t_out, self.rise, self.dur, self.align = tl, cx, y, t_in, t_out, rise, dur, align

    def render(self, dst, t):
        p = eo((t - self.t_in) / self.dur)
        op = p
        if self.t_out is not None:
            op *= 1 - eio((t - self.t_out) / 0.35)
        if op > 0:
            place(dst, self.tl, self.cx, self.y, op, (1 - p) * self.rise, self.align)


def lines(text, font, y, t0, fill=PAPER, stagger=0.12, gap=0.10, cx=W / 2, **kw):
    """Headline split into lines that rise in one after another. Returns (items, bottom_y)."""
    out = []
    asc, desc = font.getmetrics()
    step = int((asc + desc) * (1 + gap))
    for i, s in enumerate(text.split('\n')):
        out.append(Txt(text_layer(s, font, fill), cx, y + i * step, t0 + i * stagger, **kw))
    return out, y + (len(text.split('\n')) - 1) * step + asc + desc


def label(text, y, t0, fill=(200, 208, 216), size=31, **kw):
    return Txt(text_layer(text, MONO_B(size), fill, spacing=0.30, shadow=0.85), W / 2, y, t0, **kw)


class Count:
    """A number that counts up, re-rendered per frame."""

    def __init__(self, value, fmt, font, y, t0, dur=0.9, fill=PAPER, suffix=''):
        self.value, self.fmt, self.font, self.y, self.t0, self.dur, self.fill, self.suffix = value, fmt, font, y, t0, dur, fill, suffix
        self.cache = {}

    def render(self, dst, t):
        p = eo((t - self.t0) / self.dur)
        if p <= 0:
            return
        v = int(round(self.value * p))
        s = self.fmt(v) + self.suffix
        if s not in self.cache:
            self.cache[s] = text_layer(s, self.font, self.fill)
        place(dst, self.cache[s], W / 2, self.y, eo((t - self.t0) / 0.3), (1 - eo((t - self.t0) / 0.5)) * 30)


def indian(n):
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ','.join(parts + [tail])


# ---------------------------------------------------------------- scenes

class Scene:
    xf = 0.3

    def __init__(self, dur, items=(), xf=0.3):
        self.dur, self.items, self.xf = dur, list(items), xf

    def draw_bg(self, dst, t):
        dst[:] = INK

    def render(self, dst, t):
        self.draw_bg(dst, t)
        for it in self.items:
            it.render(dst, t)


class Clip:
    def __init__(self, key, ss):
        self.path, self.ss = VID[key], ss
        self.p = None
        self.idx = -1
        self.cur = None

    def _start(self, t):
        if self.p:
            self.p.kill()
        vf = 'fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d' % (FPS, W, H, W, H)
        self.p = subprocess.Popen([FF, '-v', 'error', '-ss', '%.3f' % (self.ss + t), '-i', self.path, '-an', '-vf', vf,
                                   '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)
        self.idx = int(round(t * FPS)) - 1

    def get(self, t):
        want = int(round(t * FPS))
        if self.p is None or want < self.idx or want > self.idx + 45:
            self._start(t)
        while self.idx < want:
            buf = self.p.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            self.cur = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            self.idx += 1
        return self.cur

    def close(self):
        if self.p:
            self.p.kill()
            self.p = None


class VideoScene(Scene):
    def __init__(self, key, ss, dur, items=(), zoom=(1.0, 1.08), dim=0.0, scrim=1.0, xf=0.3, focus=(0.5, 0.5)):
        super().__init__(dur, items, xf)
        self.clip = Clip(key, ss)
        self.zoom, self.dim, self.scrim, self.focus = zoom, dim, scrim, focus

    def draw_bg(self, dst, t):
        fr = self.clip.get(t)
        if fr is None:
            dst[:] = INK
            return
        z = self.zoom[0] + (self.zoom[1] - self.zoom[0]) * (t / self.dur)
        if z > 1.001:
            cw, ch = W / z, H / z
            x0 = (W - cw) * self.focus[0]
            y0 = (H - ch) * self.focus[1]
            im = Image.fromarray(fr).resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
            dst[:] = np.asarray(im, np.float32)
        else:
            dst[:] = fr
        if self.dim:
            dst *= 1 - self.dim
        if self.scrim:
            scrim(dst, self.scrim)


class Card:
    """A photo in a rounded card with shadow and a slow push-in."""

    def __init__(self, name, maxw, maxh, fy=0.5):
        im = load(name)
        s = min(maxw / im.width, maxh / im.height)
        self.w, self.h = int(im.width * s), int(im.height * s)
        self.big = im.resize((int(self.w * 1.1), int(self.h * 1.1)), Image.LANCZOS)
        self.mask = np.asarray(rounded_mask(self.w, self.h, 26), np.float32)[..., None] / 255
        pad = 70
        sm = Image.new('L', (self.w + 2 * pad, self.h + 2 * pad), 0)
        ImageDraw.Draw(sm).rounded_rectangle((pad, pad + 18, pad + self.w, pad + self.h + 18), 26, fill=190)
        sm = sm.filter(ImageFilter.GaussianBlur(30))
        self.shadow = np.dstack([np.zeros((sm.height, sm.width, 3), np.uint8), np.asarray(sm)]).astype(np.uint8)
        self.shpad = pad
        bm = Image.new('L', (self.w, self.h), 0)
        ImageDraw.Draw(bm).rounded_rectangle((0, 0, self.w - 1, self.h - 1), 26, outline=255, width=2)
        b = np.asarray(bm, np.float32)[..., None] / 255 * 0.28
        self.border = b
        self.bg = blurred_bg(im)

    def render(self, dst, cx, cy, p, op=1.0):
        z = 1.0 + 0.07 * p
        bw, bh = self.big.size
        cw, ch = bw / z, bh / z
        x0, y0 = (bw - cw) / 2, (bh - ch) / 2
        im = np.asarray(self.big.resize((self.w, self.h), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)), np.float32)
        im = im * (1 - self.border) + np.array(LED, np.float32) * self.border
        x, y = int(cx - self.w / 2), int(cy - self.h / 2)
        blit(dst, self.shadow, x - self.shpad, y - self.shpad, op)
        rgba = np.dstack([im, self.mask[..., 0] * 255 * 1.0]).astype(np.uint8)
        blit(dst, rgba, x, y, op)


class CardScene(Scene):
    """One or more photos in a card, cut quickly, with persistent text and optional per-photo captions."""

    def __init__(self, photos, per, items=(), captions=None, cy=0.36, maxw=0.80, maxh=0.42, xf=0.3, cap_y=None):
        super().__init__(per * len(photos), items, xf)
        self.cards = [Card(p, int(W * maxw), int(H * maxh)) for p in photos]
        self.per, self.cy = per, H * cy
        self.caps = [text_layer(c, MONO_B(30), (205, 212, 220), spacing=0.25, shadow=0.8) for c in captions] if captions else None
        self.cap_y = cap_y

    def _idx(self, t):
        return min(len(self.cards) - 1, int(t / self.per))

    def draw_bg(self, dst, t):
        i = self._idx(t)
        lt = t - i * self.per
        cut = 0.14
        dst[:] = self.cards[i].bg
        if i > 0 and lt < cut:
            a = eio(lt / cut)
            dst[:] = self.cards[i - 1].bg * (1 - a) + dst * a
        if i > 0 and lt < cut:
            self.cards[i - 1].render(dst, W / 2, self.cy, 1.0, 1 - eio(lt / cut))
        self.cards[i].render(dst, W / 2, self.cy, c01(lt / (self.per + 0.4)) + (0.0 if i == 0 else 0.0), eio(lt / cut) if i > 0 else 1)
        if self.caps:
            y = self.cap_y if self.cap_y else self.cy + self.cards[i].h / 2 + 34
            place(dst, self.caps[i], W / 2, y, eo(lt / 0.3), (1 - eo(lt / 0.3)) * 14)


class EndCard(Scene):
    def __init__(self, dur, tagline='Any shape. Any size.\nLit to order.', extra=None, xf=0.35):
        super().__init__(dur, (), xf)
        self.glow = radial(W / 2, H * 0.36, W * 0.85, LED, 0.13)
        self.logo = text_layer('LUME', LOGO(150), PAPER, spacing=0.30, shadow=0)
        self.sub = text_layer('LED MIRRORS', MONO(30), DIM, spacing=0.55, shadow=0)
        self.tag, _ = lines(tagline, SERIF(88), int(H * 0.455), 0.55, stagger=0.14)
        y_chip = int(H * 0.615)
        self.chip_y = y_chip
        self.wa = text_layer('WhatsApp  +91 62832 25517', SANS(42), PAPER, shadow=0)
        self.url = text_layer('lume.co.in', MONO(36), LED, spacing=0.18, shadow=0)
        self.extra = text_layer(extra, MONO(26), DIM, spacing=0.28, shadow=0) if extra else None
        cw, chh = int(self.wa.w + 120), 96
        m = rounded_mask(cw, chh, chh // 2)
        bm = Image.new('L', (cw, chh), 0)
        ImageDraw.Draw(bm).rounded_rectangle((1, 1, cw - 2, chh - 2), chh // 2 - 1, outline=255, width=2)
        a = np.asarray(m, np.float32) / 255 * 0.10 + np.asarray(bm, np.float32) / 255 * 0.45
        self.chip = np.dstack([np.full(a.shape, 255.0), np.full(a.shape, 255.0), np.full(a.shape, 255.0), a * 255]).astype(np.uint8)
        dm = Image.new('L', (60, 60), 0)
        ImageDraw.Draw(dm).ellipse((18, 18, 42, 42), fill=255)
        dm2 = dm.filter(ImageFilter.GaussianBlur(6))
        da = np.clip(np.asarray(dm, np.float32) / 255 + np.asarray(dm2, np.float32) / 255 * 0.8, 0, 1)
        self.dot = np.dstack([np.full(da.shape, GREEN[0]), np.full(da.shape, GREEN[1]), np.full(da.shape, GREEN[2]), da * 255]).astype(np.uint8)
        self.cw, self.chh = cw, chh

    def draw_bg(self, dst, t):
        dst[:] = INK
        blit(dst, self.glow, 0, 0, eo(t / 0.8))

    def render(self, dst, t):
        self.draw_bg(dst, t)
        y0 = H * 0.255
        p = eo(t / 0.6)
        place(dst, self.logo, W / 2, y0, p, (1 - p) * 26)
        place(dst, self.sub, W / 2, y0 + 190, eo((t - 0.15) / 0.6))
        led_line(dst, W / 2, y0 + 262, 560 * eo((t - 0.25) / 0.9), LED, 1.0)
        for it in self.tag:
            it.render(dst, t)
        q = eo((t - 1.0) / 0.5)
        cx = W / 2
        blit(dst, self.chip, cx - self.cw / 2, self.chip_y + (1 - q) * 24, q)
        blit(dst, self.dot, cx - self.cw / 2 + 26, self.chip_y + self.chh / 2 - 30 + (1 - q) * 24, q)
        place(dst, self.wa, cx + 22, self.chip_y + (self.chh - self.wa.h) / 2 - 6 + (1 - q) * 24, q)
        r = eo((t - 1.25) / 0.5)
        place(dst, self.url, cx, self.chip_y + self.chh + 44, r, (1 - r) * 20)
        if self.extra:
            place(dst, self.extra, cx, self.chip_y + self.chh + 112, eo((t - 1.45) / 0.5))
        # gentle fade to black over the last 0.5 s
        tail = c01((t - (self.dur - 0.5)) / 0.5)
        if tail:
            dst *= 1 - 0.85 * tail


class TraceScene(Scene):
    """An LED line traces an organic mirror outline, then the inside softly lights."""

    def __init__(self, dur, items=(), cy=0.355, rx=300, ry=410, draw_time=1.5, xf=0.3):
        super().__init__(dur, items, xf)
        n = 600
        th = np.linspace(-math.pi / 2, 3 * math.pi / 2, n)
        r = 1 + 0.10 * np.sin(2 * th + 0.6) + 0.06 * np.sin(3 * th + 1.9) + 0.03 * np.sin(5 * th)
        self.pts = list(zip(W / 2 + rx * r * np.cos(th), H * cy + ry * r * np.sin(th)))
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        self.box = (int(min(xs)) - 80, int(min(ys)) - 80, int(max(xs)) + 80, int(max(ys)) + 80)
        self.draw_time = draw_time
        bx0, by0, bx1, by1 = self.box
        fm = Image.new('L', (bx1 - bx0, by1 - by0), 0)
        ImageDraw.Draw(fm).polygon([(x - bx0, y - by0) for x, y in self.pts], fill=255)
        f = np.asarray(fm.filter(ImageFilter.GaussianBlur(3)), np.float32) / 255
        yy = np.linspace(0, 1, f.shape[0], dtype=np.float32)[:, None]
        self.fill = f * (0.05 + 0.10 * (1 - yy))
        self.glow = radial(W / 2, H * cy, W * 0.8, LED, 0.10)

    def render(self, dst, t):
        dst[:] = INK
        blit(dst, self.glow, 0, 0, eo((t - 0.3) / 1.2))
        p = eo(t / self.draw_time)
        k = max(2, int(len(self.pts) * p))
        bx0, by0, bx1, by1 = self.box
        m = Image.new('L', (bx1 - bx0, by1 - by0), 0)
        ImageDraw.Draw(m).line([(x - bx0, y - by0) for x, y in self.pts[:k]], fill=255, width=7, joint='curve')
        core = np.asarray(m, np.float32) / 255
        glow = np.asarray(m.resize((m.width // 4, m.height // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5)).resize(m.size, Image.BILINEAR), np.float32) / 255
        a = np.clip(core + glow * 2.6, 0, 1)
        fa = self.fill * eo((t - self.draw_time + 0.2) / 0.8)
        a = np.clip(a + fa, 0, 1)
        arr = np.dstack([np.full(a.shape, LED[0]), np.full(a.shape, LED[1]), np.full(a.shape, LED[2]), a * 255]).astype(np.uint8)
        blit(dst, arr, bx0, by0)
        if k < len(self.pts):  # bright head of the line
            hx, hy = self.pts[k - 1]
            hm = Image.new('L', (80, 80), 0)
            ImageDraw.Draw(hm).ellipse((30, 30, 50, 50), fill=255)
            ha = np.asarray(hm.filter(ImageFilter.GaussianBlur(9)), np.float32) / 255 * 2.5
            ha = np.clip(ha, 0, 1)
            blit(dst, np.dstack([np.full(ha.shape, 255.0)] * 3 + [ha * 255]).astype(np.uint8), hx - 40, hy - 40)
        for it in self.items:
            it.render(dst, t)


class GridScene(Scene):
    """A 3x2 grid of designs; one gets picked and lit."""

    def __init__(self, photos, dur, pick=1, items=(), cy=0.355, xf=0.3):
        super().__init__(dur, items, xf)
        tw, th, g = 296, 370, 22
        self.tw, self.th, self.g = tw, th, g
        self.tiles = []
        m = np.asarray(rounded_mask(tw, th, 18), np.float32)[..., None]
        for p in photos:
            im = np.asarray(cover(load(p), tw, th), np.float32)
            self.tiles.append(np.dstack([im, m[..., 0]]).astype(np.uint8))
        self.pick = pick
        self.x0 = (W - (3 * tw + 2 * g)) / 2
        self.y0 = H * cy - (2 * th + g) / 2
        bm = Image.new('L', (tw + 80, th + 80), 0)
        ImageDraw.Draw(bm).rounded_rectangle((40, 40, 40 + tw, 40 + th), 18, outline=255, width=5)
        core = np.asarray(bm, np.float32) / 255
        glow = np.asarray(bm.filter(ImageFilter.GaussianBlur(16)), np.float32) / 255
        a = np.clip(core + glow * 2.4, 0, 1)
        self.ring = np.dstack([np.full(a.shape, LED[0]), np.full(a.shape, LED[1]), np.full(a.shape, LED[2]), a * 255]).astype(np.uint8)
        self.bgglow = radial(W / 2, H * cy, W * 0.9, LED, 0.07)

    def render(self, dst, t):
        dst[:] = INK
        blit(dst, self.bgglow, 0, 0)
        hp = eo((t - 1.5) / 0.5)
        for i, tile in enumerate(self.tiles):
            c, r = i % 3, i // 3
            x = self.x0 + c * (self.tw + self.g)
            y = self.y0 + r * (self.th + self.g)
            p = eo((t - 0.08 * i) / 0.5)
            op = p * (1 - 0.68 * hp if i != self.pick else 1)
            blit(dst, tile, x, y + (1 - p) * 40, op)
            if i == self.pick and hp > 0:
                blit(dst, self.ring, x - 40, y - 40, hp)
        for it in self.items:
            it.render(dst, t)


class LightScene(Scene):
    """A mirror outline with size markers whose LED edge cycles warm -> neutral -> cool."""

    def __init__(self, dur, items=(), cy=0.33, mw=540, mh=740, xf=0.3):
        super().__init__(dur, items, xf)
        self.cy, self.mw, self.mh = H * cy, mw, mh
        pad = 90
        m = Image.new('L', (mw + 2 * pad, mh + 2 * pad), 0)
        ImageDraw.Draw(m).rounded_rectangle((pad, pad, pad + mw, pad + mh), 44, outline=255, width=8)
        core = np.asarray(m, np.float32) / 255
        glow = np.asarray(m.filter(ImageFilter.GaussianBlur(24)), np.float32) / 255
        self.edge = np.clip(core + glow * 2.8, 0, 1)
        fm = Image.new('L', m.size, 0)
        ImageDraw.Draw(fm).rounded_rectangle((pad + 6, pad + 6, pad + mw - 6, pad + mh - 6), 40, fill=255)
        yy = np.linspace(0, 1, m.height, dtype=np.float32)[:, None]
        xx = np.linspace(0, 1, m.width, dtype=np.float32)[None, :]
        sheen = np.clip(0.10 - 0.18 * np.abs((xx * 0.8 + yy * 0.6) - 0.55), 0, 0.1)
        self.inner = np.asarray(fm, np.float32) / 255 * (0.035 + sheen)
        self.pad = pad
        self.w_lbl = text_layer('24 in', MONO(30), DIM, spacing=0.12, shadow=0)
        hl = text_layer('36 in', MONO(30), DIM, spacing=0.12, shadow=0)
        self.h_lbl = np.ascontiguousarray(np.rot90(hl.arr, 3))
        self.h_lbl_size = hl

    def color(self, t):
        seq = [(0.0, WARM), (1.2, WARM), (1.55, NEUTRAL), (2.3, NEUTRAL), (2.65, COOL), (99, COOL)]
        for (t0, c0), (t1, c1) in zip(seq, seq[1:]):
            if t0 <= t < t1:
                if c0 == c1:
                    return c0
                a = eio((t - t0) / (t1 - t0))
                return tuple(c0[i] + (c1[i] - c0[i]) * a for i in range(3))
        return COOL

    def render(self, dst, t):
        dst[:] = INK
        col = self.color(t)
        on = eo(t / 0.6)
        x = W / 2 - self.mw / 2 - self.pad
        y = self.cy - self.mh / 2 - self.pad
        a = np.clip(self.edge * on + self.inner * on, 0, 1)
        arr = np.dstack([np.full(a.shape, col[0]), np.full(a.shape, col[1]), np.full(a.shape, col[2]), a * 255]).astype(np.uint8)
        blit(dst, arr, x, y)
        q = eo((t - 0.4) / 0.5)
        # width marker above, height marker on the right
        top = self.cy - self.mh / 2 - 58
        lx0, lx1 = W / 2 - self.mw / 2, W / 2 + self.mw / 2
        mk = np.zeros((14, int(self.mw), 4), np.uint8)
        mk[6:8, :, :3] = DIM
        mk[6:8, :, 3] = 200
        mk[:, :2, :3] = DIM
        mk[:, :2, 3] = 200
        mk[:, -2:, :3] = DIM
        mk[:, -2:, 3] = 200
        blit(dst, mk, lx0, top, q)
        blk = np.zeros((self.w_lbl.arr.shape[0], self.w_lbl.arr.shape[1] + 0, 4), np.uint8)
        blk[..., :3] = INK
        blk[..., 3] = 255
        place(dst, self.w_lbl, W / 2, top - 14, q)
        side = W / 2 + self.mw / 2 + 44
        mv = np.ascontiguousarray(np.transpose(mk, (1, 0, 2)))
        mv = np.ascontiguousarray(np.resize(mv, (int(self.mh), 14, 4))) if mv.shape[0] != int(self.mh) else mv
        mvv = np.zeros((int(self.mh), 14, 4), np.uint8)
        mvv[:, 6:8, :3] = DIM
        mvv[:, 6:8, 3] = 200
        mvv[:2, :, :3] = DIM
        mvv[:2, :, 3] = 200
        mvv[-2:, :, :3] = DIM
        mvv[-2:, :, 3] = 200
        blit(dst, mvv, side, self.cy - self.mh / 2, q)
        blit(dst, self.h_lbl, side + 24, self.cy - self.h_lbl.shape[0] / 2, q)
        for it in self.items:
            it.render(dst, t)


class ToneWords:
    """'Warm · Neutral · Cool' with the active tone highlighted in sync with LightScene."""

    def __init__(self, y, t0=0.6):
        self.words = [(text_layer(w, SANS(40), c if True else PAPER, shadow=0), rng) for w, c, rng in
                      (('Warm', WARM, (0, 1.4)), ('Natural', NEUTRAL, (1.4, 2.5)), ('Cool', COOL, (2.5, 99)))]
        self.dot = text_layer('\u00b7', SANS(40), DIM, shadow=0)
        self.y, self.t0 = y, t0
        gap = 26
        total = sum(w.w for w, _ in self.words) + 2 * (self.dot.w + 2 * gap)
        x = W / 2 - total / 2
        self.pos = []
        for i, (w, _) in enumerate(self.words):
            self.pos.append(x)
            x += w.w + gap
            if i < 2:
                self.pos.append(x)
                x += self.dot.w + gap

    def render(self, dst, t):
        base = eo((t - self.t0) / 0.5)
        for i, (w, (a, b)) in enumerate(self.words):
            act = 1.0 if a <= t < b else 0.35
            place(dst, w, self.pos[i * 2], self.y, base * act, align='left')
            if i < 2:
                place(dst, self.dot, self.pos[i * 2 + 1], self.y, base * 0.6, align='left')


def step_text(num, title, sub, y0=None, t0=0.35, sub_fill=DIM):
    y0 = y0 or int(H * 0.585)
    items = [Txt(text_layer(num, MONO_B(36), LED, spacing=0.3, shadow=0.5), W / 2, y0, t0)]
    tl, bottom = lines(title, SERIF(92), y0 + 62, t0 + 0.1, stagger=0.1)
    items += tl
    if sub:
        items.append(Txt(text_layer(sub, SANS(38), sub_fill, shadow=0.8), W / 2, bottom + 22, t0 + 0.35))
    return items


# ---------------------------------------------------------------- music

SR = 44100


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def make_music(path, dur, bpm=100, prog=None, seed=7, drive=1.0, intro_bars=1):
    rng = np.random.default_rng(seed)
    n = int(SR * (dur + 0.2))
    L = np.zeros(n)
    R = np.zeros(n)
    beat = 60.0 / bpm
    bar = 4 * beat
    prog = prog or [([53, 57, 60, 64], 41), ([55, 59, 62, 67], 43), ([52, 55, 59, 64], 40), ([57, 60, 64, 67], 45)]
    nbars = int(math.ceil(dur / bar)) + 1
    end_music = dur - 1.6  # rhythm stops here; pad rings out
    pad_L = np.zeros(n)
    pad_R = np.zeros(n)
    for b in range(nbars):
        chord, root = prog[b % len(prog)]
        s = int(b * bar * SR)
        if s >= n:
            break
        e = min(n, int(((b + 1) * bar + 1.2) * SR))
        tt = np.arange(e - s) / SR
        env = np.minimum(1, tt / 0.45) * np.where(tt < bar, 1.0, np.exp(-(tt - bar) / 0.35))
        for m in chord:
            f = midi_hz(m)
            for det, pan in ((0.996, 0.25), (1.004, 0.75)):
                ph = rng.uniform(0, 2 * np.pi)
                w = np.sin(2 * np.pi * f * det * tt + ph) + 0.30 * np.sin(4 * np.pi * f * det * tt + ph) + 0.10 * np.sin(6 * np.pi * f * det * tt)
                pad_L[s:e] += 0.045 * env * w * (1 - pan)
                pad_R[s:e] += 0.045 * env * w * pan
        if b * bar >= end_music:
            continue
        # bass on every beat after the intro
        if b >= intro_bars:
            for k in range(4):
                bs = int((b * bar + k * beat) * SR)
                if bs / SR >= end_music:
                    break
                be = min(n, bs + int(beat * SR))
                bt = np.arange(be - bs) / SR
                benv = np.minimum(1, bt / 0.01) * np.exp(-bt / 0.32)
                bw = np.sin(2 * np.pi * midi_hz(root) * bt) + 0.25 * np.sin(4 * np.pi * midi_hz(root) * bt)
                L[bs:be] += 0.16 * drive * benv * bw
                R[bs:be] += 0.16 * drive * benv * bw
        # arpeggio (eighth notes)
        if b >= intro_bars:
            pattern = [0, 1, 2, 3, 2, 1, 2, 3]
            for k in range(8):
                ns = int((b * bar + k * beat / 2) * SR)
                if ns / SR >= end_music:
                    break
                ne = min(n, ns + int(0.9 * SR))
                nt = np.arange(ne - ns) / SR
                f = midi_hz(chord[pattern[k]] + 12)
                penv = np.minimum(1, nt / 0.004) * np.exp(-nt / 0.20)
                pw = np.sin(2 * np.pi * f * nt) + 0.2 * np.sin(4 * np.pi * f * nt) * np.exp(-nt / 0.05)
                pan = 0.35 if k % 2 == 0 else 0.65
                L[ns:ne] += 0.060 * penv * pw * (1 - pan)
                R[ns:ne] += 0.060 * penv * pw * pan
    # kick (beats 1 & 3) and soft hats (off-beats) after the intro
    kick_times = []
    t = intro_bars * bar
    while t < end_music:
        kick_times.append(t)
        t += 2 * beat if drive < 1.1 else beat
    for kt in kick_times:
        ks = int(kt * SR)
        ke = min(n, ks + int(0.5 * SR))
        tt = np.arange(ke - ks) / SR
        ph = 2 * np.pi * (46 * tt + 90 * 0.035 * (1 - np.exp(-tt / 0.035)))
        k = np.sin(ph) * np.exp(-tt / 0.22) * 0.42 * drive
        L[ks:ke] += k
        R[ks:ke] += k
    t = intro_bars * bar + beat / 2
    while t < end_music:
        hs = int(t * SR)
        he = min(n, hs + int(0.08 * SR))
        nz = rng.standard_normal(he - hs)
        nz = np.diff(np.concatenate([[0], nz]))
        hh = nz * np.exp(-np.arange(he - hs) / SR / 0.018) * 0.030 * drive
        L[hs:he] += hh * 0.8
        R[hs:he] += hh
        t += beat
    # sidechain-style pump on the pad
    pump = np.ones(n)
    tt_all = np.arange(n) / SR
    for kt in kick_times:
        ks = int(kt * SR)
        ke = min(n, ks + int(0.45 * SR))
        pump[ks:ke] = np.minimum(pump[ks:ke], 1 - 0.38 * np.exp(-(tt_all[ks:ke] - kt) / 0.16))
    pad_L *= pump
    pad_R *= pump
    # closing bell shimmer
    last_chord = prog[int(end_music / bar) % len(prog)][0]
    for i, m in enumerate(last_chord + [last_chord[0] + 12]):
        bs = int((end_music + 0.08 * i) * SR)
        if bs >= n:
            continue
        be = n
        bt = np.arange(be - bs) / SR
        f = midi_hz(m + 24)
        bw = (np.sin(2 * np.pi * f * bt) + 0.3 * np.sin(2 * np.pi * f * 2.76 * bt) * np.exp(-bt / 0.2)) * np.exp(-bt / 0.9) * 0.05
        pan = 0.3 + 0.13 * i
        L[bs:be] += bw * (1 - pan)
        R[bs:be] += bw * pan
    # reverb on everything melodic (pad + arp + bells)
    wetL, wetR = L + pad_L, R + pad_R
    ir_n = int(2.4 * SR)
    irt = np.arange(ir_n) / SR
    out = []
    for ch, sd in ((wetL, 1), (wetR, 2)):
        ir = np.random.default_rng(seed + sd).standard_normal(ir_n) * np.exp(-irt / 0.55)
        ir /= np.sqrt(np.sum(ir ** 2))
        size = 1 << int(math.ceil(math.log2(n + ir_n)))
        rv = np.fft.irfft(np.fft.rfft(ch, size) * np.fft.rfft(ir, size), size)[:n]
        out.append(rv)
    mixL = L + pad_L + 0.22 * out[0]
    mixR = R + pad_R + 0.22 * out[1]
    fade = np.ones(n)
    fo = int(1.4 * SR)
    fade[-fo:] = np.linspace(1, 0, fo) ** 1.5
    fade[:int(0.03 * SR)] = np.linspace(0, 1, int(0.03 * SR))
    mixL *= fade
    mixR *= fade
    peak = max(np.abs(mixL).max(), np.abs(mixR).max())
    mixL, mixR = mixL / peak * 0.89, mixR / peak * 0.89
    data = (np.stack([mixL, mixR], 1) * 32767).astype('<i2')
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(data.tobytes())


# ---------------------------------------------------------------- reels

def end(extra=None, tagline='Any shape. Any size.\nLit to order.', dur=3.8):
    return EndCard(dur, tagline, extra)


def reel_r1():
    """Made in our own workshop (trust / story)."""
    s1i, _ = lines('Every Lume mirror\nstarts here.', SERIF(104), int(H * 0.545), 0.35)
    s2i, _ = lines('Etched with\n\u00b10.1 mm precision.', SERIF(104), int(H * 0.545), 0.25)
    s3i, _ = lines('Made in-house,\nin Panchkula.', SERIF(104), int(H * 0.545), 0.25)
    s4i, _ = lines('Warm, natural\nor cool light.', SERIF(96), int(H * 0.625), 0.3)
    scenes = [
        VideoScene('closeup', 0.4, 3.6, [label('LUME  \u00b7  LED MIRRORS', int(H * 0.505), 0.15)] + s1i, zoom=(1.04, 1.12), xf=0),
        VideoScene('fibre', 0.0, 3.2, [label('LASER FROSTING', int(H * 0.505), 0.1)] + s2i, zoom=(1.0, 1.08)),
        VideoScene('machine', 1.0, 3.2, [label('OUR OWN WORKSHOP', int(H * 0.505), 0.1)] + s3i, zoom=(1.02, 1.10)),
        CardScene(['round-led-mirror-12.jpg', 'irregular-led-mirror-12.jpg', 'oval-capsule-led-mirror-02.jpg', 'rectangle-led-mirror-05.jpg'], 1.2,
                  [label('THEN WE LIGHT IT', int(H * 0.585), 0.2)] + s4i),
        VideoScene('machine', 9.0, 3.8, [
            Count(20, str, SERIF(150), int(H * 0.22), 0.25, suffix='+'),
            label('YEARS IN MIRROR & GLASS', int(H * 0.22) + 182, 0.4, fill=PAPER),
            Count(1500, indian, SERIF(150), int(H * 0.37), 0.7),
            label('MIRRORS MADE EVERY MONTH', int(H * 0.37) + 182, 0.85, fill=PAPER),
            Txt(text_layer('Pan-India', SERIF(150), PAPER), W / 2, int(H * 0.52), 1.15),
            label('DELIVERY  \u00b7  GST INVOICE', int(H * 0.52) + 182, 1.3, fill=PAPER),
        ], dim=0.72, scrim=0.6, zoom=(1.0, 1.05)),
        end(),
    ]
    return scenes, 105, None, 1.9


def reel_r2():
    """Any shape (product range)."""
    def section(word, photos, names):
        tl = Txt(text_layer(word, SERIF(110), PAPER), W / 2, int(H * 0.615), 0.1, rise=24, dur=0.4)
        return CardScene(photos, 0.8, [tl], captions=names, cap_y=int(H * 0.585), xf=0.18)

    hook, _ = lines('Any shape.', SERIF(120), int(H * 0.64), 1.0)
    s6, _ = lines('Any size.\nMade for your wall.', SERIF(100), int(H * 0.545), 0.25)
    scenes = [
        TraceScene(2.6, [label('LUME  \u00b7  LED MIRRORS', int(H * 0.60), 0.6)] + hook, xf=0),
        section('Round', ['round-led-mirror-12.jpg', 'round-led-mirror-03.jpg', 'round-led-mirror-10.jpg'],
                ['HALO RING', 'SUNBURST DOT', 'GREEK KEY RING']),
        section('Rectangle', ['rectangle-led-mirror-20.jpg', 'rectangle-led-mirror-04.jpg', 'rectangle-led-mirror-14.jpg'],
                ['DOUBLE-LINE SLAT', 'FULL-LENGTH DECO', 'HOLLYWOOD VANITY']),
        section('Capsule & oval', ['oval-capsule-led-mirror-02.jpg', 'oval-capsule-led-mirror-04.jpg', 'oval-capsule-led-mirror-01.jpg'],
                ['BLOSSOM BRANCH', 'CAPSULE GREEK KEY', 'CAPSULE COOL HALO']),
        section('Free-form', ['irregular-led-mirror-12.jpg', 'irregular-led-mirror-14.jpg', 'irregular-led-mirror-11.jpg'],
                ['PEBBLE BACKLIT', 'ORGANIC BLOB', 'WAVE CLOCK']),
        VideoScene('closeup', 6.0, 2.8, [label('MADE TO MEASURE', int(H * 0.505), 0.1)] + s6, zoom=(1.0, 1.08)),
        end(extra='55 DESIGNS  \u00b7  OR BRING YOUR OWN'),
    ]
    return scenes, 100, [([57, 60, 64, 67], 45), ([53, 57, 60, 64], 41), ([48, 52, 55, 60], 48), ([55, 59, 62, 67], 43)], 1.8


def reel_r3():
    """How to order in 3 steps."""
    hook, _ = lines('Your custom\nLED mirror,\nin 3 steps.', SERIF(118), int(H * 0.29), 0.2, stagger=0.14)
    s5, _ = lines('Delivered,\nanywhere in India.', SERIF(96), int(H * 0.625), 0.25)

    class Hook(Scene):
        def __init__(self):
            super().__init__(2.6, [label('HOW IT WORKS', int(H * 0.245), 0.05)] + hook, xf=0)
            self.bg = blurred_bg(load('round-led-mirror-12.jpg'), 0.42)

        def draw_bg(self, dst, t):
            dst[:] = self.bg
            led_line(dst, W / 2, int(H * 0.60), 420 * eo((t - 0.7) / 0.9))

    scenes = [
        Hook(),
        GridScene(['round-led-mirror-12.jpg', 'irregular-led-mirror-12.jpg', 'rectangle-led-mirror-20.jpg',
                   'oval-capsule-led-mirror-02.jpg', 'round-led-mirror-03.jpg', 'irregular-led-mirror-14.jpg'], 3.6, pick=1,
                  items=step_text('01', 'Pick a design', '55 designs online, or share your own idea')),
        LightScene(3.8, step_text('02', 'Send your size\n& light colour', None) + [ToneWords(int(H * 0.585) + 62 + 2 * 104 + 20, 0.6)]),
        VideoScene('closeup', 1.0, 3.6, step_text('03', 'We laser-frost\n& build it', 'In our own Panchkula workshop', y0=int(H * 0.50), sub_fill=PAPER), zoom=(1.02, 1.10)),
        CardScene(['rectangle-led-mirror-20.jpg'], 2.6, [label('THEN', int(H * 0.585), 0.15)] + s5),
        end(),
    ]
    return scenes, 96, [([53, 57, 60, 64], 41), ([55, 59, 62, 67], 43), ([57, 60, 64, 67], 45), ([52, 55, 59, 64], 40)], 1.6


def reel_r4():
    """Bulk / OEM (B2B)."""
    s1, _ = lines('LED mirrors,\nby the hundred.', SERIF(108), int(H * 0.545), 0.3)
    s3, b3 = lines('Your brand.\nOur workshop.', SERIF(108), int(H * 0.545), 0.25)
    s4, b4 = lines('CE-certified\ncomponents.', SERIF(100), int(H * 0.625), 0.3)
    scenes = [
        VideoScene('machine', 0.5, 3.2, [label('HOTELS  \u00b7  BUILDERS  \u00b7  RETAILERS', int(H * 0.505), 0.1, size=28)] + s1, zoom=(1.03, 1.11), xf=0),
        VideoScene('closeup', 2.0, 3.0, [Count(1500, indian, SERIF(190), int(H * 0.47), 0.15, dur=1.0),
                                         label('MIRRORS A MONTH, MADE IN-HOUSE', int(H * 0.47) + 228, 0.45, fill=PAPER)], zoom=(1.0, 1.08), dim=0.25),
        VideoScene('fibre', 3.0, 3.2, [label('OEM & PRIVATE LABEL', int(H * 0.505), 0.1)] + s3 +
                   [Txt(text_layer('From 500 pieces, with your logo', SANS(40), PAPER), W / 2, b3 + 26, 0.65)], zoom=(1.0, 1.08)),
        CardScene(['rectangle-led-mirror-05.jpg', 'round-led-mirror-15.jpg', 'oval-capsule-led-mirror-04.jpg'], 1.2,
                  [label('BUILT TO SPEC', int(H * 0.585), 0.2)] + s4 +
                  [Txt(text_layer('GST invoicing  \u00b7  Pan-India dispatch', SANS(38), (205, 212, 220)), W / 2, b4 + 24, 0.6)]),
        VideoScene('machine', 10.0, 2.8, [Count(20, str, SERIF(190), int(H * 0.47), 0.15, suffix='+', dur=0.7),
                                          label('YEARS IN MIRROR & GLASS', int(H * 0.47) + 228, 0.4, fill=PAPER)], zoom=(1.0, 1.06), dim=0.3),
        end(tagline='Get a bulk\nor OEM quote.', extra='BULK & OEM ENQUIRIES WELCOME'),
    ]
    return scenes, 108, [([57, 60, 64, 67], 45), ([53, 57, 60, 64], 41), ([48, 52, 55, 60], 48), ([55, 59, 62, 67], 43)], 1.9


REELS = {
    'r1': ('lume-reel-01-made-in-our-workshop', reel_r1),
    'r2': ('lume-reel-02-any-shape', reel_r2),
    'r3': ('lume-reel-03-how-to-order', reel_r3),
    'r4': ('lume-reel-04-bulk-oem', reel_r4),
}


def timeline(scenes):
    starts = [0.0]
    for i in range(1, len(scenes)):
        starts.append(starts[-1] + scenes[i - 1].dur - scenes[i].xf)
    total = starts[-1] + scenes[-1].dur
    return starts, total


def frame_at(scenes, starts, T, buf2):
    frame = np.empty((H, W, 3), np.float32)
    active = [i for i, s in enumerate(scenes) if starts[i] <= T < starts[i] + s.dur]
    if not active:
        active = [len(scenes) - 1]
    first = True
    for i in active:
        s = scenes[i]
        lt = T - starts[i]
        a = 1.0 if (first or s.xf <= 0) else eio(lt / s.xf)
        if first or a >= 1:
            s.render(frame, lt)
        else:
            s.render(buf2, lt)
            frame *= 1 - a
            frame += buf2 * a
        first = False
    return frame


def render(key):
    name, fn = REELS[key]
    scenes, bpm, prog, cover_t = fn()
    starts, total = timeline(scenes)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SCRATCH, exist_ok=True)
    wav = os.path.join(SCRATCH, name + '.wav')
    make_music(wav, total, bpm=bpm, prog=prog, drive=1.15 if key == 'r4' else 1.0)
    out = os.path.join(OUT, name + '.mp4')
    p = subprocess.Popen([FF, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-',
                          '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-pix_fmt', 'yuv420p',
                          '-profile:v', 'high', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', out], stdin=subprocess.PIPE)
    buf2 = np.empty((H, W, 3), np.float32)
    nfr = int(round(total * FPS))
    cover_f = int(cover_t * FPS)
    for f in range(nfr):
        fr = np.clip(frame_at(scenes, starts, f / FPS, buf2), 0, 255).astype(np.uint8)
        p.stdin.write(fr.tobytes())
        if f == cover_f:
            Image.fromarray(fr).save(os.path.join(OUT, name + '-cover.jpg'), quality=90)
    p.stdin.close()
    p.wait()
    for s in scenes:
        if isinstance(s, VideoScene):
            s.clip.close()
    print('%s  %.1fs  %d frames' % (out, total, nfr))


def preview(key, times):
    name, fn = REELS[key]
    scenes, *_ = fn()
    starts, total = timeline(scenes)
    os.makedirs(SCRATCH, exist_ok=True)
    buf2 = np.empty((H, W, 3), np.float32)
    ims = []
    for T in times:
        fr = np.clip(frame_at(scenes, starts, T, buf2), 0, 255).astype(np.uint8)
        ims.append(Image.fromarray(fr).resize((W // 3, H // 3), Image.LANCZOS))
    sheet = Image.new('RGB', (len(ims) * (W // 3 + 8), H // 3), (60, 60, 60))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * (W // 3 + 8), 0))
    path = os.path.join(SCRATCH, 'preview-%s.jpg' % key)
    sheet.save(path, quality=88)
    print(path, 'total %.1fs' % total, 'starts', ['%.2f' % s for s in starts])
    for s in scenes:
        if isinstance(s, VideoScene):
            s.clip.close()


if __name__ == '__main__':
    if sys.argv[1] == 'render':
        for k in sys.argv[2:]:
            render(k)
    else:
        preview(sys.argv[2], [float(x) for x in sys.argv[3:]])
