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


def wrap_text(text, max_chars=50):
    """Simple text wrap based on character count."""
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
    John 3:16 (NET) - "..." | Image: [pic](https://your-url/vimg/KEY)
    """
    try:
        reference, text = get_random_verse()

        # Create unique key for image request
        key = uuid.uuid4().hex
        VERSE_CACHE[key] = (reference, text)

        base_url = request.url_root.rstrip("/")
        img_url = f"{base_url}/vimg/{key}"

        # Nightbot-friendly hyperlink
        image_link = f"[pic]({img_url})"

        return f"{reference} - \"{text}\" | Image: {image_link}"

    except Exception as e:
        print("Error in /votd_combo:", e)
        return "Sorry, there was an error generating your verse."


@app.route("/vimg/<key>")
def verse_image(key):
    """
    Generate PNG image for a verse.
    """
    verse = VERSE_CACHE.pop(key, None)

    if verse is None:
        try:
            verse = get_random_verse()
        except:
            verse = ("Verse not available", "Sorry, could not load verse text.")

    reference, text = verse

    # --------------------------
    # Create image canvas
    # --------------------------
    width, height = 1200, 630
    background_color = (20, 24, 38)
    text_color = (255, 255, 255)
    accent_color = (200, 200, 255)

    img = Image.new("RGB", (width, height), background_color)
    draw = ImageDraw.Draw(img)

    body_font = ImageFont.load_default()
    ref_font = ImageFont.load_default()

    # Wrap text
    lines = wrap_text(text, max_chars=50)
    line_height = 20
    total_text_height = line_height * len(lines)
    start_y = (height - total_text_height) // 2 - 40

    x_margin = 80
    y = max(60, start_y)

    # Draw verse text
    for line in lines:
        draw.text((x_margin, y), line, fill=text_color, font=body_font)
        y += line_height + 5

    # Draw reference
    ref_y = height - 80
    draw.text((x_margin, ref_y), reference, fill=accent_color, font=ref_font)

    # --------------------------
    # Draw watermark tag
    # --------------------------
    credit_text = '/votd • "PwimpMyWide"'
    bbox = draw.textbbox((0, 0), credit_text, font=ref_font)
    credit_w = bbox[2] - bbox[0]

    draw.text(
        (width - credit_w - 20, height - 40),
        credit_text,
        fill=(180, 180, 200),
        font=ref_font
    )

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
