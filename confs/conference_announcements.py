"""Turns conferences into generic ``announcements.Announcement`` rows.

The Announcement model knows nothing about conferences, so all the
conference-specific wiring — what to say, when to post it, and linking the row
back to the conference's ``start_announcement`` / ``end_announcement`` — lives
here. These helpers only read ``Conference`` fields (never model methods), so
they work with both the live model and the historical model a data migration
hands over.
"""

import datetime as dt
import zoneinfo

from django.urls import reverse

SITE_URL = "https://fedidevs.com"

START = "start"
END = "end"
# Announcements go out in the conference's own timezone.
MORNING_HOUR = 8  # "kicks off today" — the morning of the start date
EVENING_HOUR = 18  # "that's a wrap" — the evening of the end date


def post_at_for(conference, kind: str) -> dt.datetime:
    tz = zoneinfo.ZoneInfo(conference.time_zone)
    if kind == START:
        return dt.datetime.combine(conference.start_date, dt.time(MORNING_HOUR), tzinfo=tz)
    return dt.datetime.combine(conference.end_date, dt.time(EVENING_HOUR), tzinfo=tz)


def hashtags_for(conference) -> str:
    tags = (tag.strip() for tag in conference.tags.split(","))
    return " ".join(tag if tag.startswith("#") else f"#{tag}" for tag in tags if tag)


def content_for(conference, kind: str) -> str:
    url = SITE_URL + reverse("conference", kwargs={"conference_slug": conference.slug})
    hashtags = hashtags_for(conference)

    if kind == START:
        body = (
            f"{conference.name} kicks off today! 🎉\n\n"
            f"Follow the fediverse conversation about the conference on FediDevs:\n{url}"
        )
    else:
        body = (
            f"That's a wrap on {conference.name}! 👋\n\n"
            "Thanks to everyone who joined the conversation on the fediverse. "
            f"You can still browse all the discussion on FediDevs:\n{url}"
        )

    return f"{body}\n\n{hashtags}" if hashtags else body


def sync_conference(conference, announcement_model) -> None:
    """Create (or refresh, while still unposted) a conference's start/end announcements.

    Already-posted announcements are left untouched. ``announcement_model`` is
    passed in explicitly so data migrations can hand over their historical model.
    """
    changed = []
    for field, kind in (("start_announcement", START), ("end_announcement", END)):
        announcement = getattr(conference, field)
        if announcement is None:
            announcement = announcement_model.objects.create(
                content=content_for(conference, kind),
                post_at=post_at_for(conference, kind),
            )
            setattr(conference, field, announcement)
            changed.append(field)
        elif announcement.posted_at is None:
            announcement.content = content_for(conference, kind)
            announcement.post_at = post_at_for(conference, kind)
            announcement.save(update_fields=["content", "post_at"])

    if changed:
        conference.save(update_fields=changed)


def sync_upcoming(conference_model, announcement_model, today: dt.date) -> None:
    """Ensure every not-yet-finished conference has up-to-date announcements."""
    upcoming = conference_model.objects.filter(archived_date__isnull=True, end_date__gte=today).select_related(
        "start_announcement", "end_announcement"
    )
    for conference in upcoming:
        sync_conference(conference, announcement_model)
