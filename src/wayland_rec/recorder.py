import shutil
import signal
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class RecorderError(RuntimeError):
    """Raised when the media capture pipeline fails to start or finalize."""


@contextmanager
def record_session(
    video_node_id: str,
    audio_monitor_source: str,
    output_path: str | Path,
    fps: int = 30,
) -> Generator[subprocess.Popen, None, None]:
    """
    Captures a PipeWire video stream (by object.serial) and Pulse/PipeWire audio
    monitor source into a single H.264/AAC MP4 file using GStreamer, sending EOS
    on exit so the MP4 header is cleanly finalized.
    """
    if not shutil.which("gst-launch-1.0"):
        raise RecorderError("gst-launch-1.0 not found. Install gstreamer1.0-tools and gstreamer1.0-pipewire.")

    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Pipeline muxes PipeWire video (from Weston) + virtual sink audio monitor into MP4
    pipeline = [
        "gst-launch-1.0",
        "-e",
        "mp4mux",
        "name=mux",
        "!",
        "filesink",
        f"location={out}",
        "pipewiresrc",
        f"target-object={video_node_id}",
        "do-timestamp=true",
        "keepalive-time=1000",
        "!",
        "videoconvert",
        "!",
        "videorate",
        "!",
        f"video/x-raw,framerate={fps}/1",
        "!",
        "videoconvert",
        "!",
        "videorate",
        "!",
        f"video/x-raw,framerate={fps}/1",
        "!",
        "videoconvert",
        "!",
        "video/x-raw,format=I420",
        "!",
        "x264enc",
        "tune=zerolatency",
        "speed-preset=ultrafast",
        "!",
        "h264parse",
        "!",
        "queue",
        "!",
        "mux.",
        "pulsesrc",
        f"device={audio_monitor_source}",
        "do-timestamp=true",
        "!",
        "audioconvert",
        "!",
        "audioresample",
        "!",
        "avenc_aac",
        "bitrate=128000",
        "!",
        "aacparse",
        "!",
        "queue",
        "!",
        "mux.",
    ]

    proc = subprocess.Popen(
        pipeline,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Verify pipeline doesn't immediately fail due to missing GStreamer element
        time.sleep(0.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RecorderError(f"GStreamer exited immediately (code {proc.returncode}): {stderr.strip()}")
        yield proc
    finally:
        if proc.poll() is None:
            # SIGINT with gst-launch-1.0 -e triggers clean EOS and writes the MP4 moov atom
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=8.0)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=3.0)

