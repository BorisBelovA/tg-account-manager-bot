#!/usr/bin/env bash
# Safe SQLite backup while the bot is running.
# Usage:  bash deploy/backup.sh
# Cron:   30 3 * * * bash /opt/expense-bot/deploy/backup.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/expense-bot}"
DB="${DB:-$APP_DIR/data/bot.db}"
DEST="${DEST:-$APP_DIR/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$DEST"
stamp="$(date +%F_%H%M%S)"

if [ ! -f "$DB" ]; then
  echo "database not found: $DB" >&2
  exit 1
fi

sqlite3 "$DB" ".backup '$DEST/bot-$stamp.db'"
find "$DEST" -type f -name 'bot-*.db' -mtime +"$KEEP_DAYS" -delete

echo "backup written: $DEST/bot-$stamp.db"
