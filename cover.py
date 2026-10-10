"""cover.py - a cover image for every Lee reel (1080 x 1920, the Lee paper look, one big number or claim).

  python cover.py                 writes output/covers/<NN>-<name>.png for every reel below
  python cover.py "Big text" "small line" out.png

Instagram's grid crops a cover to the middle, so the text stays inside the middle 4:5 band (y 285 to 1635)."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920
BG, GRID, INK, ACCENT, MUTE = (238, 236, 225), (221, 219, 208), (42, 27, 19), (246, 97, 27), (150, 140, 126)

# number, big line, small line, tag under the text
COVERS = {
    "01-fifty-dollar-lot": ("$50", "= $150,000", "of value in a mobile home park"),
    "02-who-puts-up-the-money": ("$10M", "4 people. 1 deal.", "nobody buys a building alone"),
    "03-seller-finance-stack": ("$100K", "from you", "on a $1 million park"),
    "04-cheap-isnt-cheap": ("10%", "or a trap?", "the cap rate that sounds like a steal"),
    "05-lots-to-replace-a-paycheck": ("30 lots", "= your paycheck", "the honest math"),
    "06-three-questions": ("3", "questions", "before I read any offering"),
    "07-which-would-you-buy": ("A or B?", "same price", "two properties, one choice"),
    "08-your-salary-in-lots": ("25 lots", "= $90,000", "your salary in mobile home lots"),
    "09-what-a-lender-checks": ("9 to 5", "buy a building?", "3 things a lender checks"),
    "10-what-your-hour-is-worth": ("$45", "an hour", "is what your job pays"),
    "11-dont-quit-your-job": ("Don't", "quit your job", "own first, then decide"),
}


def font(px):
    for name in ("arialbd.ttf", "segoeuib.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            pass
    return ImageFont.load_default()


def fit(draw, text, max_w, start, floor=60):
    px = start
    while px > floor and draw.textlength(text, font=font(px)) > max_w:
        px -= 4
    return px


def cover(big, line, small, out):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    for x in range(0, W, 60):
        d.line([x, 0, x, H], fill=GRID, width=1)
    for y in range(0, H, 60):
        d.line([0, y, W, y], fill=GRID, width=1)
    maxw = W - 220
    p1 = fit(d, big, maxw, 340)
    p2 = fit(d, line, maxw, 130)
    p3 = fit(d, small, maxw, 62, 40)
    block = p1 * 1.05 + p2 * 1.2 + p3 * 1.8
    y = (H - block) / 2 - 20
    d.text((W / 2, y + p1 / 2), big, font=font(p1), fill=ACCENT, anchor="mm")
    y += p1 * 1.05
    d.text((W / 2, y + p2 / 2), line, font=font(p2), fill=INK, anchor="mm")
    y += p2 * 1.2 + 36
    d.line([W / 2 - 90, y, W / 2 + 90, y], fill=INK, width=8)
    d.text((W / 2, y + 60), small, font=font(p3), fill=MUTE, anchor="mm")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    im.save(out)


if __name__ == "__main__":
    if len(sys.argv) >= 4:
        cover(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 4 else "", sys.argv[-1])
    else:
        for name, (a, b, c) in COVERS.items():
            cover(a, b, c, ROOT / "output" / "covers" / f"{name}.png")
            print("cover", name)
