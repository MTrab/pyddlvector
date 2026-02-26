from __future__ import annotations

import pytest

from pyddlvector.exceptions import VectorProtocolError
from pyddlvector.statistics import (
    RobotStatistics,
    fetch_lifetime_statistics,
    parse_lifetime_statistics_jdoc,
)


def test_parse_lifetime_statistics_jdoc() -> None:
    stats = parse_lifetime_statistics_jdoc(
        '{"Alive.seconds": 45754588, "BStat.ReactedToTriggerWord": 786, '
        '"FeatureType.Utility": 61, "Odom.Body": 733912608810, "Pet.ms": 2413967}'
    )

    assert isinstance(stats, RobotStatistics)
    assert stats.days_alive == 529
    assert stats.reacted_to_trigger_word == 786
    assert stats.utility_features_used == 61
    assert stats.seconds_petted == 2413
    assert stats.distance_moved_cm == 73391


def test_parse_lifetime_statistics_jdoc_missing_fields() -> None:
    with pytest.raises(VectorProtocolError):
        parse_lifetime_statistics_jdoc('{"Alive.seconds": 100}')


@pytest.mark.asyncio
async def test_fetch_lifetime_statistics_uses_raw_rpc_path_when_stub_lacks_method() -> None:
    class FakeClient:
        class Stub:
            pass

        def __init__(self) -> None:
            self.stub = self.Stub()

        async def unary_unary(self, path: str, request, **kwargs):  # type: ignore[no-untyped-def]
            del request, kwargs
            assert path == "/Anki.Vector.external_interface.ExternalInterface/PullJdocs"

            class FakeDoc:
                json_doc = (
                    '{"Alive.seconds": 86400, "BStat.ReactedToTriggerWord": 1, '
                    '"FeatureType.Utility": 2, "Pet.ms": 3000, "Stim.CumlPosDelta": 250}'
                )

            class FakeNamedJdoc:
                jdoc_type = 1
                doc = FakeDoc()

            class FakeResponse:
                named_jdocs = [FakeNamedJdoc()]

            return FakeResponse()

    stats = await fetch_lifetime_statistics(FakeClient(), timeout=5)
    assert stats.days_alive == 1
    assert stats.reacted_to_trigger_word == 1
    assert stats.utility_features_used == 2
    assert stats.seconds_petted == 3
    assert stats.distance_moved_cm == 25
