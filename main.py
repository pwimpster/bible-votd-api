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

# Bible.org labs API for random verse (NET translation)
BIBLE_API_URL = "https://labs.bible.org/api/?passage=random&type=json"

# We will use Pexels for random nature backgrounds
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# Some nature-related search terms for Pexels
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

# Cache for verse text keyed by image ID
VERSE_CACHE = {}


# --------------------------
# Helpers
# --------------------------

def get_random_verse():
    """Fetch a random verse and return (reference, text)."""
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
    """
    Try to load nicer TrueType fonts; fall back to default if unavailable.
    """
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
    """
    Wrap text so each line fits within max_width pixels, using font metrics.
    """
    words = text.split()
    lines = []
    line = ""

    for w in words:
        test_line = w if not line else line + " " + w
        bbox = draw.textbbox((0, 0), test_line, font=font)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width:
            line = test_line
        else:
            if line:
                lines.append(line)
            line = w

    if line:
        lines.append(line)

    if not lines:
        return [text]
    return lines


def create_gradient_background(width, height):
    """
    Fallback gradient (if Pexels fails or key is missing).
    """
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    top_color = (60, 35, 120)     # purple-ish
    bottom_color = (10, 25, 70)   # deep blue

    for y in range(height):
        ratio = y / height
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    return img


def get_pexels_background(width, height):
    """
    Fetch a random nature photo from Pexels and return as a Pillow Image.
    Falls back to a gradient if anything goes wrong.
    """
    if not PEXELS_API_KEY:
        print("PEXELS_API_KEY not set; using gradient background.")
        return create_gradient_background(width, height)

    try:
        query = random.choice(NATURE_QUERIES)
        headers = {"Authorization": PEXELS_API_KEY}
        params = {
            "query": query,
            "per_page": 1,
            "orientation": "landscape",
            "size": "large",
        }
        resp = requests.get("https://api.pexels.com/v1/search",
                            headers=headers, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        photos = data.get("photos", [])
        if not photos:
            print("No photos returned from Pexels; using gradient.")
            return create_gradient_background(width, height)

        photo = photos[0]
        src = photo.get("src", {})
        img_url = (
            src.get("landscape")
            or src.get("large2x")
            or src.get("original")
        )

        if not img_url:
            print("No src URL in Pexels response; using gradient.")
            return create_gradient_background(width, height)

        img_resp = requests.get(img_url, timeout=10)
        img_resp.raise_for_status()

        bg_img = Image.open(BytesIO(img_resp.content)).convert("RGB")
        bg_img = bg_img.resize((width, height), Image.LANCZOS)

        # Dark overlay for readability
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 110))
        bg_img = bg_img.convert("RGBA")
        bg_img = Image.alpha_composite(bg_img, overlay).convert("RGB")

        return bg_img

    except Exception as e:
        print("Error fetching Pexels background:", e)
        return create_gradient_background(width, height)


# --------------------------
# Routes
# --------------------------

@app.route("/")
def home():
    return "Bible VOTD / random verse endpoint is running."


@app.route("/votd")
def votd_text():
    """Text-only random verse."""
    try:
        reference, text = get_random_verse()
        return f"{reference} - \"{text}\""
    except Exception as e:
        print("Error in /votd:", e)
        return "Sorry, there was an error getting a verse."


@app.route("/votd_combo")
def votd_combo():
    """
    Text + link to image.
    Example reply:
    John 3:16 (NET) - "..." | Click for pic: https://your-app/vimg/KEY
    """
    try:
        reference, text = get_random_verse()

        key = uuid.uuid4().hex
        VERSE_CACHE[key] = (reference, text)

        base_url = request.url_root.rstrip("/")
        img_url = f"{base_url}/vimg/{key}"

        return f'{reference} - "{text}" | Click for pic: {img_url}'

    except Exception as e:
        print("Error in /votd_combo:", e)
        return "Sorry, there was an error generating your verse. Please try again."


@app.route("/vimg/<key>")
def verse_image(key):
    """
    Generate a PNG with a Pexels nature background + verse text.
    """
    verse = VERSE_CACHE.pop(key, None)

    if verse is None:
        try:
            verse = get_random_verse()
        except Exception as e:
            print("Error in /vimg fallback:", e)
            verse = ("Verse not available", "Sorry, could not load verse text.")

    reference, text = verse

    # Canvas size (16:9)
    width, height = 1400, 788

    # Background from Pexels (or gradient fallback)
    bg_img = get_pexels_background(width, height)
    img = bg_img.convert("RGB")
    draw = ImageDraw.Draw(img)

    verse_font, ref_font, tag_font = load_fonts()

    # Text area
    margin_x = 160
    text_box_width = width - 2 * margin_x

    lines = wrap_text_pixels(text, verse_font, draw, max_width=text_box_width)

    # Compute total height of verse
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=verse_font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)

    total_text_height = sum(line_heights) + (len(lines) - 1) * 12  # 12px spacing
    verse_top_y = (height - total_text_height) // 2

    # Draw verse lines centered
    current_y = verse_top_y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=verse_font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x = (width - line_w) // 2
        draw.text((x, current_y), line, fill=(245, 245, 255), font=verse_font)
        current_y += line_h + 12

    # Draw reference below verse
    ref_bbox = draw.textbbox((0, 0), reference, font=ref_font)
    ref_w = ref_bbox[2] - ref_bbox[0]
    ref_h = ref_bbox[3] - ref_bbox[1]
    ref_x = (width - ref_w) // 2
    ref_y = current_y + 30
    draw.text((ref_x, ref_y), reference, fill=(220, 220, 255), font=ref_font)

    # Tag in corner
    credit_text = '/VerseP PwimpMyWide'
    tag_bbox = draw.textbbox((0, 0), credit_text, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_h = tag_bbox[3] - tag_bbox[1]
    tag_x = width - tag_w - 24
    tag_y = height - tag_h - 24
    draw.text((tag_x, tag_y), credit_text, fill=(200, 200, 230), font=tag_font)

    # Return PNG
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# --------------------------
# Run app (Render-friendly)
# --------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
