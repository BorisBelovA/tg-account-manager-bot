# Deploying to a Linux server

The bot uses **long polling**, so it needs no domain, open port, or TLS —
only outbound HTTPS to `api.telegram.org`.

Target layout: `/opt/expense-bot` with `data/` on persistent disk and `.env`
holding the token.

## 1. Prepare the server

Ubuntu/Debian assumed.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git sqlite3

# Docker (recommended path)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"   # log out and back in

# Only SSH needs to be reachable
sudo ufw allow OpenSSH
sudo ufw enable
```

## 2. Get the code onto the server

### Option A — copy from your PC

From the project root on your PC (forward slashes work in PowerShell,
Git Bash and WSL):

```bash
scp -r ./bot ./requirements.txt ./pyproject.toml \
       ./Dockerfile ./docker-compose.yml ./.dockerignore ./deploy \
       you@server:/opt/expense-bot/
```

> Do **not** copy `.env`, `.venv/`, `data/` or `backups/`.

Or make a tarball that excludes them:

```bash
tar -czf expense-bot.tar.gz \
    --exclude=.venv --exclude=data --exclude=backups \
    --exclude=__pycache__ --exclude=.env \
    bot requirements.txt pyproject.toml Dockerfile docker-compose.yml .dockerignore deploy
scp expense-bot.tar.gz you@server:/tmp/
# on the server:
sudo mkdir -p /opt/expense-bot
sudo tar -xzf /tmp/expense-bot.tar.gz -C /opt/expense-bot
```

### Option B — private git repo

```bash
sudo mkdir -p /opt/expense-bot && sudo chown "$USER":"$USER" /opt/expense-bot
git clone git@github.com:you/tg-expense-bot.git /opt/expense-bot
```

## 3. Create `.env` on the server

```bash
cd /opt/expense-bot
nano .env
```

```env
BOT_TOKEN=8123456789:AAH...
DATABASE_URL=sqlite:///data/bot.db
LOG_LEVEL=INFO
REPORT_TZ=Europe/Nicosia
```

```bash
chmod 600 .env
```

## 4. Run

### Docker (recommended)

```bash
cd /opt/expense-bot
mkdir -p data backups
sudo chown -R 1000:1000 data backups   # matches appuser in the image
docker compose up -d --build
docker compose logs -f
```

`Ctrl+C` stops following logs; the container keeps running.
On reboot Docker restarts it because of `restart: unless-stopped`.

### systemd + venv (no Docker)

```bash
sudo apt install -y python3 python3-venv python3-pip
cd /opt/expense-bot
sudo chown -R expensebot:expensebot /opt/expense-bot
sudo -u expensebot python3 -m venv .venv
sudo -u expensebot .venv/bin/pip install -r requirements.txt

sudo cp deploy/expensebot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now expensebot
sudo journalctl -u expensebot -f
```

## 5. Backups

```bash
chmod +x deploy/backup.sh
# nightly at 03:30
( crontab -l 2>/dev/null; echo "30 3 * * * bash /opt/expense-bot/deploy/backup.sh" ) | crontab -
```

Backups land in `/opt/expense-bot/backups` and older than 14 days are pruned.
For off-site copies use Litestream or `rclone` to S3/B2/R2.

## 6. Update

```bash
cd /opt/expense-bot
git pull                                  # or re-copy the files
docker compose up -d --build              # Docker
sudo systemctl restart expensebot         # systemd
```

## 7. Notes

- **Timezone:** the container sets `TZ=Europe/Nicosia` and installs `tzdata`.
  Without it `/history` shows UTC times on most VPSes.
- **Secrets:** `.env` is git-ignored and excluded from the image; pass it only
  at runtime via `env_file`.
- **No inbound ports:** do not expose the bot; it makes outbound connections only.
- **SSH:** prefer key-only auth (`PasswordAuthentication no`) and
  `unattended-upgrades` for patches.
