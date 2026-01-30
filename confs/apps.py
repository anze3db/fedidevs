import logging

from celery import shared_task
from django.apps import AppConfig
from django.core import management
from django.db.models import signals

logger = logging.getLogger(__name__)


def post_save_action(sender, instance, created, **kwargs):  # noqa: ARG001
    if created:
        bg_taks.delay(instance.slug)


@shared_task
def bg_taks(slug: str):
    management.call_command("findinstances", f"--slug={slug}")
    management.call_command("stattag", f"--slug={slug}")


class ConfsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "confs"

    def ready(self):
        signals.post_save.connect(post_save_action, sender="confs.Conference")
