from django import template
from django.utils.safestring import mark_safe

from accounts.management.commands.crawler import INSTANCES

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
def render_username_at_instance(account_url: str):
    # account_url: https://fosstodon.org/@djangocon
    # return: @djangocon@fosstodon.org
    instance, username = account_url.replace("https://", "").split("/")
    return f"{username}@{instance}"


@register.simple_tag
def instances_datalist():
    res = "<datalist id='instances'>"
    for instance in INSTANCES:
        res += f"<option value='{instance}'>"
    res += "</datalist>"
    return mark_safe(res)  # noqa: S308)


@register.inclusion_tag("v2/follow_button.html")
def follow_button(user, account):
    if not user.is_authenticated:
        _type = "login"
    elif user.accountaccess.account.account_id == account.account_id:
        _type = "self"
    elif account.is_following:
        _type = "unfollow"
    else:
        _type = "follow"

    return {"account": account, "type": _type}
