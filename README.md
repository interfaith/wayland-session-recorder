# wayland-session-recorder (`wayland-rec`)

[![CI](https://github.com)](https://github.com)

An isolated headless Wayland compositor and PipeWire audio/video session recorder for Linux. Spawns a self-contained Weston/PipeWire environment to capture GUI/browser workloads into synchronized H.264/AAC `.mp4` files without affecting host displays or audio.

## Use Cases
- **CI/CD Automated Testing:** Capture video/audio of headless Playwright, Selenium, or Firefox runs.
- **Bug Reproductions:** Deterministic, isolated Wayland recording for triage.
- **Kiosk Verification:** Validate fullscreen Wayland rendering in headless environments.

## Architecture
- **Core (Python):** Uses `contextlib.ExitStack` for lifecycle and clean `SIGINT` (`gst-launch-1.0 -e`) teardown to ensure valid MP4 `moov` headers and zero orphan processes.
- **Compositor & Audio:** Weston 14+ with `pipewire-backend.so` and isolated PipeWire null-sink monitors.
- **Muxing:** GStreamer (`pipewiresrc`, `pulsesrc`, `x264enc`, `avenc_aac`, `mp4mux`).

## Installation

### System Dependencies (Ubuntu 24.04+ / Debian 13+)
```bash
sudo apt update && sudo apt install -y \
  weston pipewire-bin pipewire-pulse pulseaudio-utils \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
  gstreamer1.0-pipewire gstreamer1.0-pulseaudio python3-venv
```

### Install from Source / Snap
```bash
git clone https://github.com
cd wayland-session-recorder && python3 -m venv .venv && source .venv/bin/activate && pip install -e .
# Or via Snap:
snapcraft && sudo snap install ./wayland-session-recorder_0.1.0_amd64.snap --dangerous
```

## Usage

```bash
# Record until exit or Ctrl+C
wayland-rec --cmd "weston-terminal" --out terminal-session.mp4

# Record fixed-duration 1080p/60fps browser session
wayland-rec --cmd "firefox --kiosk https://ubuntu.com" --width 1920 --height 1080 --fps 60 --duration 15 --out browser-test.mp4
```

### Local QA Web Dashboard (`wayland-rec-ui`)
Launch a zero-dependency local web interface to trigger headless browser captures and play back `.mp4` artifacts:
```bash
wayland-rec-ui --host 127.0.0.1 --port 8080
```

## Running Tests & License
```bash
pip install -e . pytest && pytest -v
```
**License:** GPL-3.0-or-later

