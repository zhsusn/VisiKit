import hashlib
from pathlib import Path
from PIL import Image
import pytest
from src.photo_organizer.deduplicator import (
    Deduplicator,
    initialize_heif,
)
import src.photo_organizer.deduplicator as dedup_mod


class TestDeduplicatorRegression:
    """存量回归用例，不得删除"""
    def test_exact_duplicate_detection(self, tmp_path):
        file1 = tmp_path / "a.jpg"
        file2 = tmp_path / "b.jpg"
        content = b"test exact duplicate content"
        file1.write_bytes(content)
        file2.write_bytes(content)

        dedup = Deduplicator()
        dedup.add_photo(file1)
        dedup.add_photo(file2)

        groups = list(dedup.find_exact_duplicates())
        assert len(groups) == 1
        assert len(groups[0].photos) == 2
        assert groups[0].duplicate_type.value == "exact"

    def test_no_duplicate(self, tmp_path):
        file1 = tmp_path / "a.jpg"
        file2 = tmp_path / "b.jpg"
        file1.write_bytes(b"unique content 1")
        file2.write_bytes(b"unique content 2")

        dedup = Deduplicator()
        dedup.add_photo(file1)
        dedup.add_photo(file2)

        assert len(list(dedup.find_exact_duplicates())) == 0
        assert len(list(dedup.find_similar_duplicates())) == 0

    def test_similar_detection(self, tmp_path):
        file1 = tmp_path / "a.jpg"
        file2 = tmp_path / "b.jpg"
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(255, 5, 5))
        img1.save(file1)
        img2.save(file2)

        dedup = Deduplicator(similarity_threshold=10)
        dedup.add_photo(file1)
        dedup.add_photo(file2)

        groups = list(dedup.find_similar_duplicates())
        assert len(groups) == 1
        assert len(groups[0].photos) == 2
        assert groups[0].duplicate_type.value == "similar"


class TestHeifInitFail:
    """HEIF初始化容错降级测试"""
    @pytest.fixture(autouse=True)
    def reset_heif_state(self):
        original_pillow_heif = dedup_mod.pillow_heif
        original_degraded = dedup_mod.heif_degraded
        original_initialized = dedup_mod._heif_initialized

        dedup_mod.heif_degraded = False
        dedup_mod._heif_initialized = False

        yield

        dedup_mod.pillow_heif = original_pillow_heif
        dedup_mod.heif_degraded = original_degraded
        dedup_mod._heif_initialized = original_initialized

    def test_heif_init_fail_runtime_error(self, tmp_path, monkeypatch):
        class MockPillowHeif:
            @staticmethod
            def register_heif_opener():
                raise RuntimeError("HEIF initialization failed")

        monkeypatch.setattr(dedup_mod, "pillow_heif", MockPillowHeif())

        initialize_heif()
        assert dedup_mod.heif_degraded is True
        assert dedup_mod._heif_initialized is True

        heic_file = tmp_path / "test.HEIC"
        test_content = b"fake heic file content"
        heic_file.write_bytes(test_content)

        dedup = Deduplicator()
        expected_exact = hashlib.md5(test_content).hexdigest()
        assert dedup.compute_file_hash(heic_file) == expected_exact
        assert dedup.compute_image_hash(heic_file) is None

    def test_heif_init_fail_keyboard_interrupt(self, monkeypatch):
        class MockPillowHeif:
            @staticmethod
            def register_heif_opener():
                raise KeyboardInterrupt()

        monkeypatch.setattr(dedup_mod, "pillow_heif", MockPillowHeif())

        with pytest.raises(KeyboardInterrupt):
            initialize_heif()
        assert dedup_mod.heif_degraded is False
        assert dedup_mod._heif_initialized is False

    def test_heif_init_fail_system_exit(self, monkeypatch):
        class MockPillowHeif:
            @staticmethod
            def register_heif_opener():
                raise SystemExit(1)

        monkeypatch.setattr(dedup_mod, "pillow_heif", MockPillowHeif())

        with pytest.raises(SystemExit):
            initialize_heif()
        assert dedup_mod.heif_degraded is False
        assert dedup_mod._heif_initialized is False

    def test_heif_init_fail_missing_dependency(self, tmp_path, monkeypatch):
        monkeypatch.setattr(dedup_mod, "pillow_heif", None)

        initialize_heif()
        assert dedup_mod.heif_degraded is True
        assert dedup_mod._heif_initialized is True

        heic_file = tmp_path / "test.heic"
        test_content = b"fake heic without dependency"
        heic_file.write_bytes(test_content)

        dedup = Deduplicator()
        assert dedup.compute_file_hash(heic_file) == hashlib.md5(test_content).hexdigest()
        assert dedup.compute_image_hash(heic_file) is None
