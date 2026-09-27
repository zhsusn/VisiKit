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
