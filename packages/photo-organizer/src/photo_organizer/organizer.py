"""
整理模块 - 按时间/类型组织照片，执行移动/复制/删除操作
"""

import shutil
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Callable
import json

from .scanner import PhotoInfo
from .classifier import PhotoCategory
from .deduplicator import Deduplicator, render_heic_fail_note


class OrganizeMode(Enum):
    """整理模式"""
    COPY = "copy"      # 复制（保留原文件）
    MOVE = "move"      # 移动（不保留原文件）
    SIMULATE = "simulate"  # 模拟（不执行实际操作）


class DateFormat(Enum):
    """日期文件夹格式"""
    YEAR = "%Y"                    # 2024
    YEAR_MONTH = "%Y-%m"           # 2024-03
    YEAR_MONTH_DAY = "%Y-%m-%d"    # 2024-03-21
    YEAR_MONTH_NAME = "%Y/%B"      # 2024/March


@dataclass
class OrganizePlan:
    """整理计划项"""
    source: Path
    target: Path
    operation: str  # copy/move/skip
    photo_info: PhotoInfo = None
    category: PhotoCategory = None
    is_duplicate: bool = False  # 是否为重复文件


@dataclass
class OrganizeResult:
    """整理结果"""
    success: list[OrganizePlan]
    failed: list[tuple[OrganizePlan, str]]
    skipped: list[OrganizePlan]
    output_dir: Path = None
    source_dir: Path = None


