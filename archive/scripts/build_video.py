import os, subprocess

OUT = r"C:\Workspace\openjiuwenothers\factory"
SC = os.path.join(OUT, "video_scenes")
AU = os.path.join(OUT, "video_audio")
FF = r"C:\Users\m00645993\AppData\Local\Temp\opencode\vidvenv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v9.0.2.exe"

scenes = [
    ("01_invoice_21", 8, 200),
    ("02_four_days", 12, 8500),
    ("03_almost_none", 8, 20300),
    ("04_rewind", 8, 28300),
    ("05_three_ways", 10, 36300),
    ("06_plan_gate", 12, 46300),
    ("07_build_check", 12, 58300),
    ("08_proof", 10, 70300),
    ("09_release", 8, 80300),
    ("10_return_19", 14, 88300),
    ("11_products", 8, 102300),
    ("12_end", 5, 110300),
]

concat = os.path.join(OUT, "scenes.txt")
with open(concat, "w", encoding="utf-8") as f:
    for name, dur, _ in scenes:
        f.write(f"file 'video_scenes/{name}.png'\nduration {dur}\n")
    f.write(f"file 'video_scenes/{scenes[-1][0]}.png'\n")

inputs = ["-f", "concat", "-safe", "0", "-i", concat]
for i, _ in enumerate(scenes, start=1):
    inputs += ["-i", os.path.join(AU, f"v{i:02d}.wav")]

parts = []
for i, (_, _, start) in enumerate(scenes, start=1):
    parts.append(f"[{i}:a]adelay={start}|{start}[a{i}]")
mix = "".join(f"[a{i}]" for i in range(1, len(scenes) + 1))
filter_complex = ";".join(parts) + f";{mix}amix=inputs={len(scenes)}:normalize=0[aout]"

out = os.path.join(OUT, "openjiuwen-works-concept.mp4")
cmd = [FF, "-y"] + inputs + [
    "-filter_complex", filter_complex,
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p", "-r", "30",
    "-c:a", "aac", "-b:a", "160k",
    "-shortest", out,
]
print("running ffmpeg...")
r = subprocess.run(cmd, capture_output=True, text=True)
print("return code:", r.returncode)
if r.returncode != 0:
    print(r.stderr[-3000:])
else:
    print("wrote", out, os.path.getsize(out), "bytes")
