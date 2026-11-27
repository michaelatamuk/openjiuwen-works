import os
import subprocess

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AN = os.path.join(OUT, "docs", "assets", "frames")
SC = AN
os.makedirs(SC, exist_ok=True)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

INK = "#111827"; MUT = "#6B7280"; PUR = "#6D28D9"; GREY = "#9CA3AF"

def cup(x, y):
    return (f'<path d="M {x} {y} l 24 0 l -4 -26 l -16 0 z" fill="#FFFFFF" stroke="{INK}" stroke-width="3"/>'
            f'<path d="M {x+24} {y-18} q 10 0 8 8 q -2 6 -10 4" fill="none" stroke="{INK}" stroke-width="3"/>')

def clock(cx, cy, r, ang):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#FFFFFF" stroke="{INK}" stroke-width="5"/>'
            f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy-r*0.62}" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
            f'<line x1="{cx}" y1="{cy}" x2="{cx+r*0.5}" y2="{cy}" stroke="{INK}" stroke-width="7" stroke-linecap="round" transform="rotate({ang} {cx} {cy})"/>'
            f'<circle cx="{cx}" cy="{cy}" r="6" fill="{INK}"/>')

def timeline(usual, works, names):
    x0, x1 = 360, 1480
    w = x1 - x0
    s = []
    s.append(f'<text x="{x0}" y="74" font-size="22" font-weight="700" fill="{MUT}" letter-spacing="2">TWO MONDAYS · ONE BUG</text>')

    # usual way
    s.append(f'<text x="{x0}" y="122" font-size="13" font-weight="700" fill="{MUT}" letter-spacing="1.6">THE USUAL WAY</text>')
    s.append(f'<rect x="{x0}" y="132" width="{w}" height="24" rx="12" fill="#E5E7EB"/>')
    s.append(f'<rect x="{x0}" y="132" width="{max(8, w*usual)}" height="24" rx="12" fill="{GREY}"/>')

    # works
    s.append(f'<text x="{x0}" y="184" font-size="13" font-weight="700" fill="{PUR}" letter-spacing="1.6">WITH OPENJIUWEN WORKS</text>')
    s.append(f'<rect x="{x0}" y="194" width="{w}" height="24" rx="12" fill="#EDE9FE"/>')
    s.append(f'<rect x="{x0}" y="194" width="{max(10, w*works)}" height="24" rx="12" fill="{PUR}"/>')
    s.append(f'<text x="{x0 + max(10, w*works) + 14}" y="212" font-size="14" font-weight="700" fill="{PUR}">1 h 45 min</text>')

    # axis
    s.append(f'<line x1="{x0}" y1="246" x2="{x1}" y2="246" stroke="#D1D5DB" stroke-width="2"/>')
    for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        x = x0 + w * i / 4
        s.append(f'<line x1="{x}" y1="246" x2="{x}" y2="256" stroke="#D1D5DB" stroke-width="2"/>')
        s.append(f'<text x="{x}" y="278" font-size="13" fill="{MUT}" text-anchor="middle">{d}</text>')
    return "\n".join(s)

