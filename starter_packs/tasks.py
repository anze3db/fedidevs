"""Potatoq workers only import each app's `tasks.py`, so tasks defined in
other modules must be re-exported here for the worker to register them."""

from starter_packs.views import follow_bg, update_starter_pack_splash_images

__all__ = ["follow_bg", "update_starter_pack_splash_images"]
