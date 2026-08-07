#!/usr/bin/env python3
"""Section headings as SVGs — the only way to get our own typeface on a
heading. Lowercase mono label, hairline rule running to the right edge.
Static; run once locally and commit. Alt text carries the word for
screen readers since image headings never reach GitHub's outline.
"""
import base64
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_B64 = base64.b64encode((ROOT / "assets" / "ui.woff2").read_bytes()).decode()

PALETTES = {
    "dark": {"accent": "#a78bfa", "faint": "#30363d"},
    "light": {"accent": "#6d28d9", "faint": "#d0d7de"},
}
HEADINGS = ["stats", "projects", "certs"]
W, H = 820, 30


def build(label, p):
    text_w = (len(label) + 2) * 8.4
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="{label}">'
        f"<defs><style>@font-face{{font-family:'JBM';"
        f"src:url(data:font/woff2;base64,{FONT_B64}) format('woff2');}}"
        f"text{{font-family:'JBM','JetBrains Mono',monospace;font-size:14px;fill:{p['accent']};"
        f"letter-spacing:2px;}}</style></defs>"
        f'<text x="0" y="19">{label}</text>'
        f'<line x1="{text_w:.0f}" y1="14" x2="{W}" y2="14" stroke="{p["faint"]}" stroke-width="1"/>'
        "</svg>"
    )


for theme, p in PALETTES.items():
    for label in HEADINGS:
        path = ROOT / "svg" / f"hd-{label}-{theme}.svg"
        path.write_text(build(label, p))
        print(f"wrote {path.name}")
