import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from PIL import Image
import photo_organizer.deduplicator as dedup_mod
from photo_organizer.deduplicator import Deduplicator


@pytest.fixture(autouse=True)
def reset_heif_state():
    dedup_mod.heif_degraded = False
    dedup_mod._heif_initialized = False
    Deduplicator.heic_decode_fail_count = 0
    yield
    dedup_mod.heif_degraded = False
    dedup_mod._heif_initialized = True
    Deduplicator.heic_decode_fail_count = 0


class TestHeifInitFail:
    def test_init_fail_runtime_error(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {
            'register_heif_opener': lambda: (_ for _ in ()).throw(RuntimeError("init fail"))
        })
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        dedup_mod.initialize_heif()
        assert dedup_mod.heif_degraded is True
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            heic_path = Path(f.name)
        dedup = Deduplicator()
        assert dedup.compute_image_hash(heic_path) is None
        assert dedup.compute_file_hash(heic_path) is not None
        heic_path.unlink()

    def test_init_keyboard_interrupt_propagate(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {
            'register_heif_opener': lambda: (_ for _ in ()).throw(KeyboardInterrupt())
        })
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        with pytest.raises(KeyboardInterrupt):
            dedup_mod.initialize_heif()
        assert dedup_mod.heif_degraded is False

    def test_init_system_exit_propagate(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {
            'register_heif_opener': lambda: (_ for _ in ()).throw(SystemExit())
        })
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        with pytest.raises(SystemExit):
            dedup_mod.initialize_heif()
        assert dedup_mod.heif_degraded is False

    def test_missing_pillow_heif_degrade(self, monkeypatch):
        monkeypatch.setattr(dedup_mod, "pillow_heif", None)
        dedup_mod.initialize_heif()
        assert dedup_mod.heif_degraded is True
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            heic_path = Path(f.name)
        dedup = Deduplicator()
        assert dedup.compute_image_hash(heic_path) is None
        assert dedup.compute_file_hash(heic_path) is not None
        heic_path.unlink()


class TestHeicDecodeFailCounter:
    def test_initial_counter_zero(self):
        assert Deduplicator.heic_decode_fail_count == 0

    def test_single_heic_decode_fail_count(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {'register_heif_opener': lambda: None})
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        dedup_mod.initialize_heif()
        dedup = Deduplicator()
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"invalid heic")
            bad_heic = Path(f.name)
        assert dedup.compute_image_hash(bad_heic) is None
        assert dedup.heic_decode_fail_count == 1
        assert dedup.compute_file_hash(bad_heic) is not None
        bad_heic.unlink()

    def test_multiple_heic_fail_count(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {'register_heif_opener': lambda: None})
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        dedup_mod.initialize_heif()
        dedup = Deduplicator()
        paths = []
        for _ in range(2):
            with NamedTemporaryFile(suffix=".heic", delete=False) as f:
                f.write(b"bad")
                paths.append(Path(f.name))
        for p in paths:
            dedup.compute_image_hash(p)
        assert dedup.heic_decode_fail_count == 2
        for p in paths:
            p.unlink()

    def test_non_heic_fail_no_count(self):
        dedup = Deduplicator()
        with NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"invalid jpg")
            bad_jpg = Path(f.name)
        assert dedup.compute_image_hash(bad_jpg) is None
        assert dedup.heic_decode_fail_count == 0
        bad_jpg.unlink()

    def test_case_insensitive_suffix(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {'register_heif_opener': lambda: None})
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        dedup_mod.initialize_heif()
        dedup = Deduplicator()
        for suffix in [".HEIC", ".Heic", ".hEiC"]:
            with NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(b"bad")
                p = Path(f.name)
            dedup.compute_image_hash(p)
            p.unlink()
        assert dedup.heic_decode_fail_count == 3

    def test_scan_reset_counter(self, monkeypatch):
        mock_heif = type('MockPillowHeif', (), {'register_heif_opener': lambda: None})
        monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
        dedup_mod.initialize_heif()
        dedup = Deduplicator()
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"bad")
            p1 = Path(f.name)
        dedup.add_photo(p1)
        assert dedup.heic_decode_fail_count == 1
        dedup.start_new_scan()
        assert dedup.heic_decode_fail_count == 0
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            f.write(b"bad")
            p2 = Path(f.name)
        dedup.add_photo(p2)
        assert dedup.heic_decode_fail_count == 1
        p1.unlink()
        p2.unlink()


class TestRealHeic:
    def test_real_heic_decode_success(self):
        pytest.importorskip("pillow_heif")
        dedup_mod._heif_initialized = False
        dedup_mod.initialize_heif()
        assert dedup_mod.heif_degraded is False
        img = Image.new('RGB', (100, 100), color='red')
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            img.save(f.name, format="HEIF")
            heic_path = Path(f.name)
        dedup = Deduplicator()
        assert dedup.compute_image_hash(heic_path) is not None
        assert dedup.compute_file_hash(heic_path) is not None
        assert dedup.heic_decode_fail_count == 0
        heic_path.unlink()


class TestHeicFullScanRecalc:
    def test_two_scans_full_recalc(self, monkeypatch):
        pytest.importorskip("pillow_heif")
        dedup_mod._heif_initialized = False
        dedup_mod.initialize_heif()
        img = Image.new('RGB', (100, 100), color='blue')
        with NamedTemporaryFile(suffix=".heic", delete=False) as f:
            img.save(f.name, format="HEIF")
            heic_path = Path(f.name)
        dedup = Deduplicator()
        call_count = 0
        original = dedup.compute_image_hash
        def wrapper(path):
            nonlocal call_count
            call_count += 1
            return original(path)
        monkeypatch.setattr(dedup, "compute_image_hash", wrapper)
        dedup.start_new_scan()
        dedup.add_photo(heic_path)
        dedup.start_new_scan()
        dedup.add_photo(heic_path)
        assert call_count == 2
        heic_path.unlink()
