# Warranty Plugin — Full Install & Configure (Remote Docker at `http://139.84.201.15/`)

End-to-end guide to install, enable, configure SafetyCulture credentials, run a sync, and verify results for the **warranty** InvenTree plugin on your remote server.

---

## ✅ Prerequisites

- SSH access to the host: `ssh root@139.84.201.15`
- Docker Compose project at: `~/inventree-docker`
- Plugin repo/tag to install: `huangderek02/inventree-warranty@v0.2.0`
- Your SafetyCulture **Template ID** and **API token**

---

## 0) SSH into the Server

```bash
ssh root@139.84.201.15
# Accept the host key on first connect
1) Bring Stack Up & Detect Backend Path
bash
Copy code
cd ~/inventree-docker
docker compose up -d

# Detect InvenTree backend path inside the container (where manage.py lives)
BACKEND_DIR="$(docker compose exec -T inventree-server sh -lc 'ls -d /home/inventree/src/backend/InvenTree 2>/dev/null || ls -d /home/invenree/src/backend/InvenTree 2>/dev/null')"
echo "BACKEND_DIR=$BACKEND_DIR"
Expected to be one of:

/home/inventree/src/backend/InvenTree

/home/invenree/src/backend/InvenTree

2) Install / Upgrade the Plugin Package
bash
Copy code
# Choose the code ref you want to install
REF="v0.2.0"

# Server
docker compose exec -T inventree-server sh -lc 'python3 -m pip uninstall -y warranty || true'
docker compose exec -T inventree-server sh -lc "python3 -m pip install -U 'git+https://github.com/huangderek02/inventree-warranty.git@${REF}#egg=warranty'"

# Worker (if present) — ensures scheduled tasks import the same version
if docker compose ps inventree-worker >/dev/null 2>&1; then
  docker compose exec -T inventree-worker sh -lc 'python3 -m pip uninstall -y warranty || true'
  docker compose exec -T inventree-worker sh -lc "python3 -m pip install -U 'git+https://github.com/huangderek02/inventree-warranty.git@${REF}#egg=warranty'"
fi
3) Enable the Plugin Persistently
Add to ./data/config.yaml. Adjust the directory path if your image uses /home/invenree.

bash
Copy code
mkdir -p ./data
if ! grep -qE '^\s*plugins:' ./data/config.yaml 2>/dev/null; then
  cat > ./data/config.yaml <<'YAML'
plugins:
  directory: /home/inventree/plugins
  enabled:
    - warranty
YAML
else
  # Ensure "- warranty" exists under plugins.enabled (idempotent)
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
  ' ./data/config.yaml > ./data/config.yaml.tmp && mv ./data/config.yaml.tmp ./data/config.yaml
fi

docker compose restart inventree-server >/dev/null
docker compose ps inventree-worker >/dev/null 2>&1 && docker compose restart inventree-worker >/dev/null
4) Verify Registry Sees the Plugin
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
Expected:

yaml
Copy code
registered: True
is_active : True
version   : 0.2.0
If not active, re-check Step 3 and restart inventree-server.

5) Configure SafetyCulture Credentials
Prompts for the token without echo; values are stored in the InvenTree DB as plugin settings.

bash
Copy code
# Provide your values (replace the template ID with yours if different)
SC_TEMPLATE_ID="template_60dc405af153456289d32d0abb62f3a4"
read -s -p "Paste SC_API_TOKEN (hidden): " SC_API_TOKEN; echo
SC_BASE_URL="https://api.safetyculture.io"  # change only if using a custom base

# Save settings into the plugin
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
(Optional) Label & Rules Overrides
bash
Copy code
docker compose exec -T inventree-server sh -lc "
  cd \"$BACKEND_DIR\"
  python3 - <<'PY'
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('LABEL_UNIT_SN',    'Unit Serial Number')  # or 'Unit QR Code' if your audits use that label for SN
p.set_setting('LABEL_TM_ID',      'Unit QR Code')
p.set_setting('LABEL_UMS_SN',     'UMS QR Code')
p.set_setting('LABEL_AUDIT_DATE', 'Conducted on')
p.set_setting('SERIAL_PREFIX_RULES','{\"IG\": {\"length\": 3, \"warranty\": 3}}')
for k in ('LABEL_UNIT_SN','LABEL_TM_ID','LABEL_UMS_SN','LABEL_AUDIT_DATE','SERIAL_PREFIX_RULES'):
    print(k,'->',p.get_setting(k))
PY
"
6) Run a One-Off Sync
Equivalent to Admin → Plugins → warranty → “Sync from SafetyCulture”.

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
7) Verify Data
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
Browse:

UI: http://139.84.201.15/

Admin list: http://139.84.201.15/admin/warranty/safetyculturerecord/

Troubleshooting
Plugin not active

Ensure ./data/config.yaml contains:

yaml
Copy code
plugins:
  directory: /home/inventree/plugins   # or /home/invenree/plugins
  enabled:
    - warranty
Restart: docker compose restart inventree-server

Cannot reach UI

Use http://139.84.201.15/ (reverse proxy on port 80)

Open firewall: ufw allow 80/tcp (and 443/tcp if TLS)

Logs: docker compose logs --tail=200 inventree-proxy inventree-server

Token/Template unset or wrong

Re-run Step 5; settings are safe to update at any time.

Scheduled tasks not running

Ensure inventree-worker is running; scheduled jobs require it.

Notes
Reinstalling the Python package does not clear plugin settings (they are DB-backed).

When updating the plugin code, bump the version (e.g., 0.2.1) and change REF in Step 2.

If your SafetyCulture field labels differ, adjust the optional label settings and re-sync.

::contentReference[oaicite:0]{index=0}
