# Server setup: `https://aytingchi.uz` (no `:3000`)

## Fast path: Docker Compose (recommended)

On the VPS, install **Docker** and **Docker Compose plugin**, clone the repo, then from the **repo root**:

1. Copy [`.env.example`](../.env.example) to `.env` and set `PUBLIC_ORIGIN` and `WS_URL`. For a domain with **HTTPS**, set the first line of [docker/Caddyfile](../docker/Caddyfile) to your domain (e.g. `aytingchi.uz {`) and use `https` / `wss` in `.env` (no `:3000` or `:8000` in the public URL).
2. Configure `backend/.env`.
3. Run `docker compose build` and `docker compose up -d`.

Only **ports 80 and 443** need to be public. Caddy routes API paths to FastAPI and the rest to Next. See [docker-compose.yml](../docker-compose.yml) and [docker/Caddyfile](../docker/Caddyfile).

The rest of this document is the **manual** install (Node, systemd, Caddy on the host) if you do not use Docker.

---

This guide assumes a **Linux VPS** (Ubuntu 22.04/24.04) with **root** or **sudo**, one public IP, and the domain **aytingchi.uz** (change the name in DNS and config if yours differs).

**Goal:** Users open `https://aytingchi.uz` — **no** `:3000` in the URL. Next.js runs on **127.0.0.1:3000** only. **Caddy** listens on **80** and **443** and proxies to that port.

---

## 1. Point DNS at the server

1. In your domain registrar (or Cloudflare DNS), add an **A record**:
   - **Name / Host:** `aytingchi.uz` (or `@` if the panel uses that for the apex)
   - **Value:** your VPS public IPv4 address
2. If you also use **www**, add `www` as a CNAME to `aytingchi.uz`, or a second A record to the same IP.
3. Wait until `ping aytingchi.uz` or `dig aytingchi.uz` shows the new IP (often a few minutes, sometimes up to 48h).

---

## 2. Open the firewall (HTTP/HTTPS)

On Ubuntu with **ufw** (adjust if you use another firewall or cloud security group):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

