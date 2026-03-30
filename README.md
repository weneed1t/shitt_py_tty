# shitt_py_tty
A quick AI script for launching a TTY in the browser to quickly set up local servers without a monitor or keyboard

# Don't forget to open the firewall port if you're going to use this crap outside your local machine 

# 🖥️ Web Terminal (shitt_py_tty)

A lightweight, browser-based terminal emulator for Linux servers. Built with FastAPI, WebSockets, PTY, and xterm.js.

> ⚠️ **Warning**: This provides direct shell access. Do not expose to the public internet without authentication.

---

## 🚀 Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/weneed1t/shitt_py_tty.git
cd shitt_py_tty

# 2. Make the setup script executable
chmod +x setup-run.sh

# 3. Run the setup and launch script
./setup-run.sh
```

The server will start at: **http://localhost:8200**

---

## 📋 Prerequisites

- Linux or macOS (PTY support required)
- Python 3.8+
- `python3-venv` package (install via `sudo apt install python3-venv` on Debian/Ubuntu)

---

## 🔧 Manual Installation (Optional)

If you prefer to set up manually:

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install 'uvicorn[standard]' fastapi

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8200
```

---

## 🎮 Usage

1. Open your browser to `http://<server-ip>:8200`
2. A fully functional terminal will appear
3. Type commands as you would in a regular shell
4. Resize your browser window – the terminal adapts automatically

---

This application spawns an interactive shell. Before deploying:

| Action | Why |
|--------|-----|
| 🔒 Bind to `127.0.0.1` only | Prevents external access |
| 🔐 Add authentication | See FastAPI's `HTTPBasic` docs |
| 🌐 Use HTTPS/WSS | Terminate TLS via nginx or Caddy |
| 👤 Run as non-root user | Limit privilege escalation risk |
| 📝 Enable logging | Audit terminal sessions |

---

## 🛠️ Script Options

```bash
./setup-run.sh --help

# Options:
#   --reinstall   Force rebuild of virtual environment & dependencies
#   --no-sudo     Run without elevated privileges (for testing)
```

---

## ❓ Troubleshooting

| Issue | Solution |
|-------|----------|
| `No supported WebSocket library` | Run `pip install 'uvicorn[standard]'` |
| `Permission denied` on PTY | Ensure you have terminal access; try `--no-sudo` for testing |
| Terminal not responding | Check browser console (F12) and server logs |
| Port 8200 in use | Change `PORT=8200` in `setup-run.sh` |

---

> Built for Linux server automation. Use responsibly. 🐧
