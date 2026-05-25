# Codex Task: Route audio and video attachments through STT and VLM

## Background

The Discord bridge already downloads image bytes and passes them as
`image_attachments` to Awareness. Sensory then routes those bytes to the VLM
(qwen3.5 vision passthrough). The same pattern needs to be applied to audio and
video attachments.

Infrastructure that already exists and must NOT be changed:
- `AuditoryPercept` dataclass in `coordinators/percepts.py` — has `transcript`,
  `voice_present`, `sound_class`, `speaker_id`, `tone_signal` fields.
- `Sensory.process()` already handles a pre-populated `auditory_percept` dict
  in the packet — it parses it, and if `transcript` is set and `message` is empty,
  promotes the transcript to `packet["message"]` with `input_type = "audio"`.
- `interface/stt.py` — `transcribe(audio_bytes)` function calling OpenAI Whisper API.
- `interface/tts.py` — not touched by this task.

## Changes required

---

### 1. `interface/stt.py` — fix filename passthrough

The current code hardcodes `audio_file.name = "audio.webm"`. The OpenAI Whisper
API infers format from the filename. Discord voice messages are `.ogg` (Opus-encoded);
Whisper does not officially support `.ogg`, but accepts `.webm` (same Opus codec).

Change `transcribe()` to accept an optional `filename` parameter and remap `.ogg`
to `.webm`:

```python
def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    from openai import OpenAI
    from pathlib import Path as _Path

    suffix = _Path(filename).suffix.lower()
    # Whisper API doesn't list .ogg but accepts .webm (both use Opus codec).
    if suffix == ".ogg":
        api_filename = _Path(filename).stem + ".webm"
    elif suffix in {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}:
        api_filename = filename
    else:
        api_filename = _Path(filename).stem + ".webm"  # best-effort fallback

    audio_file = BytesIO(audio_bytes)
    audio_file.name = api_filename

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    transcript = client.audio.transcriptions.create(
        model=_get_stt_model(),
        file=audio_file,
    )
    return str(getattr(transcript, "text", "")).strip()
```

---

### 2. `interface/discord_bot.py` — add audio and video attachment handling

Add two new extension sets after `IMAGE_EXTENSIONS`:

```python
AUDIO_EXTENSIONS = {".ogg", ".mp3", ".wav", ".m4a", ".flac", ".webm", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".wmv"}
```

Note: `.webm` can be either audio or video. Check audio first; treat it as audio if
it appears in `AUDIO_EXTENSIONS` and the file size is under 10 MB.

Add `_download_audio_attachments()` immediately after `_download_image_attachments()`:

```python
async def _download_audio_attachments(message: discord.Message) -> list[dict]:
    """
    Download audio attachments and return them as
    {"filename": str, "data": bytes} dicts for the Sensory coordinator.
    """
    result = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix not in AUDIO_EXTENSIONS:
            continue
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"[discord] Skipping oversized audio: {attachment.filename}")
            continue
        try:
            data = await attachment.read()
            result.append({"filename": attachment.filename, "data": data})
        except Exception as exc:
            print(f"[discord] Failed to download {attachment.filename}: {exc}")
    return result
```

Add `_download_video_attachments()` immediately after:

```python
async def _download_video_attachments(message: discord.Message) -> list[dict]:
    """
    Download video attachments and return them as
    {"filename": str, "data": bytes} dicts for the Sensory coordinator.
    """
    result = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix not in VIDEO_EXTENSIONS:
            continue
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"[discord] Skipping oversized video: {attachment.filename}")
            continue
        try:
            data = await attachment.read()
            result.append({"filename": attachment.filename, "data": data})
        except Exception as exc:
            print(f"[discord] Failed to download {attachment.filename}: {exc}")
    return result
```

In `on_message()`, add audio and video downloads alongside image downloads:

```python
image_attachments = await _download_image_attachments(message)
audio_attachments = await _download_audio_attachments(message)
video_attachments = await _download_video_attachments(message)

if not content.strip() and not image_attachments and not audio_attachments and not video_attachments:
    return

packet = await asyncio.to_thread(
    bot.awareness.synchronous_run,
    content,
    image_attachments=image_attachments,
    audio_attachments=audio_attachments,
    video_attachments=video_attachments,
    text_attachments=text_attachments,
)
```

---

### 3. `coordinators/sensory.py` — audio and video routing

#### Audio handling

Add this block **before** the existing `auditory_percept` parsing block
(which starts with `if "auditory_percept" in packet`). It builds `auditory_percept`
from raw audio bytes if none is already set:

```python
audio_attachments = packet.pop("audio_attachments", None) or []
if audio_attachments and "auditory_percept" not in packet:
    for attachment in audio_attachments:
        filename = attachment.get("filename", "audio.ogg")
        data = attachment.get("data", b"")
        if not data:
            continue
        try:
            from interface.stt import transcribe as _transcribe
            transcript = _transcribe(data, filename=filename)
        except Exception as exc:
            logger.warning("Audio transcription failed for %s: %s", filename, exc)
            transcript = ""
        import time as _time_mod
        packet["auditory_percept"] = {
            "timestamp": _time_mod.time(),
            "voice_present": bool(transcript),
            "transcript": transcript,
            "sound_class": "speech" if transcript else "unknown",
            "speaker_id": "unknown",
            "tone_signal": "",
        }
        break  # Process first audio attachment; extend to multi-audio later if needed
```

#### Video handling

Add this block **after** the audio block but **before** the existing
`visual_percept` / `auditory_percept` handling. Video extracts both frames
(→ `visual_percept`) and audio (→ `auditory_percept`), with graceful
degradation if ffmpeg is not installed.

```python
video_attachments = packet.pop("video_attachments", None) or []
if video_attachments and "visual_percept" not in packet:
    attachment = video_attachments[0]  # Process first video; extend later if needed
    filename = attachment.get("filename", "video.mp4")
    data = attachment.get("data", b"")
    if data:
        _process_video(packet, data, filename, get_tier_config(packet.get("tier", DEFAULT_TIER)))
```

Add `_process_video()` as a module-level helper at the bottom of `sensory.py`
(below `_parse_classification`):

```python
def _process_video(packet: dict, video_data: bytes, filename: str, tier_config: dict) -> None:
    """
    Extract frames and audio from a video attachment using ffmpeg.
    Sets packet["visual_percept"] from frame descriptions and/or
    packet["auditory_percept"] from the audio transcript.

    Gracefully does nothing if ffmpeg is not installed.
    """
    import subprocess
    import tempfile
    import os
    import time as _time_mod

    # Check ffmpeg availability
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        logger.warning("ffmpeg not found; video attachment from %s not processed", filename)
        packet["visual_percept"] = {
            "timestamp": _time_mod.time(),
            "objects": [],
            "motion_detected": False,
            "motion_region": None,
            "scene_type": "user_attachment",
            "text_in_scene": [],
            "faces_detected": 0,
            "pose_summary": "",
            "description": f"[{filename}]: (video attached; ffmpeg required for processing)",
        }
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write video to temp file
        video_path = os.path.join(tmpdir, filename)
        with open(video_path, "wb") as f:
            f.write(video_data)

        # --- Extract keyframes (1 per 5 seconds, max 4 frames) ---
        frames_pattern = os.path.join(tmpdir, "frame%02d.jpg")
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", video_path,
                    "-vf", "fps=1/5,scale=480:-1",
                    "-frames:v", "4",
                    "-q:v", "3",
                    frames_pattern,
                ],
                capture_output=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg frame extraction timed out for %s", filename)

        frame_files = sorted(
            f for f in os.listdir(tmpdir) if f.startswith("frame") and f.endswith(".jpg")
        )

        frame_descriptions: list[str] = []
        for frame_file in frame_files:
            frame_path = os.path.join(tmpdir, frame_file)
            try:
                with open(frame_path, "rb") as f:
                    frame_data = f.read()
                desc = _describe_image(frame_data, frame_file, tier_config)
                if desc:
                    frame_descriptions.append(desc)
            except Exception as exc:
                logger.warning("Frame description failed for %s: %s", frame_file, exc)

        # --- Extract audio track ---
        audio_path = os.path.join(tmpdir, "audio.wav")
        audio_transcript = ""
        try:
            subprocess.run(
                [
                    "ffmpeg", "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    audio_path,
                ],
                capture_output=True,
                timeout=60,
            )
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    audio_data = f.read()
                from interface.stt import transcribe as _transcribe
                audio_transcript = _transcribe(audio_data, filename="audio.wav")
        except Exception as exc:
            logger.warning("Video audio extraction/transcription failed for %s: %s", filename, exc)

    # Build percepts
    combined_visual = "\n".join(
        f"[Frame {i+1}]: {desc}" for i, desc in enumerate(frame_descriptions)
    ) or f"[{filename}]: (video frames could not be described)"

    packet["visual_percept"] = {
        "timestamp": _time_mod.time(),
        "objects": [],
        "motion_detected": False,
        "motion_region": None,
        "scene_type": "user_attachment",
        "text_in_scene": [],
        "faces_detected": 0,
        "pose_summary": "",
        "description": combined_visual,
    }

    if audio_transcript and "auditory_percept" not in packet:
        packet["auditory_percept"] = {
            "timestamp": _time_mod.time(),
            "voice_present": True,
            "transcript": audio_transcript,
            "sound_class": "speech",
            "speaker_id": "unknown",
            "tone_signal": "",
        }
```

