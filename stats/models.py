import datetime as dt

from django.db import models

from accounts.models import LANGUAGES, Account, AccountLookup


def store_daily_stats():
    defaults = {
        "total_accounts": Account.objects.count(),
    }
    lang_defaults = {
        f"{lang.code}_accounts": AccountLookup.objects.filter(
            language=lang.code
        ).count()
        for lang in LANGUAGES
    }
    Daily.objects.update_or_create(
        date=dt.date.today(), defaults=defaults | lang_defaults
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
    dotnet_accounts = models.IntegerField()
    cpp_accounts = models.IntegerField()
    linux_accounts = models.IntegerField()
    haskell_accounts = models.IntegerField()
    ocaml_accounts = models.IntegerField()
    nix_accounts = models.IntegerField()
    opensource_accounts = models.IntegerField()
    php_accounts = models.IntegerField()
