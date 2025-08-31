# Pulse Panel - A Python Game Server Management Dashboard
# Version 5.0: Config Editor Update (File Browser, Editor, and Saver)

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
app.config['SECRET_KEY'] = 'config-editor-secret-key'
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
    """Validates that a path is safely within a server's directory."""
    server_config = get_server_config(server_id)
    if not server_config:
        return None, "Server not found."
    
    base_dir = os.path.abspath(server_config['cwd'])
    safe_relative_path = os.path.normpath(relative_path).lstrip('.\\/')
    full_path = os.path.abspath(os.path.join(base_dir, safe_relative_path))
    
    if os.path.commonprefix([full_path, base_dir]) != base_dir:
        return None, "Access denied: Path is outside of server directory."
        
    return full_path, None

# --- Stream Readers ---
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
        socketio.emit('installer_output', {'data': '\n--- Process Finished!---\n', 'context_id': context_id})

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

# --- Socket.IO Handlers for File Management ---
@socketio.on('list_files')
def handle_list_files(data):
    server_id, subdirectory = data.get('id'), data.get('path', '')
    path, error = get_safe_path(server_id, subdirectory)
    if error: 
        socketio.emit('file_browser_error', {'message': error}); return
    try:
        items = os.listdir(path)
        files, dirs = [], []
        for item in items:
            if os.path.isdir(os.path.join(path, item)): dirs.append(item)
            else: files.append(item)
        dirs.sort(key=str.lower); files.sort(key=str.lower)
        socketio.emit('file_list', {'id': server_id, 'path': subdirectory, 'dirs': dirs, 'files': files})
    except Exception as e: 
        socketio.emit('file_browser_error', {'message': f"Could not read directory: {e}"})

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
        socketio.emit('file_saved', {'path': file_path, 'success': False, 'message': error}); return
    try:
        with open(path, 'w', encoding='utf-8') as f: f.write(content)
        socketio.emit('file_saved', {'path': file_path, 'success': True, 'message': f"Successfully saved {os.path.basename(file_path)}."