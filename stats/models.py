import datetime as dt

from django.db import models

from accounts.models import LANGUAGES, Account, AccountLookup
from posts.models import Post


def store_daily_stats():
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)

    account_defaults = {
        f"{lang.code}_accounts": AccountLookup.objects.filter(
            language=lang.code
        ).count()
        for lang in LANGUAGES
    }
    account_defaults["total_accounts"] = Account.objects.count()

    post_defaults = {
        f"{lang.code}_posts": Post.objects.filter(
            created_at__gte=yesterday,
            created_at__lt=today,
            account__accountlookup__language=lang.code,
        ).count()
        for lang in LANGUAGES
    }
    post_defaults["total_posts"] = (
        Post.objects.filter(created_at__gte=yesterday, created_at__lt=today).count(),
    )

    Daily.objects.update_or_create(date=today, defaults=account_defaults)
    Daily.objects.update_or_create(date=yesterday, defaults=post_defaults)


# Create your models here.
class Daily(models.Model):
    date = models.DateField(unique=True, db_index=True)
    total_accounts = models.IntegerField()
    python_accounts = models.IntegerField()
    javascript_accounts = models.IntegerField()
    rust_accounts = models.IntegerField()
    ruby_accounts = models.IntegerField()
    golang_accounts = models.IntegerField()
    java_accounts = models.IntegerField()
    kotlin_accounts = models.IntegerField()
    scala_accounts = models.IntegerField()
    swift_accounts = models.IntegerField()
    csharp_accounts = models.IntegerField()
    fsharp_accounts = models.IntegerField()
    dotnet_accounts = models.IntegerField()
    cpp_accounts = models.IntegerField()
    linux_accounts = models.IntegerField()
    haskell_accounts = models.IntegerField()
    ocaml_accounts = models.IntegerField()
    nix_accounts = models.IntegerField()
    opensource_accounts = models.IntegerField()
    php_accounts = models.IntegerField()

    total_posts = models.IntegerField(default=0)
    python_posts = models.IntegerField(default=0)
    javascript_posts = models.IntegerField(default=0)
    rust_posts = models.IntegerField(default=0)
    ruby_posts = models.IntegerField(default=0)
    golang_posts = models.IntegerField(default=0)
    java_posts = models.IntegerField(default=0)
    kotlin_posts = models.IntegerField(default=0)
    scala_posts = models.IntegerField(default=0)
    swift_posts = models.IntegerField(default=0)
    csharp_posts = models.IntegerField(default=0)
    fsharp_posts = models.IntegerField(default=0)
    dotnet_posts = models.IntegerField(default=0)
    cpp_posts = models.IntegerField(default=0)
    linux_posts = models.IntegerField(default=0)
    haskell_posts = models.IntegerField(default=0)
    ocaml_posts = models.IntegerField(default=0)
    nix_posts = models.IntegerField(default=0)
    opensource_posts = models.IntegerField(default=0)
    php_posts = models.IntegerField(default=0)

    def __str__(self):
        return self.date.strftime("%Y-%m-%d")