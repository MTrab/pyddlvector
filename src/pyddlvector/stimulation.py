"""Stimulation event helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RobotStimulation:
    """Normalized stimulation payload derived from robot event stream."""

    value: float
    velocity: float
    accel: float
    value_before_event: float
    min_value: float
    max_value: float
    emotion_events: tuple[str, ...]


def parse_stimulation_info(payload: Any) -> RobotStimulation:
    """Normalize a stimulation_info protobuf payload."""
    emotion_events_raw = getattr(payload, "emotion_events", ())
    emotion_events = tuple(
        event.strip() for event in emotion_events_raw if isinstance(event, str) and event.strip()
    )

    return RobotStimulation(
        value=float(getattr(payload, "value", 0.0)),
        velocity=float(getattr(payload, "velocity", 0.0)),
        accel=float(getattr(payload, "accel", 0.0)),
        value_before_event=float(getattr(payload, "value_before_event", 0.0)),
        min_value=float(getattr(payload, "min_value", 0.0)),
        max_value=float(getattr(payload, "max_value", 0.0)),
        emotion_events=emotion_events,
    )
