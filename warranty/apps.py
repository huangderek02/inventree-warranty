from django.apps import AppConfig


class WarrantyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "warranty"
    verbose_name = "Warranty"

    def ready(self):
        # Define the plugin class now (after apps are populated)
        from . import create_plugin_class

        create_plugin_class()
