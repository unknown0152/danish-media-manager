# Sample Data For UI Design

These examples are simplified but realistic enough for mockups.

## Status

```json
{
  "app": "Danish Media Manager",
  "prowlarr_url": "http://prowlarr:9696",
  "prowlarr_ready": true,
  "altmount_url": "http://danish-intelligence:9699/altmount",
  "altmount_ready": true
}
```

## Search Response

```json
{
  "query": "Big Hero 6 2014",
  "media_type": "movie",
  "metadata": {
    "title": "Big Hero 6",
    "year": 2014,
    "overview": "A robotics prodigy forms a superhero team to uncover a mystery.",
    "poster_url": "https://image.tmdb.org/t/p/w342/example.jpg",
    "source": "tmdb",
    "tmdb_id": "177572",
    "imdb_id": "tt2245084"
  },
  "total": 48,
  "accepted": 7,
  "rejected": 41,
  "indexers": [
    { "id": 1, "name": "NZBgeek {DK}", "total": 18, "accepted": 3, "best_score": 11000 },
    { "id": 2, "name": "NZB.life {DK}", "total": 12, "accepted": 2, "best_score": 9800 },
    { "id": 3, "name": "DrunkenSlug {DK}", "total": 18, "accepted": 2, "best_score": 9100 }
  ],
  "quality": {
    "resolutions": { "2160p": 8, "1080p": 30, "720p": 10 },
    "sources": { "WEB-DL": 32, "BluRay": 13, "HDTV": 3 },
    "verdicts": { "accepted": 7, "rejected": 41 },
    "accepted_by_resolution": { "2160p": 2, "1080p": 5 },
    "best_score": 11000,
    "best_resolution": "2160p",
    "best_source": "WEB-DL"
  },
  "rejection_summary": {
    "Wrong year": 11,
    "Below minimum resolution": 8,
    "No Danish/NORDiC signal": 22
  },
  "warning_summary": {
    "NORDiC implies Danish subtitles but is not confirmed": 4
  },
  "releases": [
    {
      "result_id": "cached-release-id-1",
      "title": "Big.Hero.6.2014.2160p.DSNP.WEB-DL.MULTI.DDP.5.1.HDR10.H.265-OldT.DanishAudio",
      "indexer": "NZBgeek {DK}",
      "age": 113,
      "size": 19112604467,
      "indexer_id": 1,
      "quality": {
        "resolution": "2160p",
        "source": "WEB-DL",
        "codec": "H.265",
        "audio": "DDP 5.1",
        "release_group": "OldT"
      },
      "indexer_attrs": {
        "language": ["Danish", "English"],
        "subs": ["Danish", "English", "Norwegian", "Swedish"],
        "audio": ["Danish", "English"]
      },
      "score": {
        "score": 11000,
        "verdict": "accepted",
        "reasons": [
          "Exact title/year match",
          "2160p WEB-DL",
          "Confirmed Danish audio",
          "Nordic subtitle set"
        ]
      },
      "decision": {
        "accepted": true,
        "grab_allowed": true,
        "rejections": [],
        "warnings": []
      }
    },
    {
      "result_id": "cached-release-id-2",
      "title": "Big.Hero.6.2014.1080p.WEB-DL.NORDiC.H264-GROUP",
      "indexer": "NZB.life {DK}",
      "age": 22,
      "size": 8589934592,
      "indexer_id": 2,
      "quality": {
        "resolution": "1080p",
        "source": "WEB-DL",
        "codec": "H.264",
        "audio": "Unknown",
        "release_group": "GROUP"
      },
      "indexer_attrs": {
        "subs": ["Danish", "Norwegian", "Swedish", "Finnish"]
      },
      "score": {
        "score": 7600,
        "verdict": "accepted",
        "reasons": [
          "Exact title/year match",
          "NORDiC release",
          "Danish subtitles from indexer attrs"
        ]
      },
      "decision": {
        "accepted": true,
        "grab_allowed": true,
        "rejections": [],
        "warnings": ["Danish audio not confirmed"]
      }
    }
  ]
}
```

## Wanted Requests

