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

    def test_mixed_success_and_fail_count(self, monkeypatch, tmp_path):
        """测试点7 补强：N 成功 + M 失败混合场景——计数等于 M，成功 HEIC pHash 正常返回。"""
        pytest.importorskip("pillow_heif")  # 成功 HEIC 需真实编解码；缺依赖时 skip 并在 TEST_REPORT.md 区分记录
        dedup_mod._heif_initialized = False
        dedup_mod.initialize_heif()
        img = Image.new('RGB', (50, 50), color='green')
        good_heic = tmp_path / "good.heic"
        img.save(good_heic, format="HEIF")
        bad_heic = tmp_path / "bad.heic"
        bad_heic.write_bytes(b"bad")
        dedup = Deduplicator()
        assert dedup.compute_image_hash(good_heic) is not None
        assert dedup.compute_image_hash(bad_heic) is None
        assert dedup.heic_decode_fail_count == 1

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


# ── 扫描入口接线 + 报告汇总区标注（评审打回修复：start_new_scan 真实入口接线，测试点9/11/12/13/16）──
import argparse as _argparse

from photo_organizer import cli as _cli
from photo_organizer.organizer import OrganizeResult, PhotoOrganizer
from photo_organizer.deduplicator import render_heic_fail_note


def _run_dedup_command(source) -> None:
    """经由真实 CLI 扫描入口（dedup_command）执行一轮去重扫描，而非手动调用内部方法。"""
    args = _argparse.Namespace(source=str(source), threshold=5, similar=False, delete=False)
    _cli.dedup_command(args)


def _mock_heif_init(monkeypatch):
    mock_heif = type('MockPillowHeif', (), {'register_heif_opener': lambda: None})
    monkeypatch.setattr(dedup_mod, "pillow_heif", mock_heif)
    dedup_mod.initialize_heif()


class TestScanEntryReset:
    """测试点9：第二次全新扫描经由真实扫描入口时计数器重置、只统计本轮失败量。"""

    def test_second_scan_via_cli_entry_resets_counter(self, tmp_path, monkeypatch):
        _mock_heif_init(monkeypatch)
        scan1 = tmp_path / "scan1"
        scan1.mkdir()
        (scan1 / "bad1.heic").write_bytes(b"bad")
        _run_dedup_command(scan1)
        assert Deduplicator.heic_decode_fail_count == 1

        # 第二轮全新扫描：仍含 1 张坏 HEIC——若入口未重置计数会累计为 2；
        # 入口重置后只统计本轮失败量，应仍为 1
        scan2 = tmp_path / "scan2"
        scan2.mkdir()
        (scan2 / "bad2.heic").write_bytes(b"bad")
        _run_dedup_command(scan2)
        assert Deduplicator.heic_decode_fail_count == 1

    def test_scan_without_heic_via_entry_shows_zero(self, tmp_path, monkeypatch):
        _mock_heif_init(monkeypatch)
        scan1 = tmp_path / "scan1"
        scan1.mkdir()
        (scan1 / "bad1.heic").write_bytes(b"bad")
        _run_dedup_command(scan1)
        assert Deduplicator.heic_decode_fail_count == 1

        # 无 HEIC 文件的全新扫描：入口重置后计数归 0
        scan2 = tmp_path / "scan2"
        scan2.mkdir()
        img = Image.new('RGB', (10, 10), color='red')
        img.save(scan2 / "ok.jpg", format="JPEG")
        _run_dedup_command(scan2)
        assert Deduplicator.heic_decode_fail_count == 0


