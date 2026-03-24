"""
命令行接口
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

from .scanner import PhotoScanner
from .deduplicator import Deduplicator
from .classifier import PhotoClassifier
from .organizer import PhotoOrganizer, OrganizeMode, DateFormat


def scan_command(args):
    """扫描命令"""
    print(f"🔍 扫描目录: {args.source}")
    
    scanner = PhotoScanner()
    photos = list(scanner.scan(args.source, recursive=not args.no_recursive))
    
    stats = scanner.get_stats()
    print(f"\n📊 扫描结果:")
    print(f"  文件数: {len(photos)}")
    print(f"  总大小: {stats['total_size'] / (1024*1024):.2f} MB")
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            for p in photos:
                f.write(f"{p.path}\t{p.size}\t{p.capture_time}\n")
        print(f"  结果已保存: {args.output}")
    
    return 0


def dedup_command(args):
    """去重命令"""
    print(f"🔍 扫描并去重: {args.source}")
    
    scanner = PhotoScanner()
    dedup = Deduplicator(similarity_threshold=args.threshold)
    
    photos = list(tqdm(scanner.scan(args.source), desc="扫描"))
    
    for photo in tqdm(photos, desc="计算哈希"):
        dedup.add_photo(photo.path)
    
    groups = dedup.find_all_duplicates(include_similar=args.similar)
    
    print(f"\n📊 去重结果:")
    print(f"  重复组: {len(groups)}")
    
    for g in groups:
        print(f"\n  [{g.duplicate_type.value}] 保留: {g.reference.name}")
        for dup in g.can_delete:
            print(f"    可删除: {dup}")
            if args.delete:
                dup.unlink()
                print(f"    ✓ 已删除")
    
    stats = dedup.get_stats()
    print(f"\n  预计节省: {stats['space_saved'] / (1024*1024):.2f} MB")
    
    return 0


def classify_command(args):
    """分类命令"""
    print(f"📂 分类照片: {args.source}")
    
    scanner = PhotoScanner()
    classifier = PhotoClassifier()
    
    photos = list(tqdm(scanner.scan(args.source), desc="扫描"))
    
    results = []
    for photo in tqdm(photos, desc="分类"):
        result = classifier.classify(photo.path)
        results.append(result)
        if args.verbose:
            print(f"  {result.category.value}: {photo.path.name}")
    
    stats = classifier.get_category_stats(results)
    print(f"\n📊 分类统计:")
    for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {cat.value}: {count}")
    
    return 0


def organize_command(args):
    """整理命令"""
    print(f"📁 整理照片")
    print(f"  源: {args.source}")
    print(f"  目标: {args.output}")
    
    # 解析参数
    format_map = {
        'year': DateFormat.YEAR,
        'month': DateFormat.YEAR_MONTH,
        'day': DateFormat.YEAR_MONTH_DAY
    }
    mode_map = {
        'copy': OrganizeMode.COPY,
        'move': OrganizeMode.MOVE,
        'simulate': OrganizeMode.SIMULATE
    }
    
    # 扫描
    scanner = PhotoScanner()
    photos = list(tqdm(scanner.scan(args.source), desc="扫描"))
    print(f"  发现 {len(photos)} 张照片")
    
    # 分类
    categories = {}
    if args.classify:
        classifier = PhotoClassifier()
        for photo in tqdm(photos, desc="分类"):
            result = classifier.classify(photo.path)
            categories[photo.path] = result.category
    
    # 整理
    organizer = PhotoOrganizer(
        output_dir=args.output,
        date_format=format_map.get(args.date_format, DateFormat.YEAR_MONTH),
        organize_by_category=args.classify,
        mode=mode_map.get(args.mode, OrganizeMode.COPY)
    )
    
    plans = organizer.generate_plan(photos, categories)
    print(f"  生成 {len(plans)} 个整理任务")
    
    result = organizer.execute(plans)
    
    print(f"\n✅ 整理完成:")
    print(f"  成功: {len(result.success)}")
    print(f"  跳过: {len(result.skipped)}")
    print(f"  失败: {len(result.failed)}")
    
    return 0


def gui_command(args):
    """启动GUI"""
    import flet as ft
    try:
        from .gui_flet import PhotoOrganizerFlet
        app = PhotoOrganizerFlet()
        try:
            ft.run(main=app.main)
        except:
            ft.run(main=app.main, view=ft.AppView.WEB_BROWSER, port=0)
    except ImportError as e:
        print(f"Flet GUI 启动失败: {e}")
        print("尝试启动备用 GUI...")
        from .gui import main as gui_main
        gui_main()
    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        prog='photo-organizer',
        description='本地照片智能整理工具'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # scan 命令
    scan_parser = subparsers.add_parser('scan', help='扫描目录')
    scan_parser.add_argument('source', help='源目录')
    scan_parser.add_argument('-o', '--output', help='输出结果到文件')
    scan_parser.add_argument('--no-recursive', action='store_true', help='不递归子目录')
    
    # dedup 命令
    dedup_parser = subparsers.add_parser('dedup', help='查找/删除重复照片')
    dedup_parser.add_argument('source', help='源目录')
    dedup_parser.add_argument('--similar', action='store_true', help='包含相似照片')
    dedup_parser.add_argument('--threshold', type=int, default=5, help='相似度阈值')
    dedup_parser.add_argument('--delete', action='store_true', help='自动删除重复')
    
    # classify 命令
    classify_parser = subparsers.add_parser('classify', help='分类照片')
    classify_parser.add_argument('source', help='源目录')
    classify_parser.add_argument('-v', '--verbose', action='store_true', help='详细输出')
    
    # organize 命令
    org_parser = subparsers.add_parser('organize', help='整理照片')
    org_parser.add_argument('source', help='源目录')
    org_parser.add_argument('output', help='输出目录')
    org_parser.add_argument('--classify', action='store_true', help='启用分类')
    org_parser.add_argument('--date-format', choices=['year', 'month', 'day'], 
                           default='month', help='日期格式')
    org_parser.add_argument('--mode', choices=['copy', 'move', 'simulate'],
                           default='copy', help='操作模式')
    
    # gui 命令
    subparsers.add_parser('gui', help='启动图形界面')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    commands = {
        'scan': scan_command,
        'dedup': dedup_command,
        'classify': classify_command,
        'organize': organize_command,
        'gui': gui_command,
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        return cmd_func(args)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
