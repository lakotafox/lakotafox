#!/usr/bin/env python3
"""ASCII portrait -> animated typing SVG.

Reads assets/skull-source.jpg, renders a 90-column ASCII portrait and writes
svg/portrait-dark.svg and svg/portrait-light.svg. Each row types itself in
left-to-right (SMIL clipPath wipe with a cursor block riding the edge),
staggered top to bottom, printed once with fill="freeze".

Run once locally; output is committed. Not part of the nightly workflow.
"""
import base64
import pathlib

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAMP = " .`:-=+*cs#%@"  # dark -> bright, 13 levels
COLS = 90
CHAR_ASPECT = 0.48  # mono glyphs are ~2x taller than wide
FONT_SIZE = 12.9
CHAR_W = 7.74  # 0.600 em at 12.9px, matches JetBrains Mono exactly
LINE_H = CHAR_W / CHAR_ASPECT
ROW_STAGGER = 0.09
ROW_DUR = 0.55

PALETTES = {
    "dark": {"fill": "#a78bfa", "cursor": "#c4b5fd"},
    "light": {"fill": "#6d28d9", "cursor": "#7c3aed"},
}


def ascii_grid():
    im = Image.open(ROOT / "assets" / "skull-source.jpg").convert("L")
    arr = np.array(im)

    # The illustration sits on flat white: background = the white connected
    # component touching the border, not every bright pixel (skull highlights
    # are bright too).
    white = arr >= 235
    labels, _ = ndimage.label(white)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border_labels.discard(0)
    bg = np.isin(labels, list(border_labels))

    fg = ~bg
    ys, xs = np.where(fg)
    pad = 8
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, arr.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, arr.shape[1])
    arr, bg = arr[y0:y1, x0:x1], bg[y0:y1, x0:x1]

    h, w = arr.shape
    rows = int(COLS * (h / w) * CHAR_ASPECT)

    img = Image.fromarray(arr)
    img = ImageOps.autocontrast(img, cutoff=1)
    small = np.array(img.resize((COLS, rows), Image.LANCZOS), dtype=float)
    bg_small = np.array(
        Image.fromarray(bg.astype(np.uint8) * 255).resize((COLS, rows), Image.LANCZOS)
    ) > 127

    # Mild gamma lift so mid-tones spread across the ramp instead of pooling.
    norm = (small / 255.0) ** 0.85
    idx = (norm * (len(RAMP) - 1)).round().astype(int)
    idx[bg_small] = 0

    return ["".join(RAMP[i] for i in row) for row in idx]


def build_svg(lines, palette):
    fill, cursor = palette["fill"], palette["cursor"]
    n = len(lines)
    width = COLS * CHAR_W
    height = n * LINE_H

    font_b64 = base64.b64encode((ROOT / "assets" / "ramp.woff2").read_bytes()).decode()

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} {height:.2f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="ASCII skull portrait">',
        "<defs>",
        "<style>",
        "@font-face{font-family:'JBMRamp';src:url(data:font/woff2;base64,"
        + font_b64
        + ") format('woff2');}",
        f"text{{font-family:'JBMRamp','JetBrains Mono',monospace;font-size:{FONT_SIZE}px;"
        f"fill:{fill};white-space:pre;}}",
        "</style>",
    ]

    for i in range(n):
        end = ROW_STAGGER * i
        parts.append(
            f'<clipPath id="r{i}"><rect x="0" y="{i * LINE_H:.2f}" width="0" height="{LINE_H:.2f}">'
            f'<animate attributeName="width" from="0" to="{width:.2f}" dur="{ROW_DUR}s" '
            f'begin="{end:.2f}s" fill="freeze"/></rect></clipPath>'
        )
    parts.append("</defs>")

    for i, line in enumerate(lines):
        y = i * LINE_H + FONT_SIZE  # baseline inside the row box
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        parts.append(
            f'<g clip-path="url(#r{i})"><text x="0" y="{y:.2f}" xml:space="preserve" '
            f'textLength="{COLS * CHAR_W:.2f}" lengthAdjust="spacing">{safe}</text></g>'
        )
        # cursor block riding the wipe edge, hidden when its row finishes
        parts.append(
            f'<rect y="{i * LINE_H + 1:.2f}" width="{CHAR_W:.2f}" height="{LINE_H - 2:.2f}" '
            f'fill="{cursor}" opacity="0">'
            f'<animate attributeName="x" from="0" to="{width:.2f}" dur="{ROW_DUR}s" '
            f'begin="{ROW_STAGGER * i:.2f}s" fill="freeze"/>'
            f'<set attributeName="opacity" to="0.9" begin="{ROW_STAGGER * i:.2f}s" '
            f'end="{ROW_STAGGER * i + ROW_DUR:.2f}s"/>'
            "</rect>"
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    lines = ascii_grid()
    print(f"{len(lines)} rows x {COLS} cols")
    out = ROOT / "svg"
    out.mkdir(exist_ok=True)
    for name, palette in PALETTES.items():
        path = out / f"portrait-{name}.svg"
        path.write_text(build_svg(lines, palette))
        print(f"wrote {path} ({path.stat().st_size // 1024} KB)")
    # plain-text preview for tuning
    print("\n".join(lines))


if __name__ == "__main__":
    main()
