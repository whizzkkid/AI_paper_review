"""Royalty-free sound design (no accounts, no paid services).

  sfx_track(events, total, pack)  one-shot effects placed on the exact frames the stage animates
                                  (bubble pops, transitions, stamp thud, verdict ding, count-up riser …)
  music_bed(total)                a soft pad + arpeggio bed; render_video ducks it under the narration

Two effect packs (config.yml → video.sfx_pack):
  "soundweaver"  pre-rendered WAVs from the SoundWeaver plugin (MIT, pipeline/video/sfx/soundweaver/),
                 picked by their labels; kinds without a match fall back to the synth below
  "synth"        everything synthesized here with numpy
Everything is mono, 48 kHz float32 in [-1, 1].
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 48000
_rng = np.random.default_rng(7)  # deterministic: re-renders sound identical


def _t(dur: float) -> np.ndarray:
    return np.arange(int(dur * SR)) / SR


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, min(a, n))[: min(a, n)]
    if r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _band_sweep(noise: np.ndarray, f_from: float, f_to: float, width: float = 0.8) -> np.ndarray:
    """Band-pass filtered noise whose centre frequency glides f_from → f_to (overlap-add FFT)."""
    n, hop, size = len(noise), 512, 2048
    out = np.zeros(n + size)
    win = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1 / SR)
    for start in range(0, n, hop):
        seg = np.zeros(size)
        chunk = noise[start:start + size]
        seg[: len(chunk)] = chunk
        p = min(1.0, start / max(1, n - 1))
        fc = f_from * (f_to / f_from) ** p
        mask = np.exp(-0.5 * (np.log2(np.maximum(freqs, 1) / fc) / width) ** 2)
        out[start:start + size] += np.fft.irfft(np.fft.rfft(seg * win) * mask, size) * win
    return out[:n]


def whoosh(dur: float = 0.45, up: bool = True) -> np.ndarray:
    x = _band_sweep(_rng.standard_normal(int(dur * SR)), 350 if up else 3200, 3200 if up else 350)
    t = np.linspace(0, 1, len(x))
    shape = np.sin(np.pi * t ** (0.7 if up else 1.4)) ** 2
    return x * shape / (np.abs(x).max() + 1e-9)


def pop(f0: float = 950, f1: float = 520, dur: float = 0.09) -> np.ndarray:
    t = _t(dur)
    f = f1 + (f0 - f1) * np.exp(-t * 60)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38)
    x[: int(0.002 * SR)] += _rng.standard_normal(int(0.002 * SR)) * 0.3
    return x


def tick(f: float = 2400, dur: float = 0.035) -> np.ndarray:
    t = _t(dur)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 140)


def ding(f: float = 880, dur: float = 1.1) -> np.ndarray:
    t = _t(dur)
    partials = [(1.0, 1.0, 4.5), (2.0, 0.45, 6), (2.76, 0.3, 8), (5.4, 0.12, 12)]
    x = sum(a * np.sin(2 * np.pi * f * m * t) * np.exp(-t * d) for m, a, d in partials)
    return x * _env(len(t), 0.003, 0.05)


def error(dur: float = 0.34) -> np.ndarray:
    out = []
    for f in (330, 247):
        t = _t(dur / 2)
        tone = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 3 * f * t)
        out.append(tone * _env(len(t), 0.004, 0.04) * 0.8)
    return np.concatenate(out)


def thud(dur: float = 0.5) -> np.ndarray:
    t = _t(dur)
    f = 45 + 75 * np.exp(-t * 18)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)
    hit = _band_sweep(_rng.standard_normal(len(t)), 900, 300, 1.2) * np.exp(-t * 40)
    return body + 0.5 * hit / (np.abs(hit).max() + 1e-9)


def riser(dur: float = 1.3) -> np.ndarray:
    t = _t(dur)
    f = 260 * (4 ** (t / dur))
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    air = _band_sweep(_rng.standard_normal(len(t)), 600, 5000, 1.0)
    air /= np.abs(air).max() + 1e-9
    return (0.7 * tone + 0.4 * air) * (t / dur) ** 1.6 * _env(len(t), 0.02, 0.06)


def shimmer(dur: float = 0.9) -> np.ndarray:
    t = _t(dur)
    x = sum(np.sin(2 * np.pi * f * t + p) for f, p in ((2093, 0), (2637, 1.1), (3136, 2.3), (4186, .7)))
    return x / 4 * (0.6 + 0.4 * np.sin(2 * np.pi * 9 * t)) * _env(len(t), 0.08, 0.5)


def click(dur: float = 0.025) -> np.ndarray:
    t = _t(dur)
    return _rng.standard_normal(len(t)) * np.exp(-t * 300) + 0.6 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 200)


# kind → (generator, gain). Gains are relative to a voice at about -16 LUFS.
KINDS = {
    "intro": (lambda d: whoosh(0.6), 0.16),
    "whoosh": (lambda d: whoosh(0.42), 0.13),
    "whoosh_s": (lambda d: whoosh(0.3), 0.09),
    "zoom": (lambda d: whoosh(0.7), 0.12),
    "swell": (lambda d: whoosh(0.8, up=False), 0.11),
    "pop": (lambda d: pop(), 0.22),
    "pop2": (lambda d: pop(760, 430), 0.2),
    "blip": (lambda d: pop(1300, 1100, 0.07), 0.14),
    "tick": (lambda d: tick(), 0.12),
    "rise": (lambda d: pop(500, 820, 0.12), 0.14),
    "ding": (lambda d: ding(), 0.17),
    "error": (lambda d: error(), 0.13),
    "thud": (lambda d: thud(), 0.3),
    "riser": (lambda d: riser(min(d or 1.3, 1.8)), 0.06),
    "shimmer": (lambda d: shimmer(), 0.08),
    "click": (lambda d: click(), 0.25),
    "msg_out": (lambda d: pop(), 0.22),
    "msg_in": (lambda d: pop(760, 430), 0.2),
}

# kind → (SoundWeaver file, gain). Picked from the plugin's labels (bestContexts / feeling);
# gains match each file's 30 ms peak loudness to the synth sound it replaces.
PACK_DIR = Path(__file__).resolve().parent / "video" / "sfx" / "soundweaver"
SOUNDWEAVER = {
    "msg_out": ("message-sent-swish", 0.20),        # "'Off it goes'" — the user's bubble
    "msg_in": ("message-incoming-pop", 0.11),       # "A chat message landed" — the model's reply
    "pop": ("popover-pop", 0.13),                   # "A small overlay appears" — node / card / highlight
    "blip": ("select-item", 0.12),                  # "Precise 'picked'" — step items
    "tick": ("type-key", 0.16),                     # "Tiny key-tick" — token words typing in
    "rise": ("modal-open-rise", 0.063),             # "Something rising into focus" — bar grows
    "ding": ("success-warm-chime", 0.15),           # "Rewarding 'you did it'" — highlight / verdict
    "error": ("error-soft-thud", 0.17),             # "Gentle 'that didn't work'" — wrong answer
    "whoosh": ("transition-smooth-whoosh", 0.11),   # "Motion and continuity" — scene change
    "whoosh_s": ("whoosh-short", 0.10),             # "Quick motion accent"
    "zoom": ("transition-glide", 0.11),             # "Smooth guided movement" — zoom into a figure
    "swell": ("modal-close-fall", 0.057),           # "Dismissed and receding" — middle turns fade out
    "click": ("click-crisp-primary", 0.11),         # "primary CTA" — subscribe tap
}


def _resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x
    n_out = int(round(len(x) * sr_to / sr_from))
    spec = np.fft.rfft(x)
    out = np.zeros(n_out // 2 + 1, dtype=complex)
    k = min(len(spec), len(out))
    out[:k] = spec[:k]
    return np.fft.irfft(out, n_out) * (n_out / len(x))


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: only 16-bit PCM is supported")
        x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
        return _resample(x, w.getframerate(), SR)


def _sound(kind: str, dur: float, pack: str) -> np.ndarray:
    if pack == "soundweaver" and kind in SOUNDWEAVER:
        name, gain = SOUNDWEAVER[kind]
        f = PACK_DIR / f"{name}.wav"
        if f.exists():
            x = read_wav(f)
            return gain * x / (np.abs(x).max() + 1e-9)
    gen, gain = KINDS[kind]
    x = gen(dur)
    return gain * x / (np.abs(x).max() + 1e-9)


def sfx_track(events: list[dict], total: float, pack: str = "soundweaver") -> np.ndarray:
    out = np.zeros(int(total * SR) + SR)
    cache: dict[tuple, np.ndarray] = {}
    for ev in events:
        kind, at, dur = ev.get("kind"), float(ev.get("t", 0)), float(ev.get("d") or 0)
        if kind not in KINDS or at < 0 or at >= total:
            continue
        key = (kind, round(dur, 2))
        if key not in cache:
            cache[key] = _sound(kind, dur, pack)
        x = cache[key]
        i = int(at * SR)
        out[i:i + len(x)] += x[: len(out) - i]
    return out[: int(total * SR)]


def music_bed(total: float, bpm: float = 92) -> np.ndarray:
    """Am – F – C – G pad with a soft eighth-note arpeggio; quiet, steady, loopable."""
    beat = 60 / bpm
    chord_len = 4 * beat
    chords = [(57, 60, 64, 69), (53, 57, 60, 65), (48, 52, 55, 60), (55, 59, 62, 67)]  # MIDI
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    n = int(total * SR)
    pad = np.zeros(n + SR)
    arp = np.zeros(n + SR)
    t_chord = _t(chord_len + 0.6)
    k = 0
    while k * chord_len < total:
        notes = chords[k % len(chords)]
        seg = np.zeros(len(t_chord))
        for m in notes:
            f = hz(m - 12)
            for det in (-0.0015, 0.0015):
                seg += np.sin(2 * np.pi * f * (1 + det) * t_chord) + 0.25 * np.sin(4 * np.pi * f * (1 + det) * t_chord)
        seg *= _env(len(seg), 0.5, 0.7)
        i = int(k * chord_len * SR)
        pad[i:i + len(seg)] += seg[: len(pad) - i]
        for e in range(8):  # eighth notes
            m = notes[[0, 2, 1, 3, 2, 1, 3, 2][e]] + 12
            tp = _t(beat * 0.9)
            pluck = (np.sin(2 * np.pi * hz(m) * tp) + 0.2 * np.sin(4 * np.pi * hz(m) * tp)) * np.exp(-tp * 7)
            j = i + int(e * beat / 2 * SR)
            arp[j:j + len(pluck)] += (0.9 if e % 2 == 0 else 0.6) * pluck[: max(0, len(arp) - j)]
        k += 1
    x = pad[:n] / (np.abs(pad).max() + 1e-9) * 0.55 + arp[:n] / (np.abs(arp).max() + 1e-9) * 0.25
    fade = np.ones(n)
    fi, fo = int(1.0 * SR), int(1.6 * SR)
    fade[:fi] = np.linspace(0, 1, fi)
    fade[-fo:] = np.linspace(1, 0, fo)
    x *= fade
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-9) * 0.035  # ≈ -29 dBFS RMS before ducking


def write_wav(path: Path, x: np.ndarray) -> Path:
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path
