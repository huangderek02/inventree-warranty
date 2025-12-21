# warranty/models.py
"""
Django models for the Warranty plugin.

Contains:
- SafetyCultureRecord: a normalized row per device/unit pulled from SafetyCulture.
  Uses `unit_sn` as the primary key to prevent duplicates for the same unit.

Design notes:
- Keep this module import-light (no requests, no plugin imports).
- Business logic that depends on plugin settings (e.g., SERIAL_PREFIX_RULES)
  should live in admin.py / services modules (sync code), not in model.save().
"""

from django.db import models
from django.core.validators import RegexValidator


class SafetyCultureRecord(models.Model):
    """
    One row per unit/device from SafetyCulture.

    Key behaviors:
    - unit_sn is the primary key (dedupe per physical unit)
    - audit_id is unique (dedupe per SafetyCulture audit)
    - This model only normalizes data; it does NOT decide warranty years or model parsing.
      That logic should be done by sync code using SERIAL_PREFIX_RULES.
    """

    # SafetyCulture audit id (unique per audit)
    audit_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="SafetyCulture audit_id (unique).",
    )

    # Audit modified timestamp from SafetyCulture (UTC)
    sc_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="SafetyCulture audit modified timestamp (UTC).",
    )

    # Primary key = Unit Serial Number
    #
    # If you truly ONLY accept IG1... units, keep this validator.
    # If you need other prefixes (e.g. OG...), relax it (see comment below).
    unit_sn = models.CharField(
        max_length=64,
        primary_key=True,
        validators=[
            RegexValidator(r"^IG1[A-Z0-9]+$", "Unit Serial Number must start with IG1")
            # If you need to accept more, replace with something like:
            # RegexValidator(r"^[A-Z0-9]+$", "Unit Serial Number must be alphanumeric (A-Z/0-9)")
        ],
        help_text="Unit serial number (primary key).",
    )

    # Derived by sync logic (SERIAL_PREFIX_RULES), but we’ll keep a safe fallback if blank
    model_number = models.CharField(
        max_length=16,
        blank=True,
        help_text="Model identifier (usually derived from unit_sn via SERIAL_PREFIX_RULES).",
    )

    # Allow either "1234-5678" OR "12345678" (we normalize to xxxx-xxxx in save()).
    ums_sn = models.CharField(
        max_length=9,
        blank=True,
        null=True,
        validators=[
            RegexValidator(r"^\d{4}-?\d{4}$", "UMS SN must be in xxxx-xxxx (or xxxxxxxx) format")
        ],
        help_text="UMS serial number (normalized to xxxx-xxxx).",
    )

    audit_date = models.DateField(help_text="Audit conducted/completed date.")
    warranty_expiry = models.DateField(
        blank=True,
        null=True,
        help_text="Warranty expiry date (should be computed by sync logic).",
    )

    tm_device_id = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="TM device ID / Unit QR Code (if present).",
    )

    payload = models.JSONField(
        blank=True,
        null=True,
        help_text="Raw SafetyCulture audit JSON payload (for debugging/auditing).",
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
            # audit_id already has db_index=True above; sc_modified_at too.
        ]

    def __str__(self) -> str:
        return f"{self.unit_sn} ({self.model_number})"

    def save(self, *args, **kwargs):
        """
        Normalize fields before persisting.

        IMPORTANT:
        - Do NOT hardcode model parsing or warranty years here.
          The sync layer should set `model_number` and `warranty_expiry`
          using SERIAL_PREFIX_RULES and the audit date.
        """
        # Normalize unit_sn
        if self.unit_sn:
            self.unit_sn = str(self.unit_sn).strip().upper()

        # Only fill model_number if missing (do not overwrite what sync computed)
        if self.unit_sn and not (self.model_number or "").strip():
            self.model_number = self.unit_sn[:3]

        # Normalize UMS serial into "xxxx-xxxx" if digits available
        if self.ums_sn:
            digits = "".join(ch for ch in str(self.ums_sn) if ch.isdigit())
            if len(digits) >= 8:
                self.ums_sn = f"{digits[:4]}-{digits[4:8]}"

        return super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Incremental sync cursor state
#
# Using audit_id alone as a cursor is often not enough for SafetyCulture search
# (which is typically "modified_after"). Storing last_modified_at gives you
# a stable cursor for incremental syncs, and last_audit_id can be used as a
# tie-breaker if needed.
# ─────────────────────────────────────────────────────────────────────────────

class WarrantySyncState(models.Model):
    """
    Persist incremental sync cursors.

    Recommended usage (single row):
        state, _ = WarrantySyncState.objects.get_or_create(pk="default")
        state.last_modified_at = <utc datetime>
        state.last_audit_id = "audit_..."
        state.save()
    """

    id = models.CharField(primary_key=True, max_length=32, default="default")

    # Optional: last processed audit id (tie-breaker / debugging)
    last_audit_id = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="Cursor: last processed SafetyCulture audit_id (optional).",
    )

    # Recommended: last processed modified timestamp from SC (UTC)
    last_modified_at = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        help_text="Cursor: last processed SafetyCulture modified_at timestamp (UTC).",
    )

    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Warranty Sync State"
        verbose_name_plural = "Warranty Sync State"

    def __str__(self) -> str:
        lm = self.last_modified_at.isoformat() if self.last_modified_at else "-"
        return f"WarrantySyncState(pk={self.pk}, last_modified_at={lm}, last_audit_id={self.last_audit_id or '-'})"
