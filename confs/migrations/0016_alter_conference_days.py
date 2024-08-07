# Generated by Django 5.1a1 on 2024-07-10 16:41

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("confs", "0015_conference_days_alter_conference_instances_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="conference",
            name="days",
            field=models.TextField(
                default="",
                help_text="Comma seperated list of conference day names, e.g. Tutorials, Tutorials, Talks, Talks",
            ),
        ),
    ]
