from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import urllib.request
import json
import threading
import time
import re

app = Flask(__name__)
CORS(app)

DISPLAY_ALIGN_FILE = '/home/pi/.kiosk_display_align.json'


def pick_lan_ip():
    """Real LAN IP of the default-route interface (never the Docker bridge or
    the Tailscale CGNAT address). Falls back to filtering `hostname -I`."""
    try:
        out = subprocess.run(['ip', '-4', 'route', 'get', '1.1.1.1'],
                             capture_output=True, text=True, timeout=5).stdout
        m = re.search(r'src (\d+\.\d+\.\d+\.\d+)', out)
        if m:
            return m.group(1)
    except Exception:
        pass
    for a in subprocess.run(['hostname', '-I'], capture_output=True,
                            text=True).stdout.split():
        if ':' in a:                       # skip IPv6
            continue
        # skip loopback, link-local, Docker bridges (172.17/172.18)
        if a.startswith(('127.', '169.254.', '172.17.', '172.18.')):
            continue
        return a
    return 'unknown'


def net_status():
    """Return (ssid, net_type): active WiFi SSID, and 'wifi'/'ethernet'/'none'."""
    ssid = ''
    try:
        wifi = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                              capture_output=True, text=True, timeout=10)
        for line in wifi.stdout.split('\n'):
            if line.startswith('yes:'):
                ssid = line.split(':', 1)[1]
                break
    except Exception:
        pass
    if ssid:
        return ssid, 'wifi'
    # No WiFi — is a wired link up?
    try:
        dev = subprocess.run(['nmcli', '-t', '-f', 'TYPE,STATE', 'device', 'status'],
                             capture_output=True, text=True, timeout=10)
        for line in dev.stdout.split('\n'):
            parts = line.split(':')
            if len(parts) >= 2 and parts[0] == 'ethernet' and parts[1] == 'connected':
                return '', 'ethernet'
    except Exception:
        pass
    return '', 'none'

@app.route('/wifi/scan')
def wifi_scan():
    try:
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
            capture_output=True, text=True, timeout=15
        )
        networks = []
        seen = set()
        for line in result.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 2:
                ssid = parts[0].strip()
                signal = parts[1].strip() if len(parts) > 1 else '0'
                security = parts[2].strip() if len(parts) > 2 else ''
                if ssid and ssid not in seen:
                    seen.add(ssid)
                    networks.append({'ssid': ssid, 'signal': signal, 'security': security})
        networks.sort(key=lambda x: int(x['signal']) if x['signal'].isdigit() else 0, reverse=True)
        return jsonify({'networks': networks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/wifi/connect', methods=['POST'])
def wifi_connect():
    data = request.json
    ssid = data.get('ssid', '').strip()
    password = data.get('password', '').strip()
    try:
        # Clear any stale/half-configured profile for this SSID so we start clean
        # (a previous failed attempt can leave a profile missing key-mgmt).
        subprocess.run(['sudo', 'nmcli', 'connection', 'delete', ssid],
                       capture_output=True, text=True)
        if password:
            # Build the profile explicitly with wifi-sec.key-mgmt=wpa-psk — the
            # `nmcli device wifi connect` shorthand can't set security properties,
            # which is what caused "802-11-wireless-security.key-mgmt is missing".
            add = subprocess.run(
                ['sudo', 'nmcli', 'connection', 'add', 'type', 'wifi',
                 'con-name', ssid, 'ifname', 'wlan0', 'ssid', ssid,
                 'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password],
                capture_output=True, text=True, timeout=30)
            if add.returncode != 0:
                return jsonify({'success': False, 'error': add.stderr.strip()})
            result = subprocess.run(['sudo', 'nmcli', 'connection', 'up', ssid],
                                    capture_output=True, text=True, timeout=30)
        else:
            # Open network — the shorthand is fine and sets key-mgmt=none itself.
            result = subprocess.run(
                ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid],
                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': result.stderr.strip()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/system/status')
def system_status():
    try:
        ssid, net_type = net_status()
        return jsonify({'ssid': ssid, 'net_type': net_type, 'ip': pick_lan_ip()})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/opensky')
def opensky_proxy():
    try:
        lat = float(request.args.get('lat', 51.5074))
        lon = float(request.args.get('lon', -0.1278))
        r = 1.5
        url = f'https://opensky-network.org/api/states/all?lamin={lat-r}&lomin={lon-1.3}&lamax={lat+r}&lomax={lon+1.3}'
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = json.loads(resp.read())
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/feeder/location')
def feeder_location():
    try:
        with open('/opt/adsb/config/config.json', 'r') as f:
            config = json.load(f)
        lat = config.get('FEEDER_LAT', 51.5074)
        lon = config.get('FEEDER_LONG', -0.1278)
        if isinstance(lat, list): lat = lat[0] if lat else 51.5074
        if isinstance(lon, list): lon = lon[0] if lon else -0.1278
        return jsonify({'lat': float(lat), 'lon': float(lon)})
    except Exception as e:
        return jsonify({'lat': 51.5074, 'lon': -0.1278})

@app.route('/system/reset', methods=['POST'])
def system_reset():
    try:
        def do_reset():
            time.sleep(2)
            subprocess.run(['sudo', 'bash', '/opt/adsb/factory-reset-DANGER.sh'], capture_output=True)
        threading.Thread(target=do_reset).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/system/reboot', methods=['POST'])
def system_reboot():
    try:
        def do_reboot():
            time.sleep(2)
            subprocess.run(['sudo', 'reboot'], capture_output=True)
        threading.Thread(target=do_reboot).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})




@app.route('/system/shutdown', methods=['POST'])
def system_shutdown():
    try:
        def do_shutdown():
            time.sleep(2)
            subprocess.run(['sudo', 'shutdown', '-h', 'now'], capture_output=True)
        threading.Thread(target=do_shutdown).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/system/display-align', methods=['GET'])
def get_display_align():
    try:
        with open(DISPLAY_ALIGN_FILE) as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({'x': 0, 'y': 0})

@app.route('/system/display-align', methods=['POST'])
def set_display_align():
    try:
        data = request.json or {}
        x = int(data.get('x', 0))
        y = int(data.get('y', 0))
        with open(DISPLAY_ALIGN_FILE, 'w') as f:
            json.dump({'x': x, 'y': y}, f)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/system/sdr-status')
def sdr_status():
    detected = False
    feeder_running = False
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        detected = '0bda:2838' in result.stdout
    except Exception:
        pass
    try:
        result = subprocess.run(
            ['sudo', 'docker', 'ps', '--filter', 'name=ultrafeeder', '--filter', 'status=running', '--format', '{{.Names}}'],
            capture_output=True, text=True, timeout=5)
        feeder_running = 'ultrafeeder' in result.stdout
    except Exception:
        pass
    return jsonify({'detected': detected, 'feeder_running': feeder_running})

@app.route('/system/restart-feeder', methods=['POST'])
def restart_feeder():
    try:
        def do_restart():
            time.sleep(1)
            subprocess.run(['sudo', 'docker', 'restart', 'ultrafeeder'], capture_output=True)
        threading.Thread(target=do_restart).start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
