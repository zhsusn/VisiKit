"""
去重模块 - 精确匹配 + 感知哈希相似检测
"""

import hashlib
from pathlib import Path
from typing import Iterator
from collections import defaultdict
import imagehash
from PIL import Image
from dataclasses import dataclass
from enum import Enum

# 可选依赖：HEIC/HEIF 支持。未安装或初始化失败时自动降级为仅精确哈希。
try:
    import pillow_heif
except Exception:  # 仅捕获 Exception，KeyboardInterrupt/SystemExit 等中断类不被吞掉
    pillow_heif = None

# HEIF 全局降级标记：初始化失败后置为 True，HEIC 跳过感知哈希
heif_degraded: bool = False
_heif_initialized: bool = False


def initialize_heif() -> None:
    """初始化 HEIF 支持（注册 pillow-heif opener）。

    进程内仅初始化一次，初始化失败（含依赖缺失、注册抛出非中断类异常）后
    永久标记全局降级，不会重试；扫描不中断，HEIC自动降级为仅精确哈希。
    KeyboardInterrupt/SystemExit 等中断类异常不在此捕获，继续向外抛出。
    """
    global heif_degraded, _heif_initialized
    if _heif_initialized:
        return
    if pillow_heif is None:
        heif_degraded = True
        _heif_initialized = True
        return
    try:
        pillow_heif.register_heif_opener()
    except Exception:
        heif_degraded = True
    _heif_initialized = True


initialize_heif()


class DuplicateType(Enum):
    """重复类型"""
    EXACT = "exact"      # 完全一致（文件哈希）
    SIMILAR = "similar"  # 相似照片（感知哈希）


@dataclass
class DuplicateGroup:
    """重复照片组"""
    group_id: int
    duplicate_type: DuplicateType
    photos: list[Path]
    reference: Path  # 保留的参考文件（通常是质量最好的）

    @property
    def can_delete(self) -> list[Path]:
        """可以删除的重复文件（除参考文件外）"""
        return [p for p in self.photos if p != self.reference]