class TestHeicFailReportRender:
    """测试点11/12/13：重复报告汇总区 HEIC 解码失败标注（计数>0 显示 / =0 隐藏 / 无单文件实时提示）。"""

    @staticmethod
    def _bad_heic_dir(tmp_path, n):
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        for i in range(n):
            (src / f"bad{i}.heic").write_bytes(b"bad")
        return src

    def test_cli_summary_shows_fail_count(self, tmp_path, monkeypatch, capsys):
        """测试点11：计数>0 时 CLI 终端汇总显示失败数，数值与计数器完全一致。"""
        _mock_heif_init(monkeypatch)
        _run_dedup_command(self._bad_heic_dir(tmp_path, 2))
        out = capsys.readouterr().out
        assert "HEIC解码失败: 2" in out
        assert Deduplicator.heic_decode_fail_count == 2

    def test_cli_summary_hides_when_zero(self, tmp_path, capsys):
        """测试点12：计数=0（无 HEIC 文件）时 CLI 汇总无任何 HEIC 解码失败标注项。"""
        src = tmp_path / "src"
        src.mkdir()
        img = Image.new('RGB', (10, 10), color='blue')
        img.save(src / "a.jpg", format="JPEG")
        _run_dedup_command(src)
        out = capsys.readouterr().out
        assert "HEIC解码失败" not in out

    def test_cli_no_realtime_single_file_notice(self, tmp_path, monkeypatch, capsys):
        """测试点13：HEIC 解码失败时扫描过程无单文件实时失败提示，仅最终汇总按规则展示。

        注：坏 HEIC 内容相同时会进入正常去重结果列表（[exact] 保留/可删除行），
        那是业务输出而非失败提示；故断言「含失败文件名的行不得含失败字样」。
        """
        _mock_heif_init(monkeypatch)
        src = self._bad_heic_dir(tmp_path, 2)
        _run_dedup_command(src)
        captured = capsys.readouterr()
        all_output = captured.out + captured.err
        for line in all_output.splitlines():
            if "bad0.heic" in line or "bad1.heic" in line:
                assert "失败" not in line, f"出现单文件实时失败提示: {line}"
        assert "HEIC解码失败: 2" in captured.out

    def test_detail_report_shows_fail_count(self, tmp_path, monkeypatch):
        """测试点11：计数>0 时整理明细.md 去重区块显示失败数，数值与计数器完全一致。"""
        monkeypatch.setattr(Deduplicator, "heic_decode_fail_count", 3)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        organizer = PhotoOrganizer(output_dir=out_dir)
        organizer._generate_detail_report(OrganizeResult(success=[], skipped=[], failed=[]))
        text = (out_dir / "整理明细.md").read_text(encoding="utf-8")
        assert "## 去重信息" in text
        assert "HEIC解码失败: 3" in text

    def test_detail_report_hides_when_zero(self, tmp_path):
        """测试点12：计数=0（无 HEIC/全成功）时整理明细.md 无去重信息区块、无 HEIC 标注项。"""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        organizer = PhotoOrganizer(output_dir=out_dir)
        organizer._generate_detail_report(OrganizeResult(success=[], skipped=[], failed=[]))
        text = (out_dir / "整理明细.md").read_text(encoding="utf-8")
        assert "去重信息" not in text
        assert "HEIC" not in text

    def test_render_heic_fail_note_direct(self):
        """渲染函数纯逻辑：计数 0/负数隐藏，正数显示且数值一致。"""
        assert render_heic_fail_note(0) == []
        assert render_heic_fail_note(-1) == []
        assert render_heic_fail_note(5) == ["HEIC解码失败: 5 张（已降级为仅精确哈希参与去重）"]


class TestTestReportAnchor:
    """测试点16：TEST_REPORT.md 含 4 个固定场景关键词且结果行标注为通过；skip 场景区分记录。"""

    def test_report_contains_four_scenarios_all_passed(self):
        report = Path(__file__).resolve().parent.parent / "TEST_REPORT.md"
        text = report.read_text(encoding="utf-8")
        for keyword in ("pillow-heif正常", "初始化失败", "解码失败", "无HEIC"):
            rows = [ln for ln in text.splitlines() if keyword in ln]
            assert rows, f"TEST_REPORT.md 缺少固定场景关键词: {keyword}"
            assert any("通过" in ln for ln in rows), f"场景未标注为通过: {keyword}"

    def test_report_records_skip_distinction(self):
        """测试点1 配套：环境缺 pillow-heif 时 skip 的用例在 TEST_REPORT.md 中区分记录。"""
        report = Path(__file__).resolve().parent.parent / "TEST_REPORT.md"
        text = report.read_text(encoding="utf-8")
        assert "区分记录" in text
        assert "skip" in text.lower()


# ── 步骤 2 完成标准机械对齐（plan.md 的 -k 选择器真实可跑）──────────────────
# plan.md 完成标准按 `-k heic_decode_fail_count` 选测试；存量用例为 CamelCase 类名，
# pytest -k 逐字子串匹配（含下划线）不命中。本区块用例名内嵌关键字，让 `-k` 命中数 ≥1
# 且断言覆盖步骤 2 完成标准（计数准确/非HEIC不计数/初始0/重置/大小写归一/降级/混合）。

