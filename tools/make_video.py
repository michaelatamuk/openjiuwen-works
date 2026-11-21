import os, subprocess, textwrap

OUT = os.path.dirname(os.path.abspath(__file__))
SC = os.path.join(OUT, "video_scenes")
os.makedirs(SC, exist_ok=True)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

BG = "#F4F5F9"
INK = "#111827"
MUT = "#6B7280"
PUR = "#6D28D9"
DARK = "#0B1020"

def svg(inner, bg=BG):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" font-family="Inter, Segoe UI, Arial, Helvetica, sans-serif">
<rect x="0" y="0" width="1600" height="900" fill="{bg}"/>
{inner}
</svg>'''

def t(x, y, s, size=24, fill=INK, weight=400, anchor="start", ls=0):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{ls}">{s}</text>')

def card(x, y, w, h, fill="#FFFFFF", stroke="#E5E7EB", sw=1.5, rx=18, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}"{d}/>')

scenes = []

# 1. invoice 21%
s = []
s.append(card(170, 120, 420, 660, "#FFFFFF", "#E5E7EB", 2, 34))
s.append(t(210, 190, "INVOICE", 18, MUT, 700, ls=3))
s.append(t(210, 232, "Berlin Utilities", 26, INK, 600))
s.append(t(210, 268, "Customer #4417", 18, MUT))
s.append(f'<line x1="210" y1="320" x2="550" y2="320" stroke="#E5E7EB" stroke-width="2"/>')
s.append(t(210, 380, "VAT", 22, MUT))
s.append(t(200, 520, "21%", 120, INK, 800, ls=-4))
s.append(t(210, 580, "should be 19%", 26, PUR, 600))
s.append(f'<line x1="210" y1="640" x2="550" y2="640" stroke="#E5E7EB" stroke-width="2"/>')
s.append(t(210, 692, "Total  1,210.00 EUR", 22, INK, 600))
s.append(t(700, 380, "A customer in Berlin,", 44, INK, 700))
s.append(t(700, 436, "Monday 09:00.", 44, INK, 700))
s.append(t(700, 500, "One line to support. Then", 24, MUT))
s.append(t(700, 536, "she waits.", 24, MUT))
scenes.append(("01_invoice_21", svg("\n".join(s))))

# 2. four days
s = []
s.append(t(120, 220, "Four days.", 104, INK, 800, ls=-3))
s.append(t(120, 282, "Almost none of it is the fix.", 28, MUT))
days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
x0, y0, step = 160, 520, 280
s.append(f'<line x1="{x0}" y1="{y0}" x2="{x0 + step*4}" y2="{y0}" stroke="#D1D5DB" stroke-width="4"/>')
for i, d in enumerate(days):
    x = x0 + i*step
    col = PUR if i == 4 else "#D1D5DB"
    s.append(f'<circle cx="{x}" cy="{y0}" r="14" fill="{col}"/>')
    s.append(t(x, y0+58, d, 26, PUR if i == 4 else INK, 700, "middle"))
s.append(t(800, 650, "a queue  ·  answers  ·  a review", 30, MUT, 400, "middle"))
scenes.append(("02_four_days", svg("\n".join(s))))

# 3. almost none of it
s = []
s.append(t(800, 380, "Almost none of it", 88, INK, 800, "middle", -2))
s.append(t(800, 480, "is writing code.", 88, PUR, 800, "middle", -2))
s.append(t(800, 570, "four days, one fix", 30, MUT, 400, "middle"))
scenes.append(("03_almost_none", svg("\n".join(s))))

# 4. rewind
s = []
s.append(t(800, 380, "Same Monday,", 96, "#F8FAFC", 800, "middle", -2))
s.append(t(800, 486, "again.", 96, "#A78BFA", 800, "middle", -2))
s.append(t(800, 580, "09:00", 34, "#64748B", 600, "middle", 4))
scenes.append(("04_rewind", svg("\n".join(s), DARK)))

# 5. three ways in
s = []
s.append(t(120, 220, "Three ways in.", 84, INK, 800, ls=-2))
rows = [("DigitalMate", "a failure caught in the app"),
        ("Jira · Linear · GitHub", "a bug already filed"),
        ("A person", "reported in the window")]
for i, (a, b) in enumerate(rows):
    y = 340 + i*140
    s.append(card(120, y-50, 780, 110, "#FFFFFF", "#E5E7EB", 1.5, 16))
    s.append(t(150, y, a, 32, INK, 700))
    s.append(t(150, y+34, b, 22, MUT))
s.append(f'<line x1="930" y1="480" x2="1010" y2="480" stroke="{PUR}" stroke-width="4"/>')
s.append(f'<path d="M 1010 460 L 1050 480 L 1010 500 Z" fill="{PUR}"/>')
s.append(card(1070, 380, 400, 200, "#FBFAFF", "#DDD6FE", 2, 18))
s.append(t(1270, 470, "one engine", 34, INK, 700, "middle"))
s.append(t(1270, 512, "eight automatic steps", 20, MUT, 400, "middle"))
scenes.append(("05_three_ways", svg("\n".join(s))))

# 6. plan + gate 1
s = []
s.append(t(120, 200, "A plan, then one click.", 76, INK, 800, ls=-2))
s.append(card(120, 280, 760, 420, "#FFFFFF", "#E5E7EB", 1.5, 18))
s.append(t(160, 340, "THE PLAN", 18, MUT, 700, ls=3))
for i, line in enumerate(["restore uploaded files for the whole session",
                          "keep the reference in session state",
                          "add a timeout for cleanup"]):
    s.append(f'<circle cx="170" cy="{392 + i*54}" r="6" fill="{PUR}"/>')
    s.append(t(196, f"{398 + i*54}", line, 24, "#374151"))
s.append(f'<rect x="160" y="596" width="300" height="66" rx="12" fill="{PUR}"/>')
s.append(t(310, 638, "Approve", 28, "#FFFFFF", 700, "middle"))
s.append(t(1040, 360, "GATE 1", 20, "#B45309", 700, ls=3))
s.append(t(1040, 420, "the plan", 44, INK, 700))
s.append(t(1040, 470, "one decision,", 24, MUT))
s.append(t(1040, 504, "one click.", 24, MUT))
scenes.append(("06_plan_gate", svg("\n".join(s))))

# 7. sandbox + check
s = []
s.append(t(120, 200, "Build. Then a second opinion.", 68, INK, 800, ls=-2))
s.append(card(120, 280, 640, 400, "#FFFFFF", "#E5E7EB", 1.5, 18))
s.append(t(160, 340, "BUILD", 18, MUT, 700, ls=3))
s.append(t(160, 400, "its own sandbox", 34, INK, 700))
s.append(t(160, 446, "a copy per task", 24, MUT))
s.append(t(160, 486, "nothing shared", 24, MUT))
s.append(card(840, 280, 640, 400, "#FBFAFF", "#DDD6FE", 2, 18))
s.append(t(880, 340, "CHECK", 18, PUR, 700, ls=3))
s.append(t(880, 400, "a fresh agent", 34, INK, 700))
s.append(t(880, 446, "tests the builder", 24, MUT))
s.append(t(880, 486, "never saw", 24, MUT))
s.append(f'<line x1="770" y1="480" x2="826" y2="480" stroke="{PUR}" stroke-width="4"/>')
s.append(f'<path d="M 826 460 L 866 480 L 826 500 Z" fill="{PUR}"/>')
scenes.append(("07_build_check", svg("\n".join(s))))

# 8. proof page
s = []
s.append(t(120, 200, "One page. Not a diff.", 76, INK, 800, ls=-2))
s.append(card(120, 280, 900, 420, "#FFFFFF", "#E5E7EB", 1.5, 18))
s.append(t(160, 336, "PROOF · fix-upload-loss", 18, MUT, 700, ls=2))
rows = [("what changed", "2 files, 41 lines"),
        ("what was tested", "17 scenarios, 3 hidden"),
        ("what it cost", "0.31 · 4 minutes")]
for i, (a, b) in enumerate(rows):
    y = 400 + i*86
    s.append(f'<line x1="160" y1="{y-28}" x2="980" y2="{y-28}" stroke="#F3F4F6" stroke-width="2"/>')
    s.append(t(160, y+8, a, 26, MUT))
    s.append(t(980, y+8, b, 26, INK, 700, "end"))
s.append(t(1080, 360, "the person reads", 24, MUT))
s.append(t(1080, 394, "for 60 seconds,", 24, MUT))
s.append(t(1080, 428, "not 60 minutes.", 24, PUR, 700))
scenes.append(("08_proof", svg("\n".join(s))))

# 9. release
s = []
s.append(t(800, 340, "One more click.", 88, INK, 800, "middle", -2))
s.append(f'<rect x="560" y="430" width="480" height="96" rx="16" fill="{PUR}"/>')
s.append(t(800, 492, "Release", 38, "#FFFFFF", 700, "middle"))
s.append(f'<rect x="660" y="580" width="280" height="56" rx="28" fill="#DCFCE7"/>')
s.append(t(800, 617, "released", 24, "#166534", 700, "middle"))
scenes.append(("09_release", svg("\n".join(s))))

# 10. return 19%
s = []
s.append(card(170, 100, 420, 640, "#FFFFFF", "#E5E7EB", 2, 34))
s.append(t(210, 170, "INVOICE", 18, MUT, 700, ls=3))
s.append(t(210, 212, "Berlin Utilities", 26, INK, 600))
s.append(f'<line x1="210" y1="260" x2="550" y2="260" stroke="#E5E7EB" stroke-width="2"/>')
s.append(t(210, 320, "VAT", 22, MUT))
s.append(t(200, 460, "19%", 120, PUR, 800, ls=-4))
s.append(t(210, 520, "correct", 26, "#166534", 700))
s.append(f'<line x1="210" y1="580" x2="550" y2="580" stroke="#E5E7EB" stroke-width="2"/>')
s.append(t(210, 632, "Total  1,190.00 EUR", 22, INK, 600))
s.append(f'<rect x="700" y="250" width="760" height="120" rx="18" fill="#FFFFFF" stroke="#E5E7EB" stroke-width="1.5"/>')
s.append(t(740, 300, "support thread · closed", 20, MUT))
s.append(t(740, 340, "“Fixed — thank you.”", 28, INK, 600))
s.append(f'<rect x="700" y="410" width="620" height="90" rx="18" fill="#DCFCE7"/>')
s.append(t(740, 466, "customer notified", 26, "#166534", 700))
s.append(t(700, 570, "The fix goes back", 40, INK, 700))
s.append(t(700, 620, "where the bug was seen.", 40, INK, 700))
scenes.append(("10_return_19", svg("\n".join(s))))

# 11. products
s = []
s.append(t(120, 200, "Built on what exists.", 72, INK, 800, ls=-2))
prods = [("jiuwenswarm", "builds: worktree, CI, auto-fix"),
         ("agent-core", "runs the checking agent"),
         ("PPMA", "remembers the project state"),
         ("Orbit", "optional: shares the proof")]
for i, (a, b) in enumerate(prods):
    y = 320 + i*110
    s.append(t(120, y, a, 34, INK, 700))
    s.append(t(520, y, b, 24, MUT))
scenes.append(("11_products", svg("\n".join(s))))

# 12. end card
s = []
s.append(t(800, 400, "openJiuwen Works", 88, INK, 800, "middle", -2))
s.append(t(800, 470, "The waiting moved. The judgement stayed.", 30, PUR, 600, "middle"))
scenes.append(("12_end", svg("\n".join(s))))

for name, content in scenes:
    p = os.path.join(SC, name + ".svg")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    out = os.path.join(SC, name + ".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--virtual-time-budget=2000", "--window-size=1600,900",
                    f"--screenshot={out}", "file:///" + p.replace("\\", "/")],
                   check=True, capture_output=True)
print("scenes:", len(scenes))
