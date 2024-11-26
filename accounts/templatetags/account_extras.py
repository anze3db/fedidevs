from django import template
from django.templatetags.static import static
from django.utils.html import escape
from django.utils.safestring import mark_safe

from accounts.models import FRAMEWORKS, LANGUAGES, Instance

register = template.Library()


@register.simple_tag
def render_emojis(msg: str, emoji_list: list[str]):
    for emoji in emoji_list:
        msg = msg.replace(
            f":{emoji['shortcode']}:",
            f"<img src='{emoji['url']}' class='emojione' alt='{emoji['shortcode']}' title='{emoji['shortcode']}' />",
        )
    return mark_safe(msg)  # noqa: S308


@register.simple_tag
def render_language_emojis(msg: str):
    msg = escape(msg)
    for lang in LANGUAGES + FRAMEWORKS:
        msg = msg.replace(
            f":{lang.code}:",
            f"<img src='{static(lang.image)}' class='emojione' alt=':{lang.code}:' title=':{lang.code}:' />",
        )
    return mark_safe(msg)  # noqa: S308


@register.simple_tag
def instances_datalist():
    instances = Instance.objects.filter(deleted_at__isnull=True).values_list("domain", flat=True)
    res = "<datalist id='instances'>"
    for instance in instances:
        res += f"<option value='{instance}'>"
    res += "</datalist>"
    return mark_safe(res)  # noqa: S308)
