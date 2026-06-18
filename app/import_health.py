from pathlib import Path

from app.config import Settings
from app.models import ImportHealth, PathProbe, SymlinkProbe


def check_import_health(settings: Settings, max_samples: int = 20) -> ImportHealth:
    import_dir = Path(settings.altmount_import_dir)
    mount_path = Path(settings.altmount_mount_path)
    media_root = Path(settings.media_root)
    warnings: list[str] = []

    import_probe = _probe_path(import_dir)
    mount_probe = _probe_path(mount_path)
    media_probe = _probe_path(media_root)

    if not import_probe.exists:
        warnings.append(f"Import directory is not visible: {import_dir}")
    if not mount_probe.exists:
        warnings.append(f"AltMount FUSE path is not visible: {mount_path}")
    if not media_probe.exists:
        warnings.append(f"Media root is not visible: {media_root}")

    symlink_count = 0
    regular_file_count = 0
    sample_symlinks: list[SymlinkProbe] = []

    if import_probe.is_dir and import_probe.readable:
        for path in _safe_walk(import_dir):
            if path.is_symlink():
                symlink_count += 1
                if len(sample_symlinks) < max_samples:
                    sample_symlinks.append(_probe_symlink(path, mount_path))
            elif path.is_file():
                regular_file_count += 1

    if regular_file_count:
        warnings.append(
            f"Import directory contains {regular_file_count} regular files; expected symlinks"
        )
    if symlink_count and not any(item.target_under_mount for item in sample_symlinks):
        warnings.append(f"Sampled symlinks do not point under {mount_path}")

    return ImportHealth(
        import_dir=import_probe,
        mount_path=mount_probe,
        media_root=media_probe,
        symlink_count=symlink_count,
        regular_file_count=regular_file_count,
        sample_symlinks=sample_symlinks,
        warnings=warnings,
    )


def _probe_path(path: Path) -> PathProbe:
    return PathProbe(
        path=str(path),
        exists=path.exists(),
        is_dir=path.is_dir(),
        readable=path.is_dir() and _readable(path),
    )


def _readable(path: Path) -> bool:
    try:
        next(path.iterdir(), None)
    except OSError:
        return False
    return True


def _safe_walk(root: Path):
    try:
        yield from (path for path in root.rglob("*") if path.exists() or path.is_symlink())
    except OSError:
        return


def _probe_symlink(path: Path, mount_path: Path) -> SymlinkProbe:
    try:
        target = path.resolve(strict=False)
    except OSError:
        target = None
    target_text = str(target) if target else None
    return SymlinkProbe(
        path=str(path),
        target=target_text,
        target_exists=target.exists() if target else False,
        target_under_mount=_is_relative_to(target, mount_path) if target else False,
    )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True
