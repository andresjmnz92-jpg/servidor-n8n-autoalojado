***English** · [Español](README.es.md)*

# Self-hosted n8n — built to survive being ignored

My own automation server on a VPS: n8n in Docker, behind HTTPS on a domain I control. The point
is not saving money on the cloud version — it's being able to run automation for companies whose
data cannot leave their own infrastructure.

**Server:** Hetzner CX33 (4 vCPU, 8 GB RAM, 40 GB) · Ubuntu 26.04 LTS · Falkenstein, Germany
**Stack:** Docker + Docker Compose + n8n + Caddy · **~9 USD/month**

---

## What it runs, and how it stays up

It is not a demo instance. A **client's Telegram ordering bot** runs on it in production, plus my
own automations — an hourly job radar and a weekly reporting workflow.

Four things keep it alive without me:

| **Automatic patching** | `unattended-upgrades` with a reboot window at 3am local |
| **Daily backups** | n8n volume at 2am → **Cloudflare R2**, 7 days local / 30 off-site |
| **External watchdog** | GitHub Actions asks `/healthz` every 30 min and emails on failure |
| **HTTPS that renews itself** | Caddy + Let's Encrypt, zero intervention |

**Both alarms were tested in the failing direction, not just the passing one.** The watchdog was
pointed at a path that doesn't exist to confirm it goes red. **An alarm you have never seen fire
is an assumption, not a warning.**

**And the backups were restored, not just written.**

---

## The restore drill

A backup stored on the same disk it protects is a copy. One that has never been restored is an
assumption. This was done on day two **on purpose** — with the instance nearly empty the drill
isn't scary, and scary things get postponed forever.

Without touching the live instance: a fresh volume, a throwaway n8n pointed at it, then ask it
what's inside.

```bash
docker volume create n8n_data_test
docker run --rm -v n8n_data_test:/data -v /home/user/backups:/backup alpine \
  sh -c "cd /data && tar xzf /backup/n8n-YYYY-MM-DD.tar.gz"
docker run -d --name n8n-test --env-file /path/to/.env \
  -v n8n_data_test:/home/node/.n8n docker.n8n.io/n8nio/n8n:stable
docker exec n8n-test n8n list:workflow      # <- the proof
docker rm -f n8n-test && docker volume rm n8n_data_test
```

`n8n list:workflow` returned the workflows with their exact IDs, out of a `.tar.gz`. The live
instance was then confirmed untouched and still answering 200 from outside.

**Three things the drill taught:**

- **SQLite's `-wal` file is part of the backup.** `database.sqlite` was two hours older than
  `database.sqlite-wal`, and the most recent work lived in that `-wal`. Copying only the `.sqlite`
  would have restored a database missing the last few hours.
- **Without the encryption key, the backup doesn't open.** The `.tar.gz` and the key are two
  pieces that only work together — which is why they live in different places.
- **Restores are tested on a separate volume, never on top of the live one.** One underscore
  separates `n8n_data_test` from `n8n_data`, and all your data from none of it.

---

## Three bugs worth writing down

### The encryption key has a second copy

Rotating `N8N_ENCRYPTION_KEY` in `.env` put n8n into a restart loop and the site started returning
502. The log said what none of the guides did:

```
Error: Mismatching encryption keys. The encryption key in the settings file
/home/node/.n8n/config does not match the N8N_ENCRYPTION_KEY env var.
```

**n8n keeps a second copy of that key inside its own data volume.** Changing `.env` alone is not
enough — `/home/node/.n8n/config` has to match.

There is an earlier trap too: the same key encrypts the 2FA secret and its recovery codes. Rotate
it with 2FA on and you lock yourself out of your own instance. **Disable 2FA before rotating.**

### A four-year-old client against a current API

Every R2 upload failed with `NotImplemented: 501` on the first attempt and succeeded on the
second. The backup "worked" but left an error on every run — the kind of noise that trains you to
ignore errors.

A **7-byte** test file failing the same way gave it away: that rules out size, multipart and
chunking, and leaves only headers. The cause was the version — `apt` ships rclone **v1.60.1, from
November 2022**. With the official build (v1.75.0) the error was gone, verified with `--retries 1`
so no retry could hide it.

> On a strange S3 error, check `rclone version` first. Distro packages can run years behind the
> services they talk to.

### The reboot window is in UTC

