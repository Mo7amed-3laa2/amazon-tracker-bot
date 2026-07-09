#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/amazon-tracker-bot"
SERVICE_NAME="amazon-tracker-bot"
REPO_URL="${1:-}"

if [ "${EUID}" -ne 0 ]; then
  echo "Please run as root (sudo)."
  exit 1
fi

if ! id ubuntu >/dev/null 2>&1; then
  echo "Expected ubuntu user not found. This script targets Ubuntu EC2 instances."
  exit 1
fi

if [ -z "${REPO_URL}" ]; then
  echo "Usage: sudo bash deploy/ec2_setup.sh <git_repo_url>"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip git

if [ ! -d "${APP_DIR}/.git" ]; then
  rm -rf "${APP_DIR}"
  git clone "${REPO_URL}" "${APP_DIR}"
fi

chown -R ubuntu:ubuntu "${APP_DIR}"

sudo -u ubuntu bash -lc "cd ${APP_DIR} && python3 -m venv .venv"
sudo -u ubuntu bash -lc "cd ${APP_DIR} && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt"

if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  chown ubuntu:ubuntu "${APP_DIR}/.env"
  chmod 600 "${APP_DIR}/.env"
  echo "Created ${APP_DIR}/.env from .env.example"
  echo "Edit it before starting the service."
fi

cp "${APP_DIR}/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"

echo "Setup finished."
echo "Next steps:"
echo "1) Edit ${APP_DIR}/.env"
echo "2) systemctl restart ${SERVICE_NAME}"
echo "3) systemctl status ${SERVICE_NAME}"
