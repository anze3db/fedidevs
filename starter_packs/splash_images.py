import hashlib
import io
import logging
import math
import random

import httpx
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

from accounts.models import Account

logger = logging.getLogger(__name__)


# The maximum number of avatars that will appear on a starter pack splash
# image, limited for the purposes of render time/traffic and aesthetics.
SPLASH_IMAGE_NUMBER_OF_AVATARS = 24


def get_splash_image_accounts(starter_pack):
    accounts = (
        Account.objects.filter(
            starterpackaccount__starter_pack=starter_pack,
            instance_model__isnull=False,
            instance_model__deleted_at__isnull=True,
            discoverable=True,
        )
        .select_related("accountlookup", "instance_model")
        .order_by("starterpackaccount__created_at")
    )
    return list(accounts)


def get_splash_image_signature(starter_pack):
    """
    Calculates a 32 character signature (checksum, hash) of the content in
    a given starter pack which would appear on the splash image. This is
    used to discern whether the splash image needs to be rerendered after
    a starter pack has been modified, or if the content is unchanged under
    the current render settings.
    """
    accounts = get_splash_image_accounts(starter_pack)
    accounts = accounts[:SPLASH_IMAGE_NUMBER_OF_AVATARS]
    accounts = [account.get_username_at_instance() for account in accounts]
    content = starter_pack.title + ",".join(sorted(accounts))
    return hashlib.sha512(content.encode("utf-8")).hexdigest()[:32]


def get_splash_background(width, height, attribution, font, cache_path):
    """
    Creates a PIL image according to the given `width` and `height`, fills it
    with a gradient background, and adds a site-specific `attribution` in the
    lower right corner using `font`.
    This function caches its result in `cache_path` and attempts to reuse it
    for successive images of the same dimensions.
    """
    if cache_path.is_file():
        try:
            return Image.open(cache_path)
        except UnidentifiedImageError:
            logger.warning("Cached splash image background for size (%d, %d) corrupted, rerendering", width, height)
            # Fall through into (re-)render code path

    background = Image.new("RGBA", (width, height))
    left_color = (255, 87, 87)
    right_color = (140, 82, 255)
    for x in range(width):
        progress = x / (width - 1)
        mixed_color = (
            round(progress * left_color[0] + (1 - progress) * right_color[0]),
            round(progress * left_color[1] + (1 - progress) * right_color[1]),
            round(progress * left_color[2] + (1 - progress) * right_color[2]),
            255,
        )
        background.paste(mixed_color, (x, 0, x + 1, height))

    draw = ImageDraw.Draw(background)
    font_size = font.getmetrics()[0] - font.getmetrics()[1]
    draw.text(
        (width - 0.6 * font_size, height - 0.3 * font_size), attribution, fill=(255, 255, 255), font=font, anchor="rb"
    )

    try:
        background.save(cache_path)
        return background
    except OSError:
        logger.exception("Unable to save splash image: %s", cache_path)
        return None


def fetch_avatar(url, crop_mask):
    """
    Fetches a remote avatar from a URL and returns it as PIL image resized to
    the dimensions of `mask` and with `mask` applied as an alpha mask size in
    pixels (same width and height). If the avatar is non-square, it is squished.
    If it contains transparency, a gray background is applied before `crop`mask.

    Returns `None` if the download fails, the avatar is too large (in bytes or
    in resolution), or pretty much anything else goes wrong.
    """

    max_bytes = 8 * 1024 * 1024
    client = httpx.Client()
    avatar_bytes = io.BytesIO()

    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
            if response.status_code != 200:
                return None
            size_bytes = int(response.headers.get("Content-Length", "0"))
            if size_bytes > max_bytes:
                return None
            for chunk in response.iter_bytes():
                if response.num_bytes_downloaded > max_bytes:
                    return None
                avatar_bytes.write(chunk)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    finally:
        client.close()

    original_max_image_pixels = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = 4000 * 4000
        avatar = Image.open(avatar_bytes)
    except (Image.DecompressionBombError, UnidentifiedImageError):
        return None
    finally:
        Image.MAX_IMAGE_PIXELS = original_max_image_pixels

    avatar = avatar.convert("RGBA")
    avatar = avatar.resize((crop_mask.width, crop_mask.height), resample=Image.Resampling.LANCZOS)
    modified = Image.new("RGBA", (crop_mask.width, crop_mask.height), (127, 127, 127, 255))
    modified.alpha_composite(avatar)
    modified.putalpha(crop_mask)
    return modified


