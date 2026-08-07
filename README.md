***English** · [Español](README.es.md)*

# Self-hosted n8n

My own automation server on a VPS: n8n in Docker, behind HTTPS on a domain I control. The
point is not to save money on the cloud version — it is to run automation for companies whose
data cannot leave their own servers.

**Server:** Hetzner CX23 (2 vCPU, 4 GB RAM, 40 GB) · Ubuntu 26.04 LTS · Falkenstein, Germany
**Stack:** Docker + Docker Compose + n8n + Caddy
**Cost:** ~7 USD/month

---

## Build log

### Day 1 — August 6, 2026 · Harden the server, then install

The server was locked down before anything was installed on it. Order matters: a freshly
created server starts getting login attempts within minutes of coming online.

**What was done:**

1. **System updated** — `apt update && apt upgrade`, then a reboot.
2. **A regular user with sudo** — stopped working as `root`. A typo as root wipes the
   system; the same typo as a normal user does not.
3. **SSH key authentication only** — generated an ed25519 key pair. The public key lives on
   the server; the private key never leaves my machine.
4. **Passwords turned off** — `/etc/ssh/sshd_config.d/99-endurecer.conf`:
   ```
   PermitRootLogin no
   PasswordAuthentication no
   KbdInteractiveAuthentication no
   ```
   With no password to guess, brute force stops being a threat. This went in as a drop-in
   file rather than an edit to `sshd_config`, so it survives package upgrades.
5. **ufw enabled** — SSH, 80 and 443 open. Everything else closed.
6. **Docker installed** from the official repository, with the GPG signature verified.

**Verified, not assumed:**

- `sudo sshd -T | grep -Ei "permitrootlogin|passwordauthentication"` → `no` and `no`
- Opened a second session with the key *before* closing the one that worked
- `docker run hello-world` ran the test container
- `docker compose version` → v5.4.0

**Two things I learned the hard way:**

- **Read the prompt before typing.** `PS C:\...` is my machine; `user@homelab` is the
  server. I tried to SSH into the server from inside the server. Twice.
- **Allow before you enable.** `ufw allow OpenSSH` first, `ufw enable` second. The other way
  around locks you out of your own box.

**Next:** point a subdomain at the server and bring up n8n over HTTPS.

### Day 2 — August 7, 2026 · n8n over HTTPS on my own domain

n8n running behind Caddy with a Let's Encrypt certificate that renews itself. Deployed
without editing a single file on the server.

**The workflow is the point of this day:**

1. Files are written on my machine, inside the cloned repo.
2. `git push` to GitHub.
3. On the server: `git clone`, then `docker compose up -d`.

The server is a runtime, not a build server. The only file that exists there and not in this
repo is `.env` — it holds secrets, so by definition it cannot be versioned.

**What went up:**

- **An A record** pointing the subdomain at the server, with the **Cloudflare proxy turned
  off** (grey cloud). With the orange cloud on, Cloudflare intercepts the ACME challenge and
  the certificate never gets issued.
- **Caddy** as the reverse proxy. It obtains and renews the certificate with no intervention,
  and adds four security headers (HSTS, nosniff, SAMEORIGIN, referrer-policy).
- **n8n publishes no ports.** It is not exposed to the internet — only Caddy is, and it
  reaches n8n over Docker's private network.
- **Secrets generated on the server**, never copied from elsewhere and never typed by hand:
  `openssl rand -base64 32`. `.env` set to mode `600`.
- **2FA enabled** on the owner account.

**Verified, not assumed:**

- `docker compose exec n8n wget -qO- http://localhost:5678/healthz` → `{"status":"ok"}`
- `docker compose logs caddy | grep -i "certificate obtained"` → certificate issued
- `/healthz` requested from outside the server → HTTP 200
- Certificate issued by Let's Encrypt, valid through November 5, 2026

**The mistake of the day: rotating the encryption key broke n8n.**

I changed `N8N_ENCRYPTION_KEY` in `.env`. n8n went into a restart loop and the site started
returning 502. The log said what none of the guides did:

```
Error: Mismatching encryption keys. The encryption key in the settings file
/home/node/.n8n/config does not match the N8N_ENCRYPTION_KEY env var.
```

**n8n keeps a second copy of that key inside its own data volume.** Changing `.env` alone is
not enough — `/home/node/.n8n/config` has to be updated to match.

There is an earlier trap too: the same key encrypts the 2FA secret and its recovery codes.
Rotate it while 2FA is on and you lock yourself out of your own instance. **Disable 2FA
before rotating, re-enable it after.**

Neither of those came from a search engine. Both came from reading the logs of the program
that was failing.

### Later the same day · Make it look after itself

A server you have to babysit isn't finished. Three things, and not one custom script.

**Automatic patching.** `unattended-upgrades` was already on, but **it never reboots by
default** — so kernel patches sit downloaded and unused for months. Added a `99-automatic-reboot`
drop-in with a reboot window.

The detail almost everyone misses: that time uses the system clock, which here is **UTC**.
Setting "02:00" would have rebooted the box at 9pm local, in the middle of the working evening.
It's set to `08:00` UTC — 3am in Colombia.

**A watchdog that lives off the server.** It runs on GitHub's machines every 30 minutes and asks
whether `/healthz` answers. If it doesn't, the run goes red and the email arrives.

It lives elsewhere on purpose: a monitor installed on the machine it watches cannot warn you the
day that machine goes down.

**Daily backups** of the n8n volume at 2am, an hour before the reboot window, with anything older
than 7 days deleted automatically. Without that cleanup the disk fills up and the server goes
down because of its own backups.

**The lesson of the day, in numbers: −46 lines, +1.**

The watchdog was first written as a 30-line Python script. It did exactly what this does:

```
curl -fsS --retry 3 --retry-delay 20 "$N8N_URL/healthz" | grep -q '"ok"'
```

Deleting the script also made the `actions/checkout` step redundant — there was no longer a file
to check out. Removing code removed a whole dependency.

**And the alarm was tested both ways.** Green against the real URL, and **red** against a path
that doesn't exist. An alarm you have never seen fire is an assumption, not a warning.

**What is still weak**, stated plainly:

- The backup lives on the same disk it protects. It covers human error and a bad upgrade; it does
  not cover that disk dying.
- No backup has been restored yet. Until one is, it's an assumption.

**Next:** move backups off the server, restore one as a drill, and automate the `git pull` with
GitHub Actions.

---

## What this is not

A lab in progress, not a finished template. There are no automated backups yet, no
monitoring, and no automated deploys. That is the order they are coming in.

## A note on secrets

This repository is public. The private SSH key, `.env` files and passwords never go in here.
`.gitignore` blocks them.
