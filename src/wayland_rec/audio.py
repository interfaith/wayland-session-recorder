import os
import subprocess
from contextlib import contextmanager
from typing import Generator


class AudioRouterError(RuntimeError):
    """Raised when virtual audio sink creation or cleanup fails."""


@contextmanager
def virtual_audio_sink(session_id: str | None = None) -> Generator[dict[str, str], None, None]:
    """
    Creates an isolated PipeWire/PulseAudio null-sink and yields environment
    variables to route a target application's audio into it.
    """
    uid = session_id or str(os.getpid())
    sink_name = f"wayland_rec_sink_{uid}"
    module_id: str | None = None

    try:
        result = subprocess.run(
            [
                "pactl",
                "load-module",
                "module-null-sink",
                f"sink_name={sink_name}",
                f"sink_properties=device.description=WaylandRec_{uid}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        module_id = result.stdout.strip()

        yield {
            "sink_name": sink_name,
            "monitor_source": f"{sink_name}.monitor",
            "PULSE_SINK": sink_name,
        }
    except subprocess.CalledProcessError as exc:
        raise AudioRouterError(f"Failed to load null-sink: {exc.stderr.strip()}") from exc
    finally:
        if module_id and module_id.isdigit():
            subprocess.run(
                ["pactl", "unload-module", module_id],
                capture_output=True,
                check=False,
            )

