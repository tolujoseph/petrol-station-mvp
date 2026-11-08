from django.apps import AppConfig


class DailyOpsConfig(AppConfig):
    name = 'daily_ops'

    def ready(self):
        from . import signals  # noqa: F401
