from app.danish_intelligence import search_params
from app.models import SearchRequest
from app.prowlarr import release_from_item


def test_danish_intelligence_search_params_include_external_ids() -> None:
    params = search_params(
        SearchRequest(
            query="The Batman 2022",
            media_type="movie",
            limit=50,
            tmdb_id="414906",
            imdb_id="tt1877830",
        )
    )

    assert params == {
        "query": "The Batman 2022",
        "media_type": "movie",
        "limit": 50,
        "tmdb_id": "414906",
        "imdb_id": "tt1877830",
    }


def test_rich_indexer_attrs_are_exposed_without_raw_payload() -> None:
    release = release_from_item(
        {
            "title": "The.Batman.2022.NORDiC.2160p.WEB-DL.x265",
            "indexer": "OldBoys {DK}",
            "attrs": {
                "files": ["42"],
                "grabs": ["7"],
                "genre": ["Action"],
            },
        },
        query="The Batman 2022",
        min_resolution="1080p",
        expected_year=2022,
    )

    dumped = release.model_dump()

    assert dumped["indexer_attrs"] == {
        "files": ["42"],
        "grabs": ["7"],
        "genre": ["Action"],
    }
    assert "raw" not in dumped
