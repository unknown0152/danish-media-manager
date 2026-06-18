from app.config import Settings
from app.models import MediaTarget, MediaType


def targets_for(settings: Settings, media_type: MediaType) -> list[MediaTarget]:
    raw = settings.movie_targets if media_type == "movie" else settings.tv_targets
    return parse_targets(raw, media_type)


def all_targets(settings: Settings) -> dict[str, list[MediaTarget]]:
    return {
        "movie": targets_for(settings, "movie"),
        "tv": targets_for(settings, "tv"),
    }


def parse_targets(raw: str, media_type: MediaType) -> list[MediaTarget]:
    targets: list[MediaTarget] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if "=" in entry:
            label, path = entry.split("=", 1)
        else:
            path = entry
            label = path.rstrip("/").rsplit("/", 1)[-1] or path
        label = label.strip()
        path = path.strip()
        if label and path:
            targets.append(MediaTarget(media_type=media_type, label=label, path=path))
    return targets


def target_for_path(settings: Settings, media_type: MediaType, path: str | None) -> MediaTarget | None:
    targets = targets_for(settings, media_type)
    if path:
        for target in targets:
            if target.path == path:
                return target
    return targets[0] if targets else None
