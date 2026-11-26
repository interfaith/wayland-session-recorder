from unittest.mock import MagicMock, patch
from wayland_rec.cli import parse_args
from wayland_rec.compositor import _find_pipewire_video_serials


def test_parse_args_defaults():
    args = parse_args(["--cmd", "weston-terminal"])
    assert args.cmd == "weston-terminal"
    assert args.out == "session.mp4"
    assert args.width == 1280
    assert args.height == 720
    assert args.fps == 30
    assert args.duration == 0.0


def test_parse_args_custom():
    args = parse_args([
        "--cmd", "firefox https://ubuntu.com",
        "--out", "ci-run.mp4",
        "--width", "1920",
        "--height", "1080",
        "--fps", "60",
        "--duration", "10.5",
    ])
    assert args.width == 1920
    assert args.height == 1080
    assert args.fps == 60
    assert args.duration == 10.5


@patch("wayland_rec.compositor.shutil.which", return_value="/usr/bin/pw-cli")
@patch("wayland_rec.compositor.subprocess.run")
def test_find_pipewire_video_serials(mock_run, _mock_which):
    mock_run.return_value = MagicMock(
        stdout=(
            '        id 44, type PipeWire:Interface:Node/3\n'
            '                object.serial = "700"\n'
            '                node.name = "auto_null"\n'
            '                media.class = "Audio/Sink"\n'
            '        id 62, type PipeWire:Interface:Node/3\n'
            '                object.serial = "738"\n'
            '                node.name = "weston.pipewire"\n'
            '                media.class = "Stream/Output/Video"\n'
        )
    )
    serials = _find_pipewire_video_serials()
    assert serials == {"738"}

