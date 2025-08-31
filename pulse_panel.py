# Pulse Panel - A Python Game Server Management Dashboard
# Version 3.0: Phoenix Update (SteamCMD Auto-Install & UI Overhaul)

import os
import subprocess
import threading
import json
import time
import sys
import webview
import psutil
import requests # New: For downloading files
import zipfile  # New: For unpacking zip files
import io       # New: For handling in-memory zip data
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO

# --- Configuration Files ---
CONFIG_FILE = 'config.json'
SERVERS_FILE = 'servers.json'
GAMES_FILE = 'games.json'

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'phoenix-secret-key-change-this'
socketio = SocketIO(app, async_mode='threading')

# --- Globals for Server Management ---
server_processes = {}
steam_process = None

# --- Initial Setup & Config Management ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {"steamcmd_path": ""} # Start with empty path
        with open(CONFIG_FILE, 'w') as f: json.dump(default_config, f, indent=2)
        return default_config
    try:
        with open(CONFIG_FILE, 'r') as f: return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError): return {"steamcmd_path": ""}

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f: json.dump(config_data, f, indent=2)
    socketio.emit('config_updated', config_data)

def first_time_setup():
    load_config()
    if not os.path.exists(SERVERS_FILE):
        with open(SERVERS_FILE, 'w') as f: json.dump([], f)
    if not os.path.exists(GAMES_FILE):
        # Expanded list of games for a better out-of-the-box experience
        default_games = [
            {"id": "ark_se", "name": "ARK: Survival Evolved", "appid": "376030"},
            {"id": "valheim", "name": "Valheim", "appid": "896660"},
            {"id": "csgo", "name": "Counter-Strike: GO", "appid": "740"},
            {"id": "zomboid", "name": "Project Zomboid", "appid": "380870"},
            {"id": "sevendays", "name": "7 Days to Die", "appid": "294420"},
            {"id": "rust", "name": "Rust", "appid": "258550"},
            {"id": "terraria", "name": "Terraria", "appid": "105600"},
            {"id": "arma3", "name": "Arma 3", "appid": "233780"},
            {"id": "satisfactory", "name": "Satisfactory", "appid": "1690800"},
            {"id": "factorio", "name": "Factorio", "appid": "427520"},
        ]
        with open(GAMES_FILE, 'w') as f: json.dump(default_games, f, indent=2)

def load_json_file(file_path):
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, FileNotFoundError): return []

def save_servers(servers_data):
    with open(SERVERS_FILE, 'w') as f: json.dump(servers_data, f, indent=2)

def get_server_config(server_id):
    for server in load_json_file(SERVERS_FILE):
        if server['id'] == server_id: return server
    return None

def read_stream(stream, server_id):
    while True:
        line = stream.readline()
        if not line: break
        socketio.emit('console_output', {'id': server_id, 'data': line})

def read_installer_stream(stream):
    global steam_process
    while True:
        line = stream.readline()
        if not line: break
        socketio.emit('installer_output', {'data': line})
    if steam_process and steam_process.poll() is not None:
        if not steam_process.stdout.peek() and not steam_process.stderr.peek():
            steam_process = None
            socketio.emit('installer_output', {'data': '''
--- Installation Process Finished! ---
'''})

# --- Background Monitoring ---
def monitor_servers():
    while True:
        for server_id, data in list(server_processes.items()):
            try:
                process = data['process']
                p = psutil.Process(process.pid)
                if process.poll() is None and p.is_running():
                    status, cpu, mem = 'online', p.cpu_percent(interval=0.1), p.memory_info().rss / (1024 * 1024)
                else:
                    raise psutil.NoSuchProcess(process.pid)
            except psutil.NoSuchProcess:
                status, cpu, mem = 'offline', 0, 0
                if server_id in server_processes: del server_processes[server_id]
                socketio.emit('console_output', {'id': server_id, 'data': '''
--- Server Stopped Unexpectedly ---
'''})
            socketio.emit('status_update', {'id': server_id, 'status': status, 'cpu': f"{cpu:.2f}", 'mem': f"{mem:.2f}"})
        all_ids = [s['id'] for s in load_json_file(SERVERS_FILE)]
        running_ids = list(server_processes.keys())
        for server_id in all_ids:
            if server_id not in running_ids:
                socketio.emit('status_update', {'id': server_id, 'status': 'offline', 'cpu': '0.00', 'mem': '0.00'})
        socketio.sleep(3)

# --- Flask Routes ---
@app.route('/')
def index():
    with open('dashboard.html', 'r', encoding='utf-8') as f: html_content = f.read()
    return render_template_string(
        html_content,
        servers=load_json_file(SERVERS_FILE),
        games=load_json_file(GAMES_FILE),
        config=load_config()
    )

# --- Socket.IO Events ---
@socketio.on('save_settings')
def handle_save_settings(data):
    save_config({'steamcmd_path': data.get('steamcmd_path', '')})

@socketio.on('download_steamcmd')
def handle_download_steamcmd(data):
    """New: Downloads and extracts SteamCMD."""
    install_path = data.get('path')
    steamcmd_zip_url = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip'

    if not install_path or not os.path.isdir(install_path):
        socketio.emit('installer_output', {'data': f"""--- ERROR: Invalid folder path provided: '{install_path}' ---
"""})
        return

    try:
        socketio.emit('installer_output', {'data': f"""--- Starting download from {steamcmd_zip_url} ---
"""})
        response = requests.get(steamcmd_zip_url, stream=True)
        response.raise_for_status()

        socketio.emit('installer_output', {'data': """--- Download complete. Extracting... ---
"""})
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall(install_path)
        
        final_exe_path = os.path.join(install_path, 'steamcmd.exe')
        if os.path.exists(final_exe_path):
            socketio.emit('installer_output', {'data': f"""--- Successfully extracted steamcmd.exe to {final_exe_path} ---
"""})
            save_config({'steamcmd_path': final_exe_path})
        else:
            socketio.emit('installer_output', {'data': '''--- ERROR: steamcmd.exe not found after extraction. ---
'''})
            
    except requests.RequestException as e:
        socketio.emit('installer_output', {'data': f"""--- ERROR: Failed to download SteamCMD. Check connection. Details: {e} ---
"""})
    except zipfile.BadZipFile:
        socketio.emit('installer_output', {'data': '''--- ERROR: Downloaded file is not a valid zip file. ---
'''})
    except Exception as e:
        socketio.emit('installer_output', {'data': f"""--- An unexpected error occurred: {e} ---
"""})


