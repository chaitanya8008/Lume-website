"""Trend-format Lume Reels: native-style caption boxes, hard cuts on the beat, lights-off/on reveals.

usage: python trends.py render t1 [t2 ...]
       python trends.py preview t1 0.2 3.1 ...
"""
import math
import os
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import reels as R
from reels import (H, W, FPS, FF, INK, PAPER, LED, WARM, COOL, F, Scene, VideoScene, Card, LightScene,
                   blit, place, text_layer, load, cover, blurred_bg, radial, rounded_mask, led_line, eo, eio, c01,
                   TL, SERIF, MONO, LOGO, timeline, frame_at, make_music)

OUT = R.OUT.replace('reels', 'trend-reels')
EMO = lambda s: F('seguiemj.ttf', s)
SEMI = lambda s: F('seguisb.ttf', s)
BLK = lambda s: F('seguibl.ttf', s)
NATURAL = (255, 240, 222)
EMOJI_EXTRA = set('✨❄✅❌⭐☀⏱☝✋❤⚡')


def is_emoji(ch):
    return ord(ch) >= 0x1F000 or ch in EMOJI_EXTRA


def runs(text):
    text = text.replace('️', '')
    out = []
    for ch in text:
        e = is_emoji(ch)
        if out and out[-1][1] == e:
            out[-1][0] += ch
        else:
            out.append([ch, e])
    return out


def rich_width(d, text, font, efont):
    return sum(d.textlength(s, font=efont) + font.size * 0.06 if e else d.textlength(s, font=font) for s, e in runs(text))


def rich_draw(d, x, y, text, font, efont, fill, stroke=0, stroke_fill=None):
    for s, e in runs(text):
        if e:
            d.text((x + font.size * 0.06, y + font.size * 0.16), s, font=efont, embedded_color=True)
            x += font.size * 0.06
            x += d.textlength(s, font=efont)
        else:
            d.text((x, y), s, font=font, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
            x += d.textlength(s, font=font)


def cap_box(text, size=58, style='white', font=None):
    """Instagram-style caption: one rounded box per line (white/dark) or bold outlined text."""
    font = font or SEMI(size)
    efont = EMO(int(size * 0.92))
    probe = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    lines = text.split('\n')
    asc, desc = font.getmetrics()
    padx, pady = int(size * 0.42), int(size * 0.16)
    lh = asc + desc + 2 * pady
    step = int(lh * 0.92)
    widths = [rich_width(probe, s, font, efont) for s in lines]
    bw = int(max(widths)) + 2 * padx
    bh = step * (len(lines) - 1) + lh
    m = 40
    im = Image.new('RGBA', (bw + 2 * m, bh + 2 * m), (0, 0, 0, 0))
    if style == 'outline':
        sh = Image.new('L', im.size, 0)
        sd = ImageDraw.Draw(sh)
        for i, s in enumerate(lines):
            x = m + (bw - widths[i]) / 2
            sd.text((x, m + i * step + pady + 6), ''.join(c for c in s if not is_emoji(c) and c != '️'), font=font, fill=255,
                    stroke_width=int(size * 0.10), stroke_fill=255)
        sh = sh.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * 0.75))
        im.paste((0, 0, 0, 255), (0, 0), sh)
    d = ImageDraw.Draw(im)
    for i, s in enumerate(lines):
        x = m + (bw - widths[i]) / 2
        y = m + i * step
        if style in ('white', 'dark', 'led'):
            bg = {'white': (255, 255, 255, 255), 'dark': (8, 10, 12, 215), 'led': (223, 233, 245, 255)}[style]
            d.rounded_rectangle((x - padx, y, x + widths[i] + padx, y + lh), int(size * 0.28), fill=bg)
    for i, s in enumerate(lines):
        x = m + (bw - widths[i]) / 2
        y = m + i * step + pady - int(size * 0.04)
        if style == 'outline':
            rich_draw(d, x, y, s, font, efont, (255, 255, 255), stroke=int(size * 0.07), stroke_fill=(0, 0, 0))
        else:
            fg = (255, 255, 255) if style == 'dark' else (0, 0, 0)
            rich_draw(d, x, y, s, font, efont, fg)
    return TL(np.asarray(im).copy(), m, bw, bh)


def backout(p):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


