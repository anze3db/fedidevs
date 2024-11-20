import re

from django import forms
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import slugify

from accounts.models import Account
from mastodon_auth.models import AccountFollowing
from starter_packs.models import StarterPack


def starter_packs(request):
    if request.user.is_anonymous:
        starter_packs = StarterPack.objects.none()
    else:
        starter_packs = StarterPack.objects.filter(created_by=request.user).order_by("-created_at")
    return render(
        request,
        "starter_packs.html",
        {
            "page": "starter_packs",
            "starter_packs": starter_packs,
        },
    )


class StarterPackForm(forms.ModelForm):
    class Meta:
        model = StarterPack
        fields = ["title", "description"]


def add_accounts_to_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, created_by=request.user)
    if not (q := request.GET.get("q", "")):
        followed_accounts = AccountFollowing.objects.filter(account=request.user.accountaccess.account)
        accounts = Account.objects.filter(url__in=Subquery(followed_accounts.values("url"))).prefetch_related(
            "instance_model"
        )
    else:
        search = q.strip()
        if search.startswith("@"):
            search = search[1:]
        if len(splt := search.split("@")) == 2:
            username, instance = splt
            url = f"{instance}/@{username}"
        else:
            url = search

        accounts = Account.objects.filter(
            url__icontains=url,
        ).prefetch_related("instance_model")

    paginator = Paginator(accounts, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    accounts_count = page_obj.paginator.count

    is_username = re.match(r"(@[a-zA-Z0-9_\.\-]+)@([a-zA-Z0-9_\.\-]+)", q)

    if request.method == "POST":
        pass

    return render(
        request,
        "add_accounts_list.html" if "HX-Request" in request.headers else "add_accounts.html",
        {
            "page": "edit_starter_pack",
            "q": q,
            "is_username": is_username,
            "accounts": page_obj,
            "starter_pack": starter_pack,
        },
    )


def edit_starter_pack(request, starter_pack_slug):
    starter_pack = get_object_or_404(StarterPack, slug=starter_pack_slug, created_by=request.user)
    if request.method == "POST":
        form = StarterPackForm(request.POST, instance=starter_pack)
        if form.is_valid():
            form.save()
            return redirect("add_starter_packs", starter_pack_slug=starter_pack.slug)
    else:
        form = StarterPackForm(instance=starter_pack)

    return render(
        request,
        "create_starter_pack.html",
        {
            "page": "edit_starter_pack",
            "form": form,
            "starter_pack": starter_pack,
        },
    )


def create_starter_pack(request):
    if request.method == "POST":
        form = StarterPackForm(request.POST)
        if form.is_valid():
            starter_pack = form.save(commit=False)
            starter_pack.created_by = request.user
            starter_pack.slug = slugify(starter_pack.title)
            try:
                starter_pack.save()
                return redirect("add_starter_packs", starter_pack_slug=starter_pack.slug)
            except IntegrityError:
                form.add_error(
                    "title",
                    forms.ValidationError("You already have a starter pack with this title."),
                )
    else:
        form = StarterPackForm()

    return render(
        request,
        "create_starter_pack.html",
        {
            "page": "create_starter_pack",
            "form": form,
        },
    )
