"""Poster and tote files from the annotated Pride and Prejudice page.

  python annotated_print.py      # poster-2x3.png, poster-3x4.png, poster-4x5.png, tote.png (+ previews)

Poster: the full annotated page (both paragraphs) on a full-bleed paper tone, with a small caption,
one file per Printify aspect ratio (4000-4800 x 6000 px). Tote: the bolder sweatshirt artwork,
transparent, fitted to the 3000 x 3600 px tote print area.
"""
from PIL import Image, ImageDraw
import annotated_page as ap
import annotated_shirt as sh

PAPER = (246, 238, 220, 255)


def poster(width, out, height=6000):
    page = ap.main("_page.png", with_paper=False)
    box = page.getchannel("A").getbbox()
    art = page.crop(box)
    margin = int(width * 0.11)
    scale = (width - 2 * margin) / art.width
    if art.height * scale > height * 0.78:
        scale = height * 0.78 / art.height
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    img = Image.new("RGBA", (width, height), PAPER)
    top = int((height - art.height) * 0.42)
    img.alpha_composite(art, ((width - art.width) // 2, top))
    d = ImageDraw.Draw(img)
    cap = ap.font("EBGaramond.ttf", int(width * 0.026), 450)
    t = "PRIDE AND PREJUDICE  ·  JANE AUSTEN  ·  1813"
    d.text(((width - d.textlength(t, font=cap)) / 2, height - int(height * 0.075)), t, font=cap, fill=(90, 80, 68, 255))
    img.convert("RGB").save(out, optimize=True)
    img.convert("RGB").resize((width // 8, height // 8), Image.LANCZOS).save(out.replace(".png", "-preview.jpg"), quality=88)


def tote(out="tote.png", w=3000, h=3600):
    art = sh.main("_shirt.png")
    art = art.crop(art.getchannel("A").getbbox())
    scale = min(w * 0.94 / art.width, h * 0.94 / art.height)
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.alpha_composite(art, ((w - art.width) // 2, (h - art.height) // 2))
    img.save(out, optimize=True)
    bg = Image.new("RGBA", (w, h), (224, 210, 197, 255)); bg.alpha_composite(img)
    bg.convert("RGB").resize((w // 6, h // 6), Image.LANCZOS).save("tote-preview.jpg", quality=88)


if __name__ == "__main__":
    poster(4000, "poster-2x3.png")
    poster(4500, "poster-3x4.png")
    poster(4800, "poster-4x5.png")
    tote()
    print("done")
