"""Tests for routing Discord audio and video attachments through Sensory."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _transcript_response(text: str = "ok") -> MagicMock:
    return MagicMock(text=text)


# ---------------------------------------------------------------------------
# STT filename handling
# ---------------------------------------------------------------------------

def test_transcribe_ogg_renamed_to_webm():
    from interface.stt import transcribe

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = _transcript_response()

    with patch("openai.OpenAI", return_value=fake_client):
        transcribe(b"fakeaudio", filename="voice-message.ogg")

    audio_file = fake_client.audio.transcriptions.create.call_args.kwargs["file"]
    assert audio_file.name == "voice-message.webm"


def test_transcribe_wav_keeps_extension():
    from interface.stt import transcribe

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = _transcript_response()

    with patch("openai.OpenAI", return_value=fake_client):
        transcribe(b"fakeaudio", filename="recording.wav")

    audio_file = fake_client.audio.transcriptions.create.call_args.kwargs["file"]
    assert audio_file.name == "recording.wav"


def test_transcribe_unknown_extension_falls_back_to_webm():
    from interface.stt import transcribe

    fake_client = MagicMock()
    fake_client.audio.transcriptions.create.return_value = _transcript_response()

    with patch("openai.OpenAI", return_value=fake_client):
        transcribe(b"fakeaudio", filename="clip.xyz")

    audio_file = fake_client.audio.transcriptions.create.call_args.kwargs["file"]
    assert audio_file.name == "clip.webm"


# ---------------------------------------------------------------------------
# Discord bridge extension sets
# ---------------------------------------------------------------------------

def test_audio_extensions_include_ogg_and_mp3():
    from interface.discord_bot import AUDIO_EXTENSIONS

    assert ".ogg" in AUDIO_EXTENSIONS
    assert ".mp3" in AUDIO_EXTENSIONS


def test_video_extensions_include_mp4_and_mov():
    from interface.discord_bot import VIDEO_EXTENSIONS

    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mov" in VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# Sensory audio routing
# ---------------------------------------------------------------------------

def test_sensory_sets_auditory_percept_from_audio_attachment():
    from coordinators.sensory import Sensory

    packet = {
        "audio_attachments": [
            {"filename": "voice-message.ogg", "data": b"fakeaudio"}
        ],
    }
    with (
        patch("interface.stt.transcribe", return_value="Hello from voice message."),
        patch.object(Sensory, "classify", return_value={"intent": "share", "keywords": ["voice"]}),
    ):
        result = Sensory().process(packet)

    assert "auditory_percept" in result
    assert result["auditory_percept"]["transcript"] == "Hello from voice message."
    assert result["auditory_percept"]["voice_present"] is True
    assert result["message"] == "Hello from voice message."
    assert result["input_type"] == "audio"
    assert "audio_attachments" not in result


def test_sensory_audio_transcription_failure_sets_empty_transcript():
    from coordinators.sensory import Sensory

    packet = {
        "audio_attachments": [
            {"filename": "voice-message.ogg", "data": b"fakeaudio"}
        ],
    }
    with patch("interface.stt.transcribe", side_effect=Exception("API error")):
        result = Sensory().process(packet)

    assert result["auditory_percept"]["transcript"] == ""
    assert result["auditory_percept"]["voice_present"] is False
    assert "audio_attachments" not in result


def test_sensory_skips_audio_when_auditory_percept_already_set():
    from coordinators.sensory import Sensory

    packet = {
        "message": "already transcribed",
        "audio_attachments": [
            {"filename": "voice-message.ogg", "data": b"fakeaudio"}
        ],
        "auditory_percept": {
            "timestamp": 1.0,
            "voice_present": True,
            "transcript": "Existing transcript.",
            "sound_class": "speech",
            "speaker_id": "unknown",
            "tone_signal": "",
        },
    }
    with (
        patch("interface.stt.transcribe", return_value="should not be called") as mock_transcribe,
        patch.object(Sensory, "classify", return_value={"intent": "share", "keywords": ["voice"]}),
    ):
        result = Sensory().process(packet)

    mock_transcribe.assert_not_called()
    assert result["auditory_percept"]["transcript"] == "Existing transcript."
    assert "audio_attachments" not in result


# ---------------------------------------------------------------------------
# Sensory video routing
# ---------------------------------------------------------------------------

def test_sensory_video_graceful_degradation_when_ffmpeg_missing():
    from coordinators.sensory import Sensory

    packet = {
        "message": "check this video",
        "video_attachments": [{"filename": "clip.mp4", "data": b"fakevideo"}],
    }
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        patch.object(Sensory, "classify", return_value={"intent": "share", "keywords": ["video"]}),
    ):
        result = Sensory().process(packet)

    assert "visual_percept" in result
    assert "ffmpeg required" in result["visual_percept"]["description"]
    assert "video_attachments" not in result
