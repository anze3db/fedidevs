from django.db import models
from django.utils import timezone

from accounts.models import FRAMEWORKS, LANGUAGES, Account, AccountLookup
from posts.models import Post


def store_daily_stats():
    today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    account_defaults = {
        f"{lang.code}_accounts": AccountLookup.objects.filter(
            language=lang.code
        ).count()
        for lang in LANGUAGES + FRAMEWORKS
    }
    account_defaults["total_accounts"] = Account.objects.count()

    post_defaults = {
        f"{lang.code}_posts": Post.objects.filter(
            account__accountlookup__language=lang.code,
        ).count()
        for lang in LANGUAGES + FRAMEWORKS
    }
    post_defaults["total_posts"] = Post.objects.filter().count()

    Daily.objects.update_or_create(
        date=today, defaults=account_defaults | post_defaults
    )


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
    cpp_accounts = models.IntegerField()
    linux_accounts = models.IntegerField()
    haskell_accounts = models.IntegerField()
    ocaml_accounts = models.IntegerField()
    nix_accounts = models.IntegerField()
    opensource_accounts = models.IntegerField()
    php_accounts = models.IntegerField()

    dotnet_accounts = models.IntegerField()
    django_accounts = models.IntegerField(default=0)
    flask_accounts = models.IntegerField(default=0)
    fastapi_accounts = models.IntegerField(default=0)
    rails_accounts = models.IntegerField(default=0)
    laravel_accounts = models.IntegerField(default=0)
    symfony_accounts = models.IntegerField(default=0)
    spring_accounts = models.IntegerField(default=0)
    htmx_accounts = models.IntegerField(default=0)
    react_accounts = models.IntegerField(default=0)
    vue_accounts = models.IntegerField(default=0)
    angular_accounts = models.IntegerField(default=0)
    nextjs_accounts = models.IntegerField(default=0)
    svelte_accounts = models.IntegerField(default=0)
    tailwind_accounts = models.IntegerField(default=0)
    bootstrap_accounts = models.IntegerField(default=0)

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

    django_posts = models.IntegerField(default=0)
    flask_posts = models.IntegerField(default=0)
    fastapi_posts = models.IntegerField(default=0)
    rails_posts = models.IntegerField(default=0)
    laravel_posts = models.IntegerField(default=0)
    symfony_posts = models.IntegerField(default=0)
    spring_posts = models.IntegerField(default=0)
    htmx_posts = models.IntegerField(default=0)
    react_posts = models.IntegerField(default=0)
    vue_posts = models.IntegerField(default=0)
    angular_posts = models.IntegerField(default=0)
    nextjs_posts = models.IntegerField(default=0)
    svelte_posts = models.IntegerField(default=0)
    tailwind_posts = models.IntegerField(default=0)
    bootstrap_posts = models.IntegerField(default=0)

    def __str__(self):
        return self.date.strftime("%Y-%m-%d")
