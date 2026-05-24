from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VisualObject:
    label: str
    confidence: float
    bbox: List[float]  # [x_min, y_min, x_max, y_max] or similar


@dataclass
class TextSegment:
    text: str
    position: List[float]  # bbox or point


@dataclass
class VisualPercept:
    timestamp: float
    objects: List[VisualObject] = field(default_factory=list)
    motion_detected: bool = False
    motion_region: Optional[List[float]] = None
    scene_type: str = "unknown"
    text_in_scene: List[TextSegment] = field(default_factory=list)
    faces_detected: int = 0
    pose_summary: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "objects": [
                {"label": obj.label, "confidence": obj.confidence, "bbox": obj.bbox}
                for obj in self.objects
            ],
            "motion_detected": self.motion_detected,
            "motion_region": self.motion_region,
            "scene_type": self.scene_type,
            "text_in_scene": [
                {"text": t.text, "position": t.position} for t in self.text_in_scene
            ],
            "faces_detected": self.faces_detected,
            "pose_summary": self.pose_summary,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VisualPercept:
        objects = [
            VisualObject(
                label=obj.get("label", "unknown"),
                confidence=float(obj.get("confidence", 0.0)),
                bbox=obj.get("bbox", []),
            )
            for obj in data.get("objects", [])
        ]
        text_in_scene = [
            TextSegment(
                text=t.get("text", ""),
                position=t.get("position", []),
            )
            for t in data.get("text_in_scene", [])
        ]
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            objects=objects,
            motion_detected=bool(data.get("motion_detected", False)),
            motion_region=data.get("motion_region"),
            scene_type=str(data.get("scene_type", "unknown")),
            text_in_scene=text_in_scene,
            faces_detected=int(data.get("faces_detected", 0)),
            pose_summary=str(data.get("pose_summary", "")),
            description=str(data.get("description", "")),
        )


@dataclass
class AuditoryPercept:
    timestamp: float
    voice_present: bool = False
    transcript: str = ""
    sound_class: str = "unknown"
    speaker_id: str = "unknown"
    tone_signal: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "voice_present": self.voice_present,
            "transcript": self.transcript,
            "sound_class": self.sound_class,
            "speaker_id": self.speaker_id,
            "tone_signal": self.tone_signal,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AuditoryPercept:
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            voice_present=bool(data.get("voice_present", False)),
            transcript=str(data.get("transcript", "")),
            sound_class=str(data.get("sound_class", "unknown")),
            speaker_id=str(data.get("speaker_id", "unknown")),
            tone_signal=str(data.get("tone_signal", "")),
        )
