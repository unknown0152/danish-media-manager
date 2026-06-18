from app.config import Settings
from app.import_health import check_import_health


def test_import_health_accepts_symlinks_into_altmount(tmp_path) -> None:
    import_dir = tmp_path / "altmount-import"
    mount_path = tmp_path / "altmount"
    media_root = tmp_path / "media"
    release_dir = mount_path / "movies" / "Example.Release"
    release_dir.mkdir(parents=True)
    media_root.mkdir()
    (release_dir / "movie.mkv").write_text("fake", encoding="utf-8")
    (import_dir / "movies").mkdir(parents=True)
    (import_dir / "movies" / "Example.Release").symlink_to(release_dir)

    health = check_import_health(
        Settings(
            ALTMOUNT_IMPORT_DIR=str(import_dir),
            ALTMOUNT_MOUNT_PATH=str(mount_path),
            MEDIA_ROOT=str(media_root),
        )
    )

    assert health.symlink_count == 1
    assert health.regular_file_count == 0
    assert health.sample_symlinks[0].target_under_mount is True
    assert health.warnings == []


def test_import_health_warns_on_regular_files_in_import_dir(tmp_path) -> None:
    import_dir = tmp_path / "altmount-import"
    mount_path = tmp_path / "altmount"
    media_root = tmp_path / "media"
    import_dir.mkdir()
    mount_path.mkdir()
    media_root.mkdir()
    (import_dir / "copied-file.mkv").write_text("fake", encoding="utf-8")

    health = check_import_health(
        Settings(
            ALTMOUNT_IMPORT_DIR=str(import_dir),
            ALTMOUNT_MOUNT_PATH=str(mount_path),
            MEDIA_ROOT=str(media_root),
        )
    )

    assert health.symlink_count == 0
    assert health.regular_file_count == 1
    assert any("regular files" in warning for warning in health.warnings)
