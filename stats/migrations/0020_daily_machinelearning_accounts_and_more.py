# Generated by Django 5.1.3 on 2024-12-03 11:47

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0019_followallclick"),
    ]

    operations = [
        migrations.AddField(
            model_name="daily",
            name="machinelearning_accounts",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="daily",
            name="machinelearning_posts",
            field=models.IntegerField(default=0),
        ),
    ]
