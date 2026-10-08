"""Write the two post charts as SVG (render: rsvg-convert -z 2 X.svg -o X.png)."""

INK, MUTED, GRID, BG = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BEFORE, AFTER = "#9a9993", "#2a78d6"
W, H, L, R, T, B = 900, 500, 70, 30, 90, 70
FONT = 'font-family="-apple-system, Helvetica, Arial, sans-serif"'


def text(x, y, s, size=14, fill=INK, anchor="middle", weight="normal"):
    return (f'<text x="{x}" y="{y}" {FONT} font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{s}</text>')


def bar(x, y0, w, h, fill):
    # rounded data end at the top, square at the baseline
    r = 4
    return (f'<path d="M{x},{y0} v{-(h - r)} q0,{-r} {r},{-r} h{w - 2 * r} '
            f'q{r},0 {r},{r} v{h - r} z" fill="{fill}"/>')


def chart(title, subtitle, groups, series, ymax, out):
    pw, ph = W - L - R, H - T - B
    y = lambda v: T + ph - v / ymax * ph
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
         f'<rect width="{W}" height="{H}" fill="{BG}"/>',
         text(L, 34, title, 20, anchor="start", weight="600"),
         text(L, 58, subtitle, 14, MUTED, anchor="start")]
    for v in range(0, ymax + 1, 5):
        s.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v)}" y2="{y(v)}" stroke="{GRID}"/>')
        s.append(text(L - 10, y(v) + 5, v, 12, MUTED, anchor="end"))
    s.append(text(18, T + ph / 2, "tokens/s", 12, MUTED).replace("<text", f'<text transform="rotate(-90 18 {T + ph / 2})"'))
    gw = pw / len(groups)
    n = len(series)
    bw = min(70, gw * 0.7 / n)
    for i, (label, vals) in enumerate(groups):
        cx = L + gw * (i + 0.5)
        x0 = cx - (bw * n + 2 * (n - 1)) / 2
        for j, v in enumerate(vals):
            x = x0 + j * (bw + 2)
            fill = series[j][1] if n > 1 else (AFTER if i == len(groups) - 1 else BEFORE)
            s.append(bar(x, y(0), bw, y(0) - y(v), fill))
            s.append(text(x + bw / 2, y(v) - 8, v, 14, INK, weight="600"))
        for k, line in enumerate(label.split("|")):
            s.append(text(cx, T + ph + 22 + 17 * k, line, 13, INK if k == 0 else MUTED))
    if n > 1:
        lx = W - R - 260
        for j, (name, fill) in enumerate(series):
            s.append(f'<rect x="{lx + j * 130}" y="28" width="14" height="14" rx="3" fill="{fill}"/>')
            s.append(text(lx + j * 130 + 20, 40, name, 13, INK, anchor="start"))
    s.append("</svg>")
    open(out, "w").write("\n".join(s))


chart("One llama.cpp upgrade: +26% to +69% decode",
      "Swift IQ3_XXS + MTP 6/0.8 on an M4 Pro 64 GB; same model file and prompts, reasoning task",
      [("16k context|+26%", [18.9, 23.8]), ("64k context|+51%", [14.4, 21.7]),
       ("120k context|+69%", [10.6, 17.9])],
      [("b11139", BEFORE), ("b11443", AFTER)], 30, "b11443-ab.svg")

chart("A month of changes, real agent work at 64–128k context",
      "Median decode t/s from server logs, M4 Pro 64 GB; the last step is one llama.cpp upgrade",
      [("Sep 8|AD-4.27, no MTP", [9.4]), ("Sep 20|AD-3.84 + MTP", [11.7]),
       ("Sep 26|Swift, b11139", [13.8]), ("Sep 29|MTP 6/0.8", [15.2]),
       ("Oct 7|b11443", [23.1])],
      [("decode", BEFORE)], 30, "decode-by-era.svg")
