from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("daily_ops", "0014_dailyentry_notes"),
    ]

    operations = [
        migrations.RenameField(
            model_name="reconciliationsettings",
            old_name="tolerance",
            new_name="physical_tolerance",
        ),
        migrations.AlterField(
            model_name="reconciliationsettings",
            name="physical_tolerance",
            field=models.DecimalField(
                decimal_places=4, default=5.0, max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="reconciliationsettings",
            name="adjustment_tolerance",
            field=models.DecimalField(
                decimal_places=4, default=0.05, max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="dailyresult",
            name="physical_within_tolerance",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
