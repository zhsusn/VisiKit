"""
照片扫描模块 - 递归扫描目录，收集照片元数据
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator
from datetime import datetime
import exifread


@dataclass
class PhotoInfo:
    """照片信息数据类"""
    path: Path
    size: int
    mtime: datetime
    file_hash: str = ""  # MD5哈希
    image_hash: str = ""  # 感知哈希
    width: int = 0
    height: int = 0
    capture_time: datetime = None
    photo_type: str = "unknown"  # person/scene/document/unknown
    
    # 支持的图片格式
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic', '.raw'}
    
    @property
    def is_portrait(self) -> bool:
        """是否竖屏照片"""
        return self.height > self.width if self.height and self.width else False


class PhotoScanner:
    """照片扫描器"""
    
    def __init__(self, extensions: set[str] = None):
        self.extensions = extensions or PhotoInfo.SUPPORTED_FORMATS
        self.stats = {
            'total_files': 0,
            'total_size': 0,
            'errors': []
        }
    
    def scan(self, root_path: str | Path, recursive: bool = True) -> Iterator[PhotoInfo]:
        """
        扫描目录，返回照片信息生成器
        
        Args:
            root_path: 根目录路径
            recursive: 是否递归子目录
        """
        root = Path(root_path).expanduser().resolve()
        
        if not root.exists():
            raise FileNotFoundError(f"目录不存在: {root}")
        
        pattern = "**/*" if recursive else "*"
        
        for file_path in root.glob(pattern):
            if file_path.is_file() and file_path.suffix.lower() in self.extensions:
                try:
                    info = self._extract_info(file_path)
                    self.stats['total_files'] += 1
                    self.stats['total_size'] += info.size
                    yield info
                except Exception as e:
                    self.stats['errors'].append((str(file_path), str(e)))
    
    def _extract_info(self, file_path: Path) -> PhotoInfo:
        """提取单张照片的元数据"""
        stat = file_path.stat()
        
        info = PhotoInfo(
            path=file_path,
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
        )
        
        # 尝试读取EXIF信息
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                
                # 获取拍摄时间
                if 'EXIF DateTimeOriginal' in tags:
                    dt_str = str(tags['EXIF DateTimeOriginal'])
                    info.capture_time = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                elif 'Image DateTime' in tags:
                    dt_str = str(tags['Image DateTime'])
                    info.capture_time = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                
                # 获取图片尺寸
                if 'EXIF ExifImageWidth' in tags and 'EXIF ExifImageLength' in tags:
                    info.width = int(str(tags['EXIF ExifImageWidth']))
                    info.height = int(str(tags['EXIF ExifImageLength']))
        except Exception:
            pass
        
        # 如果EXIF没读到尺寸，用Pillow读取
        if not info.width or not info.height:
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    info.width, info.height = img.size
            except Exception:
                pass
        
        # 使用修改时间作为备选
        if not info.capture_time:
            info.capture_time = info.mtime
        
        return info
    
    def get_stats(self) -> dict:
        """获取扫描统计信息"""
        return self.stats.copy()
