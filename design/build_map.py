# Builds components-map.html (SVG with HTML text); render_map.mjs turns it into components-map.png.
from html import escape
from pathlib import Path

W, H = 2360, 1150
INK, BG, CARD = "#1f3038", "#ecf0f2", "#f7f9fa"
C = {"people": "#2B6CB0", "ai": "#1d5a33", "system": "#5d6b72", "human": "#8a2a1c"}
TAG = {"people": "PEOPLE", "ai": "AI", "system": "DATA AND SYSTEMS", "human": "HUMAN TAKES OVER"}
parts = []


def node(x, y, w, h, kind, title, body):
    col = C[kind]
    parts.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{CARD}" stroke="{col}" stroke-width="4"/>'
        f'<foreignObject x="{x}" y="{y}" width="{w}" height="{h}"><div xmlns="http://www.w3.org/1999/xhtml" class="n">'
        f'<div class="tag" style="color:{col}">{TAG[kind]}</div>'
        f'<div class="t">{escape(title)}</div><div class="b">{escape(body)}</div></div></foreignObject>')


def arrow(pts, n, bx, by, dashed=False, label=None, lx=None, ly=None):
    d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
    dash = ' stroke-dasharray="10 8"' if dashed else ''
    parts.append(f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="3"{dash} marker-end="url(#ah)"/>')
    parts.append(f'<circle cx="{bx}" cy="{by}" r="16" fill="{INK}"/>'
                 f'<text x="{bx}" y="{by + 6}" text-anchor="middle" class="num">{n}</text>')
    if label:
        parts.append(f'<text x="{lx}" y="{ly}" class="lab">{escape(label)}</text>')


for x, s in [(40, "1  FIND"), (420, "2  RESEARCH"), (800, "3  JUDGE"), (1610, "4  REVIEW"), (1990, "5  SEND")]:
    parts.append(f'<text x="{x}" y="118" class="col">{s}</text>')

# 1 find
node(40, 150, 160, 150, "system", "Daily timer", "08:00 IST, with nobody signed in.")
node(210, 150, 160, 150, "people", "Growth Lead", "Find companies now, or paste domains.")
node(40, 340, 330, 200, "system", "Hunter Discover", "Free. B2B SaaS, 11 to 200 people, in the US, UK, India, Canada and Australia. Skips any company researched before. Spares wait in a queue.")
node(40, 580, 330, 130, "system", "Run store (Neon)", "Runs, one decision record per company, cached pages.")
# 2 research
node(420, 150, 330, 150, "system", "Server research chain", "Each request researches for about 2 minutes, then hands on to the next. The page can be closed.")
node(420, 330, 330, 230, "system", "Site reader", "The company's own public pages only. Respects robots.txt and stops at blocks. Up to 4 extra pages when a fact is missing; code picks which page.")

# 3 AI section
parts.append(f'<rect x="800" y="130" width="760" height="510" rx="6" fill="#e3f1f2" stroke="{C["ai"]}" stroke-width="4"/>')
parts.append('<text x="820" y="168" class="aititle">AI SECTION: every point where the model uses judgment</text>')
parts.append('<text x="820" y="196" class="aisub">Claude Haiku reads and grades, Claude Sonnet writes. Each point has its own test cases.</text>')
chips = ["Already certified? (with the quote)", "Is it B2B SaaS?", "Stage and size signal", "Trigger: what changed",
         "Two pains from the evidence", "What this role is measured on", "Email: hook, pain, value, ask",
         "Refuse when there is no trigger", "Grade each sentence", "Follow past corrections"]
for i, c in enumerate(chips):
    col, row = divmod(i, 5)
    x, y = 820 + col * 365, 220 + row * 80
    parts.append(f'<rect x="{x}" y="{y}" width="350" height="64" rx="6" fill="{CARD}" stroke="{C["ai"]}" stroke-width="3"/>')
    parts.append(f'<text x="{x + 14}" y="{y + 39}" class="chip"><tspan class="chipn">{i + 1:02d}</tspan>  {escape(c)}</text>')
node(800, 680, 360, 190, "system", "Qualification rules (code)", "Certified, not B2B SaaS or too small: dropped. Unclear: flagged. Every quote must be on its page. A drop is replaced by a spare.")
node(1200, 680, 360, 190, "system", "Find the person (code)", "One Hunter search, plus a senior-only one if nobody fits. Ranked: security, engineering, operations, CEO. Confidence 70+. Large companies need a security lead.")

# 4 review
node(1610, 150, 330, 190, "system", "Review screen", "Only selected companies: an org chart each, the draft and its evidence. A research summary shows every company dropped and why.")
node(1610, 380, 330, 120, "people", "Growth Lead edits or skips", "Every change is kept as a correction.")
node(1610, 540, 330, 160, "human", "Growth Lead approves every send", "Nothing reaches a prospect without him. Flagged companies never enter the list.")
# 5 send
node(1990, 150, 330, 160, "system", "Gmail (SMTP)", "Sends to the operator's own inbox. A CC goes only to addresses he allowed; any other recipient is ignored.")
node(1990, 350, 330, 120, "people", "Growth Lead sends it on", "Outside the app, to the real prospect.")

# 6 learn band
parts.append('<text x="40" y="926" class="col">6  LEARN AND PROVE</text>')
node(40, 945, 700, 140, "system", "Corrections store (Neon)", "Before and after of every edit, its reason and which parts changed. The 3 closest go back to the writer; they never add facts. Paused if over half a run is skipped.")
node(800, 945, 760, 140, "system", "Tests", "Unit tests for every rule and failure (Hunter limits, blocked sites, Claude errors). Browser tests in Chrome with accessibility checks. A separate grader checks every draft.")
node(1610, 945, 710, 140, "system", "Kill numbers", "Weekly check (metrics.py): rewrite rate, minutes per company, false qualifies, contact accuracy, cost, against the kill criteria. Average disagreement shows on Review.")

# arrows, in the order of the flow
arrow([(120, 300), (120, 340)], 1, 120, 320)
arrow([(290, 300), (290, 340)], 2, 290, 320)
arrow([(205, 540), (205, 580)], 3, 205, 560)
arrow([(370, 645), (395, 645), (395, 225), (420, 225)], 4, 395, 440)
arrow([(585, 300), (585, 330)], 5, 585, 315)
arrow([(750, 445), (800, 445)], 6, 775, 445)
arrow([(980, 640), (980, 680)], 7, 980, 660)
arrow([(1160, 770), (1200, 770)], 8, 1180, 770)
arrow([(1380, 680), (1380, 640)], 9, 1380, 660, label="feeds the writer", lx=1404, ly=666)
arrow([(1560, 245), (1610, 245)], 10, 1585, 245)
arrow([(1775, 340), (1775, 380)], 11, 1775, 360)
arrow([(1775, 500), (1775, 540)], 12, 1775, 520)
arrow([(1940, 620), (1965, 620), (1965, 230), (1990, 230)], 13, 1965, 430)
arrow([(2155, 310), (2155, 350)], 14, 2155, 330)
arrow([(1610, 440), (1588, 440), (1588, 900), (390, 900), (390, 945)], 15, 1588, 780, dashed=True,
      label="every edit and skip", lx=1200, ly=892)
arrow([(740, 1015), (775, 1015), (775, 560), (800, 560)], 16, 775, 800, dashed=True)
arrow([(980, 945), (980, 870)], 17, 980, 922, dashed=True, label="tests every rule and AI point", lx=1000, ly=930)

# legend
ly, x = 1122, 40
for k, s in [("people", "People"), ("ai", "AI"), ("system", "Data and systems"), ("human", "Human takes over")]:
    parts.append(f'<rect x="{x}" y="{ly - 16}" width="26" height="26" rx="4" fill="{CARD}" stroke="{C[k]}" stroke-width="4"/>')
    parts.append(f'<text x="{x + 38}" y="{ly + 5}" class="leg">{s}</text>')
    x += 38 + len(s) * 11 + 50
parts.append(f'<path d="M {x} {ly - 3} L {x + 60} {ly - 3}" stroke="{INK}" stroke-width="3" stroke-dasharray="10 8"/>')
parts.append(f'<text x="{x + 74}" y="{ly + 5}" class="leg">Feedback and test path</text>')
x += 74 + 22 * 11 + 40
parts.append(f'<circle cx="{x + 14}" cy="{ly - 3}" r="14" fill="{INK}"/><text x="{x + 14}" y="{ly + 3}" text-anchor="middle" class="num">1</text>')
parts.append(f'<text x="{x + 40}" y="{ly + 5}" class="leg">Order of the flow</text>')

html = f'''<!doctype html><html><head><meta charset="utf-8"><title>components map</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;600&family=DM+Mono:wght@500&display=swap" rel="stylesheet">
<style>
html,body{{margin:0;background:{BG}}}
.n{{box-sizing:border-box;padding:12px 16px;font-family:'Instrument Sans',sans-serif;color:{INK};overflow:hidden;height:100%}}
.tag{{font-size:12px;font-weight:600;letter-spacing:.08em;margin-bottom:4px}}
.t{{font-weight:600;font-size:21px;line-height:1.15;margin-bottom:5px}}
.b{{font-size:16.5px;line-height:1.35}}
.num{{font-family:'DM Mono',monospace;font-weight:500;font-size:15px;fill:#ffffff}}
.col{{font-family:'Instrument Sans',sans-serif;font-weight:600;font-size:20px;letter-spacing:.06em;fill:{INK}}}
.lab{{font-family:'Instrument Sans',sans-serif;font-size:15px;font-weight:600;fill:{INK}}}
.leg{{font-family:'Instrument Sans',sans-serif;font-size:18px;fill:{INK}}}
.aititle{{font-family:'Instrument Sans',sans-serif;font-weight:600;font-size:21px;fill:{INK}}}
.aisub{{font-family:'Instrument Sans',sans-serif;font-size:16px;fill:#5d6b72}}
.chip{{font-family:'Instrument Sans',sans-serif;font-size:17px;font-weight:600;fill:{INK}}}
.chipn{{font-family:'DM Mono',monospace;font-weight:500;fill:{C["ai"]}}}
</style></head><body>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs><marker id="ah" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0 0 L12 6 L0 12 Z" fill="{INK}"/></marker></defs>
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="80" fill="{INK}"/>
<rect x="40" y="26" width="28" height="28" rx="4" fill="#0d7480"/>
<text x="86" y="52" style="font-family:'Instrument Sans',sans-serif;font-weight:600;font-size:30px;fill:#ffffff">Sprinto outbound agent: components map</text>
<text x="{W - 40}" y="50" text-anchor="end" style="font-family:'Instrument Sans',sans-serif;font-size:18px;fill:#b8c4ca">Companies found every morning, a checked draft out. The Growth Lead decides.</text>
{"".join(parts)}
</svg></body></html>'''
Path(__file__).with_name("components-map.html").write_text(html)
print("ok")
