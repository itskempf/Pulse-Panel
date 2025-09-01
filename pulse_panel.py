# Pulse Panel - A Python Game Server Management Dashboard
# Version 6.0: The Operator's Toolkit Update

import os
import subprocess
import threading
import json
import time
import sys
import webview
import psutil
import requests
import zipfile
import io
import shutil

from flask import Flask, render_template_string
from flask_socketio import SocketIO

# --- Configuration Files ---
CONFIG_FILE = 'config.json'
SERVERS_FILE = 'servers.json'
GAMES_FILE = 'games.json'

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'operators-toolkit-secret-key'
socketio = SocketIO(app, async_mode='threading')

# --- Globals for Server Management ---
server_processes = {}
steam_process = None

# --- Configuration & File Helpers ---
def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {"steamcmd_path": ""}
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
        default_games = [
            {"id": "ark_se", "name": "ARK: Survival Evolved", "appid": "376030"}, {"id": "valheim", "name": "Valheim", "appid": "896660"},
            {"id": "csgo", "name": "Counter-Strike: GO", "appid": "740"}, {"id": "zomboid", "name": "Project Zomboid", "appid": "380870"},
            {"id": "sevendays", "name": "7 Days to Die", "appid": "294420"}, {"id": "rust", "name": "Rust", "appid": "258550"},
            {"id": "terraria", "name": "Terraria", "appid": "105600"}, {"id": "arma3", "name": "Arma 3", "appid": "233780"},
            {"id": "satisfactory", "name": "Satisfactory", "appid": "1690800"}, {"id": "factorio", "name": "Factorio", "appid": "427520"},
            {"id": "gmod", "name": "Garry's Mod", "appid": "4020"}, {"id": "left4dead2", "name": "Left 4 Dead 2", "appid": "222860"}
        ]
        with open(GAMES_FILE, 'w') as f: json.dump(default_games, f, indent=2)

def load_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return json.loads(content) if content else []
    except (json.JSONDecodeError, FileNotFoundError): return []

def save_servers(servers_data):
    with open(SERVERS_FILE, 'w', encoding='utf-8') as f: json.dump(servers_data, f, indent=2)

def get_server_config(server_id):
    for server in load_json_file(SERVERS_FILE):
        if server['id'] == server_id: return server
    return None

def get_safe_path(server_id, relative_path=""):
    server_config = get_server_config(server_id)
    if not server_config:
        return None, "Server not found."
    base_dir = os.path.abspath(server_config['cwd'])
    safe_relative_path = os.path.normpath(relative_path).lstrip('.\\/')
    full_path = os.path.abspath(os.path.join(base_dir, safe_relative_path))
    if not full_path.startswith(base_dir):
        return None, "Access denied: Path is outside of server directory."
    return full_path, None

# --- Stream Readers & Process Handlers ---
def read_stream(stream, server_id):
    while True:
        line = stream.readline()
        if not line: break
        socketio.emit('console_output', {'id': server_id, 'data': line})

def read_installer_stream(stream, context_id):
    global steam_process
    while True:
        line = stream.readline()
        if not line: break
        socketio.emit('installer_output', {'data': line, 'context_id': context_id})
    if steam_process and steam_process.poll() is not None:
        steam_process = None
        socketio.emit('installer_output', {'data': '\n--- Process Finished! ---\n', 'context_id': context_id})