class TestStepKeywordAlignment:
    """步骤 2 完成标准选择器（pytest -k）的机械对齐用例。"""

    def test_heic_decode_fail_count_rules(self, monkeypatch, tmp_path):
        """步骤2：计数规则——初始为 0 / 非 HEIC 解码失败不计数 / HEIC 累计准确 /
        start_new_scan 重置（测试点9）/ 大小写变体归一（测试点15）/ 降级规则（测试点6）。"""
        _mock_heif_init(monkeypatch)
        assert Deduplicator.heic_decode_fail_count == 0      # 初始值为 0
        dedup = Deduplicator()
        bad_jpg = tmp_path / "bad.jpg"
        bad_jpg.write_bytes(b"invalid jpg")
        assert dedup.compute_image_hash(bad_jpg) is None
        assert dedup.heic_decode_fail_count == 0             # 非 HEIC 不计数
        bad_heic = tmp_path / "bad.heic"
        bad_heic.write_bytes(b"bad")
        assert dedup.compute_image_hash(bad_heic) is None
        assert dedup.heic_decode_fail_count == 1             # 单文件计数准确
        bad_heic2 = tmp_path / "bad2.heic"
        bad_heic2.write_bytes(b"bad")
        assert dedup.compute_image_hash(bad_heic2) is None
        assert dedup.heic_decode_fail_count == 2             # 多文件累计准确
        # start_new_scan 重置（测试点9）：新一轮扫描计数归零，只统计本轮
        dedup.start_new_scan()
        assert dedup.heic_decode_fail_count == 0
        # 大小写变体后缀归一（测试点15）：.HEIC/.Heic 均按 HEIC 计数
        for suffix in (".HEIC", ".Heic"):
            p = tmp_path / f"case{suffix}"
            p.write_bytes(b"bad")
            assert dedup.compute_image_hash(p) is None
            p.unlink()
        assert dedup.heic_decode_fail_count == 2
        # 降级规则（测试点6）：解码失败时 pHash 返回 None，精确哈希仍正常计算
        bad_heic3 = tmp_path / "bad3.heic"
        bad_heic3.write_bytes(b"bad")
        assert dedup.compute_image_hash(bad_heic3) is None
        assert dedup.compute_file_hash(bad_heic3) is not None
        assert dedup.heic_decode_fail_count == 3

    def test_heic_decode_fail_count_mixed_scan(self, monkeypatch, tmp_path):
        """步骤2（测试点7）：N 成功 + M 失败混合扫描——计数=M、成功 HEIC pHash 正常返回。"""
        pytest.importorskip("pillow_heif")  # 成功 HEIC 需真实编解码；缺依赖 skip 并在 TEST_REPORT.md 区分记录
        dedup_mod._heif_initialized = False
        dedup_mod.initialize_heif()
        img = Image.new('RGB', (60, 60), color='orange')
        good = tmp_path / "good.heic"
        img.save(good, format="HEIF")
        bads = [tmp_path / f"bad{i}.heic" for i in range(2)]
        for b in bads:
            b.write_bytes(b"bad")
        dedup = Deduplicator()
        assert dedup.compute_image_hash(good) is not None   # 成功 HEIC pHash 正常
        for b in bads:
            assert dedup.compute_image_hash(b) is None      # 失败 HEIC pHash=None
        assert dedup.heic_decode_fail_count == 2            # 计数只含失败 = M


# ── 步骤 3 完成标准机械对齐（-k heic_full_scan_recalc 真实可跑）──────────────

class TestStep3KeywordAlignment:
    """步骤 3（验证存量 HEIC 重算规则）的选择器对齐用例。"""

    def test_heic_full_scan_recalc_no_reuse(self, monkeypatch, tmp_path):
        """步骤3：全量扫描每次重算 HEIC pHash——无哈希复用、无持久化缓存逻辑。"""
        pytest.importorskip("pillow_heif")  # 真实 HEIC 编解码；缺依赖 skip 并在 TEST_REPORT.md 区分记录
        dedup_mod._heif_initialized = False
        dedup_mod.initialize_heif()
        img = Image.new('RGB', (80, 80), color='purple')
        heic_path = tmp_path / "recalc.heic"
        img.save(heic_path, format="HEIF")
        dedup = Deduplicator()
        call_count = 0
        original = dedup.compute_image_hash

        def wrapper(path):
            nonlocal call_count
            call_count += 1
            return original(path)

        monkeypatch.setattr(dedup, "compute_image_hash", wrapper)
        dedup.start_new_scan()
        dedup.add_photo(heic_path)   # 第 1 轮扫描：重算
        dedup.start_new_scan()       # 新一轮扫描：内存哈希清空
        dedup.add_photo(heic_path)   # 第 2 轮扫描：对同一文件再次重算（无复用）
        assert call_count == 2
        # 无持久化：两轮扫描后扫描根下除源文件外无任何缓存产物落盘
        leftovers = [p.name for p in tmp_path.rglob("*")
                     if p.is_file() and p != heic_path]
        assert leftovers == []
