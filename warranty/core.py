from plugin import InvenTreePlugin
from plugin.mixins import AppMixin, SettingsMixin
from django.utils.translation import gettext_lazy as _

class Warranty(AppMixin, SettingsMixin, InvenTreePlugin):
    TITLE = "Warranty"
    NAME = "warranty"
    SLUG = "warranty"
    VERSION = "0.2.0"
    ADMIN_SOURCE = None

    SETTINGS = {
        # ... your existing settings ...
        "SC_SYNC_CURSOR": {  # ISO-8601 string of last modified_at processed
            "name": _("Sync Cursor (modified_after)"),
            "description": _("Internal – last processed SafetyCulture modified_at"),
            "validator": str,
            "default": "",
        },
        "SC_SYNC_MODE": {
            "name": _("Sync Mode"),
            "description": _("incremental|full"),
            "validator": str,
            "default": "incremental",
        },
    }

    SCHEDULED_TASKS = {
        "warranty-sync-daily": {
            "func": "scheduled_sync_from_sc",
            "schedule": "I",
            "minutes": 1440,  # 24h
        },
    }

    def scheduled_sync_from_sc(self):
        """Daily worker job."""
        from . import admin as warranty_admin
        res = warranty_admin.run_sc_sync(incremental=True, print_each=False)
        __import__("logging").getLogger(__name__).info("Daily SC sync: %s", res)
