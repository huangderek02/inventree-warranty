# warranty/__init__.py
"""
Keep this file import-safe for pip builds:
- Do NOT import django or your plugin class at import time.
- Expose a factory that creates the plugin class only after apps are ready.
"""

__all__ = ["__version__", "create_plugin_class"]

__version__ = "0.2.0"

def create_plugin_class():
    """
    Define and return the InvenTree plugin class *after* Django apps are loaded.
    Called from WarrantyConfig.ready() in apps.py.
    """
    from plugin import InvenTreePlugin
    from plugin.mixins import SettingsMixin
    from django.utils.translation import gettext_lazy as _

    class Warranty(SettingsMixin, InvenTreePlugin):
        # Identity (match your core.py values if you keep them there)
        NAME = "warranty"
        SLUG = "warranty"
        TITLE = "Warranty + SafetyCulture"
        VERSION = __version__

        # Settings stored in the InvenTree DB
        SETTINGS = {
            "SC_API_TOKEN": {
                "name": _("SafetyCulture API Token"),
                "protected": True,
                "type": "str",
            },
            "SC_BASE_URL": {
                "name": _("SafetyCulture Base URL"),
                "type": "str",
                "default": "https://api.safetyculture.io",
            },
            "SC_TEMPLATE_ID": {
                "name": _("Default Template ID"),
                "type": "str",
                "default": "template_60dc405af153456289d32d0abb62f3a4",
            },
            "LABEL_AUDIT_DATE": {
                "name": _("Label: Audit Date"),
                "type": "str",
                "default": "Conducted on",
            },
            "LABEL_UMS_SN": {
                "name": _("Label: UMS SN"),
                "type": "str",
                "default": "UMS QR Code",
            },
            "LABEL_TM_ID": {
                "name": _("Label: TM Device ID"),
                "type": "str",
                "default": "Unit QR Code",
            },
            "LABEL_UNIT_SN": {
                "name": _("Label: Unit Serial Number"),
                "type": "str",
                "default": "Unit Serial Number",
            },
            "SERIAL_PREFIX_RULES": {
                "name": _("Serial Prefix Rules (JSON)"),
                "type": "str",
                "default": '{"IG": {"length": 3, "warranty": 3}}',
            },
        }

        # Optional: daily scheduled sync (requires inventree-worker)
        SCHEDULED_TASKS = {
            "warranty-sync-daily": {
                "func": "scheduled_sync_from_sc",
                "schedule": "I",
                "minutes": 1440,
            },
        }

        def scheduled_sync_from_sc(self):
            # Late import keeps admin/helpers import-safe during build
            from . import admin as warranty_admin
            res = warranty_admin.run_sc_sync(print_each=False)
            __import__("logging").getLogger(__name__).info("Daily SafetyCulture sync: %s", res)

    return Warranty
