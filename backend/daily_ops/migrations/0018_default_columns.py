from django.db import migrations


def add_columns(apps, schema_editor):
    Column = apps.get_model('daily_ops', 'TransactionColumn')
    columns = [('Transfer', 'transfer'), ('Wema POS', 'POS'), ('Moniepoint POS', 'POS'),
               ('Jof credit sales', 'CREDIT'), ('Victor Eberezie', 'CREDIT'),
               ('Shell credit sales', 'CREDIT'), ('Mr Sunday', 'CREDIT'),
               ('Ganiak', 'CREDIT'), ('Fafem', 'CREDIT'), ('Alef', 'CREDIT')]
    for station in apps.get_model('daily_ops', 'Station').objects.all():
        for i, (label, kind) in enumerate(columns):
            Column.objects.get_or_create(station=station, label=label, defaults={'transaction_type': kind, 'position': i})


class Migration(migrations.Migration):
    dependencies = [('daily_ops', '0017_entryedit_transactioncolumn_and_more')]
    operations = [migrations.RunPython(add_columns, migrations.RunPython.noop)]