def _start_server_process(server_id, config):
    try:
        socketio.emit('console_output', {'id': server_id, 'data': f'--- Starting server: {config["name"]} ---\n'})
        process = subprocess.Popen(config['start_command'], cwd=config['cwd'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, shell=True, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0)
        server_processes[server_id] = {'process': process}
        for stream in [process.stdout, process.stderr]: threading.Thread(target=read_stream, args=(stream, server_id), daemon=True).start()
        return True
    except Exception as e:
        socketio.emit('console_output', {'id': server_id, 'data': f'\n--- FATAL ERROR: {e} ---\nCheck CWD and start command!\n'})
        return False

def _stop_server_process(server_id):
    if server_id in server_processes:
        process = server_processes[server_id]['process']
        socketio.emit('console_output', {'id': server_id, 'data': '\n--- Sending stop command... ---\n'})
        try:
            if sys.platform == 'win32': process.send_signal(subprocess.CTRL_C_EVENT)
            else: process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            socketio.emit('console_output', {'id': server_id, 'data': '\n--- Forcing termination... ---\n'}); process.kill()
        if server_id in server_processes: del server_processes[server_id]

# --- Background Monitoring ---
def monitor_servers():
    while True:
        for server_id, data in list(server_processes.items()):
            try:
                process, p = data['process'], psutil.Process(data['process'].pid)
                if process.poll() is None and p.is_running():
                    status, cpu, mem = 'online', p.cpu_percent(interval=0.1), p.memory_info().rss / (1024*1024)
                else: raise psutil.NoSuchProcess(process.pid)
            except psutil.NoSuchProcess:
                status, cpu, mem = 'offline', 0, 0
                if server_id in server_processes: del server_processes[server_id]
                socketio.emit('console_output', {'id': server_id, 'data': '\n--- Server Stopped Unexpectedly ---\n'})
            socketio.emit('status_update', {'id': server_id, 'status': status, 'cpu': f"{cpu:.2f}", 'mem': f"{mem:.2f}"})
        all_ids = [s['id'] for s in load_json_file(SERVERS_FILE)]
        running_ids = list(server_processes.keys())
        for server_id in all_ids:
            if server_id not in running_ids:
                socketio.emit('status_update', {'id': server_id, 'status': 'offline', 'cpu': '0.00', 'mem': '0.00'})
        socketio.sleep(3)

# --- Flask Route ---
@app.route('/')
def index():
    with open('dashboard.html', 'r', encoding='utf-8') as f: html_content = f.read()
    return render_template_string(html_content, servers=load_json_file(SERVERS_FILE), games=load_json_file(GAMES_FILE), config=load_config())

# --- Socket.IO Handlers ---
@socketio.on('save_settings')
def handle_save_settings(data):
    save_config({'steamcmd_path': data.get('steamcmd_path', '')})
    socketio.emit('notification', {'status': 'success', 'message': 'Settings saved!'})

@socketio.on('download_steamcmd')
def handle_download_steamcmd(data):
    # ... (code is unchanged from previous stable version)
    install_path, url, context_id = data.get('path'), '[https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip](https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip)', "settings_installer"
    if not install_path or not os.path.isdir(install_path):
        socketio.emit('installer_output', {'data': f"--- ERROR: Invalid folder path: '{install_path}' ---\n", 'context_id': context_id}); return
    try:
        socketio.emit('installer_output', {'data': f"--- Starting download... ---\n", 'context_id': context_id})
        r = requests.get(url, stream=True); r.raise_for_status()
        socketio.emit('installer_output', {'data': "--- Download complete. Extracting... ---\n", 'context_id': context_id})
        with zipfile.ZipFile(io.BytesIO(r.content)) as z: z.extractall(install_path)
        final_path = os.path.join(install_path, 'steamcmd.exe')
        if os.path.exists(final_path):
            socketio.emit('installer_output', {'data': f"--- Success! Extracted to {final_path} ---\n", 'context_id': context_id})
            save_config({'steamcmd_path': final_path})
            socketio.emit('notification', {'status': 'success', 'message': 'SteamCMD installed and configured!'})
        else: socketio.emit('installer_output', {'data': "--- ERROR: steamcmd.exe not found. ---\n", 'context_id': context_id})
    except Exception as e: socketio.emit('installer_output', {'data': f"--- Error: {e} ---\n", 'context_id': context_id})

@socketio.on('install_server')
def handle_install_server(data):
    # ... (code is unchanged from previous stable version)
    context_id = "main_installer"
    global steam_process
    game_id, name, path = data.get('game_id'), data.get('server_name'), data.get('install_path')
    if not all([game_id, name, path]):
        socketio.emit('installer_output', {'data': '--- ERROR: All fields are required. ---\n', 'context_id': context_id}); return
    if steam_process and steam_process.poll() is None:
        socketio.emit('installer_output', {'data': '--- An installation is already in progress. ---\n', 'context_id': context_id}); return
    steam_path = load_config().get('steamcmd_path')
    if not steam_path or not os.path.exists(steam_path):
        socketio.emit('installer_output', {'data': f"--- ERROR: SteamCMD path invalid. Check Settings. ---\n", 'context_id': context_id}); return
    game_config = next((g for g in load_json_file(GAMES_FILE) if g['id'] == game_id), None)
    if not game_config:
        socketio.emit('installer_output', {'data': f"--- ERROR: Game config '{game_id}' not found. ---\n", 'context_id': context_id}); return
    try:
        if not os.path.exists(path): os.makedirs(path)
    except Exception as e:
        socketio.emit('installer_output', {'data': f"--- ERROR: Could not create directory '{path}'. {e} ---\n", 'context_id': context_id}); return
    appid, steam_cmd = game_config['appid'], [steam_path, '+force_install_dir', os.path.abspath(path), '+login', 'anonymous', '+app_update', appid, 'validate', '+quit']
    try:
        socketio.emit('installer_output', {'data': f'--- Starting SteamCMD for {game_config["name"]} ---\n', 'context_id': context_id})
        steam_process = subprocess.Popen(steam_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        for stream in [steam_process.stdout, steam_process.stderr]: threading.Thread(target=read_installer_stream, args=(stream, context_id), daemon=True).start()
        new_id = f"{game_id.replace('_','')}_{int(time.time())}"
        servers = load_json_file(SERVERS_FILE)
        new_config = {"id": new_id, "name": f"{game_config['name']} - {name}", "start_command": "# Enter start command here.\n# Example: server.exe -log", "cwd": os.path.abspath(path), "appid": appid}
        servers.append(new_config)
        save_servers(servers)
        socketio.emit('server_added', new_config)
    except Exception as e: socketio.emit('installer_output', {'data': f'\n--- FATAL ERROR: {e} ---\n', 'context_id': context_id})

@socketio.on('update_server')
def handle_update_server(data):
    # ... (code is unchanged from previous stable version)
    global steam_process
    server_id, context_id = data.get('id'), f"updater_{data.get('id')}"
    if steam_process and steam_process.poll() is None:
        socketio.emit('installer_output', {'data': '--- Another SteamCMD process is running. Please wait. ---\n', 'context_id': context_id}); return
    steam_path = load_config().get('steamcmd_path')
    if not steam_path or not os.path.exists(steam_path):
        socketio.emit('installer_output', {'data': f"--- ERROR: SteamCMD path invalid. Check Settings. ---\n", 'context_id': context_id}); return
    server_config = get_server_config(server_id)
    if not server_config or 'appid' not in server_config:
        socketio.emit('installer_output', {'data': f"--- ERROR: Server config for '{server_id}' is invalid. ---\n", 'context_id': context_id}); return
    path, appid = server_config['cwd'], server_config['appid']
    steam_cmd = [steam_path, '+force_install_dir', os.path.abspath(path), '+login', 'anonymous', '+app_update', appid, 'validate', '+quit']
    try:
        socketio.emit('installer_output', {'data': f'--- Starting update for {server_config["name"]} ---\n', 'context_id': context_id})
        steam_process = subprocess.Popen(steam_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        for stream in [steam_process.stdout, steam_process.stderr]: threading.Thread(target=read_installer_stream, args=(stream, context_id), daemon=True).start()
    except Exception as e: socketio.emit('installer_output', {'data': f'\n--- FATAL ERROR during update: {e} ---\n', 'context_id': context_id})

@socketio.on('start_server')
def handle_start_server(data):
    server_id = data.get('id')
    if server_id in server_processes and server_processes[server_id]['process'].poll() is None: return
    config = get_server_config(server_id)
    if not config: return
    _start_server_process(server_id, config)

@socketio.on('stop_server')
def handle_stop_server(data):
    _stop_server_process(data.get('id'))

@socketio.on('restart_server')
def handle_restart_server(data):
    server_id = data.get('id')
    config = get_server_config(server_id)
    if not config: return
    socketio.emit('console_output', {'id': server_id, 'data': f'\n--- Restarting server... ---\n'})
    _stop_server_process(server_id)
    # Wait for the process to fully terminate before restarting
    time.sleep(5)
    _start_server_process(server_id, config)

@socketio.on('send_command')
def handle_send_command(data):
    server_id, command = data.get('id'), data.get('command')
    if server_id in server_processes and command and server_processes[server_id]['process'].poll() is None:
        try:
            server_processes[server_id]['process'].stdin.write(command + '\n'); server_processes[server_id]['process'].stdin.flush()
        except Exception as e: socketio.emit('console_output', {'id': server_id, 'data': f'\n--- Error: {e} ---\n'})

@socketio.on('delete_server')
def handle_delete_server(data):
    server_id, delete_files = data.get('id'), data.get('delete_files', False)
    servers = load_json_file(SERVERS_FILE)
    server_to_delete = next((s for s in servers if s['id'] == server_id), None)
    if server_to_delete:
        new_servers = [s for s in servers if s['id'] != server_id]
        save_servers(new_servers)
        if delete_files:
            try:
                if os.path.exists(server_to_delete['cwd']) and len(server_to_delete['cwd']) > 5:
                    shutil.rmtree(server_to_delete['cwd'])
                    socketio.emit('notification', {'status': 'info', 'message': f"Deleted server files for {server_to_delete['name']}."})
            except Exception as e:
                socketio.emit('notification', {'status': 'error', 'message': f"Error deleting server files: {e}"})
    socketio.emit('server_deleted', {'id': server_id})
    socketio.emit('notification', {'status': 'success', 'message': 'Server removed from panel.'})


@socketio.on('save_server_config')
def handle_save_server_config(data):
    server_id, start_command = data.get('id'), data.get('start_command')
    servers = load_json_file(SERVERS_FILE)
    if any(s['id'] == server_id for s in servers):
        for s in servers:
            if s['id'] == server_id: s['start_command'] = start_command; break
        save_servers(servers)
        socketio.emit('notification', {'status': 'success', 'message': 'Start command saved!'})
    else: socketio.emit('notification', {'status': 'error', 'message': 'Error: Server not found.'})

# --- File Management Handlers ---
@socketio.on('list_files')
def handle_list_files(data):
    server_id, subdirectory = data.get('id'), data.get('path', '')
    path, error = get_safe_path(server_id, subdirectory)
    if error:
        socketio.emit('notification', {'status': 'error', 'message': error}); return
    try:
        items = os.listdir(path)
        files, dirs = [], []
        for item in items:
            if os.path.isdir(os.path.join(path, item)): dirs.append(item)
            else: files.append(item)
        dirs.sort(key=str.lower); files.sort(key=str.lower)
        socketio.emit('file_list', {'id': server_id, 'path': subdirectory, 'dirs': dirs, 'files': files})
    except Exception as e:
        socketio.emit('notification', {'status': 'error', 'message': f"Could not read directory: {e}"})

@socketio.on('get_file_content')
def handle_get_file_content(data):
    server_id, file_path = data.get('id'), data.get('path')
    path, error = get_safe_path(server_id, file_path)
    if error:
        socketio.emit('file_content', {'path': file_path, 'content': None, 'error': error}); return
    try:
        if os.path.getsize(path) > 5 * 1024 * 1024: # 5MB limit
             socketio.emit('file_content', {'path': file_path, 'content': None, 'error': 'File is too large to open (> 5MB).'}); return
        with open(path, 'r', encoding='utf-8', errors='ignore') as f: content = f.read()
        socketio.emit('file_content', {'path': file_path, 'content': content, 'error': None})
    except Exception as e:
        socketio.emit('file_content', {'path': file_path, 'content': None, 'error': f"Could not read file: {e}"})

@socketio.on('save_file_content')
def handle_save_file_content(data):
    server_id, file_path, content = data.get('id'), data.get('path'), data.get('content')
    path, error = get_safe_path(server_id, file_path)
    if error:
        socketio.emit('notification', {'status': 'error', 'message': error}); return
    try:
        with open(path, 'w', encoding='utf-8') as f: f.write(content)
        socketio.emit('notification', {'status': 'success', 'message': f"Saved {os.path.basename(file_path)}"})
    except Exception as e:
        socketio.emit('notification', {'status': 'error', 'message': f"Error saving file: {e}"})

@socketio.on('create_item')
def handle_create_item(data):
    server_id, path, item_type, name = data.get('id'), data.get('path'), data.get('type'), data.get('name')
    
    # Basic validation for name
    if not name or any(c in '\/:*?"<>|' for c in name):
        socketio.emit('notification', {'status': 'error', 'message': 'Invalid name provided.'}); return

    full_path, error = get_safe_path(server_id, os.path.join(path, name))
    if error:
        socketio.emit('notification', {'status': 'error', 'message': error}); return
    
    try:
        if os.path.exists(full_path):
            socketio.emit('notification', {'status': 'error', 'message': 'File or folder already exists.'}); return

        if item_type == 'file':
            open(full_path, 'a').close() # Create empty file
        elif item_type == 'folder':
            os.makedirs(full_path)
        
        socketio.emit('notification', {'status': 'success', 'message': f'Created {item_type}: {name}'})
        # Trigger a refresh of the file list
        handle_list_files({'id': server_id, 'path': path})

    except Exception as e:
        socketio.emit('notification', {'status': 'error', 'message': f'Could not create item: {e}'})

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
    webview.create_window('Pulse Panel', '[http://127.0.0.1:5000](http://127.0.0.1:5000)', width=1600, height=900, resizable=True, min_size=(1280, 720))
    webview.start(debug=True)
