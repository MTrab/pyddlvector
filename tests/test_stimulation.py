from __future__ import annotations

from types import SimpleNamespace

from pyddlvector.stimulation import RobotStimulation, parse_stimulation_info


def test_parse_stimulation_info() -> None:
    payload = SimpleNamespace(
        value=0.42,
        velocity=0.11,
        accel=-0.03,
        value_before_event=0.39,
        min_value=0.0,
        max_value=1.0,
        emotion_events=[" Frustrated ", "", "Excited"],
    )

    stimulation = parse_stimulation_info(payload)

    assert isinstance(stimulation, RobotStimulation)
    assert stimulation.value == 0.42
    assert stimulation.velocity == 0.11
    assert stimulation.accel == -0.03
    assert stimulation.value_before_event == 0.39
    assert stimulation.min_value == 0.0
    assert stimulation.max_value == 1.0
    assert stimulation.emotion_events == ("Frustrated", "Excited")
