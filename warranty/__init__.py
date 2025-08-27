PLUGIN_VERSION = "0.1.0"
"""
Keep this module lightweight. Do NOT import plugin.mixins or Django models here.

We expose a single function `create_plugin_class()` that defines the real
plugin class at runtime (after apps are loaded), so we avoid AppRegistryNotReady
and MRO issues.
"""

_plugin_created = False
WarrantyPlugin = None  # populated by create_plugin_class()


def create_plugin_class():
    """
    Define the actual plugin class AFTER Django apps are ready.
    Called from WarrantyConfig.ready().
    """
    global _plugin_created, WarrantyPlugin
    if _plugin_created and WarrantyPlugin is not None:
        return WarrantyPlugin

    # Import the real bases now that apps are loaded
    from plugin import InvenTreePlugin
    from plugin.mixins import SettingsMixin
    from django.utils.translation import gettext_lazy as _

    class _WarrantyPlugin(InvenTreePlugin, SettingsMixin):
        NAME = "Warranty"
        SLUG = "warranty"
        TITLE = "Warranty + SafetyCulture"
        DESCRIPTION = "Sync SafetyCulture into Warranty model; compute model/warranty from serial rules"
        VERSION = "0.2.0"

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
            # Prefix → {length, warranty_years}
            "SERIAL_PREFIX_RULES": {
                "name": _("Serial Prefix Rules (JSON)"),
                "type": "str",
                "default": '{"IG": {"length": 3, "warranty": 3}, "OG": {"length": 3, "warranty": 2}}',
            },
        }

    WarrantyPlugin = _WarrantyPlugin
    _plugin_created = True
    return WarrantyPlugin
