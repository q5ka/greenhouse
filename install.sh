#!/usr/bin/env bash
set -e

echo "========================================"
echo "  Greenhouse Controller Installation"
echo "  Ubuntu 24.04"
echo "========================================"

# -------------------------------
# 1. System dependencies
# -------------------------------
echo "[1/8] Installing system dependencies..."
sudo apt update
sudo apt install -y \
    python3 python3-venv python3-dev \
    build-essential \
    libatlas-base-dev \
    libjpeg-dev libpng-dev \
    libavcodec-dev libavformat-dev libswscale-dev \
    libqt5gui5 libqt5webkit5 libqt5test5 \
    ffmpeg \
    curl wget git

# -------------------------------
# 2. Create project directory
# -------------------------------
echo "[2/8] Creating /opt/greenhouse..."
sudo mkdir -p /opt/greenhouse
sudo chown -R $USER:$USER /opt/greenhouse

# -------------------------------
# 3. Create virtual environment
# -------------------------------
echo "[3/8] Creating Python virtual environment..."
cd /opt/greenhouse
python3 -m venv venv
source venv/bin/activate

# -------------------------------
# 4. Install Python packages
# -------------------------------
echo "[4/8] Installing Python packages..."
pip install --upgrade pip
pip install fastapi uvicorn[standard] \
    opencv-python numpy requests \
    paho-mqtt python-multipart jinja2

# -------------------------------
# 5. Create greenhouse user
# -------------------------------
echo "[5/8] Creating system user 'greenhouse'..."
if ! id "greenhouse" >/dev/null 2>&1; then
    sudo useradd -r -s /bin/false greenhouse
fi

sudo chown -R greenhouse:greenhouse /opt/greenhouse

# -------------------------------
# 6. Install systemd service
# -------------------------------
echo "[6/8] Installing greenhouse.service..."

sudo tee /etc/systemd/system/greenhouse.service >/dev/null <<EOF
[Unit]
Description=Greenhouse Automation Server
After=network.target

[Service]
Type=simple
User=greenhouse
Group=greenhouse
WorkingDirectory=/opt/greenhouse
ExecStart=/opt/greenhouse/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# -------------------------------
# 7. Install watchdog service
# -------------------------------
echo "[7/8] Installing greenhouse-watchdog.service..."

sudo tee /etc/systemd/system/greenhouse-watchdog.service >/dev/null <<EOF
[Unit]
Description=Greenhouse Watchdog Monitor
After=network.target greenhouse.service

[Service]
Type=simple
User=greenhouse
Group=greenhouse
WorkingDirectory=/opt/greenhouse
ExecStart=/opt/greenhouse/venv/bin/python /opt/greenhouse/watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# -------------------------------
# 8. Enable + start services
# -------------------------------
echo "[8/8] Enabling and starting services..."

sudo systemctl daemon-reload
sudo systemctl enable greenhouse.service
sudo systemctl enable greenhouse-watchdog.service

sudo systemctl restart greenhouse.service
sudo systemctl restart greenhouse-watchdog.service

echo "========================================"
echo " Installation Complete!"
echo "----------------------------------------"
echo " Service status:"
echo "   sudo systemctl status greenhouse"
echo "   sudo systemctl status greenhouse-watchdog"
echo ""
echo " Logs:"
echo "   sudo journalctl -u greenhouse -f"
echo "   sudo journalctl -u greenhouse-watchdog -f"
echo ""
echo " Your greenhouse controller is now running."
echo "========================================"
