import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class CompositorError(RuntimeError):
    """Raised when the headless Wayland compositor fails to start or expose a stream."""


def _find_pipewire_video_serials() -> set[str]:
    """Returns a set of PipeWire object.serial values exposing Weston video streams."""
    if not shutil.which("pw-cli"):
        return set()
    res = subprocess.run(["pw-cli", "list-objects", "Node"], capture_output=True, text=True, check=False)
    serials: set[str] = set()
    current_serial: str | None = None
    is_video_stream = False

    for line in res.stdout.splitlines():
        if re.match(r"^\s*id\s+\d+,", line):
            if current_serial and is_video_stream:
                serials.add(current_serial)
            current_serial = None
            is_video_stream = False
        serial_match = re.search(r'object\.serial\s*=\s*"(\d+)"', line)
        if serial_match:
            current_serial = serial_match.group(1)
        if 'media.class = "Stream/Output/Video"' in line or 'node.name = "weston.pipewire"' in line:
            is_video_stream = True

    if current_serial and is_video_stream:
        serials.add(current_serial)
    return serials


@contextmanager
def headless_wayland_session(
    session_id: str | None = None,
    width: int = 1920,
    height: int = 1080,
    startup_timeout: float = 5.0,
) -> Generator[dict[str, str], None, None]:
    """
    Starts an isolated headless Weston 14+ compositor using the PipeWire backend.
    Yields connection metadata including WAYLAND_DISPLAY and the PipeWire object.serial.
    """
    uid = session_id or str(os.getpid())
    socket_name = f"wayland-rec-{uid}"
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    socket_path = runtime_dir / socket_name

    serials_before = _find_pipewire_video_serials()

    with tempfile.TemporaryDirectory(prefix=f"wayland_rec_{uid}_") as tmpdir:
        ini_path = Path(tmpdir) / "weston.ini"
        ini_path.write_text(
            "[core]\n"
            "shell=kiosk-shell.so\n"
            "idle-time=0\n"
            "[output]\n"
            "name=pipewire\n"
            f"mode={width}x{height}\n"
        )

        cmd = [
            "weston",
            "--backend=pipewire-backend.so",
            f"--socket={socket_name}",
            f"--config={ini_path}",
            f"--width={width}",
            f"--height={height}",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            deadline = time.monotonic() + startup_timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    stderr = proc.stderr.read() if proc.stderr else ""
                    raise CompositorError(f"Weston exited prematurely (code {proc.returncode}): {stderr.strip()}")
                if socket_path.exists():
                    break
                time.sleep(0.05)
            else:
                raise CompositorError(f"Timed out waiting for Wayland socket at {socket_path}")

            video_serial = ""
            pw_deadline = time.monotonic() + 2.0
            while time.monotonic() < pw_deadline:
                if proc.poll() is not None:
                    stderr = proc.stderr.read() if proc.stderr else ""
                    raise CompositorError(f"Weston crashed after socket creation: {stderr.strip()}")
                new_serials = _find_pipewire_video_serials() - serials_before
                if new_serials:
                    video_serial = sorted(new_serials)[-1]
                    break
                time.sleep(0.05)

            yield {
                "WAYLAND_DISPLAY": socket_name,
                "socket_path": str(socket_path),
                "pipewire_node_id": video_serial,
                "width": str(width),
                "height": str(height),
            }
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if socket_path.exists():
                socket_path.unlink(missing_ok=True)

