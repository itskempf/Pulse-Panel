# Pulse Panel

A simple, standalone desktop application for managing game servers, built with Python, Flask, and web technologies.

## Features

* **Standalone Desktop App:** Runs in its own native window.
* **Real-time Monitoring:** View server status, CPU, and memory usage.
* **Full Server Lifecycle:** Start, Stop, and **Restart** your game servers.
* **Live Console & Command Sending:** Interact directly with your server's console.
* **SteamCMD Integration:**
    * Automatically download and set up SteamCMD.
    * Install new game servers from an easily editable `games.json` file.
    * Update any installed server with a single click.
* **Full Server Management:**
    * **Configuration Editor:** A built-in file browser and text editor allows you to manage all server configuration files without leaving the panel.
    * **File/Folder Creation:** Create new files and folders directly in the file manager.
    * **Start Command Editor:** Easily edit the startup command for any server.
    * **Safe Deletion:** Remove servers from the panel, with an option to securely delete the server files from your disk.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/itskempf/Pulse-Panel.git
    cd Pulse-Panel
    ```

2.  **Create and activate a Python virtual environment:**
    ```bash
    # Create the environment
    python -m venv venv
    
    # Activate it (Windows)
    .\venv\Scripts\activate
    
    # Activate it (macOS/Linux)
    source venv/bin/activate
    ```

3.  **Install the dependencies from `requirements.txt`:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python pulse_panel.py
    ```

## How to Use

1.  **First Run (SteamCMD Setup):**
    * On the first launch, click the "Settings" icon.
    * Provide a path to an empty folder (e.g., `C:\steamcmd`) and click "Download". The panel will set up SteamCMD for you.

2.  **Installing a Game Server:**
    * Click "Add New Server".
    * Select a game, give it a nickname, and provide a full path for the installation.
    * Click "Start Installation" and monitor the live console.

3.  **Managing a Server:**
    * Use the **Start/Stop/Restart** buttons for basic control.
    * Click **"Update"** to run SteamCMD and update the server files.
    * Click **"Manage"** to open the server's control center.
        * In the **"Start Command"** tab, you can change how the server launches.
        * In the **"File Browser"** tab, you can navigate all server files, create new files/folders, and click on a file to open it in the built-in editor.
    * Click **"Delete"** to remove a server from the panel. You will be asked if you also want to delete the files from your computer.

## Customizing Installable Games

You can add any Steam dedicated server to the installer by editing the `games.json` file. Simply add a new entry with a unique `id`, a `name` for the dropdown, and the correct Steam `appid`.
