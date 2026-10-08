"""Draws flash-next-silos.svg: provider silos as columns, time running down."""
W, H = 1000, 1310
COLS = ["ista", "atomic", "ukisai", "mac", "unsloth", "llama"]
HEAD = {
    "ista":    ("🎓", "ISTA",       "shrink science",  "#e0e7ff", "#3a0ca3"),
    "atomic":  ("📦", "ATOMICCHAT", "shrinks the brain", "#e3f2ec", "#2d6a4f"),
    "ukisai":  ("🏎️", "UKISAI",     "retrains it",     "#fff4cc", "#a07800"),
    "mac":     ("🖥️", "OUR SANDPIT", "speed on real work",   "#d7f3fb", "#0077b6"),
    "unsloth": ("🦥", "UNSLOTH",    "runs it first",   "#ddf5e0", "#1b4332"),
    "llama":   ("⚙️", "LLAMA.CPP",  "the engine",      "#eceef0", "#495057"),
}
X0, CW, BW, BH = 95, 150, 130, 52
cx = {c: X0 + i * CW + CW / 2 for i, c in enumerate(COLS)}
ROWS = [("before", 300), ("Sep 8", 450), ("Sep 14", 580), ("Sep 24", 710),
        ("Sep 25", 820), ("Sep 28", 940), ("Oct 7", 1100)]
Y = dict(ROWS)

# id: (col, y, line1, line2, emphasis)
N = {
    "gsq":    ("ista", 280, "GSQ", "smart rounding", 0),
    "rco":    ("ista", 350, "RCO", "bit budget", 0),
    "ad427":  ("atomic", Y["Sep 8"], "4.27-bit", "big, tight fit", 0),
    "ad384":  ("atomic", Y["Sep 14"], "3.84-bit", "room for extras", 0),
    "swift":  ("ukisai", Y["Sep 24"], "Swift", "thinks 56% less", 0),
    "swift3": ("ukisai", Y["Sep 25"], "Swift 3-bit", "same answers", 1),
    "eng":    ("llama", 300, "Engine", "runs on Mac", 0),
    "tune":   ("llama", Y["Sep 25"], "Mac tuning", "+15% speed", 0),
    "fix":    ("llama", Y["Oct 7"], "Long-text fix", "+69% long", 1),
    "srv":    ("unsloth", Y["Sep 8"], "Server + MTP", "first to run it", 0),
    "fit":    ("unsloth", Y["Sep 25"], "Fit tricks", "makes it fit", 0),
    "srv2":   ("unsloth", Y["Oct 7"], "New server", "ships the fix", 1),
}
# median decode on real agent work at 64-128k context, pooled per era from server logs
MAC = [("m1", Y["Sep 8"], 9.4, "9.4 t/s"), ("m2", Y["Sep 14"], 11.7, "11.7 t/s"),
       ("m3", Y["Sep 25"], 13.8, "13.8 t/s"), ("m4", Y["Sep 28"], 15.2, "15.2 t/s"),
       ("m5", Y["Oct 7"], 25.1, "25.1 t/s")]
for k, y, v, t in MAC:
    N[k] = ("mac", y, t, "", 2 if k == "m5" else 0)

def box(k):
    c, y, *_ = N[k]
    return cx[c], y

out = []
a = out.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  'font-family="-apple-system, Helvetica, Arial, sans-serif">')
a('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
  'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#444"/></marker>'
  '<marker id="arb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
  'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#e85d04"/></marker></defs>')
a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
a('<text x="500" y="38" text-anchor="middle" font-size="26" font-weight="700" fill="#111">'
  'Who made our Flash-Next fast?</text>')
a('<text x="500" y="64" text-anchor="middle" font-size="14" fill="#555">'
  'Each column is a provider. Time runs down the page. Arrows show who handed what to whom.</text>')

# Qwen banner: the origin of everything
a('<rect x="95" y="90" width="900" height="92" rx="14" fill="#fde2e4" stroke="#c9184a" stroke-width="2"/>')
a('<text x="545" y="122" text-anchor="middle" font-size="22" font-weight="700" fill="#c9184a">'
  '🧠 QWEN · builds the brain everyone starts from</text>')
