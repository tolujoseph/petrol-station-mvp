"""Check HTTP and database readiness inside the local container."""
import os
from urllib.request import urlopen

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    assert cursor.fetchone()[0] == 1
with urlopen('http://127.0.0.1:8080/api/auth/csrf/', timeout=3) as response:
    assert response.status == 200
