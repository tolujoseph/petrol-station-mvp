DEFAULT_COLUMNS = [
    ("Transfer", "transfer"), ("Wema POS", "POS"), ("Moniepoint POS", "POS"),
    ("Jof credit sales", "CREDIT"), ("Victor Eberezie", "CREDIT"),
    ("Shell credit sales", "CREDIT"), ("Mr Sunday", "CREDIT"),
    ("Ganiak", "CREDIT"), ("Fafem", "CREDIT"), ("Alef", "CREDIT"),
]


def seed_columns(station):
    from .models import TransactionColumn
    if not station.transaction_columns.exists():
        TransactionColumn.objects.bulk_create([
            TransactionColumn(station=station, label=label, transaction_type=kind, position=i)
            for i, (label, kind) in enumerate(DEFAULT_COLUMNS)
        ])
