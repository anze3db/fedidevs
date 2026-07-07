"""Dynamic Open Graph images for conference detail pages.

Each conference gets a 1200x630 social card rendered with Pillow showing the
conference name, its dates (and location), a "Join the conversation" prompt and
the conference hashtag. The heavy lifting for mixed-font/emoji-aware text is
reused from `starter_packs.splash_images`.
"""

import glob
import hashlib
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from confs.models import Conference
from starter_packs.splash_images import draw_text_with_emoji, split_text_emoji_segments

logger = logging.getLogger(__name__)

# Final rendered card size in pixels (standard Open Graph dimensions).
RESOLUTION = (1200, 630)
# Render on a larger canvas and downscale to avoid text aliasing.
SUPERSAMPLING_FACTOR = 2

MAIN_FONT_PATH = settings.BASE_DIR / "static" / "InterVariable.ttf"
EMOJI_FONT_PATH = settings.BASE_DIR / "static" / "NotoEmoji-Bold.ttf"

# Brand gradient (matches the starter pack splash images).
GRADIENT_LEFT = (255, 87, 87)
GRADIENT_RIGHT = (140, 82, 255)


def _load_fonts(size, bold=True):
    """Load the main font plus emoji and CJK/misc fallbacks at `size` pixels."""
    main_font = ImageFont.truetype(str(MAIN_FONT_PATH), size)
    if bold:
        try:
            main_font.set_variation_by_name("Bold")
        except OSError:
            # Non-variable build of the font; ignore and use the default weight.
            pass
    emoji_font = ImageFont.truetype(str(EMOJI_FONT_PATH), size)
    additional_fonts = [
        ImageFont.truetype(path, size) for path in glob.glob(str(settings.BASE_DIR / "static" / "NotoSans*.ttf"))
    ]
    return main_font, emoji_font, additional_fonts


def _text_width(draw, text, fonts, size):
    main_font, emoji_font, additional_fonts = fonts
    segments = split_text_emoji_segments(draw, text, main_font, emoji_font, additional_fonts, size)
    return sum(segment["width"] for segment in segments)


def _fit_font_size(draw, text, max_width, max_size, bold=True):
    """Return the largest font size (<= `max_size`) that renders `text` within
    `max_width` on a single line, along with the loaded fonts at that size."""
    fonts = _load_fonts(max_size, bold)
    width = _text_width(draw, text, fonts, max_size)
    if width <= max_width or width == 0:
        return max_size, fonts
    size = max(12, int(max_size * max_width / width))
    return size, _load_fonts(size, bold)


def _draw_centered(draw, image, text, center, max_width, max_size, fill, bold=True):
    """Draw `text` horizontally centered at `center`, shrinking to fit `max_width`."""
    size, fonts = _fit_font_size(draw, text, max_width, max_size, bold)
    main_font, emoji_font, additional_fonts = fonts
    draw_text_with_emoji(
        image_draw=draw,
        image=image,
        position=center,
        text=text,
        fill=fill,
        default_font=main_font,
        emoji_font=emoji_font,
        additional_fonts=additional_fonts,
        emoji_size=size,
        anchor="mm",
    )


def _gradient_background(width, height):
    background = Image.new("RGBA", (width, height))
    for x in range(width):
        progress = x / (width - 1)
        mixed_color = (
            round(progress * GRADIENT_LEFT[0] + (1 - progress) * GRADIENT_RIGHT[0]),
            round(progress * GRADIENT_LEFT[1] + (1 - progress) * GRADIENT_RIGHT[1]),
            round(progress * GRADIENT_LEFT[2] + (1 - progress) * GRADIENT_RIGHT[2]),
            255,
        )
        background.paste(mixed_color, (x, 0, x + 1, height))
    return background


def _primary_hashtag(conference):
    tag = next((tag.strip() for tag in conference.tags.split(",") if tag.strip()), "")
    if tag and not tag.startswith("#"):
        tag = "#" + tag
    return tag


def _date_line(conference):
    start, end = conference.start_date, conference.end_date
    if start == end:
        dates = start.strftime("%b %-d, %Y")
    elif (start.year, start.month) == (end.year, end.month):
        dates = f"{start.strftime('%b %-d')}-{end.strftime('%-d, %Y')}"
    elif start.year == end.year:
        dates = f"{start.strftime('%b %-d')} - {end.strftime('%b %-d, %Y')}"
    else:
        dates = f"{start.strftime('%b %-d, %Y')} - {end.strftime('%b %-d, %Y')}"
    if conference.location:
        return f"{dates}  ·  {conference.location}"
    return dates


