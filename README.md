# wayland-session-recorder (`wayland-rec`)

An isolated headless Wayland compositor and PipeWire audio/video session recorder for Linux.

`wayland-rec` spawns a self-contained Weston compositor backed by PipeWire, creates an isolated virtual PipeWire audio sink, executes a target GUI or browser workload inside that sandboxed session, and muxes both video and audio into a synchronized H.264/AAC `.mp4` artifact—without touching the host desktop display or physical audio hardware.

## Use Cases

- **Automated UI & Browser Testing in CI/CD:** Capture video and audio artifacts of headless Playwright, Selenium, or Firefox test runs on Ubuntu/Debian runners.
- **Reproducing GUI & Multimedia Bugs:** Record deterministic, isolated Wayland application sessions for bug triage.
- **Kiosk & Embedded Display Verification:** Validate fullscreen Wayland kiosk rendering and audio output in headless environments.

## Architecture

```text
+-------------------------------------------------------------------+

|                        wayland-rec (Python)                       |
|                     contextlib.ExitStack Lifecycle                |
+-------------------------------------------------------------------+

         |                        |                        |
         v                        v                        v
+-----------------+     +-------------------+     +-----------------+

|  Weston 14+     |     |  PipeWire Audio   |     |   Target App    |
| (pipewire-      |     |  (module-null-    |     | WAYLAND_DISPLAY |
|  backend.so)    |     |   sink monitor)   |     | PULSE_SINK      |
+-----------------+     +-------------------+     +-----------------+

         |                        |                        ^
         | Stream/Output/Video    | Audio/Source           |
         +-----------+------------+------------------------+
                     |
                     v
+-------------------------------------------------------------------+

|              GStreamer (pipewiresrc + pulsesrc)                   |
|           H.264 (x264enc) + AAC (avenc_aac) -> mp4mux             |
+-------------------------------------------------------------------+
                     |
                     v
               [ session.mp4 ]
```

### Key Design Decisions
- **Zero Host Collision:** Each run generates a unique Wayland socket (`wayland-rec-<pid>`) and PipeWire sink (`wayland_rec_sink_<pid>`), allowing multiple parallel recordings on the same machine.
- **Deterministic Teardown:** Uses `contextlib.ExitStack` and clean `SIGINT` EOS signaling (`gst-launch-1.0 -e`) so interrupted or timed-out sessions always finalize valid MP4 `moov` headers and leave zero orphan processes or sockets.
- **Modern Linux Stack:** Built natively on Wayland and PipeWire rather than legacy X11 (`Xvfb`) and PulseAudio.

## Installation

### System Dependencies (Ubuntu 24.04+ / Debian 13+)
```bash
sudo apt update && sudo apt install -y \
  weston \
  pipewire-bin \
  pipewire-pulse \
  pulseaudio-utils \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-pipewire \
  gstreamer1.0-pulseaudio \
  python3-venv
```

### Install from Source
```bash
git clone https://github.com/interfaith/wayland-session-recorder.git
cd wayland-session-recorder
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Build as a Snap
```bash
snapcraft
sudo snap install ./wayland-session-recorder_0.1.0_amd64.snap --dangerous
```

## Usage

Record a Wayland application until it exits or `Ctrl+C` is pressed:
```bash
wayland-rec --cmd "weston-terminal" --out terminal-session.mp4
```

Record a fixed-duration automated browser session at 1080p / 60fps:
```bash
wayland-rec \
  --cmd "firefox --kiosk https://ubuntu.com" \
  --width 1920 \
  --height 1080 \
  --fps 60 \
  --duration 15 \
  --out browser-test.mp4
```

## Running Tests

```bash
pip install -e . pytest
pytest -v
```

## License

GPL-3.0-or-later

