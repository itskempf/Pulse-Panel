# Pulse Panel

A simple, standalone desktop application for managing game servers, built with Python, Flask, and web technologies.

## Features

*   **Standalone Desktop App:** Runs in its own window, no browser needed.
*   **Real-time Monitoring:** View server status, CPU usage, and memory usage in real-time.
*   **Live Console:** See the live console output of your game servers.
*   **Command Sending:** Send commands directly to your game server console.
*   **SteamCMD Integration:**
    *   Automatically download and set up SteamCMD.
    *   Install new game servers from a predefined list.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/itskempf/Pulse-Panel.git
    cd Pulse-Panel
    ```

2.  **Create a Python virtual environment:**
    ```bash
    python -m venv venv
    ```

3.  **Activate the virtual environment:**
    *   On Windows:
        ```bash
        .\venv\Scripts\activate
        ```
    *   On macOS/Linux:
        ```bash
        source venv/bin/activate
        ```

4.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Run the application:**
    ```bash
    python pulse_panel.py
    ```

## How to Use

1.  **Set up SteamCMD:**
    *   The first time you run the application, click on the "Settings" icon.
    *   In the "Install SteamCMD Automatically" section, provide a path to an empty folder where you want to install SteamCMD (e.g., `C:\steamcmd`).
    *   Click "Download". The application will download and extract SteamCMD for you.

2.  **Install a Game Server:**
    *   Click the "Add New Server" button.
    *   Select a game from the dropdown list.
    *   Give your server a nickname.
    *   Provide a path to an empty folder where you want to install the game server files.
    *   Click "Start Installation". You can monitor the progress in the live console.

3.  **Manage Your Servers:**
    *   The main dashboard will show all your installed servers.
    *   You can start, stop, and send commands to your servers from the server cards.
