from django.db import models
from django.core.validators import RegexValidator


class SafetyCultureRecord(models.Model):
    # Primary key = Unit Serial Number (must start with IG1…)
    unit_sn = models.CharField(
        max_length=64,
        primary_key=True,
        validators=[
            RegexValidator(r"^IG1[A-Z0-9]+$", "Unit Serial Number must start with IG1")
        ],
    )

    # First 3 letters of the serial (we auto-fill this in save())
    model_number = models.CharField(max_length=16, blank=True)

    # Must be xxxx-xxxx (we normalise on save)
    ums_sn = models.CharField(
        max_length=9,
        blank=True,  # allow empty in forms
        null=True,  # allow NULL in DB
        validators=[
            RegexValidator(r"^\d{4}-\d{4}$", "UMS SN must be in xxxx-xxxx format")
        ],
    )

    audit_date = models.DateField()
    warranty_expiry = models.DateField(blank=True, null=True)  # auto: audit_date + 3y
    tm_device_id = models.CharField(max_length=32, blank=True, null=True)
    payload = models.JSONField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def _add_years(self, d, years):
        try:
            from dateutil.relativedelta import relativedelta

            return d + relativedelta(years=years)
        except Exception:
            try:
                return d.replace(year=d.year + years)
            except ValueError:
                # handle Feb 29
                return d.replace(month=2, day=28, year=d.year + years)

    def save(self, *args, **kwargs):
        # model_number = first 3 chars of unit_sn
        if self.unit_sn:
            self.model_number = (self.unit_sn or "").upper()[:3]

        # warranty_expiry = audit_date + 3 years
        if self.audit_date:
            self.warranty_expiry = self._add_years(self.audit_date, 3)

        # normalise UMS SN to xxxx-xxxx if we can
        if self.ums_sn:
            digits = "".join(ch for ch in self.ums_sn if ch.isdigit())
            if len(digits) >= 8:
                self.ums_sn = f"{digits[:4]}-{digits[4:8]}"

        return super().save(*args, **kwargs)


last_audit_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