**Do not** open port **3000** to the public if you use a reverse proxy; only Caddy (or nginx) should face the internet. You may keep **8000** closed to the public and use **Caddy to proxy the API** (see [Optional: API on a subdomain](#optional-api-on-apisubdomain-without-8000-in-the-url)) or expose **8000** only for your team.

---

## 3. Install Node.js (LTS) and dependencies

```bash
# Node 20 LTS via NodeSource (example for Ubuntu) — or use nvm, fnm, or distro packages
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs git
node -v
npm -v
```

---

## 4. Put the project on the server

**Option A — Git clone (recommended):**

```bash
cd /var/www
sudo git clone <YOUR_REPO_URL> SQBHack
sudo chown -R $USER:$USER SQBHack
cd SQBHack
```

**Option B — upload** the project with `rsync` or `scp` into e.g. `/var/www/SQBHack`.

---

## 5. Build the Next.js frontend (production)

Set **public** API URLs **before** `npm run build` (values are baked into the client bundle for `NEXT_PUBLIC_*`).

```bash
cd /var/www/SQBHack/frontend
cp .env.example .env.production
nano .env.production   # edit — see example below
npm ci
npm run build
```

**Example `.env.production`:**

```env
# Where the browser can reach FastAPI (same host with port, or a subdomain you configure in Caddy)
NEXT_PUBLIC_API_URL=https://aytingchi.uz:8000
# If you add api.aytingchi.uz in Caddy → 8000, use instead:
# NEXT_PUBLIC_API_URL=https://api.aytingchi.uz
```

**Only if the backend is still separate / WebSocket** (voice features):

```env
NEXT_PUBLIC_WS_URL=wss://aytingchi.uz:8000/ws/voice
# or wss://api.aytingchi.uz/ws/voice
```

**If the backend has `API_SHARED_SECRET` in `.env`:** add the same value:

```env
NEXT_PUBLIC_WS_API_KEY=your_shared_secret
```

Re-run `npm run build` whenever you change `NEXT_PUBLIC_*` variables.

---

## 6. Run the API (FastAPI) on the same machine (optional but typical)

```bash
cd /var/www/SQBHack/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

Set e.g. `FRONTEND_ORIGIN=https://aytingchi.uz` (CORS) and your LLM keys. **Bind API to all interfaces** so Caddy (or a future subdomain) can reach `127.0.0.1:8000`:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production, use **systemd** (see an example at the end) so it restarts on boot.

**Firewall:** if you do **not** use `api.aytingchi.uz` in Caddy and you call `https://aytingchi.uz:8000` from browsers, you must **allow 8000/tcp** in ufw and ensure nothing else blocks it — or use the subdomain method so only **80/443** are public (recommended).

---

## 7. Run Next.js in production (localhost only)

On the same server:

```bash
cd /var/www/SQBHack/frontend
npx --yes next start -H 127.0.0.1 -p 3000
```

This listens only on **127.0.0.1:3000** (not on the public internet). For production, run this under **systemd** or **pm2** (see examples below) so it survives logout and reboot.

---

## 8. Install and configure Caddy

**Install (Ubuntu, official package):**

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

**Caddyfile** — you can use the file from this repo:

```bash
sudo cp /var/www/SQBHack/deploy/caddy-aytingchi.uz /etc/caddy/Caddyfile
# Edit domain if not aytingchi.uz
sudo nano /etc/caddy/Caddyfile
```

Minimal content (same as `deploy/caddy-aytingchi.uz`):

```caddy
aytingchi.uz {
	encode zstd gzip
	reverse_proxy 127.0.0.1:3000
}
```

**Enable and start Caddy** (Caddy will obtain a **Let’s Encrypt** certificate if DNS points to this server and ports 80/443 are open):

```bash
sudo systemctl enable caddy
sudo systemctl restart caddy
sudo systemctl status caddy
```

Open **`https://aytingchi.uz`** in a browser — you should get the Next app **without** `:3000`.

If something fails, check:

```bash
sudo journalctl -u caddy -e
curl -I http://127.0.0.1:3000
```

If `curl` to `127.0.0.1:3000` fails, the Next process is not running — fix the systemd/pm2 step first.

---

## Optional: API on `api.aytingchi.uz` (without `:8000` in the URL)

1. **DNS:** A record for `api.aytingchi.uz` → same server IP.
2. **Caddy** — add a second block (and reload Caddy):

```caddy
api.aytingchi.uz {
	reverse_proxy 127.0.0.1:8000
}
```

3. **Frontend** rebuild with:

```env
NEXT_PUBLIC_API_URL=https://api.aytingchi.uz
NEXT_PUBLIC_WS_URL=wss://api.aytingchi.uz/ws/voice
```

4. **CORS** on the backend: `FRONTEND_ORIGIN=https://aytingchi.uz` (or include both origins if you use `www`).

---

## Systemd: Next.js (example)

Create `/etc/systemd/system/next-aytingchi.service`:

```ini
[Unit]
Description=Next.js aytingchi.uz
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/SQBHack/frontend
ExecStart=/usr/bin/npx --yes next start -H 127.0.0.1 -p 3000
Restart=on-failure
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

Adjust **User** and **paths** to your layout. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now next-aytingchi
```

---

## Systemd: Uvicorn (example)

Create `/etc/systemd/system/sqbhack-api.service`:

```ini
[Unit]
Description=SQBHack FastAPI
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/SQBHack/backend
Environment="PATH=/var/www/SQBHack/backend/.venv/bin"
ExecStart=/var/www/SQBHack/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

With API only on `127.0.0.1:8000`, the public can reach it **only** if you add **Caddy** for `api.aytingchi.uz` or open port 8000 (less ideal).

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sqbhack-api
```

---

## Checklist

| Step | What |
|------|------|
| DNS | A record for `aytingchi.uz` → VPS IP |
| Firewall | 80, 443 open; SSH as needed |
| Build | `npm run build` with correct `NEXT_PUBLIC_*` in `.env.production` |
| Next | `next start` on `127.0.0.1:3000` (systemd or pm2) |
| Caddy | `reverse_proxy` to `127.0.0.1:3000` |
| API | Uvicorn on `127.0.0.1:8000` or proxy via Caddy on `api.aytingchi.uz` |
| CORS / FRONTEND_ORIGIN | Match `https://aytingchi.uz` |

This matches the [Caddy file](caddy-aytingchi.uz) in this folder; nginx users can use [nginx-aytingchi.uz.conf](nginx-aytingchi.uz.conf) and Certbot instead of Caddy.
