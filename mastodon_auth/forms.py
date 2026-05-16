from urllib.parse import urlsplit

import idna
from django import forms
from django.utils.translation import gettext_lazy as _


class MastodonLoginForm(forms.Form):
    instance = forms.CharField(error_messages={"required": _("Please enter a Mastodon instance domain name.")})
    next = forms.CharField(required=False)

    def clean_instance(self):
        value = self.cleaned_data["instance"].strip().lower()
        if not value:
            raise forms.ValidationError(_("Please enter a Mastodon instance domain name."))

        parsed = urlsplit(value if "://" in value else f"//{value}")
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            raise forms.ValidationError(_("Invalid instance URL. Please enter a valid Mastodon instance domain name."))

        hostname = parsed.hostname
        if not hostname:
            raise forms.ValidationError(_("Invalid instance URL. Please enter a valid Mastodon instance domain name."))

        try:
            port = parsed.port
            ascii_hostname = idna.encode(hostname, uts46=True).decode("ascii")
        except (UnicodeError, ValueError, idna.IDNAError) as error:
            raise forms.ValidationError(
                _("Invalid instance URL. Please enter a valid Mastodon instance domain name.")
            ) from error

        if port is not None:
            return f"{ascii_hostname}:{port}"
        return ascii_hostname
