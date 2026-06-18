from app.altmount import normalize_downloads


def test_normalize_downloads_handles_empty_queue() -> None:
    status = normalize_downloads(
        {
            "queue": {
                "status": "Idle",
                "paused": False,
                "speed": "0 B/s",
                "mbleft": "0.00",
                "slots": [],
            }
        },
        {"history": {"slots": []}},
    )

    assert status.status == "Idle"
    assert status.paused is False
    assert status.size_left_mb == 0
    assert status.queue == []
    assert status.history == []


def test_normalize_downloads_extracts_queue_and_history_items() -> None:
    status = normalize_downloads(
        {
            "queue": {
                "status": "Downloading",
                "paused": False,
                "kbpersec": "1200",
                "mbleft": "512.5",
                "slots": [
                    {
                        "nzo_id": "SABnzbd_nzo_abc",
                        "name": "The.Batman.2022.NORDiC.2160p.BluRay",
                        "cat": "movies",
                        "mb": "24576",
                        "percentage": "42",
                        "timeleft": "00:12:00",
                        "apikey": "should-not-appear",
                    }
                ],
            }
        },
        {
            "history": {
                "slots": [
                    {
                        "id": "done-1",
                        "nzb_name": "Superman.2025.NORDiC.1080p.WEB-DL",
                        "category": "movies",
                        "size": "10.5 GB",
                        "status": "Completed",
                    }
                ]
            }
        },
    )

    dumped = status.model_dump()
    assert dumped["queue"][0]["name"] == "The.Batman.2022.NORDiC.2160p.BluRay"
    assert dumped["queue"][0]["progress_percent"] == 42
    assert dumped["history"][0]["size_mb"] == 10.5 * 1024
    assert "apikey" not in str(dumped).lower()
