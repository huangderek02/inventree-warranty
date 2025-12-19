# Warranty Plugin — Full Install & Configure ()

This runbook installs the **warranty** InvenTree plugin end-to-end on your remote server, **enables** it, **sets SafetyCulture credentials**, runs a **sync**, and verifies the import.

> Assumptions  
> - You can SSH to the host: `ssh root@` (use your auth method)  
> - Your InvenTree stack runs with Docker Compose in `~/inventree-docker`  
> - You want plugin ref/tag **`v0.2.0`** from `huangderek02/inventree-warranty`  
> - You have your SafetyCulture **Template ID** and **API token** handy

---

## 🧰 Step 0 — SSH into the server

```bash
ssh root@
# If first time, accept the host key
🚀 Step 1 — Bring the stack up & detect backend path
bash
Copy code
cd ~/inventree-docker
docker compose up -d

# Detect where manage.py lives inside the container (inventree vs invenree spelling)
BACKEND_DIR="$(docker compose exec -T inventree-server sh -lc 'ls -d /home/inventree/src/backend/InvenTree 2>/dev/null || ls -d /home/invenree/src/backend/InvenTree 2>/dev/null')"
echo "BACKEND_DIR=$BACKEND_DIR"
You should see one of:

/home/inventree/src/backend/InvenTree

/home/invenree/src/backend/InvenTree

📦 Step 2 — Install/upgrade the plugin package (server + worker)
This installs a specific tag so your environment is reproducible.

bash
Copy code
REF="v0.2.0"  # change if needed

# Server
docker compose exec -T inventree-server sh -lc 'python3 -m pip uninstall -y warranty || true'
docker compose exec -T inventree-server sh -lc "python3 -m pip install -U 'git+https://github.com/huangderek02/inventree-warranty.git@${REF}#egg=warranty'"

# Worker (if present)
if docker compose ps inventree-worker >/dev/null 2>&1; then
  docker compose exec -T inventree-worker  sh -lc 'python3 -m pip uninstall -y warranty || true'
  docker compose exec -T inventree-worker  sh -lc "python3 -m pip install -U 'git+https://github.com/huangderek02/inventree-warranty.git@${REF}#egg=warranty'"
fi
🧩 Step 3 — Ensure the plugin is enabled persistently
Even for pip-installed plugins, it’s safest to list them under plugins.enabled.
Adjust the directory path to match your image (inventree vs invenree).

bash
Copy code
if ! grep -qE '^\s*plugins:' inventree-data/config.yaml 2>/dev/null; then
  # Create a minimal config.yaml
  cat > inventree-data/config.yaml <<'YAML'
plugins:
  directory: /home/inventree/plugins
  enabled:
    - warranty
YAML
else
  # Ensure - warranty is present under plugins.enabled (idempotent)
  awk '
    BEGIN{in_plugins=0; in_enabled=0; found=0}
    /^plugins:/{in_plugins=1}
    in_plugins && /^\s*enabled:\s*$/ {in_enabled=1}
    in_enabled && /- +warranty/ {found=1}
    {print}
    END{
      if(!in_plugins){
        print "plugins:\n  directory: /home/inventree/plugins\n  enabled:\n    - warranty"
      } else if(in_plugins && in_enabled && !found){
        print "    - warranty"
      }
    }
  ' inventree-data/config.yaml > inventree-data/config.yaml.tmp && mv inventree-data/config.yaml.tmp inventree-data/config.yaml
fi

# If your image uses /home/invenree, edit the directory line accordingly.
Restart to reload the plugin registry:

bash
Copy code
docker compose restart inventree-server
docker compose ps inventree-worker >/dev/null 2>&1 && docker compose restart inventree-worker
🔎 Step 4 — Verify the registry sees it
bash
Copy code
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
from plugin import registry
p = registry.get_plugin('warranty')
print('registered:', bool(p))
active = p.is_active() if hasattr(p,'is_active') and callable(p.is_active) else getattr(p,'is_active', None)
print('is_active :', active)
print('version   :', getattr(p,'VERSION', None))
PY
"
Expect:

yaml
Copy code
registered: True
is_active : True
version   : 0.2.0
If is_active isn’t True, revisit Step 3 and restart the server.

🔐 Step 5 — Set SafetyCulture Template ID and API token
We’ll prompt for your token without echoing it, and pass it only via env to the container.

bash
Copy code
# Provide your values here
SC_TEMPLATE_ID="template_...your_template_id_here..."   # ex: template_60dc405af153456289d32d0abb62f3a4
read -s -p "Paste SC_API_TOKEN (hidden): " SC_API_TOKEN; echo
SC_BASE_URL="https://api.safetyculture.io"  # change only if you use a different base

# Save settings into the plugin (DB)
docker compose exec -T -e SC_API_TOKEN="$SC_API_TOKEN" inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
import os
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('SC_TEMPLATE_ID',  '${SC_TEMPLATE_ID}')
p.set_setting('SC_BASE_URL',     '${SC_BASE_URL}')
p.set_setting('SC_API_TOKEN',    os.environ['SC_API_TOKEN'])
print('SC_TEMPLATE_ID ->', p.get_setting('SC_TEMPLATE_ID'))
print('SC_BASE_URL    ->', p.get_setting('SC_BASE_URL'))
print('SC_API_TOKEN?  ->', bool(p.get_setting('SC_API_TOKEN')))
PY
"
Optional label tweaks (if your SafetyCulture labels differ):

bash
Copy code
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('LABEL_UNIT_SN',    'Unit Serial Number')  # or 'Unit QR Code'
p.set_setting('LABEL_TM_ID',      'Unit QR Code')
p.set_setting('LABEL_UMS_SN',     'UMS QR Code')
p.set_setting('LABEL_AUDIT_DATE', 'Conducted on')
p.set_setting('SERIAL_PREFIX_RULES','{\"IG\": {\"length\": 3, \"warranty\": 3}}')
for k in ('LABEL_UNIT_SN','LABEL_TM_ID','LABEL_UMS_SN','LABEL_AUDIT_DATE','SERIAL_PREFIX_RULES'):
    print(k,'->',p.get_setting(k))
PY
"
🔁 Step 6 — Run a one-off Sync (same as Admin → Plugins → warranty → “Sync from SafetyCulture”)
bash
Copy code
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
from django.test.client import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import site
from warranty.admin import sync_from_safetyculture, SafetyCultureRecordAdmin
from warranty.models import SafetyCultureRecord
rf = RequestFactory(); req = rf.get('/')
SessionMiddleware(lambda r: None).process_request(req); req.session.save()
setattr(req,'_messages',FallbackStorage(req))
ma = SafetyCultureRecordAdmin(SafetyCultureRecord, site)
sync_from_safetyculture(ma, req, SafetyCultureRecord.objects.none())
print('rows now:', SafetyCultureRecord.objects.count())
PY
"
✅ Step 7 — Verify records
bash
Copy code
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
from warranty.models import SafetyCultureRecord as R
print('rows:', R.objects.count())
print(list(R.objects.order_by('-audit_date').values('unit_sn','model_number','audit_date','warranty_expiry')[:10]))
PY
"
You can also browse:

UI: http://139.84.201.15/

Admin list: http://139.84.201.15/admin/warranty/safetyculturerecord/

🩺 Troubleshooting Cheats
Plugin not listed / not active

Ensure inventree-data/config.yaml contains:

yaml
Copy code
plugins:
  directory: /home/inventree/plugins    # or /home/invenree/plugins
  enabled:
    - warranty
docker compose restart inventree-server

Proxy but site won’t open

Use http:/// (port 80 via proxy), not :8000

Open firewall: ufw allow 80/tcp (and 443/tcp if using TLS)

Check logs: docker compose logs --tail=200 inventree-proxy inventree-server

Token/Template missing

Re-run Step 5; the settings live in DB and can be updated any time.

Scheduled task won’t run

Ensure inventree-worker is running (the scheduler needs it).

🧷 Notes
Re-installing the Python package does not clear plugin settings — they’re stored in the DB.

When updating code, bump the plugin version (e.g., 0.2.1) and install that tag/ref in Step 2.

You can set labels/rules later as you refine mapping; they apply on the next sync.

makefile
Copy code
::contentReference[oaicite:0]{index=0}
