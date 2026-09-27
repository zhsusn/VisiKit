"""去重模块 - 精确匹配 + 感知哈希相似检测"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

import imagehash
from PIL import Image

try:
    import pillow_heif
except Exception:
    pillow_heif = None

HEIF_DEGRADED = False


def initialize_heif() -> bool:
    global HEIF_DEGRADED
    if pillow_heif is None:
        HEIF_DEGRADED = True
        return False
    HEIF_DEGRADED = False
    try:
        pillow_heif.register_heif_opener()
    except Exception:
        HEIF_DEGRADED = True
        return False
    return True


initialize_heif()


class DuplicateType(Enum):
    EXACT = "exact"
    SIMILAR = "similar"


@dataclass
class DuplicateGroup:
    group_id: int
    duplicate_type: DuplicateType
    photos: list[Path]
    reference: Path

    @property
    def can_delete(self) -> list[Path]:
        return [p for p in self.photos if p != self.reference]


class Deduplicator:

    def __init__(self, hash_size: int = 8, similarity_threshold: int = 5):
        self.hash_size = hash_size
        self.similarity_threshold = similarity_threshold
        self.exact_hashes: dict[str, list[Path]] = defaultdict(list)
        self.image_hashes: dict[str, list[Path]] = defaultdict(list)
        initialize_heif()

    def compute_file_hash(self, file_path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def compute_image_hash(self, file_path: Path) -> str | None:
        if file_path.suffix.lower() == ".heic" and HEIF_DEGRADED:
            return None
        try:
            with Image.open(file_path) as img:
                return str(imagehash.phash(img, hash_size=self.hash_size))
        except Exception:
            return None

    def add_photo(self, photo_path: Path) -> None:
        file_hash = self.compute_file_hash(photo_path)
        self.exact_hashes[file_hash].append(photo_path)
        img_hash = self.compute_image_hash(photo_path)
        if img_hash:
            self.image_hashes[img_hash].append(photo_path)

    def find_exact_duplicates(self) -> Iterator[DuplicateGroup]:
        group_id = 0
        for paths in self.exact_hashes.values():
            if len(paths) > 1:
                group_id += 1
                reference = max(paths, key=lambda p: p.stat().st_size)
                yield DuplicateGroup(group_id, DuplicateType.EXACT,
                                     paths.copy(), reference)

    def find_similar_duplicates(self) -> Iterator[DuplicateGroup]:
        group_id = 10000
        hashes = list(self.image_hashes.keys())
        processed = set()
        for i, hash1 in enumerate(hashes):
            if hash1 in processed:
                continue
            similar_group = self.image_hashes[hash1].copy()
            for hash2 in hashes[i + 1:]:
                if hash2 in processed:
                    continue
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

                def get_resolution(p: Path) -> int:
                    try:
                        with Image.open(p) as img:
                            return img.width * img.height
                    except:
                        return 0

                reference = max(similar_group, key=get_resolution)
                yield DuplicateGroup(group_id, DuplicateType.SIMILAR,
                                     similar_group, reference)

    def find_all_duplicates(self, include_similar: bool = True) -> list[DuplicateGroup]:
        results = list(self.find_exact_duplicates())
        if include_similar:
            results.extend(self.find_similar_duplicates())
        return results

    def get_stats(self) -> dict:
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
            'space_saved': sum(sum(p.stat().st_size for p in g.can_delete) for g in exact_groups + similar_groups),
        }
