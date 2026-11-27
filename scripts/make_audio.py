import math
import os
import wave

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "assets", "film", "frames")
SR = 22050
DUR = 46.0
N = int(SR * DUR)

buf = [0.0] * N

def add(samples, start, amp):
    i0 = int(start * SR)
    for i, s in enumerate(samples):
        j = i0 + i
        if 0 <= j < N:
            buf[j] += s * amp

# pad: slow low drone
for i in range(N):
    t = i / SR
    lfo = 0.75 + 0.25 * math.sin(2 * math.pi * 0.08 * t)
    buf[i] += (0.030 * math.sin(2 * math.pi * 110 * t) +
               0.018 * math.sin(2 * math.pi * 164.81 * t)) * lfo

# clock ticks once a second while the left side waits
tick_n = int(0.020 * SR)
tick = [math.sin(2 * math.pi * 1000 * i / SR) * math.exp(-i / (0.004 * SR)) for i in range(tick_n)]
for s in range(0, 35):
    add(tick, float(s), 0.16)

# ding on every completed step on the right
ding_n = int(0.55 * SR)
ding = []
for i in range(ding_n):
    t = i / SR
    env = math.exp(-t / 0.16)
    ding.append((math.sin(2 * math.pi * 880 * t) + 0.55 * math.sin(2 * math.pi * 1320 * t)) * env)
for t0 in (0.2, 7.2, 14.2, 21.2, 28.2):
    add(ding, t0, 0.22)

# fades
fade_in = int(1.0 * SR)
fade_out = int(2.0 * SR)
for i in range(fade_in):
    buf[i] *= i / fade_in
for i in range(fade_out):
    buf[N - 1 - i] *= i / fade_out

peak = max(abs(x) for x in buf) or 1.0
scale = 0.85 / peak
path = os.path.join(OUT, "ambience.wav")
with wave.open(path, "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(
        int(max(-1.0, min(1.0, x * scale)) * 32767).to_bytes(2, "little", signed=True)
        for x in buf))
print("wrote", path, os.path.getsize(path))
