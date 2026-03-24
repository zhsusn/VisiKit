"""
扫描器测试
"""
import unittest
import tempfile
from pathlib import Path
from PIL import Image
from datetime import datetime

from photo_organizer.scanner import PhotoScanner, PhotoInfo


class TestPhotoScanner(unittest.TestCase):
    """测试照片扫描器"""
    
    def setUp(self):
        """创建临时测试目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)
        
        # 创建测试图片
        self.create_test_image(self.test_dir / "photo1.jpg")
        self.create_test_image(self.test_dir / "subdir" / "photo2.png")
    
    def tearDown(self):
        """清理临时目录"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def create_test_image(self, path: Path):
        """创建测试图片"""
        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGB', (100, 100), color='red')
        img.save(path)
    
    def test_scan_finds_photos(self):
        """测试扫描能找到照片"""
        scanner = PhotoScanner()
        photos = list(scanner.scan(self.test_dir))
        
        self.assertEqual(len(photos), 2)
        self.assertTrue(all(isinstance(p, PhotoInfo) for p in photos))
    
    def test_scan_non_recursive(self):
        """测试非递归扫描"""
        scanner = PhotoScanner()
        photos = list(scanner.scan(self.test_dir, recursive=False))
        
        self.assertEqual(len(photos), 1)
    
    def test_scan_stats(self):
        """测试扫描统计"""
        scanner = PhotoScanner()
        list(scanner.scan(self.test_dir))
        
        stats = scanner.get_stats()
        self.assertEqual(stats['total_files'], 2)
        self.assertGreater(stats['total_size'], 0)


if __name__ == '__main__':
    unittest.main()