def person(ox, bright, age, cups, cobweb, coffee, done, caption):
    wall = "#FBFAFF" if bright else "#ECEEF4"
    desk = "#EDE9FE" if bright else "#DDE1E9"
    sweater = "#C4B5FD" if bright else "#D6D3D1"
    skin = "#F7D9CC"; hair = "#3F3F46"
    s = []

    s.append(f'<rect x="{ox}" y="300" width="800" height="600" fill="{wall}"/>')
    s.append(f'<rect x="{ox}" y="640" width="800" height="260" fill="{desk}"/>')
    s.append(f'<line x1="{ox}" y1="640" x2="{ox+800}" y2="640" stroke="#D1D5DB" stroke-width="4"/>')

    lx, ly = ox + 470, 520
    s.append(f'<rect x="{lx}" y="{ly}" width="190" height="120" rx="10" fill="#FFFFFF" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<rect x="{lx+14}" y="{ly+14}" width="162" height="92" rx="6" fill="{"#EDE9FE" if bright else "#E5E7EB"}"/>')
    s.append(f'<rect x="{lx-12}" y="{ly+120}" width="214" height="14" rx="7" fill="{INK}"/>')

    bx, by = ox + 200, 470
    slump = 26 if age > 0.5 else 0
    hy = 420 + slump
    s.append(f'<rect x="{bx-80}" y="{by+slump}" width="170" height="200" rx="46" fill="{sweater}" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<path d="M {bx+80} {by+70+slump} L {ox+455} {by+120}" stroke="{sweater}" stroke-width="26" stroke-linecap="round"/>')
    s.append(f'<circle cx="{bx+5}" cy="{hy}" r="56" fill="{skin}" stroke="{INK}" stroke-width="4"/>')
    s.append(f'<path d="M {bx-51} {hy-14} q 10 -56 56 -56 q 46 0 56 56 q -30 -22 -56 -22 q -26 0 -56 22 z" fill="{hair}"/>')
    s.append(f'<circle cx="{bx-17}" cy="{hy-2}" r="15" fill="none" stroke="{INK}" stroke-width="3.5"/>')
    s.append(f'<circle cx="{bx+27}" cy="{hy-2}" r="15" fill="none" stroke="{INK}" stroke-width="3.5"/>')
    s.append(f'<line x1="{bx-2}" y1="{hy-2}" x2="{bx+12}" y2="{hy-2}" stroke="{INK}" stroke-width="3.5"/>')
    s.append(f'<circle cx="{bx-17}" cy="{hy-2}" r="3.5" fill="{INK}"/>')
    s.append(f'<circle cx="{bx+27}" cy="{hy-2}" r="3.5" fill="{INK}"/>')

    if bright:
        s.append(f'<path d="M {bx-12} {hy+24} q 18 14 36 0" stroke="{INK}" stroke-width="4" fill="none" stroke-linecap="round"/>')
    else:
        s.append(f'<path d="M {bx-12} {hy+28} q 18 -8 36 0" stroke="{INK}" stroke-width="4" fill="none" stroke-linecap="round"/>')

    if age > 0.2:
        bl = 10 + int(age * 60)
        s.append(f'<path d="M {bx-30} {hy+32} Q {bx+4} {hy+48} {bx+36} {hy+32} '
                 f'L {bx+32} {hy+58+bl} Q {bx+4} {hy+76+bl} {bx-26} {hy+58+bl} Z" fill="{hair}"/>')

    for i in range(cups):
        col = i % 3; row = i // 3
        s.append(cup(ox + 300 + col * 32, 636 - row * 26))

    if coffee:
        s.append(cup(ox + 372, 636))
        s.append(f'<path d="M {ox+380} 590 q 12 -26 0 -50" stroke="{GREY}" stroke-width="4" fill="none" stroke-linecap="round"/>')
        s.append(f'<path d="M {ox+398} 596 q 12 -22 0 -42" stroke="{GREY}" stroke-width="4" fill="none" stroke-linecap="round" opacity="0.7"/>')

    if cobweb:
        s.append(f'<g stroke="{GREY}" stroke-width="2" opacity="0.7">'
                 f'<path d="M {ox} 300 L {ox+150} 450 M {ox} 370 L {ox+80} 450 M {ox+70} 300 L {ox+150} 380"/>'
                 f'<path d="M {ox+34} 368 q 46 0 82 34" fill="none"/>'
                 f'<path d="M {ox+18} 412 q 60 0 108 44" fill="none"/></g>')

    if done:
        s.append(f'<g transform="rotate(-7 {ox+560} 380)">'
                 f'<rect x="{ox+420}" y="334" width="280" height="92" rx="10" fill="none" stroke="#16A34A" stroke-width="7"/>'
                 f'<text x="{ox+560}" y="396" font-size="40" font-weight="800" fill="#16A34A" text-anchor="middle" letter-spacing="4">DONE 10:45</text>'
                 f'</g>')

    s.append(f'<rect x="{ox+24}" y="770" width="752" height="86" rx="18" fill="#FFFFFF" opacity="0.95"/>')
    s.append(f'<text x="{ox+52}" y="822" font-size="26" font-weight="600" fill="{INK}">{caption}</text>')
    return "\n".join(s)

