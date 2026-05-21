import threading
import time
import logging
import queue
from pathlib import Path
from typing import Optional

from interface.reflex import trigger_reflex_alert
from coordinators.percepts import AuditoryPercept

logger = logging.getLogger("audio_sensor")

MODELS_DIR = Path("D:/Gopher Bot/gopher-bot/models")

# Graceful degradation flags
try:
    import numpy as np
    import sounddevice as sd
    has_audio = True
except ImportError:
    has_audio = False

try:
    import torch
    import torchaudio
    has_torch = True
except ImportError:
    has_torch = False

try:
    import whisper
    has_whisper = True
except ImportError:
    has_whisper = False

try:
    import librosa
    has_librosa = True
except ImportError:
    has_librosa = False

try:
    import tensorflow as tf
    import tensorflow_hub as hub
    has_yamnet = True
except ImportError:
    has_yamnet = False


class AudioSensor:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.latest_percept = AuditoryPercept(timestamp=time.time())
        self._percept_lock = threading.Lock()
        self.audio_queue = queue.Queue()
        
        self.vad_model = None
        self.get_speech_timestamps = None
        if has_torch:
            try:
                torch.hub.set_dir(str(MODELS_DIR))
                model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    onnx=False
                )
                self.vad_model = model
                (get_speech_timestamps, _, _, _, _) = utils
                self.get_speech_timestamps = get_speech_timestamps
            except Exception as e:
                logger.warning(f"Failed to load Silero VAD: {e}")

        self.whisper_model = None
        if has_whisper:
            weights = MODELS_DIR / "base.en.pt"
            if weights.exists():
                try:
                    self.whisper_model = whisper.load_model(str(weights))
                except Exception as e:
                    logger.warning(f"Whisper load error: {e}")
            else:
                logger.warning(f"Whisper weights missing at {weights}. Run scripts/download_models.py")

        self.yamnet_model = None
        if has_yamnet:
            try:
                # Load from tfhub
                # Note: This caches to OS temp by default, but is safe to run.
                self.yamnet_model = hub.load('https://tfhub.dev/google/yamnet/1')
            except Exception as e:
                logger.warning(f"Failed to load YAMNet: {e}")

    def start(self):
        if not has_audio:
            logger.warning("Missing sounddevice or numpy. AudioSensor will not start.")
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def get_latest_percept(self) -> dict:
        with self._percept_lock:
            return self.latest_percept.to_dict()

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning(f"Audio callback status: {status}")
        self.audio_queue.put(indata.copy())

    def _loop(self):
        SAMPLE_RATE = 16000
        CHUNK_SIZE = int(SAMPLE_RATE * 0.5)  # 500ms chunks
        
        last_yamnet_time = 0.0
        audio_buffer = np.array([], dtype=np.float32)
        
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                callback=self._audio_callback,
                dtype=np.float32
            )
            stream.start()
        except Exception as e:
            logger.error(f"Failed to start audio stream: {e}")
            self.running = False
            return
            
        while self.running:
            loop_start = time.time()
            
            try:
                chunk = self.audio_queue.get(timeout=0.5)
                chunk = chunk.flatten()
                audio_buffer = np.concatenate((audio_buffer, chunk))
            except queue.Empty:
                continue

            if len(audio_buffer) < CHUNK_SIZE:
                continue

            process_chunk = audio_buffer[:CHUNK_SIZE]
            audio_buffer = audio_buffer[CHUNK_SIZE:]
            
            voice_present = False
            transcript = ""
            tone_signal = ""
            sound_class = "unknown"
            
            # VAD Gate
            if self.vad_model and has_torch:
                try:
                    tensor_chunk = torch.from_numpy(process_chunk)
                    # Add batch dimension
                    tensor_chunk = tensor_chunk.unsqueeze(0)
                    speech_prob = self.vad_model(tensor_chunk, SAMPLE_RATE).item()
                    if speech_prob > 0.5:
                        voice_present = True
                        trigger_reflex_alert(coordinator="audio_sensor")
                except Exception as e:
                    logger.error(f"VAD error: {e}")

            # Whisper (Gated by VAD)
            if voice_present and self.whisper_model:
                try:
                    # In a real pipeline, we buffer audio while voice is present 
                    # and transcribe once silence is detected. For this stub,
                    # we transcribe the chunk directly.
                    result = self.whisper_model.transcribe(process_chunk, fp16=False)
                    transcript = result.get("text", "").strip()
                    
                    # Librosa Prosody Analysis (Gated by transcription)
                    if transcript and has_librosa:
                        zcr = librosa.feature.zero_crossing_rate(process_chunk)[0]
                        rms = librosa.feature.rms(y=process_chunk)[0]
                        avg_zcr = np.mean(zcr)
                        avg_rms = np.mean(rms)
                        if avg_rms > 0.1 and avg_zcr > 0.1:
                            tone_signal = "high_energy_agitated"
                        elif avg_rms < 0.02:
                            tone_signal = "low_energy_calm"
                        else:
                            tone_signal = "neutral"
                except Exception as e:
                    logger.error(f"Whisper/Librosa error: {e}")

            # Ambient sound classification (every 3 seconds)
            if self.yamnet_model and (loop_start - last_yamnet_time > 3.0):
                last_yamnet_time = loop_start
                try:
                    scores, embeddings, spectrogram = self.yamnet_model(process_chunk)
                    class_id = int(tf.argmax(scores, axis=1)[0])
                    sound_class = f"yamnet_class_{class_id}"
                except Exception as e:
                    logger.error(f"YAMNet error: {e}")

            percept = AuditoryPercept(
                timestamp=loop_start,
                voice_present=voice_present,
                transcript=transcript,
                sound_class=sound_class,
                speaker_id="unknown",
                tone_signal=tone_signal
            )
            
            with self._percept_lock:
                if loop_start - last_yamnet_time <= 3.0 and sound_class == "unknown":
                    percept.sound_class = self.latest_percept.sound_class
                self.latest_percept = percept

        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
