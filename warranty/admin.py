# warranty/admin.py
"""
Admin integration and SafetyCulture sync helpers.

This module provides:
- Lightweight helpers to talk to the SafetyCulture API
- A robust, idempotent sync pipeline that upserts SafetyCulture audits
  into the SafetyCultureRecord model (deduped by unit_sn)
- A Django admin action to trigger the sync from the UI
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, Iterable, Iterator, Tuple

import requests
from django.contrib import admin, messages
from django.db import transaction

from plugin import registry
from .models import SafetyCultureRecord

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# Small, single-purpose helpers (kept tight and readable)
# --------------------------------------------------------------------------------------
def _headers(token: str) -> dict[str, str]:
    """HTTP headers for SafetyCulture requests."""
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _list_all_audits(
    base_url: str,
    token: str,
    template_id: str,
    include_archived: bool = False,
) -> Iterator[str]:
    """
    Yield audit IDs for a template via the SafetyCulture /audits/search API.

    Notes:
      - Paginates via `modified_after` using the last audit's timestamp
      - Returns only audit IDs, so callers fetch details separately
    """
    url = f"{base_url.rstrip('/')}/audits/search"
    params = [("field", "audit_id"), ("field", "modified_at"), ("template", template_id)]
    if include_archived:
        params.append(("archived", "true"))

    last: str | None = None
    while True:
        ps = list(params)
        if last:
            ps.append(("modified_after", last))

        r = requests.get(url, headers=_headers(token), params=ps, timeout=60)
        r.raise_for_status()
        data = r.json() or {}
        audits = data.get("audits") or []
        if not audits:
            break

        for row in audits:
            aid = row.get("audit_id")
            if aid:
                yield str(aid)

        last = audits[-1].get("modified_at")
        if not last:
            break


def _get_audit_detail(base_url: str, token: str, audit_id: str) -> Dict[str, Any]:
    """Return the full audit JSON for a given audit_id."""
    r = requests.get(
        f"{base_url.rstrip('/')}/audits/{audit_id}",
        headers=_headers(token),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def _walk(items: Any) -> Iterator[dict]:
    """
    Depth-first walk of SafetyCulture JSON structure, yielding dict nodes only.

    This normalizes a variety of possible container keys found in real payloads
    (e.g., 'items', 'children', 'template_items', 'header_items').
    """
    if not items:
        return

    # If `items` is a list of nodes
    if isinstance(items, list):
        for it in items:
            yield from _walk(it)
        return

    # If `items` is a single node (dict)
    if isinstance(items, dict):
        yield items
        # Explore known child lists
        for key in ("items", "children", "template_items", "header_items"):
            v = items.get(key)
            if isinstance(v, list):
                for c in v:
                    yield from _walk(c)


def _find_by_label(payload: Any, label: str | None) -> str | None:
    """
    Find a single response value by its **label** (case-insensitive).

    The SafetyCulture schema varies; this searches through common response
    shapes (text/value/selected/media) and returns the first non-empty string.
    """
    if not label:
        return None
    want = str(label).strip().lower()

    def _resp_text(resp: Any) -> str | None:
        """Extract a user-readable value from common response shapes."""
        if not isinstance(resp, dict):
            return None

        # Common scalar locations
        for k in ("text", "value", "string", "string_value"):
            v = resp.get(k)
            if isinstance(v, (str, int, float)) and str(v).strip():
                return str(v)

        # Single- or multi-choice answers
        sel = resp.get("selected")
        if isinstance(sel, list) and sel:
            c = sel[0]
            for k in ("label", "value", "text"):
                v = c.get(k)
                if isinstance(v, (str, int, float)) and str(v).strip():
                    return str(v)

        # Media answers sometimes carry embedded metadata
        med = resp.get("media")
        if isinstance(med, list) and med:
            m = med[0]
            for k in ("data", "text", "value"):
                v = m.get(k)
                if isinstance(v, (str, int, float)) and str(v).strip():
                    return str(v)
            md = m.get("metadata") or {}
            for k in ("data", "text", "value"):
                v = md.get(k)
                if isinstance(v, (str, int, float)) and str(v).strip():
                    return str(v)

        return None

    for node in _walk(payload):
        if str(node.get("label", "")).strip().lower() == want:
            resp = node.get("responses") or node.get("response") or {}
            val = _resp_text(resp) or node.get("value")
            if isinstance(val, (str, int, float)):
                text = str(val).strip()
                return text or None
    return None


def _parse_iso_date(s: Any) -> date | None:
    """
    Parse dates found in SafetyCulture payloads into a Python date.

    Tries ISO-8601 (w/ 'Z' UTC), then a couple of common fallback formats.
    """
    if not s:
        return None

    if isinstance(s, str) and s.endswith("Z"):  # normalize Zulu
        s = s[:-1] + "+00:00"

    # Best-effort ISO parse
    try:
        return datetime.fromisoformat(str(s)).date()
    except Exception:
        pass

    # Fallbacks
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(s), fmt).date()
        except Exception:
            continue

    return None


def _add_years(d: date, years: int) -> date:
    """
    Add warranty years to a date.

    Uses dateutil.relativedelta when available, falls back to a safe leap-year aware
    approximation (Feb 28) to avoid ValueError on Feb 29 → non-leap years.
    """
    try:
        from dateutil.relativedelta import relativedelta

        return d + relativedelta(years=years)
    except Exception:  # keep simple and robust
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            return d.replace(month=2, day=28, year=d.year + years)


def _model_and_years_from_serial(unit_sn: str, rules_json: str) -> Tuple[str, int]:
    """
    Compute (model_number, warranty_years) from a serial via longest-prefix rule.

    Example rules JSON:
      {"IG": {"length": 3, "warranty": 3}, "OG": {"length": 3, "warranty": 2}}
    - Match the longest prefix key (case-insensitive)
    - 'length' slices the serial for the model_number
    - 'warranty' (or 'warranty_years') determines warranty duration
    """
    s = (unit_sn or "").strip().upper()
    try:
        rules = json.loads(rules_json or "{}")
    except Exception:
        rules = {}

    best_key, best_len = None, -1
    for k in rules.keys():
        ku = str(k).upper()
        if s.startswith(ku) and len(ku) > best_len:
            best_key, best_len = k, len(ku)

    if best_key is not None:
        cfg = rules.get(best_key) or {}
        length = int(cfg.get("length", 3))
        years = int(cfg.get("warranty", cfg.get("warranty_years", 1)))
        return s[:length], years

    # Sensible fallback if no rule matches
    return s[:3], 1


# --------------------------------------------------------------------------------------
# Public sync API (used by admin action and headless shell)
# --------------------------------------------------------------------------------------
def run_sc_sync(*, print_each: bool = False) -> dict:
    """
    Core SafetyCulture → DB sync (idempotent).

    - Reads settings from plugin (or env as fallback)
    - Streams audits for the configured template
    - Upserts into SafetyCultureRecord (deduped by unit_sn)
    - Returns counters for created/updated/skipped/errors

    `print_each=True` logs each processed audit for debugging.
    """
    p = registry.get_plugin("warranty")

    def _get(name: str, default: str = "") -> str:
        # Prefer plugin settings; fall back to environment variables
        try:
            v = p.get_setting(name) if p else None
            if isinstance(v, str) and v.strip():
                return v
        except Exception:
            pass
        return os.environ.get(name, default)

    base_url = (_get("SC_BASE_URL", "https://api.safetyculture.io")).rstrip("/")
    token = (_get("SC_API_TOKEN") or "").strip()
    template_id = (_get("SC_TEMPLATE_ID") or "").strip()

    if not token or not template_id:
        raise RuntimeError("Set SC_API_TOKEN and SC_TEMPLATE_ID")

    # Label overrides + rules
    lbl_audit = _get("LABEL_AUDIT_DATE", "Conducted on")
    lbl_ums = _get("LABEL_UMS_SN", "UMS QR Code")
    lbl_tm = _get("LABEL_TM_ID", "Unit QR Code")
    lbl_sn = _get("LABEL_UNIT_SN", "Unit Serial Number")
    rules = _get("SERIAL_PREFIX_RULES", '{"IG":{"length":3,"warranty":3}}')

    created = updated = skipped = errors = 0

    for aid in _list_all_audits(base_url, token, template_id, include_archived=False):
        try:
            detail = _get_audit_detail(base_url, token, aid)

            # Required serial to key the record
            unit_sn = (_find_by_label(detail, lbl_sn) or "").strip()
            if not unit_sn:
                skipped += 1
                continue

            # Optional identifiers
            ums_sn = (_find_by_label(detail, lbl_ums) or "").strip() or None
            tm_id = (_find_by_label(detail, lbl_tm) or "").strip() or None

            # Try labeled date first, then common metadata fallback keys
            ad_meta = detail.get("audit_data") or {}
            audit_raw = (
                _find_by_label(detail, lbl_audit)
                or ad_meta.get("completed_date")
                or ad_meta.get("completed_at")
                or detail.get("completed_at")
                or detail.get("created_at")
            )
            audit_date = _parse_iso_date(audit_raw)
            if not audit_date:
                skipped += 1
                continue

            model_number, years = _model_and_years_from_serial(unit_sn, rules)
            warranty_expiry = _add_years(audit_date, years)

            if print_each:
                logger.info(
                    "AUDIT id=%s unit=%s date=%s model=%s expiry=%s",
                    aid,
                    unit_sn,
                    audit_date,
                    model_number,
                    warranty_expiry,
                )

            # Upsert within a transaction; dedupe by unit_sn
            with transaction.atomic():
                obj, was_created = SafetyCultureRecord.objects.get_or_create(
                    unit_sn=unit_sn,
                    defaults=dict(
                        model_number=model_number,
                        ums_sn=ums_sn,
                        audit_date=audit_date,
                        warranty_expiry=warranty_expiry,
                        tm_device_id=tm_id,
                        payload=detail,
                    ),
                )
                if was_created:
                    created += 1
                else:
                    changed = False
                    if obj.model_number != model_number:
                        obj.model_number = model_number
                        changed = True
                    if obj.ums_sn != ums_sn:
                        obj.ums_sn = ums_sn
                        changed = True
                    if obj.audit_date != audit_date:
                        obj.audit_date = audit_date
                        changed = True
                    if obj.warranty_expiry != warranty_expiry:
                        obj.warranty_expiry = warranty_expiry
                        changed = True
                    if obj.tm_device_id != tm_id:
                        obj.tm_device_id = tm_id
                        changed = True

                    # Always refresh payload
                    obj.payload = detail

                    if changed:
                        obj.save()
                        updated += 1
                    else:
                        skipped += 1

        except Exception:
            errors += 1
            logger.exception("Audit %s failed", aid)

    return dict(created=created, updated=updated, skipped=skipped, errors=errors)


# --------------------------------------------------------------------------------------
# Django admin integration
# --------------------------------------------------------------------------------------
def sync_from_safetyculture(modeladmin, request, queryset):
    """
    Admin action: run a full SafetyCulture sync and report results via messages.

    Usage:
      - From the SafetyCultureRecord admin changelist
      - From code (call directly with a fake request/messages if needed)
    """
    try:
        result = run_sc_sync(print_each=(os.getenv("PRINT_AUDITS", "0") == "1"))
        msg = (
            "SafetyCulture sync complete. "
            f"created={result['created']}, updated={result['updated']}, "
            f"skipped={result['skipped']}"
        )
        if result.get("errors"):
            msg += f", errors={result['errors']}"
        messages.success(request, msg)
    except Exception as e:
        messages.error(request, str(e))


sync_from_safetyculture.short_description = "Sync from SafetyCulture (default template)"  # noqa: E305


@admin.register(SafetyCultureRecord)
class SafetyCultureRecordAdmin(admin.ModelAdmin):
    """
    Minimal, fast admin for SafetyCultureRecord.

    You can add more filters or columns later; keep list_display small for
    responsiveness when you have many rows.
    """
    list_display = (
        "unit_sn",
        "model_number",
        "audit_date",
        "warranty_expiry",
        "ums_sn",
        "tm_device_id",
    )
    search_fields = ("unit_sn", "model_number", "ums_sn", "tm_device_id")
    list_filter = ("audit_date",)
    actions = [sync_from_safetyculture]


# SC API Token: 7411e799480279aab66382cf9156b9f26481bbdf1cf450f5e34964a3b9168db4
# Inventree API Token: inv-3f994b27bfff196cf8a0d4bea436249b29857a3d-20250911
