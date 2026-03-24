#!/usr/bin/env python3
"""
Photo Organizer 启动脚本
"""

import sys
from pathlib import Path

# 添加src到路径
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

import flet as ft
from photo_organizer.gui import main as gui_main

if __name__ == "__main__":
    ft.run(gui_main)