for x, t in [(320, "Flash-Next 176B (brain)"), (620, "Vision (eyes)"), (770, "MTP (guesser)")]:
    pw = 280 if "brain" in t else 140
    a(f'<rect x="{x-pw/2}" y="138" width="{pw}" height="32" rx="16" fill="#fff" stroke="#c9184a"/>'
      f'<text x="{x}" y="159" text-anchor="middle" font-size="14" fill="#111">{t}</text>')

# silo columns
for c in COLS:
    em, name, tag, fill, stroke = HEAD[c]
    x = cx[c] - CW / 2 + 5
    a(f'<rect x="{x}" y="200" width="{CW-10}" height="950" rx="12" fill="{fill}" '
      f'stroke="{stroke}" stroke-opacity="0.35"/>')

# time axis
for label, y in ROWS:
    if label == "before":
        a(f'<text x="80" y="{y+5}" text-anchor="end" font-size="13" fill="#777" font-style="italic">earlier</text>')
        continue
    a(f'<line x1="88" y1="{y}" x2="{W-8}" y2="{y}" stroke="#bbb" stroke-dasharray="3 5"/>')
    a(f'<text x="80" y="{y+5}" text-anchor="end" font-size="14" font-weight="600" fill="#333">{label}</text>')
a('<line x1="86" y1="270" x2="86" y2="1140" stroke="#999" stroke-width="2" marker-end="url(#ar)"/>')

def label(x, y, t, hot=False):
    w = 7.4 * len(t) + 14
    col = "#e85d04" if hot else "#333"
    a(f'<rect x="{x-w/2}" y="{y-11}" width="{w}" height="21" rx="10" fill="#fff" stroke="{col}" stroke-width="1"/>'
      f'<text x="{x}" y="{y+4}" text-anchor="middle" font-size="12.5" font-weight="600" fill="{col}">{t}</text>')

