from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("confs", "0033_remove_legacy_conference_tables"),
        ("posts", "0006_post_posts_post_account_7eef7a_idx"),
    ]

    operations = [
        migrations.DeleteModel(
            name="DjangoConUS23Post",
        ),
    ]
