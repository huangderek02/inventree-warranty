# Warranty

A short description of the project

## Installation

### InvenTree Plugin Manager

... todo ...

### Command Line 

To install manually via the command line, run the following command:

```bash
pip install warranty
```

## Configuration

... todo ...

## Usage

... todo ...

Here’s exactly what you did (and can do again) to load the data into your localhost InvenTree:

1) Make sure the plugin is installed and loaded

From your InvenTree backend folder (/home/inventree/src/backend/InvenTree):

python -m pip install -U -e /workspaces/inventree-plugin/Warranty
python manage.py shell -c "from plugin import registry; print(bool(registry.get_plugin('warranty')))"


That last line should print True.

2) Save your SafetyCulture settings into the plugin (in DB)
python manage.py shell -c "
import os
from plugin import registry
p = registry.get_plugin('warranty')
p.set_setting('SC_API_TOKEN',  os.environ['SC_API_TOKEN'])
p.set_setting('SC_TEMPLATE_ID',os.environ['SC_TEMPLATE_ID'])
p.set_setting('SC_BASE_URL',   os.environ.get('SC_BASE_URL','https://api.safetyculture.io'))
print('saved:', len(p.get_setting('SC_API_TOKEN')), p.get_setting('SC_TEMPLATE_ID'))
"


(You can also set optional labels like LABEL_UNIT_SN='Unit QR Code' the same way.)

3) Run the sync action (the same one shown in the Admin, but from shell)

This calls the admin action Sync from SafetyCulture programmatically:

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

4) Verify rows were created
python manage.py shell -c "
from warranty.models import SafetyCultureRecord as R
print('rows:', R.objects.count())
print(list(R.objects.order_by('-audit_date').values('unit_sn','model_number','audit_date','warranty_expiry')[:10]))
"
