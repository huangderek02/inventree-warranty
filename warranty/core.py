# warranty/core.py
from plugin import InvenTreePlugin
from plugin.mixins import AppMixin, SettingsMixin
from django.utils.translation import gettext_lazy as _


class Warranty(AppMixin, SettingsMixin, InvenTreePlugin):
    """Warranty plugin integrating SafetyCulture audits into InvenTree."""

    # Identity
    TITLE = "Warranty"
    NAME = "warranty"  # keep consistent with what's enabled in config/UI
    SLUG = "warranty"
    VERSION = "0.2.0"

    # If you don’t ship a Settings.js, keep None
    ADMIN_SOURCE = None

    # Settings persisted in the InvenTree DB
    SETTINGS = {
        "SC_API_TOKEN": {
            "name": _("SafetyCulture API Token"),
            "description": _("Bearer token"),
            "validator": str,
            "default": "",
            "secret": True,
        },
        "SC_TEMPLATE_ID": {
            "name": _("Template ID"),
            "description": _("e.g. template_60dc405af153456289d32d0abb62f3a4"),
            "validator": str,
            "default": "",
        },
        "SC_BASE_URL": {
            "name": _("API Base URL"),
            "description": _("Usually https://api.safetyculture.io"),
            "validator": str,
            "default": "https://api.safetyculture.io",
        },
        "LABEL_AUDIT_DATE": {
            "name": _("Label: Audit Date"),
            "description": _("e.g. 'Conducted on'"),
            "validator": str,
            "default": "Conducted on",
        },
        "LABEL_UMS_SN": {
            "name": _("Label: UMS SN"),
            "description": _("e.g. 'UMS QR Code'"),
            "validator": str,
            "default": "UMS QR Code",
        },
        "LABEL_TM_ID": {
            "name": _("Label: TM Device ID"),
            "description": _("e.g. 'Unit QR Code'"),
            "validator": str,
            "default": "Unit QR Code",
        },
        "LABEL_UNIT_SN": {
            "name": _("Label: Unit Serial Number"),
            "description": _("Exact label in your audit"),
            "validator": str,
            "default": "Unit Serial Number",
        },
        # Prefix → {length, warranty_years}
        "SERIAL_PREFIX_RULES": {
            "name": _("Serial Rules (JSON)"),
            "description": _('e.g. {"IG": {"length": 3, "warranty": 3}}'),
            "validator": str,
            "default": '{"IG": {"length": 3, "warranty": 3}}',
        },
    }

    # Optional scheduled task (requires worker running)
    SCHEDULED_TASKS = {
        "warranty-sync-daily": {
            "func": "scheduled_sync_from_sc",
            "schedule": "I",  # interval
            "minutes": 1440,  # 24h
        },
    }

    def scheduled_sync_from_sc(self):
        """Background worker entrypoint – no args allowed."""
        from . import admin as warranty_admin  # late import keeps module light

        res = warranty_admin.run_sc_sync(print_each=False)
        __import__("logging").getLogger(__name__).info(
            "Daily SafetyCulture sync: %s", res
        )
