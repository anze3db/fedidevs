from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def render_emojis(msg: str, emoji_list: list[str]):
    for emoji in emoji_list:
        msg = msg.replace(
            f":{emoji['shortcode']}:",
            f"<img src='{emoji['url']}' class='emojione' alt='{emoji['shortcode']}' title='{emoji['shortcode']}' />",
        )
    return mark_safe(msg)


@register.simple_tag
def render_username_at_instance(account_url: str):
    # account_url: https://fosstodon.org/@djangocon
    # return: @djangocon@fosstodon.org
    instance, username = account_url.replace("https://", "").split("/")
    return f"{username}@{instance}"
