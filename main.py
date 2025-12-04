from flask import Flask, request, send_file
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import uuid

app = Flask(__name__)

# Bible.org labs API for random verse (NET translation)
API_URL = "https://labs.bible.org/api/?passage=random&type=json"

# Cache for storing verse text tied to image keys
VERSE_CACHE = {}

# --------------------------
# Helper Functions
# --------------------------

def get_random_verse():
    """Fetch a random verse and return (reference, text)."""
    resp = requests.get(API_URL, timeout=5)
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


def wrap_text_chars(text, max_chars=50):
    """Simple text wrap based on character count (used for backup if needed)."""
    words = text.split()
    lines = []
    line = ""

    for w in words:
        if len(line) + len(w) + 1 <= max_chars:
            if line:
                line += " "
            line += w
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)

    return lines


def wrap_text_pixels(text, font, draw, max_width):
    """
    Wrap text so each line fits within max_width pixels, using font metrics.
    This makes the verse look much nicer/centered.
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
            if line:  # push current line and start a new one
                lines.append(line)
            line = w
    if line:
        lines.append(line)

    # Fallback if something goes weird
    if not lines:
        return wrap_text_chars(text, max_chars=50)
    return lines


def load_fonts():
    """
    Try to load a nicer TrueType font; fall back to default if not available.
    """
    try:
        # This path often exists on Linux containers (like Render)
        base_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        verse_font = ImageFont.truetype(base_font_path, 44)
        ref_font = ImageFont.truetype(base_font_path, 32)
        tag_font = ImageFont.truetype(base_font_path, 24)
    except Exception:
        verse_font = ImageFont.load_default()
        ref_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()
    return verse_font, ref_font, tag_font


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
    Text + hyperlink to image.
    Example output:
    John 3:16 (NET) - "..." | Click for pic: https://your-url/vimg/KEY
    """
    try:
        reference, text = get_random_verse()

        # Create unique key for the image
        key = uuid.uuid4().hex
        VERSE_CACHE[key] = (reference, text)

        base_url = request.url_root.rstrip("/")
        img_url = f"{base_url}/vimg/{key}"

        # Twitch-friendly clickable link
        return f'{reference} - "{text}" | Click for pic: {img_url}'

    except Exception as e:
        print("Error in /votd_combo:", e)
        return "Sorry, there was an error generating your verse. Please try again."


@app.route("/vimg/<key>")
def verse_image(key):
    """
    Generate a prettier PNG image for a verse.
    Gradient background, centered verse, reference, and tag.
    """
    verse = VERSE_CACHE.pop(key, None)

    if verse is None:
        try:
            verse = get_random_verse()
        except Exception as e:
            print("Error in /vimg fallback:", e)
            verse = ("Verse not available", "Sorry, could not load verse text.")

    reference, text = verse

    # --------------------------
    # Create image canvas (16:9)
    # --------------------------
    width, height = 1400, 788
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Gradient background (top: purple, bottom: deep blue)
    top_color = (60, 35, 120)     # purple-ish
    bottom_color = (10, 25, 70)   # deep blue

    for y in range(height):
        # Linear interpolation
        ratio = y / height
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # --------------------------
    # Fonts
    # --------------------------
    verse_font, ref_font, tag_font = load_fonts()

    # --------------------------
    # Text box for verse
    # --------------------------
    margin_x = 160
    margin_y_top = 140
    margin_y_bottom = 140
    text_box_width = width - 2 * margin_x

    lines = wrap_text_pixels(text, verse_font, draw, max_width=text_box_width)

    # Compute total verse text height
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=verse_font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)

    total_text_height = sum(line_heights) + (len(lines) - 1) * 12  # 12px spacing
    # Center the block vertically in the middle region
    verse_top_y = (height - total_text_height) // 2

    # Draw verse lines centered horizontally within text_box_width
    current_y = verse_top_y
    for idx, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=verse_font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x = (width - line_w) // 2
        draw.text((x, current_y), line, fill=(245, 245, 255), font=verse_font)
        current_y += line_h + 12

    # --------------------------
    # Draw reference below verse
    # --------------------------
    ref_bbox = draw.textbbox((0, 0), reference, font=ref_font)
    ref_w = ref_bbox[2] - ref_bbox[0]
    ref_h = ref_bbox[3] - ref_bbox[1]
    ref_x = (width - ref_w) // 2
    ref_y = current_y + 30
    draw.text((ref_x, ref_y), reference, fill=(220, 220, 255), font=ref_font)

    # --------------------------
    # Draw watermark tag in corner
    # --------------------------
    credit_text = '/votd • "PwimpMyWide"'
    tag_bbox = draw.textbbox((0, 0), credit_text, font=tag_font)
    tag_w = tag_bbox[2] - tag_bbox[0]
    tag_h = tag_bbox[3] - tag_bbox[1]

    tag_x = width - tag_w - 24
    tag_y = height - tag_h - 24
    draw.text((tag_x, tag_y), credit_text, fill=(200, 200, 230), font=tag_font)

    # --------------------------
    # Return image as PNG
    # --------------------------
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# --------------------------
# Run app (Render friendly)
# --------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
