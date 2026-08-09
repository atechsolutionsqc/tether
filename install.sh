#!/usr/bin/env bash
#
# Tether bare-metal installer.
# Creates a Python virtual environment, installs dependencies, and (optionally)
# registers a systemd service so Tether starts on boot.
#
# Usage:
#   ./install.sh            # set up venv + deps, print run instructions
#   sudo ./install.sh --service   # also install a systemd service
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8000}"

echo "==> Tether install"
echo "    Directory: $APP_DIR"

# 1. Python check
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN not found. Install Python 3.10+ and retry." >&2
  exit 1
fi

# 2. Virtual environment
echo "==> Creating virtual environment"
"$PYTHON_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null
echo "==> Installing dependencies"
pip install -r "$APP_DIR/requirements.txt"

# 3. Data dir + secret
mkdir -p "$APP_DIR/data"
if [ ! -f "$APP_DIR/.env" ]; then
  echo "==> Creating .env (edit it to set a real secret + admin password)"
  SECRET="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(32))')"
  sed "s/please-change-this-to-a-long-random-string/$SECRET/" "$APP_DIR/.env.example" > "$APP_DIR/.env"
fi

# 4. Optional systemd service
if [ "${1:-}" == "--service" ]; then
  if [ "$EUID" -ne 0 ]; then
    echo "ERROR: --service requires root (use sudo)." >&2
    exit 1
  fi
  SERVICE_USER="${SUDO_USER:-root}"
  echo "==> Installing systemd service (user: $SERVICE_USER)"
  cat > /etc/systemd/system/tether.service <<EOF
[Unit]
Description=Tether IT Asset Management
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/.env
Environment=TETHER_DATA=$APP_DIR/data
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 0.0.0.0 --port $PORT
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now tether
  echo "==> Service started. Check status with: systemctl status tether"
  echo "==> Tether is running on http://localhost:$PORT"
  exit 0
fi

cat <<EOF

==> MariaDB setup (recommended)
If you want to use MariaDB instead of the built-in SQLite:

  sudo apt install -y mariadb-server
  sudo mysql -e "CREATE DATABASE tether CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
  sudo mysql -e "CREATE USER 'tether'@'localhost' IDENTIFIED BY 'yourpassword';"
  sudo mysql -e "GRANT ALL PRIVILEGES ON tether.* TO 'tether'@'localhost'; FLUSH PRIVILEGES;"

Then set these in your .env:
  DB_HOST=localhost
  DB_USER=tether
  DB_PASSWORD=yourpassword
  DB_NAME=tether

Or just leave DB_HOST unset to use SQLite (zero setup required).

==> Done!

To start Tether:

  source "$VENV_DIR/bin/activate"
  cd "$APP_DIR/backend"
  export \$(grep -v '^#' "$APP_DIR/.env" | xargs)
  export TETHER_DATA="$APP_DIR/data"
  uvicorn main:app --host 0.0.0.0 --port $PORT

Then open http://localhost:$PORT  (default login: admin / admin)

To install as a system service that starts on boot, run:
  sudo ./install.sh --service
EOF
