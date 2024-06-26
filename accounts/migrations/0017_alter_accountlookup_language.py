# Generated by Django 5.0.4 on 2024-05-02 21:39

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_alter_accountlookup_language"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountlookup",
            name="language",
            field=models.CharField(
                choices=[
                    ("python", "Python"),
                    ("typescript", "TypeScript"),
                    ("javascript", "JavaScript"),
                    ("rust", "Rust"),
                    ("ruby", "Ruby"),
                    ("golang", "Golang"),
                    ("java", "Java"),
                    ("kotlin", "Kotlin"),
                    ("scala", "Scala"),
                    ("swift", "Swift"),
                    ("csharp", "C#"),
                    ("fsharp", "F#"),
                    ("cpp", "C++"),
                    ("css", "CSS"),
                    ("php", "PHP"),
                    ("haskell", "Haskell"),
                    ("ocaml", "OCaml"),
                    ("nix", "Nix"),
                    ("julia", "Julia"),
                ],
                max_length=55,
            ),
        ),
    ]
