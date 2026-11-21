import os, subprocess

OUT = r"C:\Workspace\openjiuwenothers\factory"
FR = os.path.join(OUT, "anim", "frames")
AN = os.path.join(OUT, "anim")
FF = r"C:\Users\m00645993\AppData\Local\Temp\opencode\vidvenv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v9.0.2.exe"

scenes = [("b1", 7), ("b2", 7), ("b3", 7), ("b4", 7), ("b5", 8), ("punch", 6), ("end", 5)]
total = sum(d for _, d in scenes)

concat = os.path.join(AN, "scenes.txt")
with open(concat, "w", encoding="utf-8") as f:
    for name, dur in scenes:
        f.write(f"file 'frames/{name}.png'\nduration {dur}\n")
    f.write(f"file 'frames/{scenes[-1][0]}.png'\n")

inputs = ["-f", "concat", "-safe", "0", "-i", concat,
          "-i", os.path.join(AN, "ambience.wav"),
          "-i", os.path.join(AN, "a1.wav"),
          "-i", os.path.join(AN, "a2.wav")]

# a1 at punch start (35s), a2 at end start (41s)
filter_complex = ("[1:a]volume=0.55[amb];"
                  "[2:a]adelay=35200|35200[a1];[3:a]adelay=41200|41200[a2];"
                  "[amb][a1][a2]amix=inputs=3:normalize=0[aout]")

out = os.path.join(OUT, "openjiuwen-works-two-mondays.mp4")
cmd = [FF, "-y"] + inputs + [
    "-filter_complex", filter_complex,
    "-map", "0:v", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
    "-pix_fmt", "yuv420p", "-r", "30",
    "-c:a", "aac", "-b:a", "160k",
    "-t", str(total), out,
]
r = subprocess.run(cmd, capture_output=True, text=True)
print("rc", r.returncode, "size", os.path.getsize(out) if os.path.exists(out) else 0)
if r.returncode != 0:
    print(r.stderr[-2500:])