def render_splash_image(starter_pack, host_attribution):
    """
    Renders (or re-renders) a splash image for a specific starter pack.
    The result is returned as a PIL image and stored in the media
    directory. Note that this triggers a download of up to
    `SPLASH_IMAGE_NUMBER_OF_AVATARS` remote avatars and a good amount
    of CPU and RAM use -- this operation is _expensive_! The caller is
    responsible for sensible scheduling.

    Note: `host_attribution` is cached eagerly by the background gradient
    renderer. The value is only used if no background for the configured
    render size is in the local cache.
    """

    resolution = (1200, 630)  # final rendered image size in pixels
    supersampling_factor = 3  # scaling factor for render canvas size (to avoid aliasing)
    media_dir = settings.BASE_DIR / "media"
    splash_dir = media_dir / "splash"

    render_resolution = (resolution[0] * supersampling_factor, resolution[1] * supersampling_factor)
    font_path = settings.BASE_DIR / "static" / "InterVariable.ttf"
    attribution_font = ImageFont.truetype(font_path, round(30 * supersampling_factor))

    image = get_splash_background(
        render_resolution[0],
        render_resolution[1],
        f"Hosted by {host_attribution}",
        attribution_font,
        media_dir / f"starterpack_bg_{render_resolution[0]}x{render_resolution[1]}.png",
    )
    if image is None:
        # Background could be neither retrieved from cache nor generated as new
        return

    margin_top = 2.5 * 48 * supersampling_factor
    margin_bottom = 2 * 36 * supersampling_factor
    margin_side = 0.05 * resolution[0] * supersampling_factor

    accounts = get_splash_image_accounts(starter_pack)

    inner_width = render_resolution[0] - 2 * margin_side
    inner_height = render_resolution[1] - margin_top - margin_bottom
    inner_aspect_ratio = inner_width / inner_height
    
    goal_num_avatars = min(len(accounts), SPLASH_IMAGE_NUMBER_OF_AVATARS)
    if goal_num_avatars == 0:
        num_lines = 0
        per_line = 0
        leftover = 0
    else:
        num_lines = 1 + math.floor(math.sqrt(max(goal_num_avatars - 1, 1) / inner_aspect_ratio))
        per_line = math.floor(goal_num_avatars / num_lines)
        num_lines = math.floor(goal_num_avatars / per_line)
        leftover = goal_num_avatars % per_line

    lines = []
    for _i in range(num_lines):
        lines.append(per_line)
    expand_line_count = 1
    while leftover > 0:
        for i in range(expand_line_count):
            lines[i + math.floor((num_lines - expand_line_count) / 2)] += 1
            leftover -= 1
            if leftover == 0:
                break
        expand_line_count = min(expand_line_count + 2, num_lines)
    for i in range(1, num_lines):
        if lines[i] < lines[i - 1] - 1:
            lines[i] += 1
            lines[i - 1] -= 1

    if goal_num_avatars == 0:
        circle_distance = 0
    else:
        circle_distance = inner_width / max(lines)
        circle_distance = min(circle_distance, (inner_height / (1 + math.sin(math.pi / 3) * (len(lines) - 1))))

    # We separate `circle_radius` from `circle_distance` to
    # scale the circles' relative size in the future.
    circle_radius = circle_distance / 2
    outline_thickness = math.floor(0.09 * circle_distance / 2)
    avatar_size = round(circle_radius * 2)
    crop_mask = Image.new("L", (avatar_size, avatar_size), 0)
    crop_mask_draw = ImageDraw.Draw(crop_mask)
    crop_mask_draw.circle(
        (round(crop_mask.width / 2), round(crop_mask.height / 2)),
        round(crop_mask.width / 2),
        fill=255,
    )

    empty_avatar = Image.new("RGBA", (crop_mask.width, crop_mask.height), (0, 0, 0, 0))
    avatars = []
    for account in accounts:
        avatar = fetch_avatar(account.avatar, crop_mask)
        if avatar is not None:
            avatars.append(avatar)
        else:
            logger.warning("Failed to fetch avatar of account %s for splash image", account.get_username_at_instance())
        if len(avatars) >= goal_num_avatars:
            break
    if len(avatars) < goal_num_avatars:
        avatars += [empty_avatar] * (goal_num_avatars - len(avatars))
    random.shuffle(avatars)

    min_x = 9999999
    min_y = 9999999
    max_x = -9999999
    max_y = -9999999
    line_start = 0
    avatar_positions = []
    for y in range(len(lines)):
        shift = -0.25 + (y % 2) * 0.5
        if y > 0:
            if lines[y] > lines[y - 1] and shift > 0:
                line_start -= 1
            elif lines[y] < lines[y - 1] and shift < 0:
                line_start += 1
        for x in range(lines[y]):
            cx = (line_start + x + shift) * circle_distance
            cy = (y - num_lines / 2) * circle_distance * math.sin(math.pi / 3)
            avatar_positions.append((cx, cy))
            min_x = min(cx, min_x)
            max_x = max(cx, max_x)
            min_y = min(cy, min_y)
            max_y = max(cy, max_y)

    diff_x = render_resolution[0] / 2 - (max_x + min_x) / 2
    diff_y = render_resolution[1] / 2 - (margin_bottom - margin_top) / 2 - (max_y + min_y) / 2

    shadow_layer = Image.new("RGBA", render_resolution, (0, 0, 0, 0))
    outline_layer = Image.new("RGBA", render_resolution, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    outline_draw = ImageDraw.Draw(outline_layer)

    title_font = ImageFont.truetype(font_path, 64)
    title_font.set_variation_by_name("Bold")
    title_width = title_font.getlength(starter_pack.title)
    title_max_width = 0.9 * resolution[0]  # 5% margin left and right
    title_font_size = round(min(1, title_max_width / title_width) * 64 * supersampling_factor)
    title_font = ImageFont.truetype(font_path, title_font_size)
    title_font.set_variation_by_name("Bold")

    for job in ((shadow_draw, (0, 0, 0, 63)), (outline_draw, (255, 255, 255, 255))):
        job[0].text(
            (render_resolution[0] / 2, 48 * supersampling_factor),
            starter_pack.title,
            fill=job[1],
            font=title_font,
            anchor="mm",
        )
        i = 0
        for y in range(num_lines):
            for _x in range(lines[y]):
                pixel_x = round(avatar_positions[i][0] + diff_x - avatar_size / 2)
                pixel_y = round(avatar_positions[i][1] + diff_y - avatar_size / 2)
                image.alpha_composite(avatars[i], (pixel_x, pixel_y))
                job[0].circle(
                    (avatar_positions[i][0] + diff_x, avatar_positions[i][1] + diff_y),
                    math.floor(circle_radius + outline_thickness / 2),
                    outline=job[1],
                    fill=None,
                    width=outline_thickness,
                )
                i += 1

    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=3 * supersampling_factor))
    image.alpha_composite(shadow_layer)
    image.alpha_composite(outline_layer)

    image.convert("RGB")
    image = image.resize(resolution, resample=Image.Resampling.LANCZOS)
    image_path = splash_dir / (starter_pack.slug + ".png")

    try:
        image.save(image_path)
    except OSError:
        logger.exception("Unable to save splash image: %s (is %s writable?)", image_path, splash_dir)
        return

    image.close()

    starter_pack.splash_image = f"splash/{starter_pack.slug}.png"
    starter_pack.splash_image_signature = get_splash_image_signature(starter_pack)
    starter_pack.splash_image_updated_at = timezone.now()
    starter_pack.splash_image_needs_update = False
    starter_pack.save(
        update_fields=["splash_image", "splash_image_signature", "splash_image_updated_at", "splash_image_needs_update"]
    )
