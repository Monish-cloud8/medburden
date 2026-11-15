"""Create 3 sample photos in demo/: a typed medication list and two pharmacy pill-bottle labels.
All names and the pharmacy are fictional.   python scripts/make_demo_images.py"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from make_eval_images import font

DEMO = Path(__file__).resolve().parents[1] / "demo"


def grain(img, rng, amount=60):
    px = img.load()
    for _ in range(img.size[0] * img.size[1] // amount):
        x, y = rng.randrange(img.size[0]), rng.randrange(img.size[1])
        r, g, b = px[x, y]
        v = rng.randint(-30, 30)
        px[x, y] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))
    return img


def med_list(rng):
    lines = ["Mom's medicines", "Tylenol PM 2 caplets at bedtime", "Meclizine 25 mg as needed for dizziness",
             "Lisinopril 10 mg daily", "Donepezil 10 mg at bedtime"]
    img = Image.new("RGB", (1100, 520), (247, 242, 228))
    d = ImageDraw.Draw(img)
    for y in range(110, 520, 62):
        d.line([(40, y + 44), (1060, y + 44)], fill=(190, 205, 225), width=2)   # ruled notepaper
    y = 40
    for i, ln in enumerate(lines):
        d.text((70 + rng.randint(-5, 5), y), ln, fill=(30, 35, 70), font=font(40 if i == 0 else 34))
        y += 90 if i == 0 else 64
    return grain(img.rotate(-2.0, expand=True, fillcolor=(110, 100, 90)), rng).filter(ImageFilter.GaussianBlur(0.7))


def bottle(rng, drug, sig, qty):
    W, H = 1000, 560
    img = Image.new("RGB", (W + 120, H + 120), (214, 132, 52))       # amber bottle around the label
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([60, 60, W + 60, H + 60], radius=28, fill=(250, 250, 246), outline=(120, 120, 120), width=3)
    rows = [("OAK STREET PHARMACY  (555) 010-2233", 26), ("Rx# 4419027    Fill date 10/02/2026", 26),
            ("JANE DOE", 30), (drug, 40), (sig, 32), (f"Qty {qty}   Refills 2   Dr. A. Patel", 26),
            ("Discard after 10/02/2027", 24)]
    y = 90
    for txt, size in rows:
        d.text((95, y), txt, fill=(20, 20, 20), font=font(size))
        y += size + 34
    return grain(img.rotate(1.5, expand=True, fillcolor=(90, 70, 50)), rng, 80).filter(ImageFilter.GaussianBlur(0.5))


def main():
    rng = random.Random(7)
    DEMO.mkdir(exist_ok=True)
    med_list(rng).save(DEMO / "med_list_photo.png")
    bottle(rng, "OXYBUTYNIN CHLORIDE 5 MG TABLET", "TAKE 1 TABLET BY MOUTH TWICE DAILY", 60).save(DEMO / "pill_bottle_oxybutynin.png")
    bottle(rng, "AMITRIPTYLINE HCL 25 MG TABLET", "TAKE 1 TABLET BY MOUTH AT BEDTIME", 30).save(DEMO / "pill_bottle_amitriptyline.png")
    print("wrote", sorted(p.name for p in DEMO.glob("*.png")))


if __name__ == "__main__":
    main()
