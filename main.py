from flask import Flask, request, send_file
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import uuid

app = Flask(__name__)

# Bible.org labs API for a random verse (NET translation)
API_URL = "https://labs.bible.org/api/?passage=random&type=json"

# Simple in-memory cache to keep verse+text for an image request
VERSE_CACHE = {}


def get_random_verse():
    """Fetch a random verse from the Bible API and return (reference, text)."""
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


def wrap_text(text, max_chars=40):
    """Very simple word-wrap by character count (not pixel perfect, but good enough)."""
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


@app.route("/")
def home():
    return "Bible VOTD / random verse endpoint is running."


@app.route("/votd")
def votd_text_only():
    """
    Original text-only endpoint: returns just the verse.
    This is kept for compatibility if you still want a text-only command.
    """
    try:
        reference, text = get_random_verse()
        return f"{reference} - \"{text}\""
    except Exception as e:
        print("Error in /votd:", e)
        return "Sorry, there was an error getting a verse. Please try again."


@app.route("/votd_combo")
def votd_combo():
    """
    Returns text + a hyperlink to an image of the SAME verse.
    Example output:

    John 3:16 (NET) - "For God so loved..." | Image: https://.../vimg/abcdef1234
    """
    try:
        reference, text = get_random_verse()

        # Store verse in cache with a short unique key
        key = uuid.uuid4().hex
        VERSE_CACHE[key] = (reference, text)

        # Build absolute URL for the image endpoint
        base_url = request.url_root.rstrip("/")  # e.g. https://bible-votd-api.onrender.com
        image_url = f"{base_url}/vimg/{key}"

        # Nightbot will show the text & clickable URL
        return f"{reference} - \"{text}\" | Image: {image_url}"
    except Exception as e:
        print("Error in /votd_combo:", e)
        return "Sorry, there was an error getting a verse. Please try again."


@app.route("/vimg/<key>")
def verse_image(key):
    """
    Generate and return a PNG image for the verse stored under this key.
    If the key is missing, we fall back to a new random verse.
    """
    verse = VERSE_CACHE.pop(key, None)

    if verse is None:
        # If cache has been cleared or key is invalid, just get a fresh verse.
        try:
            verse = get_random_verse()
        except Exception as e:
            print("Error in /vimg fallback:", e)
            verse = ("Verse not available", "Sorry, could not load verse text.")

    reference, text = verse

    # Create image
    width, height = 1200, 630
    background_color = (20, 24, 38)  # dark bluish
    text_color = (255, 255, 255)     # white
    accent_color = (200, 200, 255)   # light for reference text

    img = Image.new("RGB", (width, height), background_color)
    draw = ImageDraw.Draw(img)

    # Use default Pillow font (no external font files needed)
    body_font = ImageFont.load_default()
    ref_font = ImageFont.load_default()

    # Wrap the verse text into multiple lines
    lines = wrap_text(text, max_chars=50)

    # Compute starting y so the text is roughly centered vertically
    line_height = 20  # rough estimate for default font
    total_text_height = line_height * len(lines)
    start_y = (height - total_text_height) // 2 - 40

    # Draw the verse lines
    x_margin = 80
    y = max(60, start_y)

    for line in lines:
        draw.text((x_margin, y), line, fill=text_color, font=body_font)
        y += line_height + 5

    # Draw the reference near the bottom
    ref_y = height - 80
    draw.text((x_margin, ref_y), reference, fill=accent_color, font=ref_font)

    # Optional tiny credit / watermark
    credit_text = "/votd • Twitch"
    credit_w, _ = draw.textsize(credit_text, font=ref_font)
    draw.text((width - credit_w - 20, height - 40), credit_text, fill=(180, 180, 200), font=ref_font)

    # Return image as PNG in-memory
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    # Replit / Render friendly
    app.run(host="0.0.0.0", port=8000)
