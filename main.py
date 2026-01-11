import os
import uuid
import random
from io import BytesIO

from flask import Flask, request, send_file
import requests
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# --------------------------
# Config
# --------------------------

BIBLE_API_URL = "https://labs.bible.org/api/?passage=random&type=json"
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

NATURE_QUERIES = [
    "forest",
    "mountains",
    "sunrise landscape",
    "sunset landscape",
    "nature landscape",
    "lake sunrise",
    "path in woods",
    "misty forest",
    "mountain sky",
]

VERSE_CACHE = {}

# --------------------------
# Helpers
# --------------------------

def get_random_verse():
    resp = requests.get(BIBLE_API_URL, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    if isinstance(data, list) and data:
        verse = data[0]
        book = verse.get("bookname", "").strip()
        chapter = str(verse.get("chapter", "")).strip()
        verse_num = str(verse.get("verse", "")).strip()
        text = verse.get("text", "").strip()
        reference = f"{book} {chapter}:{verse_num} (NET)"
        return reference, text

    raise ValueError("Empty response from Bible API")


def load_fonts():
    try:
        base_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        verse_font = ImageFont.truetype(base_font_path, 44)
        ref_font = ImageFont.truetype(base_font_path, 32)
        tag_font = ImageFont.truetype(base_font_path, 24)
    except Exception:
        verse_font = ImageFont.load_default()
        ref_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()
    return verse_font, ref_font, tag_font


def wrap_text_pixels(text, font, draw, max_width):
    words = text.split()
    lines = []
    line = ""

    for w in words:
        test_line = w if not line else line + " " + w
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = w

    if line:
        lines.append(line)

    return lines or [text]


def create_gradient_background(width, height):
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    top_color = (60, 35, 120)
    bottom_color = (10, 25, 70)

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    return img


def get_pexels_background(width, height):
    if not PEXELS_API_KEY:
        return create_gradient_background(width, height)

    try:
        headers = {"Authorization": PEXELS_API_KEY}
        query = random.choice(NATURE_QUERIES)
        params = {"query": query, "per_page": 1, "orientation": "landscape"}
        resp = requests.get("https://api.pexels.com/v1/search",
                            headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        photo = data.get("photos", [])[0]
        img_url = photo["src"].get("landscape") or photo["src"].get("original")

        img_resp = requests.get(img_url, timeout=10)
        img_resp.raise_for_status()

        bg_img = Image.open(BytesIO(img_resp.content)).convert("RGB")
        bg_img = bg_img.resize((width, height), Image.LANCZOS)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 110))
        return Image.alpha_composite(bg_img.convert("RGBA"), overlay).convert("RGB")

    except Exception:
        return create_gradient_background(width, height)

# --------------------------
# Routes
# --------------------------

@app.route("/")
def home():
    return "Bible VOTD service is running."

@app.route("/healthz")
def healthz():
    return "OK", 200

@app.route("/votd")
def votd_text():
    try:
        ref, text = get_random_verse()
        return f'{ref} - "{text}"'
    except Exception:
        return "Error fetching verse."

@app.route("/votd_combo")
def votd_combo():
    try:
        ref, text = get_random_verse()
        key = uuid.uuid4().hex
        VERSE_CACHE[key] = (ref, text)
        base = request.url_root.rstrip("/")
        return f'{ref} - "{text}" | Click for pic: {base}/vimg/{key}'
    except Exception:
        return "Error generating verse."

@app.route("/vimg/<key>")
def verse_image(key):
    verse = VERSE_CACHE.pop(key, None)
    if verse is None:
        verse = get_random_verse()

    ref, text = verse
    width, height = 1400, 788
    img = get_pexels_background(width, height)
    draw = ImageDraw.Draw(img)

    verse_font, ref_font, tag_font = load_fonts()

    lines = wrap_text_pixels(text, verse_font, draw, width - 320)
    y = (height - sum(draw.textbbox((0,0), l, font=verse_font)[3] for l in lines)) // 2

    for line in lines:
        bbox = draw.textbbox((0,0), line, font=verse_font)
        x = (width - (bbox[2]-bbox[0])) // 2
        draw.text((x, y), line, fill=(245,245,255), font=verse_font)
        y += bbox[3] + 12

    draw.text((width//2, y+30), ref, fill=(220,220,255), font=ref_font, anchor="mm")
    draw.text((width-24, height-24), "/Versep PwimpMyWide",
              fill=(200,200,230), font=tag_font, anchor="rd")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

# --------------------------
# Run app (Render-compatible)
# --------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
