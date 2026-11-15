"""Render the 'image' eval cases as photo-like PNGs (typed list, slight tilt, grain).

python scripts/make_eval_images.py
"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "tests" / "eval_set"


def font(size):
    for f in ["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "Arial.ttf",
              "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"]:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(text: str, seed: int) -> Image.Image:
    rng = random.Random(seed)
    lines = ["Medications"] + text.split("\n")
    f, fh = font(30), font(36)
    W, H = 1100, 140 + 60 * len(lines)
    paper = (rng.randint(240, 252), rng.randint(236, 248), rng.randint(222, 238))
    img = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(img)
    y = 50
    for i, ln in enumerate(lines):
        d.text((60 + rng.randint(-4, 4), y), ln, fill=(25, 25, 35), font=fh if i == 0 else f)
        y += 60 if i else 75
    img = img.rotate(rng.uniform(-2.5, 2.5), expand=True, fillcolor=(120, 115, 105))
    px = img.load()
    for _ in range(img.size[0] * img.size[1] // 60):
        x, yy = rng.randrange(img.size[0]), rng.randrange(img.size[1])
        v = rng.randint(-35, 35)
        r, g, b = px[x, yy]
        px[x, yy] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def main():
    cases = json.loads((EVAL / "cases.json").read_text())["cases"]
    (EVAL / "images").mkdir(exist_ok=True)
    for i, c in enumerate(cases):
        if c["input"] == "image":
            render(c["text"], seed=i).save(EVAL / "images" / f"{c['id']}.png")
            print("wrote", c["id"])


if __name__ == "__main__":
    main()
