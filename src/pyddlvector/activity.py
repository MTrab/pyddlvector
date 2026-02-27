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
ROBOT_STATUS_IS_ON_CHARGER = int(protocol.ROBOT_STATUS_IS_ON_CHARGER)
ROBOT_STATUS_IS_CHARGING = int(protocol.ROBOT_STATUS_IS_CHARGING)
ROBOT_STATUS_IS_PICKING_OR_PLACING = int(protocol.ROBOT_STATUS_IS_PICKING_OR_PLACING)
ROBOT_STATUS_IS_CARRYING_BLOCK = int(protocol.ROBOT_STATUS_IS_CARRYING_BLOCK)
ROBOT_STATUS_ARE_WHEELS_MOVING = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
ROBOT_STATUS_IS_PATHING = int(protocol.ROBOT_STATUS_IS_PATHING)
ROBOT_STATUS_IS_ANIMATING = int(protocol.ROBOT_STATUS_IS_ANIMATING)
ROBOT_STATUS_IS_BUTTON_PRESSED = int(protocol.ROBOT_STATUS_IS_BUTTON_PRESSED)
OBJECT_TYPE_LIGHTCUBE = int(protocol.BLOCK_LIGHTCUBE1)


def describe_robot_activity(
    robot_state: Any,
    *,
    saw_face_search: bool = False,
    saw_cube_search: bool = False,
    saw_object_search: bool = False,
) -> str:
    """Map a robot_state payload and recent search signals to a user-facing activity."""
    left_speed = abs(float(getattr(robot_state, "left_wheel_speed_mmps", 0.0)))
    right_speed = abs(float(getattr(robot_state, "right_wheel_speed_mmps", 0.0)))
    status = int(getattr(robot_state, "status", 0))
    is_on_charger = bool(status & ROBOT_STATUS_IS_ON_CHARGER)
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
    if is_on_charger:
        if status & ROBOT_STATUS_IS_CHARGING:
            return "Charging on charger"
        return "Exploring from charger"
    if is_pathing and saw_face_search:
        return "Looking for faces"
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
    if status & ROBOT_STATUS_IS_ANIMATING:
        return "Animating"
    if status & ROBOT_STATUS_IS_BUTTON_PRESSED:
        return "Button pressed"
    if being_touched:
        return "Being touched"
    if status & ROBOT_STATUS_IS_CHARGING:
        return "Charging"
    return "Ready"


@dataclass(slots=True)
class RobotActivityTracker:
    """Tracks recent event signals used to classify robot activity."""

    saw_face_search: bool = False
    saw_cube_search: bool = False
    saw_object_search: bool = False
    exploring_hold_seconds: float = 3.0
    _last_exploring_monotonic: float | None = None

    def observe_event(self, event: Any) -> None:
        """Update search signals from a shared.Event payload."""
        event_type = event.WhichOneof("event_type")

        if event_type == "robot_observed_face":
            self.saw_face_search = True
            return
        if event_type != "object_event":
            return

        object_event = event.object_event
        object_event_type = object_event.WhichOneof("object_event_type")
        if object_event_type != "robot_observed_object":
            return

        observed_object = object_event.robot_observed_object
        object_type = int(getattr(observed_object, "object_type", 0))
        if object_type == OBJECT_TYPE_LIGHTCUBE:
            self.saw_cube_search = True
        else:
            self.saw_object_search = True

    def activity_from_robot_state(
        self,
        robot_state: Any,
        *,
        now_monotonic: float | None = None,
    ) -> str:
        """Describe current activity using tracked event signals."""
        activity = describe_robot_activity(
            robot_state,
            saw_face_search=self.saw_face_search,
            saw_cube_search=self.saw_cube_search,
            saw_object_search=self.saw_object_search,
        )
        now_value = time.monotonic() if now_monotonic is None else now_monotonic
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
