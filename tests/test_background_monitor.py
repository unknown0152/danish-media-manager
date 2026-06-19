from app import main
from app.config import Settings
from app.models import WantedRetryResult


def test_background_monitor_runs_for_wanted_without_seerr_key() -> None:
    settings = Settings(SEERR_API_KEY="", WANTED_SEARCH_ENABLED=True)

    assert main.background_monitor_enabled(settings) is True


def test_background_monitor_can_be_disabled_without_seerr_or_wanted() -> None:
    settings = Settings(
        SEERR_API_KEY="",
        SEERR_SYNC_ENABLED=False,
        RECENT_FEED_SYNC_ENABLED=False,
        WANTED_SEARCH_ENABLED=False,
    )

    assert main.background_monitor_enabled(settings) is False


def test_wanted_monitor_runs_even_when_seerr_sync_fails(monkeypatch, tmp_path) -> None:
    calls: list[int] = []

    def failing_seerr_sync(**kwargs):
        raise RuntimeError("seerr offline")

    def recording_wanted_retry(**kwargs):
        calls.append(kwargs["limit"])
        return WantedRetryResult()

    monkeypatch.setattr(main, "sync_seerr_requests", failing_seerr_sync)
    monkeypatch.setattr(main, "retry_wanted_requests", recording_wanted_retry)

    settings = Settings(
        DATABASE_PATH=str(tmp_path / "dmm.db"),
        SEERR_API_KEY="seerr-key",
        SEERR_SYNC_ENABLED=True,
        WANTED_SEARCH_ENABLED=True,
        WANTED_SEARCH_MAX_PER_CYCLE=7,
    )

    main.run_background_monitor_cycle(settings)

    assert calls == [7]
