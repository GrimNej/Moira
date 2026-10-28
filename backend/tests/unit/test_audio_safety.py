"""§10.1 malicious uploads: ffmpeg reads only local files, with the demuxer pinned to the sniff."""

import shutil
import subprocess
from pathlib import Path

import pytest

from moira.media import audio
from moira.media.sniff import AUDIO_TYPES


def test_every_allowed_audio_type_has_a_pinned_demuxer() -> None:
    assert set(audio.DEMUXER) == AUDIO_TYPES
    assert audio.SAFE_INPUT == ["-protocol_whitelist", "file"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_a_real_voice_note_converts(tmp_path: Path) -> None:
    src = tmp_path / "v.ogg"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=2", "-c:a", "libopus", str(src)],
        check=True,
    )  # fmt: skip
    [wav] = audio.to_wav(src)
    assert 1.5 < audio.duration_s(wav) < 2.5
    assert not src.exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_a_playlist_disguised_as_ogg_is_not_followed(tmp_path: Path) -> None:
    src = tmp_path / "evil.ogg"
    # Starts with the Ogg magic, but is really an HLS playlist pointing elsewhere.
    src.write_bytes(b"OggS\n#EXTM3U\n#EXTINF:1,\nhttp://169.254.169.254/latest/meta-data\n")
    with pytest.raises(Exception):  # noqa: B017  # any failure; nothing fetched
        audio.to_wav(src)
    assert not src.exists()
