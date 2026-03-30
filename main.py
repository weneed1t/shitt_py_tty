#!/usr/bin/env python3
"""
Web-based terminal with PTY support and xterm.js.
Production-ready implementation with proper async/PTY handling.

Install: pip install 'uvicorn[standard]' fastapi
Run: uvicorn main:app --host 127.0.0.1 --port 8000
"""

import asyncio
import errno
import fcntl
import json
import os
import pty
import signal
import struct
import sys
import termios

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# ----------------------------------------------------------------------
# HTML Frontend with xterm.js
# ----------------------------------------------------------------------
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Web Terminal</title>
    <link href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css" rel="stylesheet" />
    <style>
        body { margin: 0; padding: 20px; background: #1e1e1e; font-family: monospace; }
        #terminal { width: 100%; height: calc(100vh - 40px); }
        .status { color: #888; font-size: 12px; margin-bottom: 10px; }
        .status.connected { color: #4caf50; }
        .status.error { color: #f44336; }
    </style>
</head>
<body>
    <div class="status" id="status">Connecting...</div>
    <div id="terminal"></div>
    <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
    <script>
        const statusEl = document.getElementById('status');
        const term = new Terminal({
            cursorBlink: true, fontSize: 14, fontFamily: 'monospace',
            theme: { background: '#1e1e1e', foreground: '#d4d4d4', cursor: '#d4d4d4' }
        });
        term.open(document.getElementById('terminal'));
        term.focus();
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);
        ws.binaryType = 'arraybuffer';
        
        ws.onopen = () => {
            statusEl.textContent = 'Connected';
            statusEl.className = 'status connected';
            term.clear();
            ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
        };
        
        term.onResize(size => {
            ws.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }));
        });
        
        term.onData(data => ws.send(data));
        
        ws.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
                term.write(new TextDecoder('utf-8').decode(event.data));
            } else {
                term.write(event.data);
            }
        };
        
        ws.onclose = () => {
            statusEl.textContent = 'Disconnected';
            statusEl.className = 'status error';
            term.write('\\r\\n\\x1b[31m[Connection closed]\\x1b[0m\\r\\n');
            term.options.disableStdin = true;
        };
        
        ws.onerror = (err) => {
            console.error('WebSocket error:', err);
            statusEl.textContent = 'Connection error';
            statusEl.className = 'status error';
        };
    </script>
</body>
</html>
"""

# ----------------------------------------------------------------------
# PTY Management (Unix/Linux only)
# ----------------------------------------------------------------------


def create_pty(shell: str = None) -> tuple[int, int]:
    """
    Create PTY and spawn shell process.
    Returns (master_fd, child_pid).
    """
    # Determine shell with fallbacks
    if shell is None:
        shell = os.environ.get("SHELL", "/bin/bash")
    if not os.path.exists(shell):
        shell = "/bin/sh"

    master_fd, slave_fd = pty.openpty()
    pid = os.fork()

    if pid == 0:  # Child process
        os.setsid()  # New session, detach from controlling terminal
        os.close(master_fd)  # Child doesn't need master

        # Redirect stdio to slave PTY
        for fd in range(3):
            if fd != slave_fd:
                os.dup2(slave_fd, fd)
        if slave_fd > 2:
            os.close(slave_fd)

        # Set controlling terminal (best effort)
        try:
            os.ioctl(0, termios.TIOCSCTTY, 0)
        except (AttributeError, OSError):
            pass

        # Clean environment for shell
        os.environ.setdefault("TERM", "xterm-256color")

        # Execute shell
        os.execvp(shell, [shell])
        sys.exit(127)  # Should never reach here

    # Parent process
    os.close(slave_fd)

    # Set non-blocking mode on master
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    return master_fd, pid


def set_pty_size(master_fd: int, cols: int, rows: int) -> None:
    """Update PTY window size via TIOCSWINSZ ioctl."""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass  # Non-fatal


def cleanup_pty(master_fd: int, pid: int, loop: asyncio.AbstractEventLoop) -> None:
    """Gracefully terminate shell and close resources."""
    # Remove reader FIRST to prevent callbacks on closed FD
    try:
        loop.remove_reader(master_fd)
    except (ValueError, RuntimeError):
        pass

    try:
        os.close(master_fd)
    except OSError:
        pass

    try:
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, os.WNOHANG)  # Non-blocking reap
    except (OSError, ChildProcessError):
        pass


# ----------------------------------------------------------------------
# FastAPI Application
# ----------------------------------------------------------------------

app = FastAPI(title="Web Terminal")


@app.get("/")
async def get_index() -> HTMLResponse:
    return HTMLResponse(content=HTML_PAGE)


@app.websocket("/ws")
async def websocket_terminal(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()

    # Initialize PTY
    try:
        master_fd, pid = create_pty()
    except Exception as e:
        print(f"[ERROR] PTY creation failed: {e}", file=sys.stderr)
        await websocket.close(code=1011, reason="Terminal initialization failed")
        return

    running = True

    # Async helper to send data to WebSocket
    async def _send_bytes(data: bytes):
        try:
            await websocket.send_bytes(data)
        except Exception:
            pass  # Connection likely closed

    # Sync callback for PTY reader (called by event loop)
    def _on_pty_readable():
        nonlocal running
        if not running:
            return

        try:
            data = os.read(master_fd, 4096)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return  # No data yet, will retry
            elif e.errno == errno.EIO:
                running = False  # Child exited
            else:
                print(f"[ERROR] PTY read: {e}", file=sys.stderr)
                running = False
            asyncio.create_task(websocket.close())
            return

        if not data:  # EOF
            running = False
            asyncio.create_task(websocket.close())
            return

        # Schedule async send
        asyncio.create_task(_send_bytes(data))

    # Register PTY with event loop
    loop.add_reader(master_fd, _on_pty_readable)

    try:
        while running:
            # Use timeout to periodically check child status
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                # Check if child still alive
                try:
                    if os.waitpid(pid, os.WNOHANG)[0] != 0:
                        break
                except ChildProcessError:
                    break
                continue
            except WebSocketDisconnect:
                break

            # Handle binary input (raw keystrokes)
            if "bytes" in msg:
                try:
                    os.write(master_fd, msg["bytes"])
                except OSError:
                    running = False

            # Handle text input (JSON commands or raw text)
            elif "text" in msg:
                text = msg["text"]
                try:
                    cmd = json.loads(text)
                    if isinstance(cmd, dict) and cmd.get("type") == "resize":
                        set_pty_size(
                            master_fd, cmd.get("cols", 80), cmd.get("rows", 24)
                        )
                    else:
                        os.write(master_fd, text.encode())
                except json.JSONDecodeError:
                    os.write(master_fd, text.encode())
                except OSError:
                    running = False

            # Final child check
            try:
                if os.waitpid(pid, os.WNOHANG)[0] != 0:
                    break
            except ChildProcessError:
                break

    except Exception as e:
        print(f"[ERROR] WebSocket: {e}", file=sys.stderr)
    finally:
        running = False
        cleanup_pty(master_fd, pid, loop)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
