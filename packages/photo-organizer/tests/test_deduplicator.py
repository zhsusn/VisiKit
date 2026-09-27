"""
HEIF 初始化容错降级测试（步骤1）

pytest 执行目录：packages/photo-organizer/（包根）
覆盖测试点：初始化失败降级、KeyboardInterrupt/SystemExit 传播、
缺 pillow-heif 环境降级、pillow-heif 真实编解码（缺依赖时 skip）。
"""

import hashlib
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# 从包根运行时保证可导入 src 下的包（无需额外 conftest.py）
_SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import photo_organizer.deduplicator as dedup_mod  # noqa: E402
from photo_organizer.deduplicator import Deduplicator  # noqa: E402


@pytest.fixture
def fresh_heif(monkeypatch):
    """重置 HEIF 初始化状态，便于模拟各类初始化结果。"""
    monkeypatch.setattr(dedup_mod, "_heif_initialized", False)
    monkeypatch.setattr(dedup_mod, "heif_degraded", False)
    yield


def _fake_heif(side_effect):
    return types.SimpleNamespace(
        register_heif_opener=mock.Mock(side_effect=side_effect)
    )


def test_heif_init_fail_runtime_error_degrades(tmp_path, monkeypatch, fresh_heif):
    """初始化抛出非中断类 Exception：全局降级，HEIC 仅精确哈希，扫描不中断。"""
    monkeypatch.setattr(
        dedup_mod, "pillow_heif", _fake_heif(RuntimeError("init boom"))
    )
    dedup_mod.initialize_heif()

    assert dedup_mod.heif_degraded is True

    heic = tmp_path / "a.heic"
    payload = b"broken-heic-bytes"
    heic.write_bytes(payload)

    dedup = Deduplicator()
    # HEIC 跳过感知哈希
    assert dedup.compute_image_hash(heic) is None
    # 精确哈希正常
    assert dedup.compute_file_hash(heic) == hashlib.md5(payload).hexdigest()
    # 扫描不中断：add_photo 正常完成，进入精确索引、不进入感知索引
    dedup.add_photo(heic)
    indexed = [p for paths in dedup.exact_hashes.values() for p in paths]
    assert heic in indexed
    assert all(heic not in paths for paths in dedup.image_hashes.values())


def test_heif_init_fail_keyboard_interrupt_propagates(monkeypatch, fresh_heif):
    """KeyboardInterrupt 不被容错逻辑吞掉，向外传播且不进入降级。"""
    monkeypatch.setattr(
        dedup_mod, "pillow_heif", _fake_heif(KeyboardInterrupt())
    )
    with pytest.raises(KeyboardInterrupt):
        dedup_mod.initialize_heif()
    assert dedup_mod.heif_degraded is False
    assert dedup_mod._heif_initialized is False


def test_heif_init_fail_system_exit_propagates(monkeypatch, fresh_heif):
    """SystemExit 不被容错逻辑吞掉，向外传播且不进入降级。"""
    monkeypatch.setattr(
        dedup_mod, "pillow_heif", _fake_heif(SystemExit(1))
    )
    with pytest.raises(SystemExit):
        dedup_mod.initialize_heif()
    assert dedup_mod.heif_degraded is False
    assert dedup_mod._heif_initialized is False


def test_heif_init_fail_missing_dependency_degrades(tmp_path, monkeypatch, fresh_heif):
    """环境未安装 pillow-heif：HEIC pHash 为 None、精确哈希正常、扫描继续。"""
    monkeypatch.setattr(dedup_mod, "pillow_heif", None)
    dedup_mod.initialize_heif()
    assert dedup_mod.heif_degraded is True

    heic = tmp_path / "b.HEIC"  # 大写后缀同样按 HEIC 处理
    payload = b"no-pillow-heif-env"
    heic.write_bytes(payload)

    dedup = Deduplicator()
    assert dedup.compute_image_hash(heic) is None
    assert dedup.compute_file_hash(heic) == hashlib.md5(payload).hexdigest()
    dedup.add_photo(heic)  # 不抛异常，扫描不中断
    assert sum(len(v) for v in dedup.exact_hashes.values()) == 1


def test_heif_init_ok_real_codec(tmp_path, monkeypatch, fresh_heif):
    """pillow-heif 真实安装时的正常编解码（缺依赖则 skip，不以 mock 冒充）。"""
    pillow_heif = pytest.importorskip("pillow_heif")
    from PIL import Image

    monkeypatch.setattr(dedup_mod, "pillow_heif", pillow_heif)
    dedup_mod.initialize_heif()
    assert dedup_mod.heif_degraded is False

    heic = tmp_path / "real.heic"
    Image.new("RGB", (48, 32), (12, 130, 210)).save(heic, format="HEIF")

    dedup = Deduplicator()
    phash = dedup.compute_image_hash(heic)
    assert phash is not None
    assert len(dedup.compute_file_hash(heic)) == 32
    dedup.add_photo(heic)
    assert sum(len(v) for v in dedup.image_hashes.values()) == 1


# ── 存量回归用例（评审打回恢复：任务只许新增 HEIF 用例，不得删存量覆盖）──
# 恢复自 arsitect/adopted-base，unittest 风格，pytest 直接收集
import unittest as _unittest
import tempfile as _tempfile
import io as _io
from PIL import Image as _Image
from photo_organizer.deduplicator import DuplicateType

class TestDeduplicator(_unittest.TestCase):
    """测试照片去重器"""
    
    def setUp(self):
        """创建临时测试目录"""
        self.temp_dir = _tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)
        self.test_dir.mkdir(exist_ok=True)
    
    def tearDown(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_image(self, path: Path, color: tuple = (255, 0, 0), size: tuple = (100, 100)):
        """创建测试图片"""
        img = _Image.new('RGB', size, color=color)
        img.save(path)
        return path
    
    def test_exact_duplicate_detection(self):
        """测试精确重复检测"""
        # 创建两个完全相同的文件
        img1 = self.create_image(self.test_dir / "photo1.jpg")
        img2 = self.create_image(self.test_dir / "photo2.jpg")
        
        dedup = Deduplicator()
        dedup.add_photo(img1)
        dedup.add_photo(img2)
        
        groups = list(dedup.find_exact_duplicates())
        
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].duplicate_type, DuplicateType.EXACT)
        self.assertEqual(len(groups[0].photos), 2)
    
    def test_no_duplicate(self):
        """测试无重复情况"""
        img1 = self.create_image(self.test_dir / "photo1.jpg", color=(255, 0, 0))
        img2 = self.create_image(self.test_dir / "photo2.jpg", color=(0, 255, 0))
        
        dedup = Deduplicator()
        dedup.add_photo(img1)
        dedup.add_photo(img2)
        
        groups = list(dedup.find_exact_duplicates())
        
        self.assertEqual(len(groups), 0)
    
    def test_similar_detection(self):
        """测试相似照片检测"""
        # 创建一张图片和它的缩略图
        img1 = self.create_image(self.test_dir / "original.jpg", size=(400, 400))
        
        # 创建缩略图
        img = _Image.open(img1)
        thumb = img.resize((200, 200))
        thumb_path = self.test_dir / "thumbnail.jpg"
        thumb.save(thumb_path)
        
        dedup = Deduplicator(similarity_threshold=10)
        dedup.add_photo(img1)
        dedup.add_photo(thumb_path)
        
        groups = list(dedup.find_similar_duplicates())
        
        self.assertGreaterEqual(len(groups), 0)  # 相似检测可能有误差


if __name__ == '__main__':
    unittest.main()
