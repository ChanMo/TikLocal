"""Regenerate the TikLocal brand assets from one geometry definition.

The mark is drawn on a 24-unit grid with 2-unit round strokes, the same
construction as the Feather icons used in the web UI. The wordmark is set in
Source Serif 4 (SIL OFL 1.1) and converted to outlines so no font ships.

Requirements (not project dependencies): ``pip install fonttools brotli pillow``
and the Source Serif 4 static WOFF2 files from ``npm pack @fontsource/source-serif-4``.

Usage:
    python scripts/build_brand.py --font-dir package/files
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "brand"
STATIC_BRAND_DIR = ROOT / "tiklocal" / "static" / "brand"

GREEN = "#36594F"
GREEN_DARK = "#B8CCBF"
SIGNAL = "#D9633B"
INK = "#23231F"
INK_DARK = "#E9E7DF"
PAPER = "#F7F6F2"

# The mark, in 24-unit grid coordinates.
STEM = ((9.0, 3.5), (9.0, 15.5))
HOOK_CENTER, HOOK_RADIUS = (12.0, 15.5), 3.0  # quarter arc from (9, 15.5) to (12, 18.5)
BAR = ((5.5, 8.5), (12.5, 8.5))
DOT_CENTER, DOT_RADIUS = (16.6, 18.5), 2.1
STROKE = 2.0
# Tight bounds of the drawn mark, used to center it on square tiles.
BOUNDS = (4.5, 2.5, DOT_CENTER[0] + DOT_RADIUS, DOT_CENTER[1] + DOT_RADIUS)

MARK_PATHS = (
    '<path d="M9 3.5v12a3 3 0 0 0 3 3"/>'
    '<path d="M5.5 8.5h7"/>'
)


def mark_svg(stroke: str, dot: str, title: str = "TikLocal") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="'
        f'{title}">\n'
        f'  <g fill="none" stroke="{stroke}" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{MARK_PATHS}</g>\n'
        f'  <circle cx="{DOT_CENTER[0]}" cy="{DOT_CENTER[1]}" r="{DOT_RADIUS}" fill="{dot}"/>\n'
        "</svg>\n"
    )


def favicon_svg() -> str:
    # Browsers render SVG favicons against their own tab color, so follow it.
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        f"  <style>.t{{stroke:{GREEN}}}@media (prefers-color-scheme:dark){{.t{{stroke:{GREEN_DARK}}}}}</style>\n"
        '  <g class="t" fill="none" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{MARK_PATHS}</g>\n'
        f'  <circle cx="{DOT_CENTER[0]}" cy="{DOT_CENTER[1]}" r="{DOT_RADIUS}" fill="{SIGNAL}"/>\n'
        "</svg>\n"
    )


def word_paths(font_dir: Path, size: float, tracking_em: float) -> tuple[str, float, float]:
    """Return (svg path data, advance width, cap height) for 'tik' light + 'Local' semibold."""
    runs = (
        ("tik", TTFont(font_dir / "source-serif-4-latin-300-normal.woff2")),
        ("Local", TTFont(font_dir / "source-serif-4-latin-600-normal.woff2")),
    )
    parts = []
    x = 0.0
    cap_height = 0.0
    for text, font in runs:
        upm = font["head"].unitsPerEm
        scale = size / upm
        cap_height = max(cap_height, font["OS/2"].sCapHeight * scale)
        glyph_set = font.getGlyphSet()
        cmap = font.getBestCmap()
        for char in text:
            name = cmap[ord(char)]
            pen = SVGPathPen(glyph_set, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
            # Font units are y-up; flip onto an SVG baseline at y = 0.
            glyph_set[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
            parts.append(pen.getCommands())
            x += glyph_set[name].width * scale + tracking_em * size
    return "".join(parts), x - tracking_em * size, cap_height


def lockup_svg(font_dir: Path, mark_color: str, text_color: str) -> str:
    size = 64.0
    scale = 80.0 / 24  # mark drawn at 80px per 24-unit grid
    gap = 22.0
    pad = 8.0
    left, top, right, bottom = BOUNDS
    path, advance, cap = word_paths(font_dir, size, tracking_em=-0.02)
    # Crop the mark to its drawn bounds so spacing is optical, not grid-based.
    mark_x = pad - left * scale
    mark_y = pad - top * scale
    mark_height = (bottom - top) * scale
    baseline = pad + mark_height / 2 + cap / 2
    text_x = pad + (right - left) * scale + gap
    width = text_x + advance + pad
    height = mark_height + pad * 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        'role="img" aria-label="TikLocal">\n'
        f'  <g transform="translate({mark_x:.2f} {mark_y:.2f}) scale({scale:.4f})">\n'
        f'    <g fill="none" stroke="{mark_color}" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{MARK_PATHS}</g>\n'
        f'    <circle cx="{DOT_CENTER[0]}" cy="{DOT_CENTER[1]}" r="{DOT_RADIUS}" fill="{SIGNAL}"/>\n'
        "  </g>\n"
        f'  <path transform="translate({text_x:.2f} {baseline:.2f})" fill="{text_color}" d="{path}"/>\n'
        "</svg>\n"
    )


def render_mark(size: int, background: str | None, fit_bounds: bool, stroke: float = STROKE) -> Image.Image:
    """Rasterize the mark with 8x supersampling.

    ``fit_bounds`` centers the drawn shape on the tile (icons); otherwise the
    full 24-unit box maps onto the image, matching the SVG favicon.
    """
    ss = 8
    canvas = size * ss
    image = Image.new("RGBA", (canvas, canvas), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    if fit_bounds:
        left, top, right, bottom = BOUNDS
        span = max(right - left, bottom - top)
        unit = canvas * 0.62 / span
        ox = canvas / 2 - (left + right) / 2 * unit
        oy = canvas / 2 - (top + bottom) / 2 * unit
    else:
        unit = canvas / 24
        ox = oy = 0.0

    def pt(x: float, y: float) -> tuple[float, float]:
        return ox + x * unit, oy + y * unit

    half = stroke / 2 * unit

    def cap(x: float, y: float) -> None:
        cx, cy = pt(x, y)
        draw.ellipse((cx - half, cy - half, cx + half, cy + half), fill=GREEN)

    for (x1, y1), (x2, y2) in (STEM, BAR):
        draw.line((pt(x1, y1), pt(x2, y2)), fill=GREEN, width=round(stroke * unit))
        cap(x1, y1)
        cap(x2, y2)

    hx, hy = pt(*HOOK_CENTER)
    outer = HOOK_RADIUS * unit + half
    draw.arc((hx - outer, hy - outer, hx + outer, hy + outer), 90, 180, fill=GREEN, width=round(stroke * unit))
    cap(HOOK_CENTER[0], HOOK_CENTER[1] + HOOK_RADIUS)

    dx, dy = pt(*DOT_CENTER)
    r = DOT_RADIUS * unit
    draw.ellipse((dx - r, dy - r, dx + r, dy + r), fill=SIGNAL)

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font-dir", type=Path, required=True, help="Directory with Source Serif 4 WOFF2 files")
    args = parser.parse_args()

    BRAND_DIR.mkdir(exist_ok=True)
    STATIC_BRAND_DIR.mkdir(parents=True, exist_ok=True)

    (BRAND_DIR / "tiklocal-mark.svg").write_text(mark_svg(GREEN, SIGNAL))
    (BRAND_DIR / "tiklocal-mark-dark.svg").write_text(mark_svg(GREEN_DARK, SIGNAL))
    (BRAND_DIR / "tiklocal-mark-mono.svg").write_text(mark_svg("currentColor", "currentColor"))
    (BRAND_DIR / "tiklocal-lockup.svg").write_text(lockup_svg(args.font_dir, GREEN, INK))
    (BRAND_DIR / "tiklocal-lockup-dark.svg").write_text(lockup_svg(args.font_dir, GREEN_DARK, INK_DARK))
    render_mark(512, PAPER, fit_bounds=True).save(BRAND_DIR / "tiklocal-avatar-512.png", optimize=True)

    (STATIC_BRAND_DIR / "favicon.svg").write_text(favicon_svg())
    render_mark(180, PAPER, fit_bounds=True).save(STATIC_BRAND_DIR / "apple-touch-icon.png", optimize=True)
    # A heavier stroke keeps the 16px tab icon from dissolving into anti-aliasing.
    small = render_mark(16, None, False, stroke=2.5)
    medium = render_mark(32, None, False)
    render_mark(48, None, False).save(
        STATIC_BRAND_DIR / "favicon.ico",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[small, medium],
    )


if __name__ == "__main__":
    main()
