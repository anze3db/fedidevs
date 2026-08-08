"""Celery autodiscovery only imports each app's `tasks.py`, so tasks defined in
other modules must be re-exported here for the worker to register them."""

from confs.og_images import update_conference_og_image

__all__ = ["update_conference_og_image"]