class PhotoOrganizer:
    """照片整理器"""
    
    def __init__(
        self,
        output_dir: str | Path,
        source_dir: str | Path = None,
        date_format: DateFormat = DateFormat.YEAR_MONTH,
        recognition_enabled: bool = False,
        recognition_categories: list = None,
        mode: OrganizeMode = OrganizeMode.COPY
    ):
        """
        Args:
            output_dir: 输出目录
            source_dir: 源目录（用于计算相对路径）
            date_format: 日期文件夹格式
            recognition_enabled: 是否启用内容识别
            recognition_categories: 识别类别列表
            mode: 操作模式
        """
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.source_dir = Path(source_dir).expanduser().resolve() if source_dir else None
        self.date_format = date_format
        self.recognition_enabled = recognition_enabled
        self.recognition_categories = recognition_categories or []
        self.mode = mode
        
        # 子目录
        self.organized_dir = self.output_dir / "去重后照片"
        self.duplicates_dir = self.output_dir / "重复照片"
        
        self.plans: list[OrganizePlan] = []
        self.progress_callback: Callable[[int, int, str], None] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]):
        """设置进度回调函数 (current, total, message)"""
        self.progress_callback = callback
    
    def generate_plan(
        self,
        photo_infos: list[PhotoInfo],
        duplicate_groups: list = None,
        categories: dict[Path, PhotoCategory] = None
    ) -> list[OrganizePlan]:
        """
        生成整理计划
        
        Args:
            photo_infos: 照片信息列表
            duplicate_groups: 重复照片组列表
            categories: 照片分类映射 {path: category}
        
        Returns:
            整理计划列表
        """
        self.plans = []
        total = len(photo_infos)
        
        # 收集重复文件路径（非参考文件）
        duplicate_files = set()
        reference_files = set()
        if duplicate_groups:
            for group in duplicate_groups:
                reference_files.add(group.reference)
                for dup_path in group.can_delete:
                    duplicate_files.add(dup_path)
        
        for i, info in enumerate(photo_infos):
            # 进度回调
            if self.progress_callback:
                self.progress_callback(i + 1, total, f"规划中: {info.path.name}")
            
            # 判断是否为重复文件
            is_duplicate = info.path in duplicate_files
            is_reference = info.path in reference_files
            
            # 确定目标路径
            target = self._build_target_path(
                info, 
                categories.get(info.path) if categories else None,
                is_duplicate
            )
            
            # 检查是否已存在相同文件
            operation = self._determine_operation(info.path, target)
            
            plan = OrganizePlan(
                source=info.path,
                target=target,
                operation=operation,
                photo_info=info,
                category=categories.get(info.path) if categories else None,
                is_duplicate=is_duplicate
            )
            self.plans.append(plan)
        
        return self.plans
    
    def _build_target_path(self, info: PhotoInfo, category: PhotoCategory = None, is_duplicate: bool = False) -> Path:
        """构建目标路径"""
        if is_duplicate:
            # 重复文件放入 /重复照片/，保留原有目录结构
            target = self.duplicates_dir
            
            # 计算相对于源目录的相对路径
            if self.source_dir:
                try:
                    rel_path = info.path.relative_to(self.source_dir)
                    target = target / rel_path
                except ValueError:
                    # 如果无法计算相对路径，使用文件名
                    target = target / info.path.name
            else:
                # 没有源目录，使用原文件名
                target = target / info.path.name
        else:
            # 非重复文件放入 /去重后照片/
            target = self.organized_dir
            
            # 按内容识别分类
            if self.recognition_enabled and category and category.value in self.recognition_categories:
                target = target / category.value
            
            # 按日期分类
            date_folder = info.capture_time.strftime(self.date_format.value)
            target = target / date_folder
            
            # 最终文件名
            new_name = info.capture_time.strftime("%Y%m%d_%H%M%S")
            original_name = info.path.stem
            ext = info.path.suffix.lower()
            
            # 如果原文件名有时间戳信息，直接用它
            if self._has_timestamp_in_name(original_name):
                target_name = f"{original_name}{ext}"
            else:
                target_name = f"{new_name}_{original_name}{ext}"
            
            target = target / target_name
        
        return target
    
    def _has_timestamp_in_name(self, filename: str) -> bool:
        """检查文件名是否已包含时间戳"""
        patterns = [
            r'\d{8}',           # 20240321
            r'\d{4}-\d{2}-\d{2}',  # 2024-03-21
            r'\d{4}_\d{2}_\d{2}',  # 2024_03_21
            r'IMG_\d+',         # IMG_20240321
            r'wx_camera_\d+',   # wx_camera_1711023456
            r'mmexport\d+',     # mmexport1711023456789
        ]
        import re
        return any(re.search(p, filename) for p in patterns)
    
    def _determine_operation(self, source: Path, target: Path) -> str:
        """确定操作类型"""
        if self.mode == OrganizeMode.SIMULATE:
            return "simulate"
        
        # 如果源和目标相同，跳过
        if source.resolve() == target.resolve():
            return "skip_same"
        
        # 如果目标已存在
        if target.exists():
            source_size = source.stat().st_size
            target_size = target.stat().st_size
            
            if source_size == target_size:
                return "skip_duplicate"
            else:
                # 文件名冲突，添加序号
                return "rename"
        
        return self.mode.value
    
    def execute(self, plans: list[OrganizePlan] = None) -> OrganizeResult:
        """
        执行整理计划
        
        Returns:
            OrganizeResult 执行结果
        """
        if plans is None:
            plans = self.plans
        
        result = OrganizeResult(
            success=[], 
            failed=[], 
            skipped=[],
            output_dir=self.output_dir,
            source_dir=self.source_dir
        )
        total = len(plans)
        
        for i, plan in enumerate(plans):
            if self.progress_callback:
                self.progress_callback(i + 1, total, f"执行中: {plan.source.name}")
            
            try:
                if plan.operation in ["skip_same", "skip_duplicate"]:
                    result.skipped.append(plan)
                    continue
                
                if plan.operation == "simulate":
                    result.success.append(plan)
                    continue
                
                # 确保目标目录存在
                plan.target.parent.mkdir(parents=True, exist_ok=True)
                
                # 处理重名
                target = plan.target
                if plan.operation == "rename" or target.exists():
                    target = self._generate_unique_name(target)
                
                # 执行操作
                if plan.operation == "copy" or self.mode == OrganizeMode.COPY:
                    shutil.copy2(plan.source, target)
                elif plan.operation == "move" or self.mode == OrganizeMode.MOVE:
                    shutil.move(str(plan.source), str(target))
                
                result.success.append(plan)
                
            except Exception as e:
                result.failed.append((plan, str(e)))
        
        # 生成整理明细
        self._generate_detail_report(result)
        
        return result
    
    def _generate_unique_name(self, target: Path) -> Path:
        """生成唯一的文件名"""
        stem = target.stem
        suffix = target.suffix
        parent = target.parent
        counter = 1
        
        new_target = parent / f"{stem}_{counter:03d}{suffix}"
        while new_target.exists():
            counter += 1
            new_target = parent / f"{stem}_{counter:03d}{suffix}"
        
        return new_target
    
    def _generate_detail_report(self, result: OrganizeResult):
        """生成整理明细 Markdown 文件"""
        report_path = self.output_dir / "整理明细.md"

        # 去重区块：HEIC 解码失败计数 > 0 时显示标注行，否则整个区块隐藏
        heic_notes = render_heic_fail_note(Deduplicator.heic_decode_fail_count)
        dedup_block = ["## 去重信息", "", *heic_notes, ""] if heic_notes else []

        lines = [
            "# 照片整理明细",
            "",
            f"**整理时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**源目录:** {self.source_dir}",
            f"**输出目录:** {self.output_dir}",
            "",
            "## 统计信息",
            "",
            f"- 成功处理: {len(result.success)} 张",
            f"- 跳过: {len(result.skipped)} 张",
            f"- 失败: {len(result.failed)} 张",
            "",
            *dedup_block,
            "## 文件映射列表",
            "",
            "| 序号 | 整理前路径 | 整理后路径 | 操作类型 |",
            "|------|-----------|-----------|---------|",
        ]
        
        # 成功处理的文件
        for i, plan in enumerate(result.success, 1):
            op_type = "归档" if not plan.is_duplicate else "隔离重复"
            lines.append(f"| {i} | {plan.source} | {plan.target} | {op_type} |")
        
        # 跳过的文件
        for i, plan in enumerate(result.skipped, len(result.success) + 1):
            lines.append(f"| {i} | {plan.source} | {plan.target} | 跳过 |")
        
        # 失败的文件
        if result.failed:
            lines.extend([
                "",
                "## 失败列表",
                "",
                "| 序号 | 源路径 | 错误信息 |",
                "|------|--------|---------|",
            ])
            for i, (plan, error) in enumerate(result.failed, 1):
                lines.append(f"| {i} | {plan.source} | {error} |")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    
    def export_plan(self, filepath: str | Path):
        """导出整理计划为JSON"""
        data = []
        for plan in self.plans:
            data.append({
                'source': str(plan.source),
                'target': str(plan.target),
                'operation': plan.operation,
                'category': plan.category.value if plan.category else None,
                'is_duplicate': plan.is_duplicate,
                'capture_time': plan.photo_info.capture_time.isoformat() if plan.photo_info else None
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def delete_duplicates(duplicate_groups: list, delete_callback: Callable[[Path], bool] = None) -> tuple[int, int]:
        """
        删除重复文件
        
        Args:
            duplicate_groups: 重复组列表
            delete_callback: 删除前的确认回调，返回False则跳过
        
        Returns:
            (成功删除数, 失败数)
        """
        deleted = 0
        failed = 0
        
        for group in duplicate_groups:
            for dup_file in group.can_delete:
                if delete_callback and not delete_callback(dup_file):
                    continue
                
                try:
                    dup_file.unlink()
                    deleted += 1
                except Exception:
                    failed += 1
        
        return deleted, failed
