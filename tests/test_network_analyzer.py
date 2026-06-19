from app.main import _network_history_records, _network_history_summary


def test_network_analyzer_summarizes_prowlarr_fanout_without_urls() -> None:
    history = {
        "records": [
            {
                "id": 12,
                "indexerId": 7,
                "date": "2026-06-19T12:00:00Z",
                "successful": True,
                "eventType": "indexerRss",
                "data": {
                    "host": "danish-media-manager",
                    "categories": "2000",
                    "queryType": "search",
                    "query": "",
                    "limit": "500",
                    "queryResults": "123",
                    "elapsedTime": "456",
                    "cached": "0",
                    "url": "https://indexer.invalid/api?apikey=secret",
                },
            },
            {
                "id": 11,
                "indexerId": 8,
                "date": "2026-06-19T12:00:00Z",
                "successful": False,
                "eventType": "indexerRss",
                "data": {
                    "host": "danish-media-manager",
                    "categories": "5000",
                    "queryType": "search",
                    "query": "",
                    "limit": "500",
                    "queryResults": "0",
                    "elapsedTime": "99",
                    "cached": "0",
                },
            },
            {
                "id": 10,
                "indexerId": 7,
                "date": "2026-06-19T11:59:00Z",
                "successful": True,
                "eventType": "indexerRss",
                "data": {
                    "host": "other-client",
                    "categories": "2000",
                },
            },
        ]
    }

    records = _network_history_records(
        history,
        indexer_names={7: "NZBgeek {DK}", 8: "NZBFinder {DK}"},
        since_id=10,
    )
    summary = _network_history_summary(records)

    assert len(records) == 2
    assert records[0]["indexer"] == "NZBgeek {DK}"
    assert records[0]["media_type"] == "movie"
    assert records[1]["media_type"] == "tv"
    assert "url" not in records[0]
    assert "apikey" not in str(records).lower()
    assert summary["upstream_calls"] == 2
    assert summary["successful"] == 1
    assert summary["failed"] == 1
    assert summary["results"] == 123
