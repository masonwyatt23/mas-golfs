"""Generate a tileable grass detail texture for the Mas Golfs Godot terrain.

The terrain is a flat unshaded green today — the single biggest reason it
reads as a diorama, not a golf course. This texture gives the grass real
micro-detail: per-blade variation, clumping, and a subtle directional
grain. It is TILEABLE (every speckle is drawn with wraparound) so the
terrain shader can repeat it across the whole course without seams.

Output: godot/tools/grass-detail.png (512x512, RGB).
The terrain shader tiles it at ~1 tile per 4 yd and multiplies it by the
fairway/rough/green base colors, so this texture carries DETAIL (relative
brightness), not the absolute color — its mean is ~0.85 so it darkens
slightly and adds variation.
Run: python3 godot/tools/make_grass_texture.py
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 512
OUT = "godot/tools/grass-detail.png"


def main() -> None:
    rng = np.random.default_rng(7)
    # Base: mid grey-green in value terms (the shader multiplies by the
    # base color, so the texture is a brightness modulator, mean ~0.85).
    img = Image.new("RGB", (SIZE, SIZE), (218, 218, 218))
    draw = ImageDraw.Draw(img)

    # Fine grain: thousands of tiny blade strokes, drawn with wraparound
    # so the texture tiles seamlessly in both axes. This is the grass —
    # short diagonal strokes, mostly near the base brightness, with a
    # spread of darker and lighter blades for variation.
    def blade(x, y, length, shade):
        # Draw the same stroke at all 9 wrapped offsets; the ones that
        # land off-canvas are clipped, the wrapped ones land on the edge.
        for dx in (-SIZE, 0, SIZE):
            for dy in (-SIZE, 0, SIZE):
                draw.line([(x + dx, y + dy), (x + dx + 1, y + dy + length)],
                          fill=shade, width=1)

    for _ in range(42000):
        x = int(rng.integers(0, SIZE))
        y = int(rng.integers(0, SIZE))
        length = int(rng.integers(2, 7))
        # Shade: mostly near the base, some darker blades, some lighter.
        v = int(rng.normal(218, 26))
        v = max(140, min(252, v))
        # Slight green tint variation (blades are greener than the base).
        blade(x, y, length, (v - 12, v, v - 18))

    # Clumps: a few hundred SMALL soft darker patches (uneven growth).
    # Kept tiny and subtle — the first version's big blobs read as
    # polka dots, not grass. These are just a whisper of variation.
    for _ in range(300):
        x = int(rng.integers(0, SIZE))
        y = int(rng.integers(0, SIZE))
        r = int(rng.integers(2, 6))
        v = int(rng.normal(208, 10))
        v = max(185, min(232, v))
        for dx in (-SIZE, 0, SIZE):
            for dy in (-SIZE, 0, SIZE):
                draw.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r],
                             fill=(v - 8, v, v - 12))

    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img.save(OUT)
    # Verify the mean is near the target (detail modulator, ~0.85).
    arr = np.asarray(img, dtype=float) / 255.0
    print(f"wrote {OUT} ({SIZE}x{SIZE}); mean brightness {arr.mean():.3f}")


if __name__ == "__main__":
    main()
