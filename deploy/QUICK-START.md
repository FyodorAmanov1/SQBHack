# Quick start: make the site work (Docker)

Do these **in order** on your **Linux server** (where you run `docker`).

## Before you start

1. You already moved this project to the server (e.g. with `git clone` or `scp`).
2. **DNS:** In your domain registrar, set an **A record** so your name (e.g. `aytingchi.uz`) points to your **server’s public IP**. Wait until it works (from your PC: `ping aytingchi.uz` shows that IP).
3. **Firewall** on the server: allow **port 22** (SSH), **80**, and **443** (e.g. `ufw allow 80` and `ufw allow 443`).

---

## 1) Configure the app (one small file in the project root)

On the server, in the same folder as `docker-compose.yml`:

```bash
cd /path/to/SQBHack
cp .env.example .env
nano .env
```

Set only these (use **your** domain; **https** and **wss** for secure site):

```env
PUBLIC_ORIGIN=https://aytingchi.uz
WS_URL=wss://aytingchi.uz/ws/voice
```

Save and close.

**Also** edit `backend/.env` (see `.env.example` there) with your LLM keys and so on. At minimum the backend must start; copy from `backend/.env.example` if you have it.

---

## 2) Turn on HTTPS in Caddy (one line in one file)

Edit `docker/Caddyfile`. Change the **first line** from:

```caddy
:80 {
```

to (use **your** domain, same spelling as in DNS):

```caddy
aytingchi.uz {
```

Do **not** change the rest of the file (the `handle` / `reverse_proxy` blocks).

Save.

---

## 3) Build and run

```bash
docker compose build
docker compose up -d
```

Wait ~1–2 minutes the first time.

---

## 4) Open the site

In a browser: **`https://aytingchi.uz`** (your domain, no **`:3000`**, no **`:8000`**).

If the page does not load: on the server run `docker compose ps` and `docker compose logs caddy` and fix errors (DNS, firewall, or typos in the domain in `Caddyfile` and `.env`).

---

## “I only want HTTP on an IP, no domain yet”

1. Keep `docker/Caddyfile` first line as **`:80 {`**.
2. In `.env` use your server IP, for example:
   ```env
   PUBLIC_ORIGIN=http://46.225.79.113
   WS_URL=ws://46.225.79.113/ws/voice
   ```
3. `docker compose build && docker compose up -d`
4. Open **`http://46.225.79.113`** (no `https` until you have a domain + step 2 above).

---

## You do **not** need Certbot for this

Caddy in Docker will get a **Let’s Encrypt** certificate **by itself** when the first line of `Caddyfile` is your **domain** and DNS points to this server. Use Certbot only if your team requires it — see [https-certbot-and-caddy.md](https-certbot-and-caddy.md).
