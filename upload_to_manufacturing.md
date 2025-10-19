ChatGPT said:
# Making Builds Appear in **Manufacturing → Build Orders**

This is a clean, end-to-end recap of the exact steps taken on the **139.84.201.15** server to create Build Orders from your **warranty** plugin data so they show up in the InvenTree UI.

---

## 1) SSH to the server and enter the compose project

```bash
ssh root@139.84.201.15
cd ~/inventree-docker

2) Detect the InvenTree backend path (where manage.py lives)
BACKEND_DIR="$(docker compose exec -T inventree-server sh -lc \
  'ls -d /home/inventree/src/backend/InvenTree 2>/dev/null || \
   ls -d /home/invenree/src/backend/InvenTree 2>/dev/null || \
   ls -d /opt/inventree 2>/dev/null')"
echo "BACKEND_DIR=$BACKEND_DIR"


Expected output example:

BACKEND_DIR=/home/inventree/src/backend/InvenTree

3) Confirm warranty data exists
docker compose exec -T inventree-server sh -lc '
  BACKEND_DIR="$(ls -d /home/inventree/src/backend/InvenTree 2>/dev/null || \
                 ls -d /home/invenree/src/backend/InvenTree 2>/dev/null || \
                 ls -d /opt/inventree 2>/dev/null)"
  cd "$BACKEND_DIR"
  python3 manage.py shell -c "
from warranty.models import SafetyCultureRecord as R
print(\"rows:\", R.objects.count())
print(list(R.objects.order_by(\"-audit_date\").values(
  \"unit_sn\",\"model_number\",\"audit_date\",\"warranty_expiry\",\"tm_device_id\",\"ums_sn\")[:15]))
"
'


You saw ~558 rows (mostly model_number = IG1).

4) Choose the target Part for each model prefix

You mapped the IG1 model prefix to an existing assembly part:

MODEL_TO_PART: {'IG1': 'K08-00044'} (IPN or Part name)

Ensure the target part is buildable (assembly=True).

(Alternative path would be to create a new buildable Part with IPN/name IG1 and map to that.)

5) Create Build Orders (idempotent; auto-compliant references)

The script below:

Resolves the target Part per record via a MODEL_TO_PART mapping.

Does not set the Build.reference (so InvenTree auto-generates BO-####).

Prevents duplicates by using a notes marker [warranty:unit_sn=<SN>] and reuses the Build if the marker exists.

Handles date vs datetime.

docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 manage.py shell <<'PY'
from datetime import date, datetime
from django.db import transaction
from part.models import Part
from build.models import Build
from warranty.models import SafetyCultureRecord as R

# Map warranty model prefix -> existing buildable Part (IPN or name)
MODEL_TO_PART = {
    'IG1': 'K08-00044',  # your existing assembly
}

def as_date(dt):
    if dt is None: return None
    if isinstance(dt, date) and not isinstance(dt, datetime): return dt
    if isinstance(dt, datetime): return dt.date()
    return None

def resolve_part(model_number: str):
    if not model_number: return None
    prefix = (model_number or '')[:3].upper()
    code = MODEL_TO_PART.get(prefix) or prefix
    # Try IPN first, then Part name
    return Part.objects.filter(IPN=code).first() or Part.objects.filter(name=code).first()

def find_existing_build_for_sn(sn: str):
    token = f\"[warranty:unit_sn={sn}]\"
    return Build.objects.filter(notes__contains=token).order_by('pk').first()

created = reused = updated = skipped = 0

for rec in R.objects.all().order_by('unit_sn'):
    sn = (rec.unit_sn or '').strip()
    if not sn:
        skipped += 1
        continue

    # Reuse a build if we've already created one for this SN
    build = find_existing_build_for_sn(sn)
    if build:
        reused += 1
        td = as_date(rec.audit_date)
        changed = False
        np = resolve_part(rec.model_number or '')
        if np and build.part_id != np.id:
            build.part = np; changed = True
        if getattr(build, 'target_date', None) != td:
            build.target_date = td; changed = True
        if changed:
            build.save(); updated += 1
        continue

    # Otherwise create a new Build
    part = resolve_part(rec.model_number or '')
    if not part:
        print(f'SKIP (no part): unit={sn} model={rec.model_number}')
        skipped += 1
        continue

    td = as_date(rec.audit_date)
    marker = f\"[warranty:unit_sn={sn}]\"
    note   = f\"Created by warranty sync {marker}\"

    with transaction.atomic():
        # Leave reference blank → InvenTree auto-generates compliant BO-####
        build = Build.objects.create(
            part=part,
            quantity=1,
            target_date=td,
            notes=note,
        )
        created += 1

print(f'Builds created={created}, reused={reused}, updated={updated}, skipped={skipped}')
PY
"

6) Verify builds exist
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 manage.py shell -c \"
from build.models import Build
print('Build count:', Build.objects.count())
print(list(Build.objects.order_by('-pk').values('reference','part__IPN','part__name','target_date')[:10]))
\"
"


You saw BO-#### references and the expected part (e.g., K08-00044).

7) View in the UI

Open http://139.84.201.15/

Go to Manufacturing → Build Orders

If nothing appears, click the refresh/reset icons to clear filters.

Troubleshooting

“SKIP (no part)”
Create or map a buildable Part for that model prefix (assembly=True) and re-run Step 5.

manage.py not found
Re-run Step 2 to detect BACKEND_DIR. If needed:
docker compose exec -T inventree-server sh -lc 'find / -maxdepth 4 -name manage.py 2>/dev/null'

UI not reachable
Ensure containers are up and proxy is listening on port 80:

docker compose ps
ss -lntp | grep ':80'
docker compose logs --tail=100 inventree-proxy inventree-server

Why this approach works

Auto references: By omitting reference, the Build model generates valid BO-#### references, avoiding regex errors.

Idempotent: The notes marker ([warranty:unit_sn=…]) ensures re-runs won’t duplicate Builds for the same unit.

Minimal schema changes: No FK needed. (You can add a ForeignKey from SafetyCultureRecord to Build later if you want a strict relational link.)
