# warranty/models.py
"""
Django models for the Warranty plugin.

Contains:
- SafetyCultureRecord: a normalized row per device/unit pulled from SafetyCulture.
  Uses `unit_sn` (e.g., IG1…) as the primary key to prevent duplicates for the same unit.

- WarrantySyncState: a tiny state row for persisting incremental sync cursors (e.g. last processed
  SafetyCulture modified_at timestamp).

Notes:
- Keep this module import-light (no requests, no plugin imports).
- Business logic that touches external APIs or plugin settings should live in admin.py / services.
"""

from django.db import models
from django.core.validators import RegexValidator


class SafetyCultureRecord(models.Model):
    """
    Normalized record for a single unit.

    Uniqueness / dedupe:
    - unit_sn is the PRIMARY KEY: one row per unit.
    - audit_id is UNIQUE (when present): prevents the same SafetyCulture audit being inserted twice.

    IMPORTANT:
    - Do not hardcode "model_number length" or "warranty years" in this model.
      Those are business rules that should be applied by the sync logic (admin.py/services),
      using your SERIAL_PREFIX_RULES configuration.
    """

    # SafetyCulture audit id (unique, when present)
    audit_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="SafetyCulture audit id (unique when present).",
    )

    # audit's modified timestamp from SafetyCulture (UTC)
    sc_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SafetyCulture audit modified_at timestamp (UTC).",
    )

    # Primary key = Unit Serial Number (example: IG1…)
    unit_sn = models.CharField(
        max_length=64,
        primary_key=True,
        validators=[
            RegexValidator(
                r"^IG1[A-Z0-9]+$",
                "Unit Serial Number must start with IG1",
            )
        ],
        help_text="Unit Serial Number (primary key).",
    )

    # Model number derived by sync logic (based on SERIAL_PREFIX_RULES)
    model_number = models.CharField(
        max_length=16,
        blank=True,
        help_text="Model number derived from serial rules; set by sync logic.",
    )

    ums_sn = models.CharField(
        max_length=9,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                r"^\d{4}-\d{4}$",
                "UMS SN must be in xxxx-xxxx format",
            )
        ],
        help_text="UMS serial number in xxxx-xxxx format.",
    )

    audit_date = models.DateField(help_text="Audit conducted/completed date.")
    warranty_expiry = models.DateField(
        blank=True,
        null=True,
        help_text="Warranty expiry date (audit_date + years based on serial rules).",
    )
    tm_device_id = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="TM Device ID (e.g., Unit QR Code).",
    )

    payload = models.JSONField(
        blank=True,
        null=True,
        help_text="Raw SafetyCulture audit payload (JSON).",
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-audit_date", "unit_sn"]
        verbose_name = "SafetyCulture Record"
        verbose_name_plural = "SafetyCulture Records"
        indexes = [
            models.Index(fields=["audit_date"]),
            models.Index(fields=["model_number"]),
            models.Index(fields=["sc_modified_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.unit_sn} ({self.model_number})"

    @staticmethod
    def normalize_ums_sn(value: str | None) -> str | None:
        """
        Normalize UMS serial into 'xxxx-xxxx' if digits are available.
        """
        if not value:
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if len(digits) >= 8:
            return f"{digits[:4]}-{digits[4:8]}"
        return str(value).strip() or None

    def save(self, *args, **kwargs):
        """
        Keep save() focused on normalization only.

        What this DOES:
        - Normalizes unit_sn to uppercase/trim
        - Normalizes ums_sn into xxxx-xxxx when possible

        What this DOES NOT do:
        - Does NOT force model_number from first 3 chars
        - Does NOT compute warranty_expiry (no hardcoded years)
        Those are business rules handled by sync logic using SERIAL_PREFIX_RULES.
        """
        if self.unit_sn:
            self.unit_sn = self.unit_sn.strip().upper()

        self.ums_sn = self.normalize_ums_sn(self.ums_sn)

        # If some existing code creates records without model_number, keep a safe fallback,
        # but do not overwrite values that sync already computed.
        if self.unit_sn and not self.model_number:
            self.model_number = self.unit_sn[:3]

        return super().save(*args, **kwargs)


class WarrantySyncState(models.Model):
    """
    Tiny singleton row to persist incremental sync cursors.

    Your sync logic already works in "modified_after / modified_at" terms, so persist the cursor
    as a UTC datetime (last processed modified_at).

    Usage:
        state, _ = WarrantySyncState.objects.get_or_create(pk="default")
        state.sc_sync_cursor = some_datetime_utc
        state.save()
    """

    id = models.CharField(primary_key=True, max_length=32, default="default")

    sc_sync_cursor = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        help_text="UTC cursor: last processed SafetyCulture modified_at (used for incremental sync).",
    )

    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Warranty Sync State"
        verbose_name_plural = "Warranty Sync State"

    def __str__(self) -> str:
        cur = self.sc_sync_cursor.isoformat() if self.sc_sync_cursor else "-"
        return f"WarrantySyncState(pk={self.pk}, sc_sync_cursor={cur})"
