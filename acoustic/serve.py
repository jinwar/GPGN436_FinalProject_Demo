"""Start Panel locally or on Render with the correct WebSocket origin."""
import os
import subprocess
import sys
from pathlib import Path


def server_command():
    command = [sys.executable, '-m', 'panel', 'serve', 'app.py',
               '--warm', '--liveness', '--liveness-endpoint', 'health',
               '--address', '0.0.0.0', '--port', os.environ.get('PORT', '5006')]
    hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if hostname:
        command.extend(['--allow-websocket-origin', hostname])
    return command


if __name__ == '__main__':
    raise SystemExit(subprocess.call(server_command(), cwd=Path(__file__).parent))