def frame(body):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" font-family="Inter, Segoe UI, Arial, Helvetica, sans-serif">
<rect width="1600" height="900" fill="#F4F5F9"/>
{body}
<rect x="0" y="300" width="1600" height="6" fill="{PUR}"/>
<rect x="794" y="300" width="12" height="600" fill="{PUR}"/>
<rect x="24" y="312" width="230" height="44" rx="22" fill="#111827"/>
<text x="139" y="341" font-size="15" font-weight="700" fill="#FFFFFF" text-anchor="middle" letter-spacing="1.6">THE USUAL WAY</text>
<rect x="824" y="312" width="330" height="44" rx="22" fill="{PUR}"/>
<text x="989" y="341" font-size="15" font-weight="700" fill="#FFFFFF" text-anchor="middle" letter-spacing="1.6">WITH OPENJIUWEN WORKS</text>
</svg>'''

beats = [
    # usual, works, clock, left(age,cups,cob), caption L, caption R, status, coffee, done
    (0.03, 0.006, 0,   0.0, 0, False, "Monday 09:00. A bug is reported.", "Monday 09:00. The same bug.",
     ["09:00 the signal", "09:20 the plan"], False, False),
    (0.12, 0.018, 35,  0.1, 1, False, "14:00. Still waiting.", "09:20. One click.",
     ["09:20 plan approved"], True, False),
    (0.30, 0.018, 70,  0.4, 3, False, "Tuesday. Another coffee.", "10:30. Built and checked.",
     ["10:30 own sandbox", "hidden tests"], True, False),
    (0.50, 0.018, 105, 0.7, 6, True,  "Wednesday. A beard.", "10:40. One page of proof.",
     ["10:40 changed", "tested, cost"], True, False),
    (1.00, 0.018, 165, 1.0, 9, True,  "Friday. Released. Nobody told her.", "10:45. Done. Nothing else happens here.",
     ["10:45 shipped", "customer told"], True, True),
]

frames = []
for i, (us, wo, ang, age, cups, cob, lcap, rcap, status, coffee, done) in enumerate(beats, start=1):
    top = clock(170, 165, 74, ang) + "\n" + timeline(us, wo, None)
    bottom = person(0, False, age, cups, cob, False, False, lcap) + "\n" + \
             person(800, True, 0, 0, False, coffee, done, rcap)
    frames.append((f"b{i}", frame(top + "\n" + bottom)))

body = f'''
<text x="800" y="250" font-size="34" fill="{MUT}" text-anchor="middle" letter-spacing="6">TWO MONDAYS</text>
<text x="400" y="520" font-size="150" font-weight="800" fill="{INK}" text-anchor="middle" letter-spacing="-6">4 days</text>
<text x="400" y="580" font-size="26" fill="{MUT}" text-anchor="middle">the usual way</text>
<text x="1200" y="520" font-size="150" font-weight="800" fill="{PUR}" text-anchor="middle" letter-spacing="-6">1:45</text>
<text x="1200" y="580" font-size="26" fill="{MUT}" text-anchor="middle">with openJiuwen Works</text>
<text x="800" y="710" font-size="30" fill="{INK}" text-anchor="middle">The waiting moved. The judgement stayed.</text>
'''
frames.append(("punch", frame(body)))

body = f'''
<text x="800" y="420" font-size="86" font-weight="800" fill="{INK}" text-anchor="middle" letter-spacing="-2">openJiuwen Works</text>
<text x="800" y="490" font-size="28" fill="{PUR}" text-anchor="middle">Same team, same code, same tests.</text>
'''
frames.append(("end", frame(body)))

for name, content in frames:
    p = os.path.join(SC, name + ".svg")
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    out = os.path.join(SC, name + ".png")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--virtual-time-budget=2500", "--window-size=1600,900",
                    f"--screenshot={out}", "file:///" + p.replace("\\", "/")],
                   check=True, capture_output=True)
print("frames:", [n for n, _ in frames])
