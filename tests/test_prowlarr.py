from app.config import Settings
from app.models import IndexerStatus, SearchRequest
from app.prowlarr import diagnostics_from_payloads, recent_search_params, search_params


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


def test_diagnostics_add_oldboys_hint_when_all_indexers_failed() -> None:
    diagnostics = diagnostics_from_payloads(
        [IndexerStatus(id=1, name="OldBoys {DK}", enable=True)],
        [],
        [
            {
                "source": "IndexerStatusCheck",
                "type": "error",
                "message": "All indexers are unavailable due to failures",
            }
        ],
    )

    assert diagnostics.hints
    assert diagnostics.hints[0].level == "error"
    assert "unsupported Newznab query types" in diagnostics.hints[0].message


def test_search_params_include_subcategories_but_not_arr_ids() -> None:
    params = search_params(
        SearchRequest(
            query="The Batman 2022",
            media_type="movie",
            tmdb_id="414906",
            imdb_id="tt1877830",
        )
    )

    assert "tmdbId" not in params
    assert "imdbId" not in params
    assert params["categories"] == "2010,2030,2040,2045,2050,2070,2080,2090"

    tv_params = search_params(
        SearchRequest(query="The Last of Us 2023", media_type="tv", tvdb_id="392256")
    )

    assert "tvdbId" not in tv_params
    assert tv_params["categories"] == "5010,5020,5030,5040,5045,5050,5080,5090"


def test_search_params_allow_category_overrides() -> None:
    settings = Settings(
        MOVIE_SEARCH_CATEGORIES="2040,2045,2045,bad, 2050",
        TV_SEARCH_CATEGORIES="5040,5045,5070",
    )

    movie_params = search_params(
        SearchRequest(query="The Batman 2022", media_type="movie"),
        settings,
    )
    tv_params = search_params(
        SearchRequest(query="The Last of Us 2023", media_type="tv"),
        settings,
    )

    assert movie_params["categories"] == "2040,2045,2050"
    assert tv_params["categories"] == "5040,5045,5070"


def test_invalid_category_overrides_fall_back_to_defaults() -> None:
    settings = Settings(MOVIE_SEARCH_CATEGORIES="bad", TV_SEARCH_CATEGORIES="")

    movie_params = search_params(
        SearchRequest(query="The Batman 2022", media_type="movie"),
        settings,
    )
    tv_params = search_params(
        SearchRequest(query="The Last of Us 2023", media_type="tv"),
        settings,
    )

    assert movie_params["categories"] == "2010,2030,2040,2045,2050,2070,2080,2090"
    assert tv_params["categories"] == "5010,5020,5030,5040,5045,5050,5080,5090"


def test_recent_search_params_use_arr_style_feed_types() -> None:
    movie_params = recent_search_params("movie", 900)
    tv_params = recent_search_params("tv", 250)

    assert movie_params == {
        "query": "",
        "type": "movie",
        "limit": 500,
        "categories": "2010,2030,2040,2045,2050,2070,2080,2090",
    }
    assert tv_params == {
        "query": "",
        "type": "tvsearch",
        "limit": 250,
        "categories": "5010,5020,5030,5040,5045,5050,5080,5090",
    }
