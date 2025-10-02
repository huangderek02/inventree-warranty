# Warranty

A plugin for integrating warranty records from SafetyCulture into InvenTree.

---

## 📦 Installation

You can install the plugin either using the **InvenTree Plugin Manager** (recommended) or manually from the command line (useful for local development).

### Option 1: InvenTree Plugin Manager

1. Open InvenTree as an administrator.  
2. Go to **Admin → Plugins → Install**.  
3. Search for `warranty` (if published to PyPI) or provide the GitHub URL if not yet on PyPI.  
   - Example:  
     ```
     https://github.com/inventree/warranty
     ```
4. Enable the plugin in **Admin → Plugins → warranty**.

### Option 2: Command Line

To install manually via the command line, run:

```bash
pip install warranty
Or, if developing locally from source:

bash
Copy code
python -m pip install -U -e /workspaces/inventree-plugin/Warranty
Verify the plugin is registered
From your InvenTree backend folder (e.g. /home/inventree/src/backend/InvenTree):

bash
Copy code
python manage.py shell -c "from plugin import registry; print(bool(registry.get_plugin('warranty')))"
If successful, this will print:

graphql
Copy code
True
⚙️ Configuration
The plugin requires SafetyCulture credentials and a template ID. These are stored as plugin settings inside the InvenTree database.

Run the following command to configure:

bash
Copy code
python manage.py shell -c "
import os
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('SC_API_TOKEN',  os.environ['SC_API_TOKEN'])
p.set_setting('SC_TEMPLATE_ID',os.environ['SC_TEMPLATE_ID'])
p.set_setting('SC_BASE_URL',   os.environ.get('SC_BASE_URL','https://api.safetyculture.io'))
print('saved:', len(p.get_setting('SC_API_TOKEN')), p.get_setting('SC_TEMPLATE_ID'))
"
Required settings
SC_API_TOKEN – SafetyCulture API token.

SC_TEMPLATE_ID – Template ID for warranty records.

Optional settings
SC_BASE_URL – API base URL (default: https://api.safetyculture.io).

LABEL_UNIT_SN – Override label for serial numbers (e.g. "Unit QR Code").

Example of setting an optional label:

python
Copy code
p.set_setting('LABEL_UNIT_SN', 'Unit QR Code')
▶️ Usage
1. Sync SafetyCulture Records
You can sync data manually from the Admin UI:
Plugins → Warranty → Actions → Sync from SafetyCulture

Or programmatically from the shell:

bash
Copy code
python manage.py shell <<'PY'
from django.test.client import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import admin
from warranty.admin import sync_from_safetyculture, SafetyCultureRecordAdmin
from warranty.models import SafetyCultureRecord

rf = RequestFactory()
req = rf.get('/')
SessionMiddleware(lambda r: None).process_request(req)
req.session.save()
setattr(req, '_messages', FallbackStorage(req))

ma = SafetyCultureRecordAdmin(SafetyCultureRecord, admin.site)
sync_from_safetyculture(ma, req, SafetyCultureRecord.objects.none())
PY
2. Verify Data Import
Check that records were created:

bash
Copy code
python manage.py shell -c "
from warranty.models import SafetyCultureRecord as R
print('rows:', R.objects.count())
print(list(R.objects.order_by('-audit_date').values('unit_sn','model_number','audit_date','warranty_expiry')[:10]))
"
This will show the number of imported rows and sample records with fields like unit_sn, model_number, audit_date, and warranty_expiry.

🚀 Quickstart Script
For local dev or quick setup, you can use the following Bash script (requires environment variables SC_API_TOKEN and SC_TEMPLATE_ID to be set):

bash
Copy code
#!/usr/bin/env bash
set -e

# Install the plugin
pip install warranty

# Verify plugin is loaded
python manage.py shell -c "from plugin import registry; print('Plugin loaded:', bool(registry.get_plugin('warranty')))"

# Configure settings
python manage.py shell -c "
import os
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('SC_API_TOKEN',  os.environ['SC_API_TOKEN'])
p.set_setting('SC_TEMPLATE_ID',os.environ['SC_TEMPLATE_ID'])
p.set_setting('SC_BASE_URL',   os.environ.get('SC_BASE_URL','https://api.safetyculture.io'))
print('Settings saved')
"

# Run sync
python manage.py shell <<'PY'
from django.test.client import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import admin
from warranty.admin import sync_from_safetyculture, SafetyCultureRecordAdmin
from warranty.models import SafetyCultureRecord

rf = RequestFactory()
req = rf.get('/')
SessionMiddleware(lambda r: None).process_request(req)
req.session.save()
setattr(req, '_messages', FallbackStorage(req))

ma = SafetyCultureRecordAdmin(SafetyCultureRecord, admin.site)
sync_from_safetyculture(ma, req, SafetyCultureRecord.objects.none())
print("Sync complete")
PY

# Verify data
python manage.py shell -c "
from warranty.models import SafetyCultureRecord as R
print('rows:', R.objects.count())
print(list(R.objects.order_by('-audit_date').values('unit_sn','model_number','audit_date','warranty_expiry')[:5]))
"
Save this as setup_warranty.sh, run chmod +x setup_warranty.sh, and execute it after setting your environment variables.

✅ Summary
Install the plugin (pip install warranty or via Plugin Manager).

Verify it loads (registry.get_plugin('warranty') → True).

Configure SafetyCulture settings (SC_API_TOKEN, SC_TEMPLATE_ID, SC_BASE_URL).

Run a sync (UI or shell).

Verify records were created.
