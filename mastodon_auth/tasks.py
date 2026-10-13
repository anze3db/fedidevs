"""Potatoq workers only import each app's `tasks.py`, so tasks defined in
other modules must be re-exported here for the worker to register them."""

from mastodon_auth.views import sync_following

__all__ = ["sync_following"]
