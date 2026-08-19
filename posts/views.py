from textwrap import dedent

from django import forms
from django.core.mail import send_mail
from django.shortcuts import redirect, render

from posts.models import PostSubscription

SUBSCRIBE_INPUT_CLASS = (
    "bg-gray-50 border border-gray-300 text-gray-900 text-sm rounded-lg focus:ring-primary-600 "
    "focus:border-primary-600 block w-full p-2.5 dark:bg-gray-700 dark:border-gray-600 "
    "dark:placeholder-gray-400 dark:text-white dark:focus:ring-primary-500 dark:focus:border-primary-500"
)


class SubscribeForm(forms.ModelForm):
    framework_or_lang = forms.CharField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = PostSubscription
        fields = ["email", "framework_or_lang"]
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": SUBSCRIBE_INPUT_CLASS,
                    "placeholder": "you@example.com",
                }
            ),
        }


def subscribe(request):
    if request.method == "POST":
        form = SubscribeForm(request.POST)
        if form.is_valid():
            form.save()
            send_mail(
                "Fedidevs new subscriber!",
                dedent(
                    f"""
                    New subscriber with email {form.cleaned_data["email"]}.
                    Framework or lang: {form.cleaned_data["framework_or_lang"]}
                """
                ),
                "anze@fedidevs.com",
                ["anze@pecar.me"],
                fail_silently=True,
            )
            return redirect("posts_subscribe_success")
        else:
            return render(request, "subscribe.html", {"form": form})
    return render(
        request,
        "subscribe.html",
        {
            "form": SubscribeForm(),
            "page_title": "Fedidevs Subscribe to Daily Posts",
            "page_header": "FEDIDEVS",
            "page_subheader": "Subscribe to Daily Posts"
            + (" on " + request.POST.get("framework_or_lang") if request.POST.get("framework_or_lang") else ""),
        },
    )


def subscribe_success(request):
    return render(
        request,
        "subscribe_success.html",
        {
            "form": SubscribeForm(),
            "page_title": "Subscribed 🎉",
            "page_header": "FEDIDEVS",
            "page_subheader": "",
        },
    )
