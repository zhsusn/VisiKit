"""
分类模块 - 基于规则和简单启发式的人物/景物/文档分类
"""

import re
from pathlib import Path
from enum import Enum, auto
from dataclasses import dataclass
from typing import Callable
from PIL import Image
import exifread


class PhotoCategory(Enum):
    """照片分类枚举 - 简化为三类"""
    UNKNOWN = "未知"     # 未分类/无法识别
    PERSON = "人物"      # 人像、合影
    SCENE = "景物"       # 风景、建筑、自然风光
    OTHER = "其他"       # 文档、宠物、美食、截图等


@dataclass
class ClassificationResult:
    """分类结果"""
    path: Path
    category: PhotoCategory
    confidence: float  # 置信度 0-1
    reason: str        # 分类理由


class PhotoClassifier:
    """照片分类器 - 基于规则和启发式"""
    
    def __init__(self):
        # 文件名关键词映射到分类 - 简化为三类
        self.keyword_rules: dict[PhotoCategory, list[str]] = {
            PhotoCategory.PERSON: [
                '人', '自拍', 'portrait', 'face', 'me', 'we', 'family', 
                '合影', '照', '头像', 'photo', 'head', 'baby', '宝宝',
                'child', 'kid', '家人', '朋友', 'party', '聚会'
            ],
            PhotoCategory.SCENE: [
                'landscape', 'scene', 'view', '风景', '旅游', 'travel', 'trip',
                'nature', '山', '海', 'sky', 'sunset', 'sunrise', 'beach',
                '海洋', '日落', '日出', '建筑', 'building', 'city', '城市',
                'park', '公园', 'flower', '花', 'tree', '树', 'snow', '雪'
            ],
            PhotoCategory.OTHER: [
                # 文档类
                'doc', 'document', '合同', '发票', 'receipt', 'id', 'card',
                '证件', '证书', 'pdf', 'paper', '扫描', 'scan', 'note', '笔记',
                'screenshot', '屏幕截图', 'screencap', 'screen', '微信截图', 'qq截图',
                # 宠物类
                'pet', 'dog', 'cat', '宠物', '狗', '猫', 'animal', 'puppy', 'kitten',
                # 美食类
                'food', 'eat', 'meal', '美食', '菜', '饭', 'lunch', 'dinner', 'breakfast',
                # 其他
                'work', '工作', 'study', '学习', 'file', '文件'
            ],
        }
        
        # 启发式规则函数列表
        self.heuristic_rules: list[Callable[[Path, Image.Image, dict], tuple[PhotoCategory, float, str] | None]] = [
            self._heuristic_screenshot,
            self._heuristic_document,
            self._heuristic_portrait,
        ]
    
    def classify(self, photo_path: Path) -> ClassificationResult:
        """
        对单张照片进行分类
        
        Returns:
            ClassificationResult 分类结果
        """
        # 1. 首先检查文件名关键词
        category, confidence, reason = self._classify_by_filename(photo_path)
        
        if category != PhotoCategory.UNKNOWN and confidence >= 0.7:
            return ClassificationResult(photo_path, category, confidence, reason)
        
        # 2. 尝试启发式规则
        try:
            with Image.open(photo_path) as img:
                # 读取EXIF
                exif = {}
                try:
                    with open(photo_path, 'rb') as f:
                        exif_tags = exifread.process_file(f, details=False)
                        exif = {k: str(v) for k, v in exif_tags.items()}
                except:
                    pass
                
                # 应用启发式规则
                for rule in self.heuristic_rules:
                    result = rule(photo_path, img, exif)
                    if result:
                        return ClassificationResult(photo_path, *result)
        except Exception as e:
            pass
        
        # 3. 根据文件名结果或返回未知
        if category != PhotoCategory.UNKNOWN:
            return ClassificationResult(photo_path, category, confidence, reason)
        
        return ClassificationResult(
            photo_path, 
            PhotoCategory.OTHER,  # 默认归类为其他
            0.3, 
            "无法确定，默认归类为其他"
        )
    
    def _classify_by_filename(self, photo_path: Path) -> tuple[PhotoCategory, float, str]:
        """基于文件名进行分类"""
        filename_lower = photo_path.stem.lower()
        
        best_match = (PhotoCategory.UNKNOWN, 0.0, "")
        
        for category, keywords in self.keyword_rules.items():
            for keyword in keywords:
                # 完全匹配
                if keyword.lower() == filename_lower:
                    return (category, 1.0, f"文件名完全匹配关键词: {keyword}")
                
                # 包含匹配
                if keyword.lower() in filename_lower:
                    confidence = 0.6 + (len(keyword) / len(filename_lower)) * 0.3
                    if confidence > best_match[1]:
                        best_match = (category, confidence, f"文件名包含关键词: {keyword}")
        
        return best_match
    
    def _heuristic_screenshot(self, path: Path, img: Image.Image, exif: dict) -> tuple[PhotoCategory, float, str] | None:
        """截图启发式：特定比例、无EXIF、特定尺寸"""
        width, height = img.size
        
        # 常见屏幕比例 16:9, 9:16, etc
        ratio = width / height
        common_ratios = [16/9, 9/16, 4/3, 3/4, 1, 2.17, 0.46]  # 包括手机长屏
        
        is_common_ratio = any(abs(ratio - r) < 0.05 for r in common_ratios)
        has_exif = bool(exif)
        
        # 文件名包含截图特征
        screenshot_keywords = ['screenshot', 'screen', '截图', 'screencap', 'wx_camera', 'mmexport']
        filename_hints = any(k in path.stem.lower() for k in screenshot_keywords)
        
        if filename_hints and not has_exif:
            return (PhotoCategory.OTHER, 0.9, "无EXIF+截图文件名特征")
        
        if is_common_ratio and not has_exif and width >= 1080:
            return (PhotoCategory.OTHER, 0.6, "常见屏幕比例且无EXIF")
        
        return None
    
    def _heuristic_document(self, path: Path, img: Image.Image, exif: dict) -> tuple[PhotoCategory, float, str] | None:
        """文档启发式：特定比例（A4纸）、高对比度、文件名特征"""
        width, height = img.size
        ratio = width / height
        
        # A4纸比例约为 1:1.414
        is_a4_like = abs(ratio - 0.707) < 0.1 or abs(ratio - 1.414) < 0.1
        
        # 文档类文件名
        doc_keywords = ['scan', '扫描', 'document', 'doc', 'contract', '合同', 'receipt', '发票']
        filename_hints = any(k in path.stem.lower() for k in doc_keywords)
        
        if is_a4_like and filename_hints:
            return (PhotoCategory.OTHER, 0.85, "A4比例+文档文件名")
        
        if filename_hints and not exif:
            return (PhotoCategory.OTHER, 0.7, "文档文件名+无相机EXIF")
        
        return None
    
    def _heuristic_portrait(self, path: Path, img: Image.Image, exif: dict) -> tuple[PhotoCategory, float, str] | None:
        """人像启发式：竖屏照片、焦距信息、人像模式"""
        width, height = img.size
        
        # 竖屏人像通常是竖着的
        if height > width:
            # 检查是否有肖像/人像模式EXIF
            lens_info = exif.get('EXIF LensModel', '') or exif.get('Image Model', '')
            
            if 'portrait' in lens_info.lower() or '人像' in lens_info:
                return (PhotoCategory.PERSON, 0.8, "人像模式EXIF")
            
            # 自拍特征：前置摄像头、正方形或接近正方形
            if 0.8 <= width/height <= 1.25:
                return (PhotoCategory.PERSON, 0.5, "接近正方形比例（可能自拍）")
        
        return None
    
    def batch_classify(self, photo_paths: list[Path]) -> list[ClassificationResult]:
        """批量分类"""
        results = []
        for path in photo_paths:
            results.append(self.classify(path))
        return results
    
    def get_category_stats(self, results: list[ClassificationResult]) -> dict:
        """获取分类统计"""
        stats = {cat: 0 for cat in PhotoCategory}
        for r in results:
            stats[r.category] += 1
        return stats
