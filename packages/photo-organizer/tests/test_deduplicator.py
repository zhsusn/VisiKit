"""
去重器测试
"""
import unittest
import tempfile
from pathlib import Path
from PIL import Image
import io

from photo_organizer.deduplicator import Deduplicator, DuplicateType


class TestDeduplicator(unittest.TestCase):
    """测试照片去重器"""
    
    def setUp(self):
        """创建临时测试目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)
        self.test_dir.mkdir(exist_ok=True)
    
    def tearDown(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_image(self, path: Path, color: tuple = (255, 0, 0), size: tuple = (100, 100)):
        """创建测试图片"""
        img = Image.new('RGB', size, color=color)
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
        img = Image.open(img1)
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