def get_conference_og_image_signature(conference):
    """32 character signature of the content shown on the conference OG card.

    Used to decide whether a prerendered image is stale and needs to be
    re-rendered. Any change to the fields that appear on the card changes the
    signature.
    """
    content = "|".join(
        [
            conference.name,
            conference.start_date.isoformat(),
            conference.end_date.isoformat(),
            conference.location,
            _primary_hashtag(conference),
        ]
    )
    return hashlib.sha512(content.encode("utf-8")).hexdigest()[:32]


def render_conference_og_image_to_image_obj(conference):
    """Render the Open Graph card for `conference` and return it as a PIL image."""
    ss = SUPERSAMPLING_FACTOR
    width, height = RESOLUTION[0] * ss, RESOLUTION[1] * ss

    image = _gradient_background(width, height)
    draw = ImageDraw.Draw(image)

    margin = round(0.06 * width)
    max_text_width = width - 2 * margin
    white = (255, 255, 255, 255)
    faint = (255, 255, 255, 220)

    # Eyebrow prompt near the top.
    _draw_centered(
        draw,
        image,
        "Join the conversation",
        (width / 2, round(0.20 * height)),
        max_text_width,
        round(38 * ss),
        faint,
    )

    # Conference name — the visual anchor of the card.
    _draw_centered(
        draw,
        image,
        conference.name,
        (width / 2, round(0.42 * height)),
        max_text_width,
        round(92 * ss),
        white,
    )

    # Dates (and location).
    _draw_centered(
        draw,
        image,
        _date_line(conference),
        (width / 2, round(0.58 * height)),
        max_text_width,
        round(40 * ss),
        faint,
    )

    # Hashtag inside a rounded pill.
    hashtag = _primary_hashtag(conference)
    if hashtag:
        tag_size, tag_fonts = _fit_font_size(draw, hashtag, max_text_width - round(0.1 * width), round(52 * ss))
        tag_width = _text_width(draw, hashtag, tag_fonts, tag_size)
        pad_x = round(0.4 * tag_size)
        pad_y = round(0.25 * tag_size)
        pill_center_y = round(0.80 * height)
        pill = (
            round(width / 2 - tag_width / 2 - pad_x),
            round(pill_center_y - tag_size / 2 - pad_y),
            round(width / 2 + tag_width / 2 + pad_x),
            round(pill_center_y + tag_size / 2 + pad_y),
        )
        draw.rounded_rectangle(pill, radius=round(pad_y + tag_size / 2), fill=(255, 255, 255, 235))
        main_font, emoji_font, additional_fonts = tag_fonts
        draw_text_with_emoji(
            image_draw=draw,
            image=image,
            position=(width / 2, pill_center_y),
            text=hashtag,
            fill=(140, 82, 255, 255),
            default_font=main_font,
            emoji_font=emoji_font,
            additional_fonts=additional_fonts,
            emoji_size=tag_size,
            anchor="mm",
        )

    # Site attribution in the lower-right corner.
    attribution_font = ImageFont.truetype(str(MAIN_FONT_PATH), round(26 * ss))
    draw.text(
        (width - margin, height - round(0.06 * height)),
        "fedidevs.com",
        fill=faint,
        font=attribution_font,
        anchor="rb",
    )

    image = image.convert("RGB")
    return image.resize(RESOLUTION, resample=Image.Resampling.LANCZOS)


def render_conference_og_image(conference):
    """Render (or re-render) the OG card for `conference` and store it on disk.

    The result is written to the media directory and referenced by the
    `Conference.og_image` field. Cheap enough to run inline (no network I/O),
    but usually invoked from a background task.
    """
    image = render_conference_og_image_to_image_obj(conference)

    og_dir = settings.MEDIA_ROOT / "conference_og"
    image_path = og_dir / f"{conference.slug}.png"
    try:
        og_dir.mkdir(parents=True, exist_ok=True)
        image.save(image_path)
    except OSError:
        logger.exception("Unable to save conference OG image: %s (is %s writable?)", image_path, og_dir)
        return

    conference.og_image = f"conference_og/{conference.slug}.png"
    conference.og_image_signature = get_conference_og_image_signature(conference)
    conference.og_image_updated_at = timezone.now()
    conference.og_image_needs_update = False
    conference.save(
        update_fields=[
            "og_image",
            "og_image_signature",
            "og_image_updated_at",
            "og_image_needs_update",
        ]
    )


@shared_task
def update_conference_og_image(conference_slug: str):
    conference = Conference.objects.filter(slug=conference_slug).first()
    if conference is not None:
        render_conference_og_image(conference)
