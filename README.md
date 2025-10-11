
# Warranty Plugin — Where to Install on 

This guide explains **exactly which directories** to use to install and enable the `warranty` plugin on your remote Docker host at `139.84.201.15` (project at `~/Inventree-Docker`). It covers two supported approaches:

- **Option A (Recommended):** Host bind-mount → container `/home/invenree/plugins` (persistent, easy updates)  
- **Option B (Quickest):** `pip install` inside containers (no bind-mount, but re-run after rebuilds)

---

## Prerequisites

```bash
ssh root@139.84.201.15
cd ~/Inventree-Docker
docker compose up -d
docker compose ps


You should see inventree-db, inventree-cache, inventree-server, inventree-worker, and (optionally) inventree-proxy up.

Option A — Bind-Mount a Host Directory (Persistent & Recommended)
1) Create a plugins directory on the host and clone the repo
mkdir -p ~/inventree-plugins
git clone https://github.com/huangderek02/inventree-warranty.git ~/inventree-plugins/warranty


Host path: ~/inventree-plugins/warranty

This folder will be mounted read-only into the container.

2) Mount the host directory into the containers

Create or edit ~/Inventree-Docker/docker-compose.override.yml:

version: "3.9"
services:
  inventree-server:
    volumes:
      - ${HOME}/inventree-plugins:/home/invenree/plugins:ro
  inventree-worker:
    volumes:
      - ${HOME}/inventree-plugins:/home/invenree/plugins:ro


Some images use /home/inventree (with t) instead of /home/invenree. If that’s your case, replace the mount target and use the same path everywhere below.

3) Enable the plugin in InvenTree config.yaml

Append to ~/Inventree-Docker/data/config.yaml (create the file if missing):

plugins:
  directory: /home/invenree/plugins
  enabled:
    - warranty

4) Apply & verify
docker compose up -d
docker compose restart inventree-server inventree-worker

# Which backend directory does your image use? (one of these will exist)
docker compose exec inventree-server sh -lc 'ls -d /home/invenree/src/backend/InvenTree 2>/dev/null || ls -d /home/inventree/src/backend/InvenTree 2>/dev/null'

# Is the plugin dir visible inside the container?
docker compose exec inventree-server sh -lc 'test -d /home/invenree/plugins/warranty && echo "plugin dir OK" || echo "plugin dir missing"'

# Does InvenTree detect the plugin?
docker compose exec inventree-server sh -lc '
  cd /home/invenree/src/backend/InvenTree || cd /home/inventree/src/backend/InvenTree
  python3 manage.py shell -c "from plugin import registry; print(bool(registry.get_plugin(\"warranty\")))"
'
# Expect: True


Summary (Option A)

Host directory: ~/inventree-plugins/warranty

Container directory: /home/invenree/plugins/warranty

Config: plugins.directory: /home/invenree/plugins, enabled: [warranty]

Option B — Install Inside the Containers (Fast, Not Persistent)

No special directory is required. pip installs to the container’s Python site-packages.

# Install the plugin into server and worker containers
docker compose exec inventree-server sh -lc 'python3 -m pip install -U "git+https://github.com/huangderek02/inventree-warranty.git@v0.1.0#egg=warranty"'
docker compose exec inventree-worker sh -lc  'python3 -m pip install -U "git+https://github.com/huangderek02/inventree-warranty.git@v0.1.0#egg=warranty"'

# Verify InvenTree detects the plugin
docker compose exec inventree-server sh -lc '
  cd /home/invenree/src/backend/InvenTree || cd /home/inventree/src/backend/InvenTree
  python3 manage.py shell -c "from plugin import registry; print(bool(registry.get_plugin(\"warranty\")))"
'
# Expect: True


⚠️ If you rebuild or pull new images, you must re-run the pip install commands (the code lives inside the containers).

Quick Checks & Diagnostics
# 1) Find the correct backend path (one of these exists):
docker compose exec inventree-server sh -lc 'ls -d /home/invenree/src/backend/InvenTree 2>/dev/null || ls -d /home/inventree/src/backend/InvenTree 2>/dev/null'

# 2) If using a bind-mount, confirm the plugin is visible in the container:
docker compose exec inventree-server sh -lc 'ls -la /home/invenree/plugins | head'

# 3) Confirm InvenTree sees the plugin:
docker compose exec inventree-server sh -lc '
  cd /home/invenree/src/backend/InvenTree || cd /home/inventree/src/backend/InvenTree
  python3 manage.py shell -c "from plugin import registry; print(registry.get_plugin(\"warranty\") is not None)"
'

Decision Guide

Want persistence and simple git updates on 139.84.201.15?
Use Option A → Host: ~/inventree-plugins/warranty, Container: /home/invenree/plugins/warranty, enable in config.yaml.

Need a quick, one-off install?
Use Option B → No directory; just pip install inside inventree-server (and inventree-worker if applicable).

Next Steps (after installation)

Configure plugin settings:

docker compose exec inventree-server sh -lc '
  cd /home/invenree/src/backend/InvenTree || cd /home/inventree/src/backend/InvenTree
  python3 manage.py shell << "PY"
from plugin import registry
p = registry.get_plugin("warranty")
p.set_setting("SC_API_TOKEN",   "<YOUR_SC_API_TOKEN>")
p.set_setting("SC_TEMPLATE_ID", "<YOUR_TEMPLATE_ID>")
p.set_setting("SC_BASE_URL",    "https://api.safetyculture.io")
print("Configured:", bool(p.get_setting("SC_API_TOKEN")), p.get_setting("SC_TEMPLATE_ID"))
PY
'


Run a sync (same logic as the Admin action) and verify records in the Admin UI:

http://139.84.201.15:8000/admin/warranty/safetyculturerecord/
