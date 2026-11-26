import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from contextlib import ExitStack

from wayland_rec.audio import virtual_audio_sink
from wayland_rec.compositor import headless_wayland_session
from wayland_rec.recorder import record_session


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wayland-rec",
        description="Record an isolated headless Wayland & PipeWire application session to MP4.",
    )
    parser.add_argument(
        "--cmd",
        required=True,
        help="Command to execute inside the isolated Wayland/PipeWire session (e.g., 'weston-simple-egl').",
    )
    parser.add_argument(
        "--out",
        default="session.mp4",
        help="Output MP4 file path (default: session.mp4).",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Virtual display width in pixels (default: 1280).",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Virtual display height in pixels (default: 720).",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Recording frame rate (default: 30).",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.0,
        help="Optional fixed recording duration in seconds (0 = record until command exits or Ctrl+C).",
    )
    return parser.parse_args(argv)


def run_session(args: argparse.Namespace) -> int:
    session_id = str(os.getpid())
    stop_requested = False

    def _handle_sigint(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGTERM, _handle_sigint)

    with ExitStack() as stack:
        audio = stack.enter_context(virtual_audio_sink(session_id))
        wl = stack.enter_context(
            headless_wayland_session(session_id, width=args.width, height=args.height)
        )
        if not wl["pipewire_node_id"]:
            raise RuntimeError("Weston started, but no PipeWire video stream node was detected.")

        # Build isolated environment for the target application
        app_env = os.environ.copy()
        app_env["WAYLAND_DISPLAY"] = wl["WAYLAND_DISPLAY"]
        app_env["PULSE_SINK"] = audio["PULSE_SINK"]
        # Force GUI toolkits (GTK/Qt/Electron/Firefox) to use Wayland instead of host X11
        app_env["GDK_BACKEND"] = "wayland"
        app_env["QT_QPA_PLATFORM"] = "wayland"
        app_env["MOZ_ENABLE_WAYLAND"] = "1"
        app_env.pop("DISPLAY", None)

        stack.enter_context(
            record_session(
                video_node_id=wl["pipewire_node_id"],
                audio_monitor_source=audio["monitor_source"],
                output_path=args.out,
                fps=args.fps,
            )
        )

        # Give GStreamer a moment to negotiate PipeWire buffers before launching target app
        time.sleep(0.5)

        app_proc = subprocess.Popen(shlex.split(args.cmd), env=app_env)
        try:
            start_time = time.monotonic()
            while not stop_requested:
                if app_proc.poll() is not None:
                    break
                if args.duration > 0 and (time.monotonic() - start_time) >= args.duration:
                    break
                time.sleep(0.1)
        finally:
            if app_proc.poll() is None:
                app_proc.terminate()
                try:
                    app_proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    app_proc.kill()
                    app_proc.wait()

    print(f"Saved recording to {args.out}")
    return 0


def main() -> None:
    args = parse_args()
    try:
        sys.exit(run_session(args))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