```json
[
  {
    "id": 42,
    "created_at": "2026-06-22T20:15:01Z",
    "updated_at": "2026-06-22T20:17:44Z",
    "query": "Inside Out 2 2024",
    "media_type": "movie",
    "min_resolution": "1080p",
    "target_path": "/media/kids-movies",
    "target_label": "Kids Movies",
    "metadata_title": "Inside Out 2",
    "metadata_year": 2024,
    "metadata_poster_url": "https://image.tmdb.org/t/p/w342/example.jpg",
    "metadata_tmdb_id": "1022789",
    "external_source": "seerr",
    "external_id": "981",
    "origin_source": "seerr",
    "status": "wanted",
    "best_result_id": "cached-release-id-8",
    "best_title": "Inside.Out.2.2024.1080p.WEB-DL.NORDiC-GROUP",
    "best_score": 8900,
    "total": 24,
    "accepted": 2,
    "rejected": 22
  },
  {
    "id": 43,
    "created_at": "2026-06-22T20:18:01Z",
    "updated_at": "2026-06-22T20:19:44Z",
    "query": "The Last of Us",
    "media_type": "tv",
    "min_resolution": "1080p",
    "target_path": "/media/tv",
    "target_label": "TV",
    "metadata_title": "The Last of Us",
    "metadata_year": 2023,
    "metadata_tvdb_id": "392256",
    "external_source": "seerr",
    "external_id": "982",
    "origin_source": "seerr",
    "tv_season": 2,
    "tv_episode": null,
    "status": "grab_failed",
    "best_result_id": null,
    "best_title": null,
    "best_score": null,
    "total": 0,
    "accepted": 0,
    "rejected": 0
  }
]
```

## Monitored TV Items

```json
[
  {
    "id": 1001,
    "request_id": 43,
    "media_type": "tv",
    "item_type": "season",
    "season_number": 2,
    "episode_number": null,
    "status": "wanted",
    "best_result_id": null,
    "best_title": null
  },
  {
    "id": 1002,
    "request_id": 43,
    "media_type": "tv",
    "item_type": "episode",
    "season_number": 2,
    "episode_number": 1,
    "status": "wanted",
    "best_result_id": null,
    "best_title": null
  }
]
```

## Downloads

```json
{
  "queue": [
    {
      "name": "Big.Hero.6.2014.2160p.DSNP.WEB-DL.MULTI.DDP.5.1.HDR10.H.265-OldT.DanishAudio",
      "category": "movies",
      "status": "downloading",
      "percentage": 74.2,
      "speed": "42 MB/s",
      "eta": "00:04:20"
    }
  ],
  "history": [
    {
      "name": "Moana.2.2024.1080p.WEB-DL.NORDiC-GROUP",
      "category": "movies",
      "status": "completed",
      "completed_at": "2026-06-22T19:55:10Z"
    }
  ]
}
```

## Import Health

```json
{
  "ok": true,
  "paths": [
    { "path": "/mnt/altmount", "exists": true, "readable": true, "writable": false },
    { "path": "/mnt/altmount-import", "exists": true, "readable": true, "writable": true },
    { "path": "/media", "exists": true, "readable": true, "writable": true }
  ],
  "warnings": []
}
```

## Indexer Health

```json
[
  {
    "id": 1,
    "name": "NZBgeek {DK}",
    "implementation": "Newznab",
    "protocol": "usenet",
    "enable": true,
    "priority": 25,
    "tags": [12]
  },
  {
    "id": 2,
    "name": "OldBoys {DK}",
    "implementation": "Newznab",
    "protocol": "usenet",
    "enable": false,
    "priority": 25,
    "tags": [12]
  }
]
```

## Network Analyzer Summary

```json
{
  "summary": {
    "total_calls": 12,
    "by_scope": {
      "manual_search": 8,
      "indexer_ui": 1,
      "diagnostics_ui": 1,
      "seerr_sync": 2
    },
    "by_method": {
      "GET": 12
    }
  },
  "calls": [
    {
      "id": 501,
      "created_at": "2026-06-22T20:30:10Z",
      "scope": "manual_search",
      "method": "GET",
      "path": "/api/v1/search",
      "status_code": 200,
      "elapsed_ms": 842,
      "result_count": 100
    }
  ]
}
```