def edge(p, q, t=None, hot=False, lp=None, bend=None):
    (x1, y1), (x2, y2) = p, q
    col, mk, sw = ("#e85d04", "arb", 3.5) if hot else ("#444", "ar", 1.6)
    if bend == "down-right":   # leave downward, arrive from the left
        d = f"M{x1},{y1} C{x1},{y2} {x1},{y2} {x2},{y2}"
    elif bend == "side-down":  # leave sideways, arrive from above
        d = f"M{x1},{y1} C{x2},{y1} {x2},{y1} {x2},{y2}"
    elif abs(x1 - x2) < 1 or abs(y1 - y2) < 1:
        d = f"M{x1},{y1} L{x2},{y2}"
    else:
        mx = (x1 + x2) / 2
        d = f"M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}"
    a(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" marker-end="url(#{mk})"/>')
    if t:
        lx, ly = lp or ((x1 + x2) / 2, (y1 + y2) / 2)
        label(lx, ly, t, hot)

L = lambda k: (box(k)[0] - BW / 2, box(k)[1])
R = lambda k: (box(k)[0] + BW / 2, box(k)[1])
T = lambda k: (box(k)[0], box(k)[1] - BH / 2)
B = lambda k: (box(k)[0], box(k)[1] + BH / 2)

# from the Qwen banner
edge((cx["atomic"], 170), T("ad427"), "¼ size", lp=(cx["atomic"], 330))
edge((300, 170), T("swift"), "retrained", lp=(cx["ukisai"], 380), bend="side-down")
edge((cx["unsloth"], 170), T("srv"), "MTP repack", lp=(cx["unsloth"], 330))
# inside / across silos
edge(B("gsq"), T("rco"))
edge(B("rco"), L("swift3"), "recipe", bend="down-right", lp=(cx["ista"], 640))
edge(B("swift"), T("swift3"), "shrunk")
edge(B("ad427"), T("ad384"), "smaller")
edge(R("ad427"), L("m1"))
edge(R("ad384"), L("m2"), "+ vision")
edge(R("swift3"), L("m3"))
edge(L("srv"), (cx["mac"] + BW / 2, Y["Sep 14"] - 8), "+ MTP", lp=(cx["unsloth"] - 75, 520))
edge(L("fit"), R("m3"))
edge(B("eng"), R("srv"), "base", bend="down-right", lp=(cx["llama"], 390))
edge(L("tune"), R("fit"))
edge(B("m3"), T("m4"), "tuned +10%")
edge(L("fix"), R("srv2"), hot=True)
edge(L("srv2"), R("m5"), hot=True)

a('<rect x="555" y="1013" width="430" height="40" rx="20" fill="#e85d04"/>'
  '<text x="770" y="1039" text-anchor="middle" font-size="17" font-weight="700" fill="#fff">'
  '⚡ One engine fix: +65% on real work</text>')
a(f'<path d="M620,1053 L620,{1100-31}" stroke="#e85d04" stroke-width="3.5" marker-end="url(#arb)"/>')

# headers on top of the arrows
for c in COLS:
    em, name, tag, fill, stroke = HEAD[c]
    a(f'<rect x="{cx[c]-CW/2+5}" y="200" width="{CW-10}" height="54" rx="12" fill="{fill}"/>')
    a(f'<text x="{cx[c]}" y="226" text-anchor="middle" font-size="15" font-weight="700" fill="{stroke}">{em} {name}</text>')
    a(f'<text x="{cx[c]}" y="244" text-anchor="middle" font-size="12" fill="{stroke}">{tag}</text>')

# boxes
for k, (c, y, l1, l2, emph) in N.items():
    _, _, _, fill, stroke = HEAD[c]
    x = cx[c]
    if c == "mac":
        v = next(m[2] for m in MAC if m[0] == k)
        h = 62 if emph else BH
        a(f'<rect x="{x-BW/2}" y="{y-h/2}" width="{BW}" height="{h}" rx="10" fill="#fff" '
          f'stroke="{"#e85d04" if emph else stroke}" stroke-width="{3 if emph else 1.8}"/>')
        bw = (BW - 20) * v / 25.1
        a(f'<rect x="{x-BW/2+10}" y="{y+4}" width="{bw}" height="{12 if emph else 10}" rx="5" '
          f'fill="{"#e85d04" if emph else stroke}"/>')
        a(f'<text x="{x}" y="{y-6}" text-anchor="middle" font-size="{20 if emph else 16}" '
          f'font-weight="700" fill="#111">{l1}</text>')
        continue
    sw, sc = (3, "#e85d04") if emph else (1.8, stroke)
    a(f'<rect x="{x-BW/2}" y="{y-BH/2}" width="{BW}" height="{BH}" rx="10" fill="#fff" stroke="{sc}" stroke-width="{sw}"/>')
    a(f'<text x="{x}" y="{y-4}" text-anchor="middle" font-size="14.5" font-weight="700" fill="#111">{l1}</text>')
    a(f'<text x="{x}" y="{y+14}" text-anchor="middle" font-size="12" fill="#555">{l2}</text>')

# footer
a('<rect x="95" y="1172" width="900" height="118" rx="12" fill="#fff8f0" stroke="#e85d04" stroke-opacity="0.5"/>')
for i, t in enumerate([
    "⚡ The biggest jump: one engine fix (Oct 7) took real work from 15.2 to 25.1 t/s, with the same model file.",
    "🎓 + 🏎️ The model we run is a team effort: UkisAI's retrained Swift, shrunk with ISTA's recipe.",
    "🦥 Unsloth's tricks are why a 176B-parameter model fits in our 64 GB Mac at all.",
    "t/s = tokens per second (about ¾ word each): median decode on our real agent work at 64–128k context, from server logs.",
]):
    a(f'<text x="115" y="{1200 + i*26}" font-size="{12.5 if i == 3 else 14.5}" '
      f'fill="{"#666" if i == 3 else "#222"}">{t}</text>')
a('</svg>')
open(__file__.replace("make_silos.py", "flash-next-silos.svg"), "w").write("\n".join(out))
