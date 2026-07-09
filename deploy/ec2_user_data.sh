#!/bin/bash
set -euo pipefail

# All output goes to /var/log/user-data.log and console for easier debugging.
exec > >(tee /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1

APP_DIR="/opt/amazon-tracker-bot"
APP_USER="ubuntu"
SERVICE_NAME="amazon-tracker-bot"
REPO_URL="https://github.com/<your-org-or-user>/<your-repo>.git"
BRANCH="main"

# Fill these before launching the instance, or use Secrets Manager/SSM retrieval.
TELEGRAM_TOKEN="<put-telegram-token-here>"
CHAT_ID="<put-chat-id-here>"
CHECK_INTERVAL_MINUTES="60"

# Wait until cloud-init networking is ready.
until ping -c1 8.8.8.8 >/dev/null 2>&1; do
  sleep 2
done

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git ca-certificates

# Create app directory and clone/update repository.
mkdir -p "${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

if [ ! -d "${APP_DIR}/.git" ]; then
  sudo -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  sudo -u "${APP_USER}" bash -lc "cd ${APP_DIR} && git checkout ${BRANCH} && git pull --ff-only origin ${BRANCH}"
fi

# Python virtual environment and dependencies.
sudo -u "${APP_USER}" bash -lc "cd ${APP_DIR} && python3 -m venv .venv"
sudo -u "${APP_USER}" bash -lc "cd ${APP_DIR} && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"

# Environment file used by systemd service.
cat > "${APP_DIR}/.env" <<EOF
TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
CHAT_ID=${CHAT_ID}
CHECK_INTERVAL_MINUTES=${CHECK_INTERVAL_MINUTES}
EOF

chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

# Install and enable systemd service.
cp "${APP_DIR}/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo "User Data provisioning completed successfully."
