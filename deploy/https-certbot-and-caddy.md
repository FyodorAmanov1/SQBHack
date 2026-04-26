# HTTPS: Certbot vs Caddy (this project)

## Option A — Simplest: Caddy + your domain (no Certbot)

[Caddy](https://caddyserver.com/) can obtain and renew **Let’s Encrypt** certificates **by itself** when the first line of [`docker/Caddyfile`](../docker/Caddyfile) is your hostname, e.g.:

```caddy
aytingchi.uz {
```

Replace `:80 {` with that, set DNS **A** record to the server, open **80** and **443**, set root **`.env`** to `https://…` and `wss://…`, then:

```bash
docker compose up -d --build
```

Caddy requests the cert on startup. **You do not need Certbot** for this stack.

If that works, stop here.

---

## Option B — You want certificates from Certbot + use them in Docker Caddy

Use this when your org requires **Certbot** (or you already have a Certbot workflow).

### 1. Prerequisites

- DNS **A** record: `aytingchi.uz` → server public IP.
- **Port 80** free on the host for the HTTP-01 challenge (see below).

### 2. Stop whatever is using port 80

```bash
cd /path/to/SQBHack
docker compose stop caddy
```

### 3. Get a certificate (standalone)

Certbot starts a small server on **80** to prove you control the domain:

```bash
sudo certbot certonly --standalone -d aytingchi.uz
# add: -d www.aytingchi.uz   if you use www
```

Follow the prompts (email, ToS). Certificates are stored under:

`/etc/letsencrypt/live/aytingchi.uz/fullchain.pem`  
`/etc/letsencrypt/live/aytingchi.uz/privkey.pem`

### 4. Point Caddy at those files

Edit **`docker/Caddyfile`**: change the first line to your domain and add **explicit TLS** (first line and `tls` inside the block):

```caddy
aytingchi.uz {
	tls /etc/letsencrypt/live/aytingchi.uz/fullchain.pem /etc/letsencrypt/live/aytingchi.uz/privkey.pem

	encode zstd gzip

	@api {
		path /health
		path /stt
		path /llm
		path /tts
		path /voice_reply
		path /operator-advice
		path /docs
		path /docs/*
		path /redoc
		path /redoc*
		path /openapi.json
		path /client-analytics*
		path /voices
		path /ws*
	}

	handle @api {
		reverse_proxy backend:8000
	}

	handle {
		reverse_proxy frontend:3000
	}
}
```

### 5. Mount Let’s Encrypt into the Caddy container

In **`docker-compose.yml`**, under the **`caddy`** service, add a **read-only** volume:

```yaml
  caddy:
    # ... existing ...
    volumes:
      - ./docker/Caddyfile:/etc/caddy/Caddyfile:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
```

Then:

```bash
docker compose up -d
```

### 6. Renewal

Certbot installs a **twice-daily** `certbot renew` (systemd timer or cron). When the cert is renewed, **Caddy must reload** so it reads the new files. Add a **deploy hook** (path may vary by OS):

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-caddy.sh <<'EOF'
#!/bin/sh
cd /path/to/SQBHack && /usr/bin/docker compose restart caddy
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-caddy.sh
```

Or use one script that runs `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` if your image supports it.

**Dry-run:** `sudo certbot renew --dry-run`

### 7. HTTP-01 and port 80 at renewal time

`certbot renew` with the **standalone** plugin also needs **port 80** free during renewal unless you switch to **webroot** or **DNS-01** challenge. Common approaches:

- **Pre-hook** stop Caddy, **post-hook** start Caddy (same as initial issuance), or
- Use **`certbot certonly --webroot`** with a small nginx/Caddy only for `/.well-known/acme-challenge/`, or
- Use a **DNS plugin** (e.g. Cloudflare) so nothing listens on 80 for renewal.

For production, many people move to **nginx + certbot** (below) or **Caddy’s built-in ACME (Option A)** to avoid port-80 contortions on renew.

---

## Option C — Nginx on the host + Certbot (`certbot --nginx`)

Typical when you want **nginx** to terminate TLS and **proxy to Docker** (not covered in full here):

1. Install nginx and Certbot’s nginx plugin: `sudo apt install nginx certbot python3-certbot-nginx`
2. Configure a `server` for `aytingchi.uz` with `location /` etc. (same routing idea as the Caddyfile: API paths to FastAPI, else to Node).
3. `sudo certbot --nginx -d aytingchi.uz`
4. Point `proxy_pass` to whatever ports your Docker stack uses (e.g. after changing compose so only **127.0.0.1:3000** is exposed, or a dedicated internal port).

You would **not** run the **docker Caddy** service on **80/443** at the same time; avoid double proxies unless you know why.

---

## Checklist (Certbot + Caddy in Docker)

| Step | Action |
|------|--------|
| DNS | A record for `aytingchi.uz` |
| Port 80 | Free for `certbot certonly --standalone` (stop Caddy first) |
| Certs | `/etc/letsencrypt/live/aytingchi.uz/*.pem` |
| Caddyfile | `tls` with those paths + same `handle` rules as now |
| Compose | Mount `/etc/letsencrypt:ro` into the Caddy service |
| App `.env` | `PUBLIC_ORIGIN=https://aytingchi.uz`, `WS_URL=wss://…` and rebuild `frontend` if needed |
| Renew | `certbot renew` + hook to restart or reload Caddy |

---

**Summary:** For this repository, the **lowest-friction** HTTPS path is **Option A** (domain in the Caddyfile, Let’s Encrypt **inside** Caddy). **Option B** is for when you must use **Certbot**-issued files with the **same** Docker Caddy service.
