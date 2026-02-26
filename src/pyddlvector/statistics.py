"""Robot statistics extraction helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .client import VectorClient
from .exceptions import VectorProtocolError
from .messaging import protocol

_PULL_JDOCS_PATH = "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"


@dataclass(frozen=True, slots=True)
class RobotStatistics:
    """Normalized lifetime statistics derived from robot jdocs."""

    days_alive: int
    reacted_to_trigger_word: int
    utility_features_used: int
    seconds_petted: int
    distance_moved_cm: int


def parse_lifetime_statistics_jdoc(raw_json: str) -> RobotStatistics:
    """Parse a ``ROBOT_LIFETIME_STATS`` jdoc JSON payload."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as err:
        raise VectorProtocolError("Lifetime stats jdoc is not valid JSON") from err

    try:
        alive_seconds = int(payload["Alive.seconds"])
        reacted = int(payload["BStat.ReactedToTriggerWord"])
        utility = int(payload["FeatureType.Utility"])
        petted_ms = int(payload["Pet.ms"])
    except (KeyError, TypeError, ValueError) as err:
        raise VectorProtocolError("Lifetime stats jdoc is missing required fields") from err

    # In observed payloads Odom.Body appears to be nanometers traveled.
    # Convert to centimeters by dividing by 10,000,000.
    if "Odom.Body" in payload:
        distance_moved_cm = int(float(payload["Odom.Body"]) / 10_000_000)
    elif "Stim.CumlPosDelta" in payload:
        # Fallback for alternate payloads where cumulative position appears in millimeters.
        distance_moved_cm = int(float(payload["Stim.CumlPosDelta"]) / 10)
    else:
        raise VectorProtocolError("Lifetime stats jdoc is missing distance fields")

    return RobotStatistics(
        days_alive=alive_seconds // 86_400,
        reacted_to_trigger_word=reacted,
        utility_features_used=utility,
        seconds_petted=petted_ms // 1_000,
        distance_moved_cm=distance_moved_cm,
    )


async def fetch_lifetime_statistics(
    client: VectorClient[Any],
    *,
    timeout: float | None = None,
) -> RobotStatistics:
    """Fetch and parse the robot ``ROBOT_LIFETIME_STATS`` jdoc."""
    request = protocol.PullJdocsRequest(jdoc_types=[protocol.ROBOT_LIFETIME_STATS])

    if hasattr(client.stub, "PullJdocs"):
        response = await client.rpc("PullJdocs", request, timeout=timeout)
    else:
        response = await client.unary_unary(
            _PULL_JDOCS_PATH,
            request,
            request_serializer=protocol.PullJdocsRequest.SerializeToString,
            response_deserializer=protocol.PullJdocsResponse.FromString,
            timeout=timeout,
        )

    for named_jdoc in response.named_jdocs:
        if named_jdoc.jdoc_type == protocol.ROBOT_LIFETIME_STATS:
            return parse_lifetime_statistics_jdoc(named_jdoc.doc.json_doc)

    raise VectorProtocolError("ROBOT_LIFETIME_STATS jdoc was not returned by robot")
