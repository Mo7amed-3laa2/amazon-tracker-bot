# Deploy Amazon Tracker Bot on AWS EC2 (Ubuntu)

This bot runs as a long-running polling process, so deployment on EC2 is best done with `systemd`.

## 1) Launch EC2

- AMI: Ubuntu 22.04 LTS
- Instance type: `t3.micro` (enough for this bot)
- Storage: 8 GB+ is enough
- Security Group:
  - Inbound: SSH (22) from your IP only
  - No other inbound ports are needed for this polling bot
- IAM role: optional (not required for current code)

### Optional: Fully automatic first boot with User Data

You can provision everything on first startup using:

- `deploy/ec2_user_data.sh`

Steps:

1. Open `deploy/ec2_user_data.sh` and update:
  - `REPO_URL`
  - `BRANCH`
  - `TELEGRAM_TOKEN`
  - `CHAT_ID`
  - `CHECK_INTERVAL_MINUTES`
2. In AWS EC2 launch wizard, expand **Advanced details**.
3. Paste the full script into **User data**.
4. Launch the instance.
5. Verify provisioning:

```bash
sudo cat /var/log/user-data.log
sudo systemctl status amazon-tracker-bot
sudo journalctl -u amazon-tracker-bot -f
```

If User Data is used, you can skip the manual setup steps below.

## 2) Connect to EC2

```bash
ssh -i /path/to/key.pem ubuntu@<EC2_PUBLIC_IP>
```

## 3) Run the setup script

Use your repository URL:

```bash
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/<your-org-or-user>/<your-repo>/<branch>/deploy/ec2_setup.sh)" -- https://github.com/<your-org-or-user>/<your-repo>.git
```

If you are not using GitHub raw URL, clone manually then run local script:

```bash
git clone https://github.com/<your-org-or-user>/<your-repo>.git /opt/amazon-tracker-bot
cd /opt/amazon-tracker-bot
sudo bash deploy/ec2_setup.sh https://github.com/<your-org-or-user>/<your-repo>.git
```

## 4) Configure environment

Edit env file:

```bash
sudo nano /opt/amazon-tracker-bot/.env
```

Required values:

- `TELEGRAM_TOKEN`: bot token from BotFather
- `CHAT_ID`: your Telegram chat id (or group id)
- `CHECK_INTERVAL_MINUTES`: e.g. `60`

## 5) Start and verify service

```bash
sudo systemctl restart amazon-tracker-bot
sudo systemctl status amazon-tracker-bot
sudo journalctl -u amazon-tracker-bot -f
```

## 6) Update bot after code changes

```bash
cd /opt/amazon-tracker-bot
sudo -u ubuntu git pull
sudo -u ubuntu /opt/amazon-tracker-bot/.venv/bin/pip install -r requirements.txt
sudo systemctl restart amazon-tracker-bot
```

## Troubleshooting

- Service fails immediately:
  - Check env variables in `/opt/amazon-tracker-bot/.env`
  - Read logs: `sudo journalctl -u amazon-tracker-bot -n 100 --no-pager`
- Telegram polling conflict:
  - Make sure bot runs in one place only (EC2 only, stop local copy)
- SQLite DB location:
  - Stored at `/opt/amazon-tracker-bot/tracker.db`
  - Back it up before redeploying server
