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

---

## 1) Bring Stack Up & Detect Backend Path

---
