# Generated by Django 4.2 on 2023-05-07 17:14

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_accountlookup_accounts_ac_languag_951751_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountLookupAny",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
            ],
        ),
        migrations.RemoveIndex(
            model_name="accountlookup",
            name="accounts_ac_languag_951751_idx",
        ),
        migrations.AlterField(
            model_name="accountlookup",
            name="language",
            field=models.CharField(
                choices=[
                    ("python", "Python"),
                    ("javascript", "JavaScript"),
                    ("rust", "Rust"),
                    ("ruby", "Ruby"),
                    ("java", "Java"),
                    ("csharp", "C#"),
                    ("kotlin", "Kotlin"),
                    ("fsharp", "F#"),
                    ("scala", "Scala"),
                    ("golang", "Golang"),
                    ("php", "PHP"),
                    ("linux", "Linux"),
                    ("haskell", "Haskell"),
                    ("nix", "Nix"),
                ],
                max_length=55,
            ),
        ),
        migrations.AddField(
            model_name="accountlookupany",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to="accounts.account"
            ),
        ),
    ]