class Deduplicator:
    """照片去重器"""

    # 类级HEIC解码失败计数器（单线程环境，每次扫描启动时重置）
    heic_decode_fail_count: int = 0

    def __init__(self, hash_size: int = 8, similarity_threshold: int = 5):
        """
        Args:
            hash_size: 感知哈希大小，越大越精确但越慢
            similarity_threshold: 感知哈希差异阈值，小于此值视为相似
        """
        self.hash_size = hash_size
        self.similarity_threshold = similarity_threshold

        # 存储哈希 -> 文件列表
        self.exact_hashes: dict[str, list[Path]] = defaultdict(list)
        self.image_hashes: dict[str, list[Path]] = defaultdict(list)

    def start_new_scan(self) -> None:
        """启动新扫描，重置所有扫描状态（哈希索引、HEIC解码失败计数器）"""
        self.exact_hashes.clear()
        self.image_hashes.clear()
        Deduplicator.heic_decode_fail_count = 0

    def compute_file_hash(self, file_path: Path) -> str:
        """计算文件MD5哈希（精确匹配）"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def compute_image_hash(self, file_path: Path) -> str | None:
        """计算感知哈希（相似检测）"""
        # HEIF 初始化失败时，HEIC 跳过感知哈希，仅保留精确哈希
        if heif_degraded and file_path.suffix.lower() == ".heic":
            return None
        try:
            with Image.open(file_path) as img:
                # 使用pHash（感知哈希），对缩放/压缩鲁棒
                return str(imagehash.phash(img, hash_size=self.hash_size))
        except Exception:
            # 仅HEIC格式（后缀小写归一）解码失败时累加类级计数器
            if file_path.suffix.lower() == ".heic":
                Deduplicator.heic_decode_fail_count += 1
            return None

    def add_photo(self, photo_path: Path) -> None:
        """添加单张照片进行索引"""
        # 精确哈希
        file_hash = self.compute_file_hash(photo_path)
        self.exact_hashes[file_hash].append(photo_path)

        # 感知哈希
        img_hash = self.compute_image_hash(photo_path)
        if img_hash:
            self.image_hashes[img_hash].append(photo_path)

    def find_exact_duplicates(self) -> Iterator[DuplicateGroup]:
        """查找完全重复的照片"""
        group_id = 0
        for file_hash, paths in self.exact_hashes.items():
            if len(paths) > 1:
                group_id += 1
                # 选择最大的文件作为参考（通常质量最好）
                reference = max(paths, key=lambda p: p.stat().st_size)
                yield DuplicateGroup(
                    group_id=group_id,
                    duplicate_type=DuplicateType.EXACT,
                    photos=paths.copy(),
                    reference=reference
                )

    def find_similar_duplicates(self) -> Iterator[DuplicateGroup]:
        """查找相似照片（基于感知哈希）"""
        group_id = 10000  # 区分于精确重复

        # 获取所有哈希值
        hashes = list(self.image_hashes.keys())
        processed = set()

        for i, hash1 in enumerate(hashes):
            if hash1 in processed:
                continue

            similar_group = self.image_hashes[hash1].copy()

            # 与其他哈希比较相似度
            for hash2 in hashes[i+1:]:
                if hash2 in processed:
                    continue

                # 计算哈希距离
                try:
                    h1 = imagehash.hex_to_hash(hash1)
                    h2 = imagehash.hex_to_hash(hash2)
                    distance = h1 - h2

                    if distance <= self.similarity_threshold:
                        similar_group.extend(self.image_hashes[hash2])
                        processed.add(hash2)
                except Exception:
                    continue

            if len(similar_group) > 1:
                group_id += 1
                processed.add(hash1)

                # 选择分辨率最高的作为参考
                def get_resolution(p: Path) -> int:
                    try:
                        with Image.open(p) as img:
                            return img.width * img.height
                    except:
                        return 0

                reference = max(similar_group, key=get_resolution)
                yield DuplicateGroup(
                    group_id=group_id,
                    duplicate_type=DuplicateType.SIMILAR,
                    photos=similar_group,
                    reference=reference
                )

    def find_all_duplicates(self, include_similar: bool = True) -> list[DuplicateGroup]:
        """
        查找所有重复照片

        Returns:
            重复照片组列表
        """
        results = []

        # 精确重复
        for group in self.find_exact_duplicates():
            results.append(group)

        # 相似照片
        if include_similar:
            for group in self.find_similar_duplicates():
                results.append(group)

        return results

    def get_stats(self) -> dict:
        """获取去重统计"""
        exact_groups = list(self.find_exact_duplicates())
        similar_groups = list(self.find_similar_duplicates())

        exact_duplicates = sum(len(g.photos) - 1 for g in exact_groups)
        similar_duplicates = sum(len(g.photos) - 1 for g in similar_groups)

        return {
            'exact_groups': len(exact_groups),
            'exact_duplicates': exact_duplicates,
            'similar_groups': len(similar_groups),
            'similar_duplicates': similar_duplicates,
            'total_duplicates': exact_duplicates + similar_duplicates,
            'space_saved': sum(
                sum(p.stat().st_size for p in g.can_delete)
                for g in exact_groups + similar_groups
            )
        }


def render_heic_fail_note(fail_count: int) -> list[str]:
    """重复报告汇总区 HEIC 解码失败标注渲染。

    仅当失败计数 > 0 时返回标注行（供 CLI 终端汇总与整理明细.md 去重区块
    共用）；计数为 0（无 HEIC 文件或全部解码成功）时返回空列表，即隐藏
    标注项，保持报告简洁。
    """
    if fail_count <= 0:
        return []
    return [f"HEIC解码失败: {fail_count} 张（已降级为仅精确哈希参与去重）"]