class Pop:
    """Caption that pops in (scale overshoot) at t_in and optionally out at t_out. y = top of block."""

    def __init__(self, tl, y, t_in=0.0, t_out=None, cx=W / 2):
        self.tl, self.y, self.t_in, self.t_out, self.cx = tl, y, t_in, t_out, cx
        self.img = Image.fromarray(tl.arr)

    def render(self, dst, t):
        p = (t - self.t_in) / 0.26
        if p <= 0:
            return
        if self.t_out is not None and t >= self.t_out + 0.12:
            return
        s = backout(c01(p)) * 0.25 + 0.75 if p < 1 else 1.0
        op = c01(p * 2.5)
        if self.t_out is not None and t > self.t_out:
            op *= 1 - (t - self.t_out) / 0.12
        arr = self.tl.arr
        if abs(s - 1) > 0.01:
            w, h = self.img.size
            arr = np.asarray(self.img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR))
        blit(dst, arr, self.cx - arr.shape[1] / 2, self.y + self.tl.h / 2 - arr.shape[0] / 2, op)


class Shot(Scene):
    """Photo in a big card over its blurred self; optional lights-off start that switches on with a flash."""

    def __init__(self, photo, dur, items=(), off_until=None, cy=0.47, maxh=0.64, flash=True, xf=0.0):
        super().__init__(dur, items, xf)
        self.card = Card(photo, int(W * 0.92), int(H * maxh))
        self.cy = H * cy
        self.off_until = off_until
        self.flash = flash

    def render(self, dst, t):
        dst[:] = self.card.bg
        punch = 0.08 * (1 - eo(t / 0.22)) if self.flash else 0
        self.card.render(dst, W / 2, self.cy, c01(t / max(self.dur, 1.5)) + punch * 8, 1.0)
        if self.off_until is not None:
            if t < self.off_until:
                lum = dst.mean(axis=2, keepdims=True)
                dst[:] = (dst * 0.35 + lum * 0.65) * 0.13 + np.array([2, 4, 8], np.float32)
            else:
                ts = t - self.off_until
                if ts < 0.9:
                    small = Image.fromarray(np.clip(dst, 0, 255).astype(np.uint8)).resize((W // 6, H // 6), Image.BILINEAR)
                    a = np.asarray(small, np.float32)
                    br = np.clip((a.mean(axis=2, keepdims=True) - 150) / 105, 0, 1) * a
                    bl = Image.fromarray(np.clip(br, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
                    dst += np.asarray(bl, np.float32) * 1.4 * math.exp(-ts / 0.35)
                if ts < 0.14:
                    dst[:] = dst * (1 - 0.55 * (1 - ts / 0.14)) + 255 * 0.55 * (1 - ts / 0.14)
        elif self.flash and t < 0.12:
            k = 0.45 * (1 - t / 0.12)
            dst[:] = dst * (1 - k) + 255 * k
        for it in self.items:
            it.render(dst, t)


class FlashVideo(VideoScene):
    def __init__(self, *a, speed=1.0, flash=True, **kw):
        super().__init__(*a, **kw)
        self.speed = speed
        self.flash = flash
        if speed != 1.0:
            clip = self.clip
            orig = clip._start

            def _start(t, clip=clip, sp=speed):
                if clip.p:
                    clip.p.kill()
                vf = 'setpts=PTS/%.3f,fps=%d,scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d' % (sp, FPS, W, H, W, H)
                clip.p = subprocess.Popen([FF, '-v', 'error', '-ss', '%.3f' % (clip.ss + t * sp), '-i', clip.path, '-an', '-vf', vf,
                                           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)
                clip.idx = int(round(t * FPS)) - 1
            clip._start = _start

    def render(self, dst, t):
        super().render(dst, t)
        if self.flash and t < 0.1:
            k = 0.5 * (1 - t / 0.1)
            dst[:] = dst * (1 - k) + 255 * k


class Split(Scene):
    """This-or-that: two photos stacked, A/B badges, a countdown bar between them."""

    def __init__(self, a, b, dur, idx, total, items=()):
        super().__init__(dur, items, 0.0)
        th = int(H * 0.385)
        self.top = np.asarray(cover(load(a), W, th, 0.5, 0.45), np.float32)
        self.bot = np.asarray(cover(load(b), W, th, 0.5, 0.45), np.float32)
        self.th = th
        self.y1 = int(H * 0.105)
        self.y2 = int(H * 0.51)
        self.badA = cap_box('A', 50, 'white', BLK(50))
        self.badB = cap_box('B', 50, 'white', BLK(50))
        self.count = cap_box('%d/%d' % (idx, total), 40, 'dark')

    def render(self, dst, t):
        dst[:] = INK
        p = eo(t / 0.2)
        off = (1 - p) * W
        x_top = int(off)
        x_bot = -int(off)

        def put(img, x, y):
            x0, x1 = max(0, x), min(W, x + W)
            if x1 > x0:
                dst[y:y + self.th, x0:x1] = img[:, x0 - x:x1 - x]
        put(self.top, x_top, self.y1)
        put(self.bot, x_bot, self.y2)
        place(dst, self.badA, 70 + x_top, self.y1 + 28, 1.0, align='left')
        place(dst, self.badB, 70 + x_bot, self.y2 + 28, 1.0, align='left')
        # countdown bar in the gap
        gy = self.y1 + self.th
        gap = self.y2 - gy
        frac = 1 - c01(t / self.dur)
        bw = int(W * 0.8 * frac)
        if bw > 2:
            led_line(dst, W / 2, gy + gap / 2 - 2, bw, LED, 1.0)
        place(dst, self.count, W - 70, self.y1 + 28, 1.0, align='right')
        for it in self.items:
            it.render(dst, t)


class TrendEnd(Scene):
    def __init__(self, dur, box, xf=0.0):
        super().__init__(dur, (), xf)
        self.glow = radial(W / 2, H * 0.36, W * 0.85, LED, 0.12)
        self.logo = text_layer('LUME', LOGO(130), PAPER, spacing=0.30, shadow=0)
        self.sub = text_layer('LED MIRRORS  ·  PANCHKULA', MONO(28), (165, 174, 184), spacing=0.4, shadow=0)
        self.box = Pop(cap_box(box, 60, 'white'), int(H * 0.43), 0.15)
        self.wa = text_layer('WhatsApp +91 62832 25517', SEMI(44), PAPER, shadow=0)
        self.url = text_layer('lume.co.in', MONO(38), LED, spacing=0.18, shadow=0)

    def render(self, dst, t):
        dst[:] = INK
        blit(dst, self.glow, 0, 0)
        y0 = H * 0.22
        place(dst, self.logo, W / 2, y0, 1.0)
        place(dst, self.sub, W / 2, y0 + 168, 1.0)
        led_line(dst, W / 2, y0 + 234, 520 * eo(t / 0.6))
        self.box.render(dst, t)
        q = eo((t - 0.45) / 0.35)
        place(dst, self.wa, W / 2, H * 0.62, q, (1 - q) * 20)
        place(dst, self.url, W / 2, H * 0.62 + 76, q, (1 - q) * 20)
        if t < 0.1:
            k = 0.5 * (1 - t / 0.1)
            dst[:] = dst * (1 - k) + 255 * k


def big_word(text, size=150):
    return cap_box(text, size, 'outline', BLK(size))


# ---------------------------------------------------------------- reels

def t1():
    """POV: a laser is drawing your mirror."""
    scenes = [
        FlashVideo('closeup', 0.3, 4.0, [Pop(cap_box('POV: a laser is\ndrawing your mirror \U0001F92F', 72), int(H * 0.17), -1)],
                   zoom=(1.22, 1.34), focus=(0.42, 0.45), scrim=0.35, xf=0, flash=False),
        FlashVideo('fibre', 0.2, 3.0, [Pop(cap_box('±0.1 mm. Every single line \U0001F3AF', 60), int(H * 0.17), 0.05),
                                       Pop(cap_box('wait for it… \U0001F440', 64, 'dark'), int(H * 0.60), 1.3)],
                   zoom=(1.30, 1.42), focus=(0.25, 0.55), speed=1.6, scrim=0.35, xf=0),
        Shot('round-led-mirror-12.jpg', 3.5, [Pop(cap_box('Lit to order ✨', 66), int(H * 0.115), 0.55),
                                              Pop(cap_box('Made in Panchkula  ·  lume.co.in', 40, 'dark'), int(H * 0.80), 1.1)], off_until=0.45),
    ]
    return scenes, [], 'lume-trend-01-pov-laser', 0.6, 6.95


def t2():
    """Every Lume mirror has 3 lights. Which one are you?"""
    def tone(photo, word, sub):
        return Shot(photo, 1.5, [Pop(big_word(word, 150), int(H * 0.11), 0.28), Pop(cap_box(sub, 46, 'dark'), int(H * 0.80), 0.45)], off_until=0.22)
    ls = LightScene(3.0, [Pop(cap_box('Every Lume mirror has\n3 lights in 1 \U0001F4A1', 66), int(H * 0.585), -1),
                          Pop(cap_box('Which one are you? \U0001F447', 56, 'dark'), int(H * 0.585) + 205, 1.1)], xf=0)
    scenes = [
        ls,
        tone('round-led-mirror-12.jpg', 'WARM \U0001F525', 'cosy, for evenings'),
        tone('round-led-mirror-15.jpg', 'NATURAL ☀️', 'true colours, for makeup'),
        tone('rectangle-led-mirror-05.jpg', 'COOL ❄️', 'bright & crisp'),
        TrendEnd(2.5, 'Comment WARM, NATURAL\nor COOL \U0001F447'),
    ]
    return scenes, [], 'lume-trend-02-which-light', 0.5, 3.0


def t3():
    """This or that?"""
    pairs = [('round-led-mirror-12.jpg', 'round-led-mirror-03.jpg'), ('irregular-led-mirror-12.jpg', 'irregular-led-mirror-01.jpg'),
             ('rectangle-led-mirror-20.jpg', 'rectangle-led-mirror-14.jpg'), ('oval-capsule-led-mirror-02.jpg', 'oval-capsule-led-mirror-04.jpg'),
             ('round-led-mirror-10.jpg', 'irregular-led-mirror-11.jpg')]
    scenes = []
    for i, (a, b) in enumerate(pairs):
        items = [Pop(cap_box('This or that? Pick fast ⏱️', 66), int(H * 0.455), -1, 1.7)] if i == 0 else []
        scenes.append(Split(a, b, 2.0, i + 1, len(pairs), items))
    scenes.append(TrendEnd(2.5, 'Comment your picks \U0001F447\nlike A B B A B'))
    return scenes, [], 'lume-trend-03-this-or-that', 0.6, 2.0


def t4():
    """Lights off -> on. Rate each one."""
    photos = ['round-led-mirror-12.jpg', 'rectangle-led-mirror-14.jpg', 'irregular-led-mirror-12.jpg', 'irregular-led-mirror-14.jpg', 'round-led-mirror-10.jpg']
    scenes = []
    for i, p in enumerate(photos):
        scenes.append(Shot(p, 1.5, [Pop(cap_box('%d/5' % (i + 1), 44, 'dark'), int(H * 0.80), 0.4)], off_until=0.5, cy=0.50, maxh=0.60))
    scenes.append(TrendEnd(2.5, 'Which number won? \U0001F447'))
    overlay = [Pop(cap_box('Lights off → on \U0001F4A1\nRate each one 1–10 \U0001F525', 64), int(H * 0.105), -1, 7.45)]
    return scenes, overlay, 'lume-trend-04-lights-on-rate-it', 1.0, 0.0


def t5():
    """3 mistakes people make buying an LED mirror."""
    def mistake(photo, n, title, body):
        return Shot(photo, 4.0, [Pop(cap_box('❌ Mistake %d: %s' % (n, title), 58), int(H * 0.115), 0.05),
                                 Pop(cap_box(body, 50, 'dark'), int(H * 0.66), 0.7)], cy=0.43, maxh=0.52)
    scenes = [
        Shot('irregular-led-mirror-14.jpg', 2.5, [Pop(cap_box('3 mistakes people make\nbuying an LED mirror ❌', 68), int(H * 0.115), -1),
                                                  Pop(cap_box('(#3 costs you every day)', 46, 'dark'), int(H * 0.68), 0.9)], cy=0.47, maxh=0.56),
        mistake('round-led-mirror-12.jpg', 1, 'wrong size', 'Go for 60–80% of your\nvanity’s width \U0001F4CF'),
        mistake('irregular-led-mirror-10.jpg', 2, 'backlight only', 'A halo lights the wall,\nnot your face. Get a lit\nfront pattern too \U0001F4A1'),
        mistake('rectangle-led-mirror-05.jpg', 3, 'one light colour', 'Get warm, natural & cool\nin one ✅ Standard on\nevery Lume mirror'),
        TrendEnd(2.6, 'Save this for your\nbathroom makeover \U0001F4CC'),
    ]
    return scenes, [], 'lume-trend-05-3-mistakes', 0.8, 0.0


TRENDS = {'t1': t1, 't2': t2, 't3': t3, 't4': t4, 't5': t5}


def add_beat(wav_path, total, bpm, drop=None):
    """Punch up the base track: claps on 2 & 4, and a riser into the drop."""
    with wave.open(wav_path, 'rb') as wf:
        sr = wf.getframerate()
        data = np.frombuffer(wf.readframes(wf.getnframes()), '<i2').reshape(-1, 2).astype(np.float64) / 32767
    n = len(data)
    beat = 60.0 / bpm
    rng = np.random.default_rng(3)
    t = beat
    while t < total - 1.6:
        s = int(t * sr)
        e = min(n, s + int(0.18 * sr))
        tt = np.arange(e - s) / sr
        nz = rng.standard_normal(e - s)
        nz = nz - np.convolve(nz, np.ones(6) / 6, 'same')
        env = np.exp(-tt / 0.06) + 0.6 * np.exp(-np.maximum(0, tt - 0.012) / 0.05) * (tt > 0.012)
        data[s:e, 0] += nz * env * 0.16
        data[s:e, 1] += nz * env * 0.16
        t += 2 * beat
    if drop:
        s = int(max(0, drop - 1.2) * sr)
        e = int(drop * sr)
        tt = np.linspace(0, 1, e - s)
        nz = rng.standard_normal(e - s)
        lp = np.convolve(nz, np.ones(4) / 4, 'same')
        rs = (nz - lp) * tt ** 2.2 * 0.22
        data[s:e, 0] += rs
        data[s:e, 1] += rs
        d0 = e
        d1 = min(n, d0 + int(0.6 * sr))
        dt = np.arange(d1 - d0) / sr
        boom = np.sin(2 * np.pi * (38 * dt + 60 * 0.05 * (1 - np.exp(-dt / 0.05)))) * np.exp(-dt / 0.35) * 0.6
        data[d0:d1, 0] += boom
        data[d0:d1, 1] += boom
    data /= np.abs(data).max() / 0.89
    with wave.open(wav_path, 'wb') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((data * 32767).astype('<i2').tobytes())


def frame(scenes, starts, overlay, T, buf2):
    fr = frame_at(scenes, starts, T, buf2)
    for it in overlay:
        it.render(fr, T)
    return fr


def render(key):
    scenes, overlay, name, cover_t, drop = TRENDS[key]()
    starts, total = timeline(scenes)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(R.SCRATCH, exist_ok=True)
    wav = os.path.join(R.SCRATCH, name + '.wav')
    make_music(wav, total, bpm=120, drive=1.2, intro_bars=0,
               prog=[([57, 60, 64, 67], 45), ([53, 57, 60, 64], 41), ([48, 52, 55, 60], 48), ([55, 59, 62, 67], 43)])
    add_beat(wav, total, 120, drop or None)
    out = os.path.join(OUT, name + '.mp4')
    p = subprocess.Popen([FF, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H), '-r', str(FPS), '-i', '-',
                          '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '19', '-pix_fmt', 'yuv420p',
                          '-profile:v', 'high', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-shortest', out], stdin=subprocess.PIPE)
    buf2 = np.empty((H, W, 3), np.float32)
    nfr = int(round(total * FPS))
    for f in range(nfr):
        fr = np.clip(frame(scenes, starts, overlay, f / FPS, buf2), 0, 255).astype(np.uint8)
        p.stdin.write(fr.tobytes())
        if f == int(cover_t * FPS):
            Image.fromarray(fr).save(os.path.join(OUT, name + '-cover.jpg'), quality=90)
    p.stdin.close()
    p.wait()
    silent = os.path.join(OUT, name + '-no-music.mp4')
    subprocess.run([FF, '-y', '-v', 'error', '-i', out, '-an', '-c:v', 'copy', '-movflags', '+faststart', silent], check=True)
    for s in scenes:
        if isinstance(s, VideoScene):
            s.clip.close()
    print('%s  %.1fs' % (out, total))


def preview(key, times):
    scenes, overlay, name, *_ = TRENDS[key]()
    starts, total = timeline(scenes)
    buf2 = np.empty((H, W, 3), np.float32)
    ims = [Image.fromarray(np.clip(frame(scenes, starts, overlay, T, buf2), 0, 255).astype(np.uint8)).resize((W // 3, H // 3), Image.LANCZOS) for T in times]
    sheet = Image.new('RGB', (len(ims) * (W // 3 + 8), H // 3), (60, 60, 60))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * (W // 3 + 8), 0))
    path = os.path.join(R.SCRATCH, 'preview-%s.jpg' % key)
    sheet.save(path, quality=88)
    print(path, 'total %.1fs' % total, ['%.2f' % s for s in starts])
    for s in scenes:
        if isinstance(s, VideoScene):
            s.clip.close()


if __name__ == '__main__':
    if sys.argv[1] == 'render':
        for k in sys.argv[2:]:
            render(k)
    else:
        preview(sys.argv[2], [float(x) for x in sys.argv[3:]])

