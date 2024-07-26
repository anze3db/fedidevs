# Generated by Django 5.1b1 on 2024-07-20 09:35

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("stats", "0016_monthlyaccountchange"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="monthlyaccountchange",
            name="account",
        ),
        migrations.RemoveField(
            model_name="weeklyaccountchange",
            name="account",
        ),
        migrations.DeleteModel(
            name="DailyAccountChange",
        ),
        migrations.DeleteModel(
            name="MonthlyAccountChange",
        ),
        migrations.DeleteModel(
            name="WeeklyAccountChange",
        ),
    ]