@socketio.on('install_server')
def handle_install_server(data):
    # This function is now more robust.
    global steam_process
    game_id, server_name, install_path = data.get('game_id'), data.get('server_name'), data.get('install_path')

    if not all([game_id, server_name, install_path]):
        socketio.emit('installer_output', {'data': '''--- ERROR: All fields are required. ---
'''})
        return
    if steam_process and steam_process.poll() is None:
        socketio.emit('installer_output', {'data': '''--- An installation is already in progress. ---
'''})
        return

    config = load_config()
    steamcmd_path = config.get('steamcmd_path')
    if not steamcmd_path or not os.path.exists(steamcmd_path):
        socketio.emit('installer_output', {'data': f"""--- ERROR: SteamCMD path is invalid. Please set it in Settings. Path: '{steamcmd_path}' ---
"""})
        return

    game_config = next((g for g in load_json_file(GAMES_FILE) if g['id'] == game_id), None)
    if not game_config:
        socketio.emit('installer_output', {'data': f"""--- ERROR: Game config '{game_id}' not found. ---
"""})
        return

    try:
        if not os.path.exists(install_path): os.makedirs(install_path)
    except Exception as e:
        socketio.emit('installer_output', {'data': f"""--- ERROR: Could not create directory '{install_path}'. Check permissions. Details: {e} ---
"""})
        return

    appid = game_config['appid']
    steam_command = [steamcmd_path, '+force_install_dir', os.path.abspath(install_path), '+login', 'anonymous', '+app_update', appid, 'validate', '+quit']
    
    try:
        socketio.emit('installer_output', {'data': f'''--- Starting SteamCMD for {game_config["name"]} (AppID: {appid}) ---
'''})
        steam_process = subprocess.Popen(steam_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        threading.Thread(target=read_installer_stream, args=(steam_process.stdout,), daemon=True).start()
        threading.Thread(target=read_installer_stream, args=(steam_process.stderr,), daemon=True).start()

        new_server_id = f"{game_id}_{int(time.time())}"
        servers = load_json_file(SERVERS_FILE)
        new_config = {"id": new_server_id, "name": f"{game_config['name']} - {server_name}", "start_command": "echo 'Please edit start command in servers.json'", "cwd": os.path.abspath(install_path)}
        servers.append(new_config)
        save_servers(servers)
        socketio.emit('server_added', new_config)

    except Exception as e:
        socketio.emit('installer_output', {'data': f'''
--- FATAL ERROR starting SteamCMD: {e} ---
'''})

# All other handlers (start, stop, send_command) remain the same as before...
@socketio.on('start_server')
def handle_start_server(data):
    server_id = data.get('id')
    if server_id in server_processes and server_processes[server_id]['process'].poll() is None: return
    config = get_server_config(server_id)
    if not config: return
    try:
        socketio.emit('console_output', {'id': server_id, 'data': f'''--- Starting server: {config["name"]} ---
'''})
        process = subprocess.Popen(
            config['start_command'], cwd=config['cwd'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
            shell=True, text=True, encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        server_processes[server_id] = {'process': process}
        threading.Thread(target=read_stream, args=(process.stdout, server_id), daemon=True).start()
        threading.Thread(target=read_stream, args=(process.stderr, server_id), daemon=True).start()
    except Exception as e:
        socketio.emit('console_output', {'id': server_id, 'data': f'''
--- FATAL ERROR starting server: {e} ---
Check CWD path and command in servers.json!
'''})

@socketio.on('stop_server')
def handle_stop_server(data):
    server_id = data.get('id')
    if server_id in server_processes:
        process = server_processes[server_id]['process']
        socketio.emit('console_output', {'id': server_id, 'data': '''
--- Sending stop command... ---
'''})
        try:
            if sys.platform == 'win32': process.send_signal(subprocess.CTRL_C_EVENT)
            else: process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            socketio.emit('console_output', {'id': server_id, 'data': '''
--- Server unresponsive, forcing termination... ---
'''})
            process.kill()
        if server_id in server_processes: del server_processes[server_id]

@socketio.on('send_command')
def handle_send_command(data):
    server_id, command = data.get('id'), data.get('command')
    if server_id in server_processes and command and server_processes[server_id]['process'].poll() is None:
        try:
            server_processes[server_id]['process'].stdin.write(command + '\n')
            server_processes[server_id]['process'].stdin.flush()
        except Exception as e:
            socketio.emit('console_output', {'id': server_id, 'data': f'''
--- Error sending command: {e} ---
'''})

# --- Main Application Start ---
def run_server():
    socketio.run(app, host='127.0.0.1', port=5000, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    print("Starting Pulse Panel...")
    first_time_setup()
    threading.Thread(target=monitor_servers, daemon=True).start()
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1)
    print("Opening Pulse Panel window...")
    webview.create_window('Pulse Panel', 'http://127.0.0.1:5000', width=1440, height=900, resizable=True, min_size=(1100, 700))
    webview.start(debug=True)
