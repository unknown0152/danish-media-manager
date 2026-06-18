from app.models import IndexerStatus
from app.prowlarr import diagnostics_from_payloads


def test_diagnostics_map_indexer_status_to_safe_names() -> None:
    diagnostics = diagnostics_from_payloads(
        [IndexerStatus(id=7, name="OldBoys {DK}")],
        [
            {
                "indexerId": 7,
                "disabledTill": "2026-06-18T20:00:00Z",
                "initialFailure": "2026-06-18T19:00:00Z",
                "mostRecentFailure": "2026-06-18T19:55:00Z",
                "escalationLevel": "warning",
                "apiKey": "should-not-appear",
            }
        ],
        [{"source": "Indexer", "type": "error", "message": "OldBoys unavailable"}],
    )

    dumped = diagnostics.model_dump()
    assert dumped["indexer_failures"][0]["name"] == "OldBoys {DK}"
    assert dumped["indexer_failures"][0]["level"] == "warning"
    assert dumped["health"][0]["message"] == "OldBoys unavailable"
    assert "apikey" not in str(dumped).lower()
