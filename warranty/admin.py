# warranty/admin.py
import json
import logging
import os
import requests
from datetime import datetime, date
from typing import Any, Dict

from django.contrib import admin, messages
from django.db import transaction

from plugin import registry
from .models import SafetyCultureRecord

logger = logging.getLogger(__name__)


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _list_all_audits(
    base_url: str, token: str, template_id: str, include_archived: bool = False
):
    """Page through /audits/search like your C#."""
    url = f"{base_url.rstrip('/')}/audits/search"
    params = [
        ("field", "audit_id"),
        ("field", "modified_at"),
        ("template", template_id),
    ]
    if include_archived:
        params.append(("archived", "true"))

    last = None
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
                yield aid
        last = audits[-1].get("modified_at")
        if not last:
            break


def _get_audit_detail(base_url: str, token: str, audit_id: str) -> Dict[str, Any]:
    r = requests.get(
        f"{base_url.rstrip('/')}/audits/{audit_id}", headers=_headers(token), timeout=60
    )
    r.raise_for_status()
    return r.json()


def _walk(items):
    """Depth-first walk but yield only dict nodes; skip strings / scalars."""
    if not items:
        return
    for it in items:
        if not isinstance(it, dict):
            continue
        yield it
        # children can be in different keys depending on schema
        children = (
            it.get("items") or it.get("children") or it.get("template_items") or []
        )
        # Some payloads also nest under 'header_items' inside an item
        if not children and isinstance(it.get("header_items"), list):
            children = it.get("header_items")
        for c in _walk(children):
            yield c


def _find_by_label(payload, label):
    if not label:
        return None
    want = str(label).strip().lower()

    def _walk_any(n):
        if isinstance(n, dict):
            yield n
            for k in ("header_items", "items", "children", "template_items"):
                v = n.get(k)
                if isinstance(v, list):
                    for c in v:
                        yield from _walk_any(c)
        elif isinstance(n, list):
            for c in n:
                yield from _walk_any(c)

    def _resp_text(resp):
        if not isinstance(resp, dict):
            return None
        for k in ("text", "value", "string", "string_value"):
            v = resp.get(k)
            if isinstance(v, (str, int, float)) and str(v).strip():
                return str(v)
        sel = resp.get("selected")
        if isinstance(sel, list) and sel:
            c = sel[0]
            for k in ("label", "value", "text"):
                v = c.get(k)
                if isinstance(v, (str, int, float)) and str(v).strip():
                    return str(v)
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

    for it in _walk_any(payload):
        if str(it.get("label", "")).strip().lower() == want:
            resp = it.get("responses") or it.get("response") or {}
            val = _resp_text(resp) or it.get("value")
            if isinstance(val, (str, int, float)):
                return str(val)
    return None


def _add_years(d: date, years: int) -> date:
    try:
        from dateutil.relativedelta import relativedelta

        return d + relativedelta(years=years)
    except Exception:
        try:
            return d.replace(year=d.year + years)
        except ValueError:
            return d.replace(month=2, day=28, year=d.year + years)


def _model_and_years_from_serial(unit_sn: str, rules_json: str) -> tuple[str, int]:
    """Longest prefix match; rules like {"IG":{"length":3,"warranty":3}}."""
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
        cfg = rules[best_key] or {}
        length = int(cfg.get("length", 3))
        years = int(cfg.get("warranty", cfg.get("warranty_years", 1)))
        return s[:length], years
    return s[:3], 1


def _parse_iso_date(s):
    if not s:
        return None
    if isinstance(s, str) and s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        return None


def sync_from_safetyculture(modeladmin, request, queryset):
    """Admin action: read audits and upsert SafetyCultureRecord by unit_sn."""
    p = registry.get_plugin("warranty")

    def _get(name, default=""):
        try:
            if p:
                v = p.get_setting(name)
                if isinstance(v, str) and v:
                    return v
        except Exception:
            pass
        return os.environ.get(name, default)

    base_url = _get("SC_BASE_URL", "https://api.safetyculture.io").rstrip("/")
    token = _get("SC_API_TOKEN")
    template_id = _get("SC_TEMPLATE_ID")
    if not token or not template_id:
        messages.error(
            request,
            "Set SC_API_TOKEN and SC_TEMPLATE_ID in Plugin settings or environment.",
        )
        return

    lbl_audit = _get("LABEL_AUDIT_DATE", "Conducted on")
    lbl_ums = _get("LABEL_UMS_SN", "UMS QR Code")
    lbl_tm = _get("LABEL_TM_ID", "Unit QR Code")
    lbl_sn = _get("LABEL_UNIT_SN", "Unit Serial Number")
    rules = _get("SERIAL_PREFIX_RULES", '{"IG":{"length":3,"warranty":3}}')

    # Preflight log: show sample audit ids
    try:
        r = requests.get(
            f"{base_url}/audits/search",
            headers=_headers(token),
            params=[("field", "audit_id"), ("template", template_id), ("limit", "10")],
            timeout=60,
        )
        r.raise_for_status()
        j = r.json() or {}
        logger.info(
            "SC template=%s total=%s sample=%s",
            template_id,
            j.get("total"),
            [a.get("audit_id") for a in (j.get("audits") or [])],
        )
    except Exception as e:
        logger.warning("Prefetch failed for template %s: %s", template_id, e)

    print_each = os.getenv("PRINT_AUDITS", "1") == "1"
    created = updated = skipped = errors = 0

    for aid in _list_all_audits(base_url, token, template_id, include_archived=False):
        try:
            detail = _get_audit_detail(base_url, token, aid)
            detail["audit_id"] = aid  # keep SC audit id in payload

            # Ensure audit_id/template_id are present in the saved payload
            if not isinstance(detail, dict):
                detail = {}
                detail.setdefault("audit_id", aid)
                detail.setdefault("template_id", template_id)

            unit_sn = (_find_by_label(detail, lbl_sn) or "").strip()
            if not unit_sn:
                skipped += 1
                continue

            ums_sn = (_find_by_label(detail, lbl_ums) or "").strip() or None
            tm_id = (_find_by_label(detail, lbl_tm) or "").strip() or None

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
                    "AUDIT id=%s unit_sn=%s audit_date=%s model=%s expiry=%s",
                    aid,
                    unit_sn,
                    audit_date,
                    model_number,
                    warranty_expiry,
                )

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
                    need_payload = (
                        not obj.payload
                        or obj.payload != detail
                        or not (
                            (obj.payload or {}).get("audit_id")
                            or ((obj.payload or {}).get("audit_data") or {}).get(
                                "audit_id"
                            )
                        )
                    )
                    if need_payload:
                        obj.payload = detail
                        changed = True

                    if changed:
                        obj.save()
                        updated += 1
                    else:
                        skipped += 1
                unit_sn = (_find_by_label(detail, lbl_sn) or "").strip()
                if not unit_sn or unit_sn.upper() in {"TBA", "N/A", "-", "--"}:
                    skipped += 1
                    continue

        except Exception as e:
            errors += 1
            if print_each:
                logger.exception("Audit %s failed: %s", aid, e)

    msg = f"SafetyCulture sync complete. created={created}, updated={updated}, skipped={skipped}"
    if errors:
        msg += f", errors={errors}"
    messages.success(request, msg)


sync_from_safetyculture.short_description = "Sync from SafetyCulture (default template)"


@admin.register(SafetyCultureRecord)
class SafetyCultureRecordAdmin(admin.ModelAdmin):
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