---

### 4. `tests/test_media_routing.py` — new test file

Create `tests/test_media_routing.py`. No live API calls, LM Studio, or ffmpeg
required. Mock everything external.

**STT filename tests**

```
test_transcribe_ogg_renamed_to_webm:
    Patch openai.OpenAI so client.audio.transcriptions.create is captured.
    Call transcribe(b"fakeaudio", filename="voice-message.ogg").
    Assert the BytesIO object's .name attribute is "voice-message.webm".

test_transcribe_wav_keeps_extension:
    Patch openai.OpenAI.
    Call transcribe(b"fakeaudio", filename="recording.wav").
    Assert the BytesIO .name is "recording.wav".

test_transcribe_unknown_extension_falls_back_to_webm:
    Patch openai.OpenAI.
    Call transcribe(b"fakeaudio", filename="clip.xyz").
    Assert the BytesIO .name is "clip.webm".
```

**Discord bridge audio/video extension sets**

```
test_audio_extensions_include_ogg_and_mp3:
    Import AUDIO_EXTENSIONS from interface.discord_bot.
    Assert ".ogg" in AUDIO_EXTENSIONS.
    Assert ".mp3" in AUDIO_EXTENSIONS.

test_video_extensions_include_mp4_and_mov:
    Import VIDEO_EXTENSIONS from interface.discord_bot.
    Assert ".mp4" in VIDEO_EXTENSIONS.
    Assert ".mov" in VIDEO_EXTENSIONS.
```

**Sensory audio routing**

```
test_sensory_sets_auditory_percept_from_audio_attachment:
    Patch interface.stt.transcribe to return "Hello from voice message.".
    Build packet with audio_attachments=[{"filename": "voice-message.ogg", "data": b"fakeaudio"}].
    Call Sensory().process(packet) (also patch classify() to return a valid dict).
    Assert "auditory_percept" in packet.
    Assert packet["auditory_percept"]["transcript"] == "Hello from voice message.".
    Assert packet["auditory_percept"]["voice_present"] is True.
    Assert "audio_attachments" not in packet.

test_sensory_audio_transcription_failure_sets_empty_transcript:
    Patch interface.stt.transcribe to raise Exception("API error").
    Build packet with audio_attachments=[{"filename": "voice-message.ogg", "data": b"fakeaudio"}].
    Call Sensory().process(packet).
    Assert packet["auditory_percept"]["transcript"] == "".
    Assert packet["auditory_percept"]["voice_present"] is False.

test_sensory_skips_audio_when_auditory_percept_already_set:
    Patch interface.stt.transcribe to return "should not be called".
    Build packet with audio_attachments=[...] AND auditory_percept already set.
    Call Sensory().process(packet).
    Assert transcribe was NOT called.
```

**Sensory video routing**

```
test_sensory_video_graceful_degradation_when_ffmpeg_missing:
    Patch subprocess.run to raise FileNotFoundError (simulating ffmpeg absent).
    Build packet with video_attachments=[{"filename": "clip.mp4", "data": b"fakevideo"}].
    Call Sensory().process(packet).
    Assert "visual_percept" in packet.
    Assert "ffmpeg required" in packet["visual_percept"]["description"].
```

---

## What NOT to change

- `coordinators/awareness.py` — `packet_overrides` already flows keyword args through.
- `coordinators/reason.py` — audio surfaces via `packet["message"]` (existing Sensory
  promotion); no changes needed.
- `coordinators/percepts.py` — schema is correct as-is.
- `interface/tts.py` — not touched.
- `world_models/config.py` — no config changes; audio uses existing `OPENAI_API_KEY`.

## Acceptance criteria

```
pytest tests/test_media_routing.py -v   # all tests pass
pytest --basetemp .tmp/pytest-tmp -q    # full suite still passes
```

Manual verification (once implemented):
- Send a Discord voice message → bot transcribes and responds to the spoken content.
- Send a `.mp4` video → bot describes visible frames and transcribes spoken audio
  (requires ffmpeg installed; gracefully notes it's missing if not).

## Commit instructions

```
git add coordinators/sensory.py interface/discord_bot.py interface/stt.py tests/test_media_routing.py
git reset HEAD world_models/config.py
git commit -m "feat: route audio and video attachments through STT and VLM

- discord_bot: add AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, download handlers
- stt: accept filename param, remap .ogg -> .webm for Whisper API compat
- sensory: transcribe audio attachments into auditory_percept
- sensory: extract frames + audio from video via ffmpeg (graceful if absent)
- tests/test_media_routing.py: covers stt filename, audio routing, video fallback"
git push origin main
```

## Security reminder

Do not stage or commit `world_models/config.py`. Run `git status` before committing.
