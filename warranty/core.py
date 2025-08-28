# warranty/core.py
from plugin import InvenTreePlugin
from plugin.mixins import AppMixin, SettingsMixin


class Warranty(AppMixin, SettingsMixin, InvenTreePlugin):
    TITLE = "Warranty"
    NAME = "warranty"
    SLUG = "warranty"
    VERSION = "0.1.0"

    # remove or set to None if you don’t have Settings.js
    ADMIN_SOURCE = None

    SETTINGS = {
        "SC_API_TOKEN": {
            "name": "SafetyCulture API Token",
            "description": "Bearer token",
            "validator": str,
            "default": "",
            "secret": True,
        },
        "SC_TEMPLATE_ID": {
            "name": "Template ID",
            "description": "e.g. template_60dc405af153456289d32d0abb62f3a4",
            "validator": str,
            "default": "",
        },
        "SC_BASE_URL": {
            "name": "API Base URL",
            "description": "Usually https://api.safetyculture.io",
            "validator": str,
            "default": "https://api.safetyculture.io",
        },
        "LABEL_AUDIT_DATE": {
            "name": "Label: Audit Date",
            "description": "e.g. 'Conducted on'",
            "validator": str,
            "default": "Conducted on",
        },
        "LABEL_UMS_SN": {
            "name": "Label: UMS SN",
            "description": "e.g. 'UMS QR Code'",
            "validator": str,
            "default": "UMS QR Code",
        },
        "LABEL_TM_ID": {
            "name": "Label: TM Device ID",
            "description": "e.g. 'Unit QR Code'",
            "validator": str,
            "default": "Unit QR Code",
        },
        "LABEL_UNIT_SN": {
            "name": "Label: Unit Serial Number",
            "description": "Exact label in your audit",
            "validator": str,
            "default": "Unit Serial Number",
        },
        "SERIAL_PREFIX_RULES": {
            "name": "Serial Rules (JSON)",
            "description": 'e.g. {"IG": {"length": 3, "warranty": 3}}',
            "validator": str,
            "default": '{"IG": {"length": 3, "warranty": 3}}',
        },
    }

    # run once every 24 hours
    SCHEDULED_TASKS = {
        "warranty-sync-daily": {
            "func": "scheduled_sync_from_sc",
            "schedule": "I",  # interval
            "minutes": 1440,  # 24h
        },
    }

    def scheduled_sync_from_sc(self):
        """Background worker entrypoint – no args allowed."""
        from . import admin as warranty_admin

        res = warranty_admin.run_sc_sync(print_each=False)
        logger = __import__("logging").getLogger(__name__)
        logger.info("Daily SafetyCulture sync: %s", res)
