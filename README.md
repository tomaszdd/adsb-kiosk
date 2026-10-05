# ADS-B Kiosk

Plug-and-play ADS-B flight tracking kiosk on Raspberry Pi 3B+ with Waveshare 3.5" TFT.

## Hardware
- Raspberry Pi 3B+
- Waveshare 3.5" RPi LCD (B) Rev2.0
- RTL-SDR Blog V3 dongle
- 40-pin GPIO stacking header

## Quick Install
git clone https://github.com/tomaszdd/adsb-kiosk.git
cd adsb-kiosk
bash install.sh
sudo tailscale up
sudo reboot

## Post-Install
1. Open http://[PI-IP]:1099 in a browser
2. Enter antenna location and timezone
3. Enable FlightRadar24 and paste sharing key
4. Plug in RTL-SDR dongle

## Remote Access
ssh pi@[TAILSCALE-IP]
