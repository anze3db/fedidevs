import logging

from celery import shared_task
from django.apps import AppConfig
from django.conf import settings
from django.core import management
from django.db.models import signals

logger = logging.getLogger(__name__)


def post_save_action(sender, instance, created, **kwargs):  # noqa: ARG001
    # Imported lazily: this module (and its transitive model imports) must not
    # load while the app registry is still being populated in AppConfig.ready().
    from confs.og_images import get_conference_og_image_signature, update_conference_og_image  # noqa: PLC0415

    if created:
        bg_taks.delay(instance.slug)

    # (Re-)render the Open Graph card whenever the content shown on it changes.
    # The render task saves with update_fields, which fires this signal again,
    # but the signature will then match and no further work is enqueued.
    if get_conference_og_image_signature(instance) != instance.og_image_signature:
        update_conference_og_image.delay(instance.slug)


@shared_task
def bg_taks(slug: str):
    management.call_command("findinstances", f"--slug={slug}")
    management.call_command("stattag", f"--slug={slug}")


class ConfsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "confs"

    def ready(self):
        if getattr(settings, "TESTS_RUNNING", False):
            return
        signals.post_save.connect(post_save_action, sender="confs.Conference")
