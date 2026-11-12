# Drifted port: copies upstream 0005's state-only username index removal. That
# is right for upstream (its 0004 never created the index) but wrong here,
# because local 0004 did. Model state matches; the database keeps an extra
# index. Schema comparison must catch this before switching to packaged
# migrations.

import uuid

from django.db import migrations, models


def deduplicate_clerkuser_uids(apps, schema_editor):
    ClerkUser = apps.get_model("django_clerk_users", "ClerkUser")
    db_alias = schema_editor.connection.alias
    seen = set()
    rows = (
        ClerkUser.objects.using(db_alias).order_by("uid", "pk").values_list("pk", "uid")
    )
    for pk, uid in rows.iterator():
        if uid not in seen:
            seen.add(uid)
            continue
        new_uid = uuid.uuid4()
        while new_uid in seen:
            new_uid = uuid.uuid4()
        ClerkUser.objects.using(db_alias).filter(pk=pk).update(uid=new_uid)
        seen.add(new_uid)


class Migration(migrations.Migration):
    dependencies = [
        ("django_clerk_users", "0004_clerkuser_username_index"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="clerkuser", name="django_cler_clerk_i_d591b6_idx"
        ),
        migrations.RemoveIndex(
            model_name="clerkuser", name="django_cler_email_f1e649_idx"
        ),
        migrations.RemoveIndex(
            model_name="clerkuser", name="django_cler_uid_9f6a95_idx"
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveIndex(
                    model_name="clerkuser", name="django_cler_usernam_323ad9_idx"
                ),
            ],
        ),
        migrations.RunPython(deduplicate_clerkuser_uids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="clerkuser",
            name="uid",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                help_text="Public unique identifier for the user.",
                unique=True,
            ),
        ),
    ]
