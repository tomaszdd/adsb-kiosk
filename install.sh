#!/bin/bash
set -e
echo "=== ADS-B Kiosk Installer ==="
echo "[1/8] Updating packages..."
sudo apt update -y
echo "[2/8] Installing dependencies..."
sudo apt install --no-install-recommends -y xserver-xorg x11-xserver-utils xinit openbox chromium xserver-xorg-video-fbturbo git python3-flask python3-flask-cors docker.io docker-compose fbset
echo "[3/8] Configuring TFT display..."
if ! grep -q "waveshare35b-v2" /boot/firmware/config.txt; then
sudo tee -a /boot/firmware/config.txt << 'BOOTEOF'
dtparam=spi=on
display_auto_detect=0
dtoverlay=waveshare35b-v2
BOOTEOF
fi
sudo tee /etc/X11/xorg.conf << 'XEOF'
Section "Device"
    Identifier "TFT"
    Driver "fbturbo"
    Option "fbdev" "/dev/fb1"
    Option "SwapbuffersWait" "false"
EndSection
XEOF
echo "[4/8] Configuring autologin..."
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d/
sudo tee /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'ALOEOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
ALOEOF
echo "[5/8] Setting up kiosk autostart..."
tee ~/.bash_profile << 'BPEOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  rm -rf /tmp/chromium
  exec startx /usr/bin/chromium --noerrdialogs --disable-infobars --kiosk --no-sandbox --user-data-dir=/tmp/chromium file:///home/pi/kiosk.html
fi
BPEOF
echo "[6/8] Copying kiosk files..."
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cp "$SCRIPT_DIR/kiosk.html" /home/pi/kiosk.html
mkdir -p /home/pi/setup-app
cp "$SCRIPT_DIR/setup-app/app.py" /home/pi/setup-app/app.py
echo "[7/8] Installing kiosk backend service..."
sudo cp "$SCRIPT_DIR/systemd/kiosk-backend.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kiosk-backend
echo "[8/8] Installing ADS-B feeder..."
curl -sSL https://raw.githubusercontent.com/dirkhh/adsb-feeder-image/main/src/tools/app-install.sh | sudo bash
echo "=== Done! ==="
echo "Run: sudo tailscale up"
echo "Then: sudo reboot"
