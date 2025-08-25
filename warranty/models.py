from django.db import models


class SafetyCultureRecord(models.Model):
    unit_sn = models.CharField(max_length=100, primary_key=True)
    model_number = models.CharField(max_length=32, blank=True)
    ums_sn = models.CharField(max_length=100, blank=True, null=True)
    audit_date = models.DateField()
    warranty_expiry = models.DateField()
    tm_device_id = models.CharField(max_length=100, blank=True, null=True)
    payload = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.unit_sn} ({self.model_number})"


last_audit_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