`unattended-upgrades` was already on, but **it never reboots by default** — so kernel patches sit
downloaded and unused for months. The fix is a `99-automatic-reboot` drop-in with a time window.

The detail almost everyone misses: that time uses the system clock, which here is **UTC**. Setting
"02:00" would have rebooted the box at 9pm local, mid-evening. It's set to `08:00` UTC — 3am in
Colombia.

---

## The lesson that removed the most code: −46 lines, +1

The watchdog was first written as a 30-line Python script. It did exactly what this does:

```
curl -fsS --retry 3 --retry-delay 20 "$N8N_URL/healthz" | grep -q '"ok"'
```

Deleting the script also made the `actions/checkout` step redundant — there was no longer a file
to check out. **Removing code removed a whole dependency.**

---

## Build log

### Day 1 — August 6, 2026 · Harden first, install second

The server was locked down before anything was installed on it. Order matters: a freshly created
server starts getting login attempts within minutes of coming online.

1. **System updated** — `apt update && apt upgrade`, then a reboot.
2. **A regular user with sudo** — stopped working as `root`. A typo as root wipes the system; the
   same typo as a normal user does not.
3. **SSH key authentication only** — ed25519 key pair. The private key never leaves my machine.
4. **Passwords turned off** — in `/etc/ssh/sshd_config.d/99-endurecer.conf`, as a drop-in rather
   than an edit to `sshd_config`, so it survives package upgrades:
   ```
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   ```
5. **ufw enabled** — SSH, 80 and 443 open. Everything else closed.
6. **Docker installed** from the official repository, GPG signature verified.

**Verified, not assumed:**

- `sudo sshd -T | grep -Ei "permitrootlogin|passwordauthentication"` → `no` and `no`
- Opened a second session with the key *before* closing the one that worked
- `docker run hello-world` ran · `docker compose version` → v5.4.0

**Two things learned the hard way:**

- **Read the prompt before typing.** `PS C:\...` is my machine; `user@homelab` is the server. I
  tried to SSH into the server from inside the server. Twice.
- **Allow before you enable.** `ufw allow OpenSSH` first, `ufw enable` second. The other way
  around locks you out of your own box.

### Day 2 — August 7, 2026 · HTTPS on my own domain

**The deployment workflow is the point of this day:**

1. Files are written on my machine, inside the cloned repo.
2. `git push` to GitHub.
3. On the server: `git pull`, then `docker compose up -d`.

**The server is a runtime, not a build server.** The only file that exists there and not in this
repo is `.env` — it holds secrets, so by definition it cannot be versioned.

**What went up:**

- **An A record** pointing the subdomain at the server, with the **Cloudflare proxy turned off**
  (grey cloud). With the orange cloud on, Cloudflare intercepts the ACME challenge and the
  certificate never gets issued.
- **Caddy** as reverse proxy — obtains and renews the certificate unattended, and adds four
  security headers (HSTS, nosniff, SAMEORIGIN, referrer-policy).
- **n8n publishes no ports.** It is not exposed to the internet — only Caddy is, and it reaches
  n8n over Docker's private network.
- **Secrets generated on the server** with `openssl rand -base64 32`, never copied and never typed
  by hand. `.env` set to mode `600`.
- **2FA enabled** on the owner account.

**Verified, not assumed:**

- `docker compose exec n8n wget -qO- http://localhost:5678/healthz` → `{"status":"ok"}`
- `docker compose logs caddy | grep -i "certificate obtained"` → certificate issued
- `/healthz` requested from outside the server → HTTP 200

---

## What's still missing

Written down because a status without its gaps isn't a status.

- **Deploys are still manual.** `git pull` + `docker compose up -d` over SSH. Automating it with
  GitHub Actions is the next step, and the safe way is a key restricted in `authorized_keys` with
  `restrict,command="/path/deploy.sh"` — so a leaked key can only deploy, never open a shell.
- **n8n runs in single mode with SQLite.** Fine for this load; a queue mode with Postgres is what
  a multi-tenant setup would need.
- **n8n upgrades are manual on purpose.** `N8N_IMAGE_TAG` is pinned, because it breaks across
  major versions and an unattended upgrade of the thing running a client's bot is not a risk worth
  automating.

## A note on secrets

This repository is public. The private SSH key, `.env` files and passwords never go in here, and
`.gitignore` blocks them. The n8n encryption key in particular decrypts every stored credential —
a backup without it is a file nobody can open, which is exactly why the two are stored apart.
