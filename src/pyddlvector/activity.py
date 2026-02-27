"""Robot activity helpers derived from event stream payloads."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .messaging import protocol

ROBOT_STATUS_IS_FALLING = int(protocol.ROBOT_STATUS_IS_FALLING)
ROBOT_STATUS_IS_PICKED_UP = int(protocol.ROBOT_STATUS_IS_PICKED_UP)
ROBOT_STATUS_CLIFF_DETECTED = int(protocol.ROBOT_STATUS_CLIFF_DETECTED)
ROBOT_STATUS_IS_BEING_HELD = int(protocol.ROBOT_STATUS_IS_BEING_HELD)
ROBOT_STATUS_IS_PICKING_OR_PLACING = int(protocol.ROBOT_STATUS_IS_PICKING_OR_PLACING)
ROBOT_STATUS_IS_CARRYING_BLOCK = int(protocol.ROBOT_STATUS_IS_CARRYING_BLOCK)
ROBOT_STATUS_ARE_WHEELS_MOVING = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
ROBOT_STATUS_IS_PATHING = int(protocol.ROBOT_STATUS_IS_PATHING)
ROBOT_STATUS_IS_BUTTON_PRESSED = int(protocol.ROBOT_STATUS_IS_BUTTON_PRESSED)
OBJECT_TYPE_LIGHTCUBE = int(protocol.BLOCK_LIGHTCUBE1)
OBJECT_TYPE_CHARGER = int(protocol.CHARGER_BASIC)
LOOKING_PREFIX = "Looking for "


def describe_robot_activity(
    robot_state: Any,
    *,
    saw_face_search: bool = False,
    saw_charger_search: bool = False,
    saw_cube_search: bool = False,
    saw_object_search: bool = False,
) -> str:
    """Map a robot_state payload and recent search signals to a user-facing activity."""
    left_speed = abs(float(getattr(robot_state, "left_wheel_speed_mmps", 0.0)))
    right_speed = abs(float(getattr(robot_state, "right_wheel_speed_mmps", 0.0)))
    status = int(getattr(robot_state, "status", 0))
    wheels_moving = bool(status & ROBOT_STATUS_ARE_WHEELS_MOVING)
    is_pathing = bool(status & ROBOT_STATUS_IS_PATHING)
    is_exploring = wheels_moving or (left_speed + right_speed) > 5.0

    touch_data = getattr(robot_state, "touch_data", None)
    being_touched = bool(getattr(touch_data, "is_being_touched", False))

    carrying_object_id = int(getattr(robot_state, "carrying_object_id", -1))
    is_carrying_object = carrying_object_id >= 0

    if status & ROBOT_STATUS_IS_FALLING:
        return "Falling"
    if status & ROBOT_STATUS_CLIFF_DETECTED:
        return "Cliff detected"
    if status & ROBOT_STATUS_IS_BEING_HELD:
        return "Being held"
    if status & ROBOT_STATUS_IS_PICKED_UP:
        return "Picked up"
    if is_pathing and saw_face_search:
        return "Looking for faces"
    if is_pathing and saw_charger_search:
        return "Looking for charger"
    if is_pathing and saw_cube_search:
        return "Looking for cubes"
    if is_pathing and saw_object_search:
        return "Looking for objects"
    if status & ROBOT_STATUS_IS_PICKING_OR_PLACING:
        return "Picking or placing object"
    if status & ROBOT_STATUS_IS_CARRYING_BLOCK or is_carrying_object:
        return "Carrying an object"
    if is_exploring:
        return "Exploring"
    if status & ROBOT_STATUS_IS_BUTTON_PRESSED:
        return "Button pressed"
    if being_touched:
        return "Being touched"
    return "Ready"


@dataclass(slots=True)
class RobotActivityTracker:
    """Tracks recent event signals used to classify robot activity."""

    search_signal_window_seconds: float = 3.0
    exploring_hold_seconds: float = 3.0
    action_hold_seconds: float = 4.0
    _last_face_search_monotonic: float | None = None
    _last_charger_search_monotonic: float | None = None
    _last_cube_search_monotonic: float | None = None
    _last_object_search_monotonic: float | None = None
    _last_exploring_monotonic: float | None = None
    _last_action_activity: str | None = None
    _last_action_monotonic: float | None = None

    @property
    def saw_face_search(self) -> bool:
        return self._last_face_search_monotonic is not None

    @property
    def saw_charger_search(self) -> bool:
        return self._last_charger_search_monotonic is not None

    @property
    def saw_cube_search(self) -> bool:
        return self._last_cube_search_monotonic is not None

    @property
    def saw_object_search(self) -> bool:
        return self._last_object_search_monotonic is not None

    def observe_event(self, event: Any, *, now_monotonic: float | None = None) -> None:
        """Update search signals from a shared.Event payload."""
        now_value = time.monotonic() if now_monotonic is None else now_monotonic
        event_type = event.WhichOneof("event_type")

        if event_type == "robot_observed_face":
            self._last_face_search_monotonic = now_value
            return
        if event_type != "object_event":
            return

        object_event = event.object_event
        object_event_type = object_event.WhichOneof("object_event_type")
        if object_event_type != "robot_observed_object":
            return

        observed_object = object_event.robot_observed_object
        object_type = int(getattr(observed_object, "object_type", 0))
        if object_type == OBJECT_TYPE_CHARGER:
            self._last_charger_search_monotonic = now_value
            return
        if object_type == OBJECT_TYPE_LIGHTCUBE:
            self._last_cube_search_monotonic = now_value
        else:
            self._last_object_search_monotonic = now_value

    def activity_from_robot_state(
        self,
        robot_state: Any,
        *,
        now_monotonic: float | None = None,
    ) -> str:
        """Describe current activity using tracked event signals."""
        now_value = time.monotonic() if now_monotonic is None else now_monotonic
        activity = describe_robot_activity(
            robot_state,
            saw_face_search=self._is_recent_search(self._last_face_search_monotonic, now_value),
            saw_charger_search=self._is_recent_search(
                self._last_charger_search_monotonic,
                now_value,
            ),
            saw_cube_search=self._is_recent_search(self._last_cube_search_monotonic, now_value),
            saw_object_search=self._is_recent_search(
                self._last_object_search_monotonic,
                now_value,
            ),
        )
        if activity.startswith(LOOKING_PREFIX):
            self._last_action_activity = activity
            self._last_action_monotonic = now_value
            return activity
        if (
            activity in {"Exploring", "Ready"}
            and self._last_action_activity is not None
            and self._is_recent_window(
                self._last_action_monotonic, now_value, window=self.action_hold_seconds
            )
        ):
            return self._last_action_activity
        if activity == "Exploring":
            self._last_exploring_monotonic = now_value
            return activity
        if (
            activity == "Ready"
            and self._last_exploring_monotonic is not None
            and (now_value - self._last_exploring_monotonic) <= self.exploring_hold_seconds
        ):
            return "Exploring"
        return activity

    def _is_recent_search(self, event_time: float | None, now_monotonic: float) -> bool:
        return self._is_recent_window(
            event_time,
            now_monotonic,
            window=self.search_signal_window_seconds,
        )

    def _is_recent_window(
        self,
        event_time: float | None,
        now_monotonic: float,
        *,
        window: float,
    ) -> bool:
        if event_time is None:
            return False
        return (now_monotonic - event_time) <= window
