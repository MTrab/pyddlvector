from __future__ import annotations

from types import SimpleNamespace

from pyddlvector.activity import RobotActivityTracker, describe_robot_activity
from pyddlvector.messaging import protocol


class _ObjectEvent:
    def __init__(self, object_event_type: str, payload: object) -> None:
        self._object_event_type = object_event_type
        if object_event_type == "robot_observed_object":
            self.robot_observed_object = payload

    def WhichOneof(self, _: str) -> str:
        return self._object_event_type


class _Event:
    def __init__(self, event_type: str, payload: object) -> None:
        self._event_type = event_type
        if event_type == "object_event":
            self.object_event = payload
        if event_type == "robot_state":
            self.robot_state = payload

    def WhichOneof(self, _: str) -> str:
        return self._event_type


def _robot_state(*, status: int = 0, left: float = 0.0, right: float = 0.0) -> object:
    return SimpleNamespace(
        status=status,
        left_wheel_speed_mmps=left,
        right_wheel_speed_mmps=right,
        touch_data=SimpleNamespace(is_being_touched=False),
        carrying_object_id=-1,
    )


def test_describe_robot_activity_on_charger_is_exploring_from_charger() -> None:
    status = int(protocol.ROBOT_STATUS_IS_ON_CHARGER)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Exploring from charger"


def test_describe_robot_activity_charging_flag_does_not_create_charging_state() -> None:
    status = int(protocol.ROBOT_STATUS_IS_ON_CHARGER | protocol.ROBOT_STATUS_IS_CHARGING)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Exploring from charger"


def test_describe_robot_activity_exploring_when_wheels_move() -> None:
    status = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Exploring"


def test_describe_robot_activity_face_search_over_exploring() -> None:
    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = describe_robot_activity(_robot_state(status=status), saw_face_search=True)
    assert activity == "Looking for faces"


def test_tracker_detects_cube_search() -> None:
    tracker = RobotActivityTracker()
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.BLOCK_LIGHTCUBE1)),
            ),
        )
    )

    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = tracker.activity_from_robot_state(_robot_state(status=status))
    assert activity == "Looking for cubes"


def test_tracker_detects_object_search() -> None:
    tracker = RobotActivityTracker()
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.CHARGER_BASIC)),
            ),
        )
    )

    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = tracker.activity_from_robot_state(_robot_state(status=status))
    assert activity == "Looking for charger"


def test_tracker_distinguishes_charger_from_cube_when_newer() -> None:
    tracker = RobotActivityTracker(search_signal_window_seconds=10.0)
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.BLOCK_LIGHTCUBE1)),
            ),
        ),
        now_monotonic=10.0,
    )
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.CHARGER_BASIC)),
            ),
        ),
        now_monotonic=11.0,
    )
    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = tracker.activity_from_robot_state(_robot_state(status=status), now_monotonic=11.2)
    assert activity == "Looking for charger"


def test_tracker_expires_old_search_signals() -> None:
    tracker = RobotActivityTracker(search_signal_window_seconds=1.0)
    tracker.observe_event(
        _Event(
            "robot_observed_face",
            SimpleNamespace(),
        ),
        now_monotonic=10.0,
    )
    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = tracker.activity_from_robot_state(_robot_state(status=status), now_monotonic=12.0)
    assert activity == "Exploring"


def test_tracker_detects_generic_object_search() -> None:
    tracker = RobotActivityTracker()
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=9999),
            ),
        )
    )
    status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    activity = tracker.activity_from_robot_state(_robot_state(status=status))
    assert activity == "Looking for objects"


def test_tracker_holds_recent_looking_state_over_exploring() -> None:
    tracker = RobotActivityTracker(search_signal_window_seconds=1.0, action_hold_seconds=4.0)
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.CHARGER_BASIC)),
            ),
        ),
        now_monotonic=10.0,
    )
    pathing_status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(_robot_state(status=pathing_status), now_monotonic=10.1)
        == "Looking for charger"
    )

    # Search signal expired, but recent looking action should still hold over exploring.
    exploring_status = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(_robot_state(status=exploring_status), now_monotonic=12.0)
        == "Looking for charger"
    )


def test_tracker_action_hold_expires_back_to_exploring() -> None:
    tracker = RobotActivityTracker(search_signal_window_seconds=1.0, action_hold_seconds=2.0)
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.BLOCK_LIGHTCUBE1)),
            ),
        ),
        now_monotonic=10.0,
    )
    pathing_status = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(_robot_state(status=pathing_status), now_monotonic=10.1)
        == "Looking for cubes"
    )

    exploring_status = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(_robot_state(status=exploring_status), now_monotonic=13.0)
        == "Exploring"
    )


def test_picking_or_placing_does_not_override_when_wheels_moving() -> None:
    status = int(
        protocol.ROBOT_STATUS_IS_PICKING_OR_PLACING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING
    )
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Exploring"


def test_tracker_keeps_looking_for_charger_while_base_flips() -> None:
    tracker = RobotActivityTracker(search_signal_window_seconds=3.0, action_hold_seconds=4.0)
    tracker.observe_event(
        _Event(
            "object_event",
            _ObjectEvent(
                "robot_observed_object",
                SimpleNamespace(object_type=int(protocol.CHARGER_BASIC)),
            ),
        ),
        now_monotonic=10.0,
    )

    # Pathing phase.
    pathing = int(protocol.ROBOT_STATUS_IS_PATHING | protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert tracker.activity_from_robot_state(_robot_state(status=pathing), now_monotonic=10.1) == (
        "Looking for charger"
    )
    # Base would otherwise become ready.
    assert tracker.activity_from_robot_state(_robot_state(status=0), now_monotonic=10.8) == (
        "Looking for charger"
    )
    # Base would otherwise be exploring.
    exploring = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(_robot_state(status=exploring), now_monotonic=11.5)
        == "Looking for charger"
    )


def test_describe_robot_activity_cliff_detected() -> None:
    status = int(protocol.ROBOT_STATUS_CLIFF_DETECTED)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Cliff detected"


def test_describe_robot_activity_being_held() -> None:
    status = int(protocol.ROBOT_STATUS_IS_BEING_HELD)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Being held"


def test_describe_robot_activity_sleeping() -> None:
    status = int(protocol.ROBOT_STATUS_CALM_POWER_MODE)
    activity = describe_robot_activity(_robot_state(status=status))
    assert activity == "Sleeping"


def test_describe_robot_activity_fallback_is_ready_not_idle() -> None:
    activity = describe_robot_activity(_robot_state())
    assert activity == "Ready"


def test_tracker_holds_exploring_for_short_pause() -> None:
    tracker = RobotActivityTracker(exploring_hold_seconds=3.0)
    moving_status = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(
            _robot_state(status=moving_status),
            now_monotonic=10.0,
        )
        == "Exploring"
    )

    # Brief pause should remain exploring instead of dropping to fallback state.
    assert tracker.activity_from_robot_state(_robot_state(), now_monotonic=11.5) == "Exploring"


def test_tracker_exploring_hold_expires() -> None:
    tracker = RobotActivityTracker(exploring_hold_seconds=3.0)
    moving_status = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
    assert (
        tracker.activity_from_robot_state(
            _robot_state(status=moving_status),
            now_monotonic=10.0,
        )
        == "Exploring"
    )
    assert tracker.activity_from_robot_state(_robot_state(), now_monotonic=13.5) == "Ready"
