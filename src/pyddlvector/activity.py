"""Robot activity helpers derived from event stream payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .messaging import protocol

ROBOT_STATUS_IS_ON_CHARGER = int(protocol.ROBOT_STATUS_IS_ON_CHARGER)
ROBOT_STATUS_ARE_WHEELS_MOVING = int(protocol.ROBOT_STATUS_ARE_WHEELS_MOVING)
ROBOT_STATUS_IS_PATHING = int(protocol.ROBOT_STATUS_IS_PATHING)
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

    if is_on_charger:
        return "Exploring from charger"
    if is_pathing and saw_face_search:
        return "Looking for faces"
    if is_pathing and saw_cube_search:
        return "Looking for cubes"
    if is_pathing and saw_object_search:
        return "Looking for objects"
    if is_exploring:
        return "Exploring"
    if being_touched:
        return "Being touched"
    if is_carrying_object:
        return "Standing still while carrying an object"
    return "Idle / standing still"


@dataclass(slots=True)
class RobotActivityTracker:
    """Tracks recent event signals used to classify robot activity."""

    saw_face_search: bool = False
    saw_cube_search: bool = False
    saw_object_search: bool = False

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

    def activity_from_robot_state(self, robot_state: Any) -> str:
        """Describe current activity using tracked event signals."""
        return describe_robot_activity(
            robot_state,
            saw_face_search=self.saw_face_search,
            saw_cube_search=self.saw_cube_search,
            saw_object_search=self.saw_object_search,
        )

