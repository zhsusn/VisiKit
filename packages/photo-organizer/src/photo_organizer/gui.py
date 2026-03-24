"""
Photo Organizer GUI v3.0 - 极简一键流程界面
基于 Flet 重构，将四步流程简化为单页一键操作
"""

import flet as ft
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import shutil
import threading
import json
import queue
import time
import traceback

# v3.0 重构：业务模块导入保持不变
from .scanner import PhotoScanner, PhotoInfo
from .deduplicator import Deduplicator, DuplicateGroup
from .classifier import PhotoClassifier, PhotoCategory
from .organizer import PhotoOrganizer, OrganizeMode, DateFormat


# ========== 常量定义 ==========

# v3.0 重构：智能默认配置（符合 ui-spec-v3.0）
DEFAULT_CONFIG = {
    "dedupe_enabled": True,           # 去重总开关
    "dedupe_fuzzy": True,             # 模糊匹配（pHash）
    "dedupe_threshold": 90,           # 相似度阈值
    
    "archive_enabled": True,          # 时间归档总开关
    "archive_granularity": "year_month",  # 默认年月
    
    "recognition_enabled": False,     # 内容识别总开关（默认关闭）
    "recognition_categories": [],     # 识别类别（人物、景物、其他）
    
    "safety_mode": "copy",            # 复制模式（安全）
    "preview_before_run": True,       # 执行前预览
    "generate_log": True,             # 生成 CSV 日志
    
    "output_suffix": "_已整理",       # 自动命名后缀
    "conflict_resolution": "rename"   # 冲突自动重命名
}

# v3.0 重构：自动分类关键词库（符合 DEVELOPMENT.md）
CATEGORY_KEYWORDS = {
    "人物": ["人", "自拍", "合影", "portrait", "family", "face", "photo", "head", "baby", "宝宝", "child", "kid", "家人", "朋友", "party", "聚会"],
    "景物": ["景", "风景", "旅游", "travel", "scenery", "landscape", "view", "nature", "山", "海", "sky", "sunset", "sunrise", "beach", "海洋", "日落", "日出", "建筑", "building", "city", "城市", "park", "公园", "flower", "花", "tree", "树", "snow", "雪"],
}

# 颜色定义（符合 ui-spec-v3.0 Design Tokens）
COLORS = {
    "primary": "#2563EB",        # Blue-600
    "secondary": "#10B981",      # Emerald-500
    "warning": "#F59E0B",        # Amber-500
    "danger": "#EF4444",         # Red-500
    "background": "#F9FAFB",     # Gray-50
    "surface": "#FFFFFF",        # 卡片背景
    "text_primary": "#111827",   # Gray-900
    "text_secondary": "#6B7280", # Gray-500
    "border": "#E5E7EB",         # Gray-200
}

# 状态枚举（符合 ui-spec-v3.0）
class AppState(Enum):
    IDLE = "idle"                    # 初始状态
    SOURCE_SELECTED = "source_ready" # 已选源目录
    SCANNING = "scanning"            # 扫描分析中
    PREVIEWING = "previewing"        # 预览对话框
    ORGANIZING = "organizing"        # 执行整理中
    COMPLETED = "completed"          # 完成
    ERROR = "error"                  # 错误


# ========== 辅助函数 ==========

def with_opacity(opacity: float, color: str) -> str:
    """v3.0 重构：生成带透明度的颜色字符串 (RGBA格式)
    
    Args:
        opacity: 透明度 0.0-1.0
        color: 颜色字符串，支持 #RRGGBB 或颜色名称
    
    Returns:
        RGBA 格式颜色字符串 #RRGGBBAA
    """
    # 处理颜色名称
    color_map = {
        "white": "#FFFFFF",
        "black": "#000000",
    }
    hex_color = color_map.get(color.lower(), color)
    
    # 确保是 #RRGGBB 格式
    if hex_color.startswith('#') and len(hex_color) == 7:
        # 转换透明度为 0-255 的十六进制
        alpha = int(opacity * 255)
        alpha_hex = f"{alpha:02X}"
        return f"{hex_color}{alpha_hex}"
    
    # 如果不是标准格式，直接返回原色
    return color


def format_size(bytes_size: int) -> str:
    """格式化文件大小显示"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 ** 2:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 ** 3:
        return f"{bytes_size / (1024 ** 2):.1f} MB"
    else:
        return f"{bytes_size / (1024 ** 3):.2f} GB"


def get_disk_space(path: Path) -> tuple[int, int, int]:
    """获取磁盘空间信息 (总空间, 已用空间, 剩余空间)"""
    try:
        usage = shutil.disk_usage(path)
        return usage.total, usage.used, usage.free
    except:
        return 0, 0, 0


def infer_category(folder_name: str) -> str:
    """v3.0 重构：根据目录名推断分类类型"""
    folder_lower = folder_name.lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in folder_lower:
                return category
    
    return "未分类"


def generate_default_output_name(source_name: str) -> str:
    """生成默认输出目录名"""
    today = datetime.now().strftime("%Y%m%d")
    return f"{source_name}{DEFAULT_CONFIG['output_suffix']}_{today}"


# ========== 主应用类 ==========

class PhotoOrganizerApp:
    """v3.0 重构：Photo Organizer 极简界面主类"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        
        # v3.0 重构：页面基础配置
        self.page.title = "Photo Organizer v3.0"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.theme = ft.Theme(color_scheme_seed=COLORS["primary"])
        self.page.bgcolor = COLORS["background"]
        self.page.padding = 0
        
        # 状态管理
        self.app_state = AppState.IDLE
        self.source_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
        self.config: dict = DEFAULT_CONFIG.copy()
        
        # 业务数据
        self.scanned_photos: list[PhotoInfo] = []
        self.duplicate_groups: list[DuplicateGroup] = []
        self.classified_photos: dict[Path, PhotoCategory] = {}
        self.inferred_category: str = "未分类"
        
        # 进度更新队列（用于线程间通信）
        self.progress_queue: queue.Queue = queue.Queue()
        self.cancel_requested: bool = False
        
        # UI 组件引用
        self._init_ui_refs()
        
        # 加载设置
        self._load_settings()
        
        # 构建界面
        self._build_ui()
    
    def _init_file_pickers(self):
        """初始化文件选择器 - 使用 tkinter 替代 Flet FilePicker
        
        注意：FilePicker 在 Flet 0.80+ 桌面版本中有渲染问题，
        会显示红色 "Unknown control: FilePicker" 错误框。
        改用 tkinter filedialog 更稳定可靠。
        """
        # 不使用 Flet FilePicker，避免红色错误框
        self.source_picker = None
        self.target_picker = None
    
    def _init_ui_refs(self):
        """初始化 UI 组件引用"""
        # 源目录卡片组件
        self.source_card: Optional[ft.Card] = None
        self.source_title: Optional[ft.Text] = None
        self.source_path_text: Optional[ft.Text] = None
        self.source_stats_text: Optional[ft.Text] = None
        self.source_change_btn: Optional[ft.TextButton] = None
        
        # 目标目录卡片组件
        self.target_card: Optional[ft.Card] = None
        self.target_path_text: Optional[ft.Text] = None
        self.target_disk_text: Optional[ft.Text] = None
        self.target_change_btn: Optional[ft.TextButton] = None
        
        # 主执行按钮
        self.execute_btn: Optional[ft.ElevatedButton] = None
        self.execute_container: Optional[ft.Container] = None
        
        # 策略摘要
        self.strategy_chips: list[ft.Chip] = []
        self.strategy_row: Optional[ft.Row] = None
        
        # 设置抽屉组件
        self.settings_drawer: Optional[ft.NavigationDrawer] = None
        self.dedupe_switch: Optional[ft.Switch] = None
        self.dedupe_fuzzy_switch: Optional[ft.Switch] = None
        self.dedupe_slider: Optional[ft.Slider] = None
        self.archive_switch: Optional[ft.Switch] = None
        self.archive_radio: Optional[ft.RadioGroup] = None
        self.classify_switch: Optional[ft.Switch] = None
        self.classify_radio: Optional[ft.RadioGroup] = None
        self.safety_radio: Optional[ft.RadioGroup] = None
        self.move_warning_banner: Optional[ft.Banner] = None
        self.preview_checkbox: Optional[ft.Checkbox] = None
        self.log_checkbox: Optional[ft.Checkbox] = None
        
        # 对话框和浮层
        self.preview_dialog: Optional[ft.AlertDialog] = None
        self.progress_overlay: Optional[ft.Container] = None
        self.complete_dialog: Optional[ft.AlertDialog] = None
        
        # 文件选择器（使用 tkinter，不使用 Flet FilePicker）
        self.source_picker: Optional[any] = None
        self.target_picker: Optional[any] = None
    
    # ========== 设置持久化 ==========
    
    def _load_settings(self):
        """v3.0 重构：从文件加载设置"""
        try:
            settings_file = Path.home() / ".photo_organizer_settings.json"
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    stored_config = json.load(f)
                    self.config.update(stored_config)
        except Exception as e:
            print(f"加载设置失败: {e}")
    
    def _save_settings(self):
        """v3.0 重构：保存设置到文件"""
        try:
            settings_file = Path.home() / ".photo_organizer_settings.json"
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存设置失败: {e}")
    
    # ========== UI 构建 ==========
    
    def _build_ui(self):
        """v3.0 重构：构建主界面"""
        # 文件选择器 - 使用页面级别的 overlay，确保不可见
        self._init_file_pickers()
        
        # AppBar
        app_bar = ft.AppBar(
            title=ft.Text("📷 Photo Organizer", size=20, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"]),
            center_title=False,
            bgcolor=COLORS["surface"],
            elevation=0,
            actions=[
                ft.IconButton(
                    icon=ft.icons.Icons.SETTINGS,
                    tooltip="整理设置",
                    on_click=self._open_settings,
                    icon_color=COLORS["text_secondary"],
                )
            ],
        )
        
        # 主内容区域（垂直居中布局）
        main_content = ft.Container(
            content=ft.Column(
                [
                    # 源目录卡片
                    self._build_source_card(),
                    
                    # 间距
                    ft.Container(height=24),
                    
                    # 目标目录卡片
                    self._build_target_card(),
                    
                    # 间距
                    ft.Container(height=32),
                    
                    # 主执行按钮
                    self._build_execute_button(),
                    
                    # 间距
                    ft.Container(height=32),
                    
                    # 分隔线
                    ft.Divider(color=COLORS["border"], height=1),
                    
                    # 间距
                    ft.Container(height=16),
                    
                    # 策略摘要
                    self._build_strategy_summary(),
                    
                    # 提示文字
                    ft.Container(height=8),
                    ft.Text(
                        "点击齿轮图标可调整默认设置",
                        size=12,
                        color=COLORS["text_secondary"],
                        italic=True,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
            ),
            padding=ft.padding.all(24),
            alignment=ft.alignment.Alignment(0, 0),
        )
        
        # 页面布局
        self.page.appbar = app_bar
        self.page.add(main_content)
        
        # 构建设置抽屉（但不显示）
        self._build_settings_drawer()
        
        # 初始状态更新
        self._update_ui_state()
    
    def _build_source_card(self) -> ft.Card:
        """v3.0 重构：构建源目录卡片"""
        self.source_title = ft.Text(
            "📁 源照片目录",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=COLORS["text_primary"],
        )
        
        self.source_path_text = ft.Text(
            "点击选择或拖拽文件夹",
            size=14,
            color=COLORS["text_secondary"],
        )
        
        self.source_stats_text = ft.Text(
            "",
            size=12,
            color=COLORS["text_secondary"],
        )
        
        self.source_change_btn = ft.TextButton(
            "选择目录",
            on_click=self._pick_source_directory,
            style=ft.ButtonStyle(color=COLORS["primary"]),
        )
        
        self.source_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        self.source_title,
                        ft.Container(height=12),
                        ft.Row(
                            [
                                ft.Icon(ft.icons.Icons.FOLDER, color=COLORS["primary"], size=32),
                                ft.Container(width=16),
                                ft.Column(
                                    [
                                        self.source_path_text,
                                        self.source_stats_text,
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                self.source_change_btn,
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.padding.all(20),
                border=ft.border.all(2, COLORS["border"]),
                border_radius=ft.border_radius.all(8),
                # v3.0 重构：拖拽视觉反馈（模拟）
                on_hover=self._on_source_hover,
            ),
            elevation=1,
            width=600,
        )
        
        return self.source_card
    
    def _build_target_card(self) -> ft.Card:
        """v3.0 重构：构建目标目录卡片"""
        self.target_path_text = ft.Text(
            "选择源目录后自动生成",
            size=14,
            color=COLORS["text_secondary"],
        )
        
        self.target_disk_text = ft.Text(
            "",
            size=12,
            color=COLORS["text_secondary"],
        )
        
        self.target_change_btn = ft.TextButton(
            "修改",
            on_click=self._pick_target_directory,
            style=ft.ButtonStyle(color=COLORS["primary"]),
            visible=False,
        )
        
        self.target_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "📂 输出目录 (自动创建子目录)",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=COLORS["text_primary"],
                        ),
                        ft.Container(height=12),
                        ft.Row(
                            [
                                ft.Icon(ft.icons.Icons.SAVE, color=COLORS["secondary"], size=32),
                                ft.Container(width=16),
                                ft.Column(
                                    [
                                        self.target_path_text,
                                        self.target_disk_text,
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                                self.target_change_btn,
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.padding.all(20),
                border=ft.border.all(1, COLORS["border"]),
                border_radius=ft.border_radius.all(8),
            ),
            elevation=1,
            width=600,
        )
        
        return self.target_card
    
    def _build_execute_button(self) -> ft.Container:
        """v3.0 重构：构建主执行按钮"""
        self.execute_btn = ft.ElevatedButton(
            content=ft.Column(
                [
                    ft.Text(
                        "🚀 开始智能整理",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color="white",
                    ),
                    ft.Text(
                        "将自动执行: 去重 → 时间归档 → 分类",
                        size=12,
                        color=with_opacity(0.8, "white"),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            on_click=self._on_execute_click,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=COLORS["primary"],
                padding=ft.padding.symmetric(horizontal=40, vertical=16),
                shape=ft.RoundedRectangleBorder(radius=12),
            ),
        )
        
        # v3.0 重构：使用 Container 包装实现悬停效果
        self.execute_container = ft.Container(
            content=self.execute_btn,
            width=400,
            animate_scale=ft.Animation(300, ft.AnimationCurve.EASE_IN_OUT),
            on_hover=self._on_execute_hover,
            shadow=ft.BoxShadow(
                spread_radius=0,
                blur_radius=4,
                color=with_opacity(0.2, "#000000"),
                offset=ft.Offset(0, 2),
            ),
        )
        
        return self.execute_container
    
    def _build_strategy_summary(self) -> ft.Row:
        """v3.0 重构：构建策略摘要 Chips"""
        # 根据当前配置确定初始文本
        # 去重
        if self.config["dedupe_enabled"]:
            dedupe_text = "模糊去重" if self.config["dedupe_fuzzy"] else "精确去重"
        else:
            dedupe_text = "不去重"
        
        # 归档
        if self.config["archive_enabled"]:
            granularity_map = {
                "year": "年仅归档",
                "year_month": "年月归档",
                "year_month_day": "年月日归档",
            }
            archive_text = granularity_map.get(self.config["archive_granularity"], "年月归档")
        else:
            archive_text = "不归档"
        
        # 内容识别
        if self.config.get("recognition_enabled", False):
            categories = self.config.get("recognition_categories", [])
            if categories:
                recognition_text = f"识别: {','.join(categories)}"
            else:
                recognition_text = "不识别"
        else:
            recognition_text = "不识别"
        
        self.strategy_chips = [
            ft.Chip(
                label=ft.Text(dedupe_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("dedupe"),
            ),
            ft.Chip(
                label=ft.Text(archive_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("archive"),
            ),
            ft.Chip(
                label=ft.Text(recognition_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("recognition"),
            ),
        ]
        
        self.strategy_row = ft.Row(
            [
                ft.Text("整理策略: ", size=12, color=COLORS["text_secondary"]),
                *self.strategy_chips,
            ],
            spacing=8,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        
        return self.strategy_row
    
    def _build_settings_drawer(self):
        """v3.0 重构：构建设置抽屉"""
        # 去重策略区
        self.dedupe_switch = ft.Switch(
            label="智能去重",
            value=self.config["dedupe_enabled"],
            on_change=self._on_dedupe_switch_changed,
        )
        
        self.dedupe_fuzzy_switch = ft.Switch(
            label="模糊匹配(>90%)",
            value=self.config["dedupe_fuzzy"],
            disabled=not self.config["dedupe_enabled"],
        )
        
        self.dedupe_slider = ft.Slider(
            min=80,
            max=99,
            divisions=19,
            value=self.config["dedupe_threshold"],
            label="{value}%",
            disabled=not self.config["dedupe_enabled"] or not self.config["dedupe_fuzzy"],
        )
        
        # 时间归档区
        self.archive_switch = ft.Switch(
            label="时间归档",
            value=self.config["archive_enabled"],
        )
        
        self.archive_radio = ft.RadioGroup(
            value=self.config["archive_granularity"],
            content=ft.Column(
                [
                    ft.Radio(value="year", label="年仅归档"),
                    ft.Radio(value="year_month", label="年月归档"),
                    ft.Radio(value="year_month_day", label="年月日归档"),
                ],
            ),
        )
        
        # 内容识别区（类似时间归档，有启用开关）
        self.recognition_enabled = self.config.get("recognition_enabled", False)
        self.recognition_categories = self.config.get("recognition_categories", [])
        
        self.recognition_switch = ft.Switch(
            label="内容识别",
            value=self.recognition_enabled,
            on_change=self._on_recognition_switch_changed,
        )
        
        self.recognition_person_cb = ft.Checkbox(
            label="人物",
            value="人物" in self.recognition_categories,
            disabled=not self.recognition_enabled,
        )
        self.recognition_scene_cb = ft.Checkbox(
            label="景物",
            value="景物" in self.recognition_categories,
            disabled=not self.recognition_enabled,
        )
        # "其他"为必选，当启用内容识别时默认勾选且不可取消
        self.recognition_other_cb = ft.Checkbox(
            label="其他（默认）",
            value=True,
            disabled=True,  # 始终禁用，强制选中
        )
        
        # 安全设置区
        self.safety_radio = ft.RadioGroup(
            value=self.config["safety_mode"],
            on_change=self._on_safety_mode_changed,
            content=ft.Column(
                [
                    ft.Radio(value="copy", label="复制模式(安全)"),
                    ft.Radio(value="move", label="移动模式(有风险)"),
                ],
            ),
        )
        
        self.move_warning_banner = ft.Banner(
            bgcolor=ft.Colors.AMBER_100,
            leading=ft.Icon(ft.icons.Icons.WARNING, color=ft.Colors.AMBER_700),
            content=ft.Text(
                "移动模式将直接重定位源文件，建议先执行一次复制模式确认无误后再使用",
                color=ft.Colors.AMBER_900,
                size=12,
            ),
            actions=[ft.TextButton("了解", on_click=lambda e: None)],
            visible=False,
        )
        
        # 复选框区
        self.preview_checkbox = ft.Checkbox(
            label="执行前预览（推荐首次开启）",
            value=self.config["preview_before_run"],
        )
        
        self.log_checkbox = ft.Checkbox(
            label="生成详细操作日志(CSV)",
            value=self.config["generate_log"],
        )
        
        # 设置抽屉内容
        drawer_content = ft.Container(
            content=ft.ListView(
                [
                    # 标题栏
                    ft.Row(
                        [
                            ft.Text("⚙️ 整理设置", size=16, weight=ft.FontWeight.BOLD),
                            ft.TextButton(
                                "恢复默认",
                                on_click=self._reset_settings,
                                style=ft.ButtonStyle(color=COLORS["text_secondary"]),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(),
                    
                    # 去重策略卡片
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    self.dedupe_switch,
                                    ft.Container(
                                        content=ft.Column(
                                            [
                                                self.dedupe_fuzzy_switch,
                                                self.dedupe_slider,
                                            ],
                                            spacing=8,
                                        ),
                                        margin=ft.margin.only(left=16),
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.all(16),
                        ),
                        elevation=1,
                    ),
                    
                    ft.Container(height=8),
                    
                    # 时间归档卡片
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    self.archive_switch,
                                    ft.Container(
                                        content=self.archive_radio,
                                        margin=ft.margin.only(left=16),
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.all(16),
                        ),
                        elevation=1,
                    ),
                    
                    ft.Container(height=8),
                    
                    # 内容识别卡片
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    self.recognition_switch,
                                    ft.Container(
                                        content=ft.Column(
                                            [
                                                ft.Row(
                                                    [
                                                        self.recognition_person_cb,
                                                        self.recognition_scene_cb,
                                                        self.recognition_other_cb,
                                                    ],
                                                    spacing=16,
                                                ),
                                                ft.Text(
                                                    "启用后，照片将按识别结果分类到对应子目录",
                                                    size=12,
                                                    color=COLORS["text_secondary"],
                                                ),
                                            ],
                                            spacing=8,
                                        ),
                                        margin=ft.margin.only(left=16),
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.all(16),
                        ),
                        elevation=1,
                    ),
                    
                    ft.Container(height=8),
                    
                    # 安全设置卡片
                    ft.Card(
                        content=ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text("🛡️ 安全设置", size=14, weight=ft.FontWeight.BOLD),
                                    self.safety_radio,
                                    self.move_warning_banner,
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.all(16),
                        ),
                        elevation=1,
                    ),
                    
                    ft.Container(height=8),
                    
                    # 其他选项
                    self.preview_checkbox,
                    self.log_checkbox,
                    
                    ft.Container(height=16),
                    
                    # 底部按钮
                    ft.Row(
                        [
                            ft.ElevatedButton(
                                "保存设置",
                                on_click=self._save_settings_and_close,
                                style=ft.ButtonStyle(
                                    bgcolor=COLORS["primary"],
                                    color="white",
                                    padding=ft.padding.symmetric(horizontal=24, vertical=12),
                                ),
                            ),
                            ft.TextButton(
                                "取消",
                                on_click=self._close_settings,
                                style=ft.ButtonStyle(
                                    padding=ft.padding.symmetric(horizontal=24, vertical=12),
                                ),
                            ),
                        ],
                        spacing=16,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    
                    ft.Container(height=16),
                ],
                spacing=0,
            ),
            padding=ft.padding.all(16),
            width=400,
        )
        
        self.settings_drawer = ft.NavigationDrawer(
            controls=[drawer_content],
            bgcolor=COLORS["surface"],
        )
    
    # ========== 事件处理 ==========
    
    def _on_source_hover(self, e: ft.HoverEvent):
        """v3.0 重构：源目录卡片悬停效果（模拟拖拽视觉反馈）"""
        if self.source_card and self.source_card.content:
            container = self.source_card.content
            if e.data == "true":
                container.border = ft.border.all(2, COLORS["primary"])
            else:
                container.border = ft.border.all(2, COLORS["border"])
            self.page.update()
    
    def _on_execute_hover(self, e: ft.HoverEvent):
        """v3.0 重构：主执行按钮悬停效果"""
        if self.source_path:
            if e.data == "true":
                self.execute_container.scale = 1.02
                self.execute_container.shadow = ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=8,
                    color=with_opacity(0.3, "#000000"),
                    offset=ft.Offset(0, 4),
                )
            else:
                self.execute_container.scale = 1.0
                self.execute_container.shadow = ft.BoxShadow(
                    spread_radius=0,
                    blur_radius=4,
                    color=with_opacity(0.2, "#000000"),
                    offset=ft.Offset(0, 2),
                )
            self.page.update()
    
    def _pick_source_directory(self, e):
        """v3.0 重构：选择源目录（使用 tkinter，避免 FilePicker 红色错误框）"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # 创建临时根窗口
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes('-topmost', True)  # 置顶显示
            
            # 打开目录选择对话框
            path = filedialog.askdirectory(
                title="选择源照片目录",
                mustexist=True
            )
            
            # 销毁临时窗口
            root.destroy()
            
            if path:
                self._handle_source_path(path)
        except Exception as ex:
            print(f"选择目录失败: {ex}")
            # 失败时使用手动输入
            self._show_path_input_dialog("source")
    
    def _pick_target_directory(self, e):
        """v3.0 重构：选择目标目录（使用 tkinter，避免 FilePicker 红色错误框）"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            # 创建临时根窗口
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes('-topmost', True)  # 置顶显示
            
            # 打开目录选择对话框
            path = filedialog.askdirectory(
                title="选择输出目录",
                mustexist=True
            )
            
            # 销毁临时窗口
            root.destroy()
            
            if path:
                self._handle_target_path(path)
        except Exception as ex:
            print(f"选择目录失败: {ex}")
            self._show_path_input_dialog("target")
    
    def _show_path_input_dialog(self, target_type: str):
        """v3.0 重构：显示路径输入对话框（后备方案）"""
        path_input = ft.TextField(label="请输入目录路径", width=400)
        
        def on_confirm(e):
            path = path_input.value
            if path and Path(path).exists():
                if target_type == "source":
                    self._handle_source_path(path)
                else:
                    self._handle_target_path(path)
                self.page.pop_dialog()
            else:
                path_input.error_text = "路径不存在"
                self.page.update()
        
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("手动输入路径"),
            content=path_input,
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.ElevatedButton("确认", on_click=on_confirm),
            ],
        )
        self.page.show_dialog(dialog)
    
    def _handle_source_path(self, path: str):
        """v3.0 重构：处理源目录路径"""
        self.source_path = Path(path)
        self.app_state = AppState.SOURCE_SELECTED
        
        # 更新源目录卡片显示
        self.source_path_text.value = str(self.source_path)
        self.source_path_text.color = COLORS["text_primary"]
        self.source_change_btn.text = "更换"
        
        # v3.0 重构：快速扫描统计
        self._update_source_stats()
        
        # v3.0 重构：自动生成目标目录
        self._auto_generate_target()
        
        # v3.0 重构：智能推断分类
        self._infer_and_update_category()
        
        # 更新 UI 状态
        self._update_ui_state()
        self.page.update()
    
    def _handle_target_path(self, path: str):
        """v3.0 重构：处理目标目录路径"""
        self.output_path = Path(path)
        self._update_target_display()
        self.page.update()
    
    def _update_source_stats(self):
        """v3.0 重构：更新源目录统计"""
        try:
            scanner = PhotoScanner()
            count = 0
            total_size = 0
            
            for photo in scanner.scan(self.source_path):
                count += 1
                total_size += photo.size
            
            self.source_stats_text.value = f"💾 {count}张照片 | 占用 {format_size(total_size)}"
        except Exception as e:
            self.source_stats_text.value = "扫描失败，请检查目录权限"
    
    def _auto_generate_target(self):
        """v3.0 重构：自动生成目标目录"""
        if self.source_path:
            parent = self.source_path.parent
            target_name = generate_default_output_name(self.source_path.name)
            self.output_path = parent / target_name
            self._update_target_display()
    
    def _update_target_display(self):
        """v3.0 重构：更新目标目录显示"""
        if self.output_path:
            self.target_path_text.value = str(self.output_path)
            self.target_path_text.color = COLORS["text_primary"]
            self.target_change_btn.visible = True
            
            # v3.0 重构：磁盘空间检查
            _, _, free = get_disk_space(self.output_path.parent)
            free_gb = free / (1024 ** 3)
            
            if free_gb < 10:
                self.target_disk_text.value = f"💿 磁盘剩余: {format_size(free)} (⚠️ 空间不足)"
                self.target_disk_text.color = COLORS["danger"]
            elif free_gb < 50:
                self.target_disk_text.value = f"💿 磁盘剩余: {format_size(free)} (⚠️ 空间紧张)"
                self.target_disk_text.color = COLORS["warning"]
            else:
                self.target_disk_text.value = f"💿 磁盘剩余: {format_size(free)} (充足)"
                self.target_disk_text.color = COLORS["secondary"]
    
    def _infer_and_update_category(self):
        """v3.0 重构：智能推断分类并更新显示"""
        if self.source_path:
            self.inferred_category = infer_category(self.source_path.name)
            # 更新策略摘要显示
            self.strategy_chips[2].label.value = f"自动分类: {self.inferred_category}"
    
    def _update_ui_state(self):
        """v3.0 重构：根据状态更新 UI"""
        # 执行按钮状态
        if self.source_path and self.output_path:
            self.execute_btn.disabled = False
            self.execute_btn.style.bgcolor = COLORS["primary"]
        else:
            self.execute_btn.disabled = True
            self.execute_btn.style.bgcolor = COLORS["text_secondary"]
        
        # 检查磁盘空间是否足够
        if self.source_path and self.output_path:
            _, _, free = get_disk_space(self.output_path.parent)
            if free < 10 * (1024 ** 3):  # < 10GB
                self.execute_btn.disabled = True
    
    async def _open_settings(self, e=None):
        """v3.0 重构：打开设置抽屉"""
        self.page.end_drawer = self.settings_drawer
        await self.page.show_end_drawer()
    
    async def _open_settings_with_section(self, section: str):
        """v3.0 重构：打开设置抽屉并定位到指定区域"""
        # 在 Flet 中无法真正滚动到指定位置，但我们可以打开抽屉
        await self._open_settings()
    
    async def _close_settings(self, e=None):
        """v3.0 重构：关闭设置抽屉"""
        await self.page.close_end_drawer()
    
    async def _save_settings_and_close(self, e=None):
        """v3.0 重构：保存设置并关闭抽屉"""
        # 收集设置
        self.config["dedupe_enabled"] = self.dedupe_switch.value
        self.config["dedupe_fuzzy"] = self.dedupe_fuzzy_switch.value
        self.config["dedupe_threshold"] = int(self.dedupe_slider.value)
        self.config["archive_enabled"] = self.archive_switch.value
        self.config["archive_granularity"] = self.archive_radio.value
        
        # 内容识别设置
        self.config["recognition_enabled"] = self.recognition_switch.value
        categories = []
        if self.recognition_person_cb.value:
            categories.append("人物")
        if self.recognition_scene_cb.value:
            categories.append("景物")
        # 其他为必选
        categories.append("其他")
        self.config["recognition_categories"] = categories
        
        self.config["safety_mode"] = self.safety_radio.value
        self.config["preview_before_run"] = self.preview_checkbox.value
        self.config["generate_log"] = self.log_checkbox.value
        
        # 保存到本地存储
        self._save_settings()
        
        # 更新策略摘要显示
        self._update_strategy_chips()
        
        # 关闭抽屉
        await self._close_settings()
    
    def _update_strategy_chips(self):
        """v3.0 重构：更新策略摘要显示"""
        # 去重
        if self.config["dedupe_enabled"]:
            mode = "模糊去重" if self.config["dedupe_fuzzy"] else "精确去重"
            dedupe_text = mode
        else:
            dedupe_text = "不去重"
        
        # 归档
        if self.config["archive_enabled"]:
            granularity_map = {
                "year": "年仅归档",
                "year_month": "年月归档",
                "year_month_day": "年月日归档",
            }
            archive_text = granularity_map.get(
                self.config["archive_granularity"], "年月归档"
            )
        else:
            archive_text = "不归档"
        
        # 分类/识别
        if self.config.get("recognition_enabled", False):
            categories = self.config.get("recognition_categories", [])
            if categories:
                classify_text = f"识别: {','.join(categories)}"
            else:
                classify_text = "不识别"
        else:
            classify_text = "不识别"
        
        # 重新创建 Chips（Flet Chip label 不能直接修改）
        chip_style = ft.ButtonStyle(
            bgcolor=with_opacity(0.1, COLORS["text_secondary"]),
            side=ft.BorderSide(1, COLORS["border"]),
        )
        
        new_chips = [
            ft.Chip(
                label=ft.Text(dedupe_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("dedupe"),
            ),
            ft.Chip(
                label=ft.Text(archive_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("archive"),
            ),
            ft.Chip(
                label=ft.Text(classify_text, size=12, color=COLORS["text_secondary"]),
                on_click=lambda _: self._open_settings_with_section("recognition"),
            ),
        ]
        
        # 更新引用和 UI
        self.strategy_chips = new_chips
        # 触发重建
        self._rebuild_strategy_row()
    
    def _rebuild_strategy_row(self):
        """v3.0 重构：重建策略摘要行"""
        if hasattr(self, 'strategy_row') and self.strategy_row:
            self.strategy_row.controls = [
                ft.Text("整理策略: ", size=12, color=COLORS["text_secondary"]),
                *self.strategy_chips,
            ]
            self.page.update()
    
    def _reset_settings(self, e=None):
        """v3.0 重构：恢复默认设置"""
        self.config = DEFAULT_CONFIG.copy()
        
        # 更新控件状态
        self.dedupe_switch.value = self.config["dedupe_enabled"]
        self.dedupe_fuzzy_switch.value = self.config["dedupe_fuzzy"]
        self.dedupe_slider.value = self.config["dedupe_threshold"]
        self.archive_switch.value = self.config["archive_enabled"]
        self.archive_radio.value = self.config["archive_granularity"]
        
        # 内容识别设置
        self.recognition_switch.value = self.config.get("recognition_enabled", False)
        categories = self.config.get("recognition_categories", [])
        self.recognition_person_cb.value = "人物" in categories
        self.recognition_scene_cb.value = "景物" in categories
        self.recognition_person_cb.disabled = not self.recognition_switch.value
        self.recognition_scene_cb.disabled = not self.recognition_switch.value
        
        self.safety_radio.value = self.config["safety_mode"]
        self.preview_checkbox.value = self.config["preview_before_run"]
        self.log_checkbox.value = self.config["generate_log"]
        
        self.move_warning_banner.visible = False
        
        self.page.update()
    
    def _on_dedupe_switch_changed(self, e):
        """v3.0 重构：去重开关变化回调"""
        enabled = e.control.value
        self.dedupe_fuzzy_switch.disabled = not enabled
        self.dedupe_slider.disabled = not enabled or not self.dedupe_fuzzy_switch.value
        self.page.update()
    
    def _on_safety_mode_changed(self, e):
        """v3.0 重构：安全模式变化回调"""
        is_move = e.control.value == "move"
        self.move_warning_banner.visible = is_move
        self.page.update()
    
    def _on_recognition_switch_changed(self, e):
        """v3.0 重构：内容识别开关变化回调"""
        enabled = e.control.value
        self.recognition_person_cb.disabled = not enabled
        self.recognition_scene_cb.disabled = not enabled
        # 其他保持选中且禁用
        self.recognition_other_cb.value = True
        self.page.update()
    
    def _on_execute_click(self, e):
        """v3.0 重构：主执行按钮点击"""
        if not self.source_path or not self.output_path:
            return
        
        # 检查是否需要预览
        if self.config["preview_before_run"]:
            self._show_preview_dialog()
        else:
            self._start_organize()
    

    # ========== 预览对话框 ==========
    
    def _show_preview_dialog(self):
        """v3.0 重构：显示预览确认对话框"""
        self.app_state = AppState.PREVIEWING
        
        # 清空之前的数据，避免重复
        self.scanned_photos = []
        self.duplicate_groups = []
        self.classified_photos = {}
        
        # 扫描统计
        scanner = PhotoScanner()
        photo_count = 0
        total_size = 0
        
        try:
            for photo in scanner.scan(self.source_path):
                photo_count += 1
                total_size += photo.size
                self.scanned_photos.append(photo)
        except Exception as e:
            self._show_error_dialog(f"扫描失败: {e}")
            return
        
        # 去重快速扫描
        duplicate_count = 0
        space_to_save = 0
        
        if self.config["dedupe_enabled"]:
            try:
                dedup = Deduplicator()
                for photo in self.scanned_photos:
                    dedup.add_photo(photo.path)
                
                self.duplicate_groups = dedup.find_all_duplicates(
                    include_similar=self.config["dedupe_fuzzy"]
                )
                duplicate_count = len(self.duplicate_groups)
                
                for group in self.duplicate_groups:
                    for dup_path in group.can_delete:
                        space_to_save += dup_path.stat().st_size
            except Exception as e:
                print(f"去重分析失败: {e}")
        
        # 构建目录树预览
        tree_items = self._build_preview_tree()
        
        # 安全提示
        if self.config["safety_mode"] == "copy":
            safety_text = "✅ 安全模式：源文件将保留"
            safety_color = COLORS["secondary"]
        else:
            safety_text = "⚠️ 移动模式：操作不可撤销"
            safety_color = COLORS["warning"]
        
        # 统计卡片
        stats_row = ft.Row(
            [
                self._build_stat_card(str(photo_count), "总照片"),
                self._build_stat_card(str(duplicate_count), "重复组"),
                self._build_stat_card(format_size(space_to_save), "预计释放"),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )
        
        # 目录树预览
        tree_view = ft.Column(
            [
                ft.Text("📁 将创建以下目录结构:", size=14, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(tree_items, spacing=4),
                    padding=ft.padding.all(16),
                    border=ft.border.all(1, COLORS["border"]),
                    border_radius=ft.border_radius.all(8),
                    bgcolor=with_opacity(0.5, COLORS["background"]),
                ),
            ],
            spacing=8,
        )
        
        # 创建对话框
        self.preview_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("📋 执行预览", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column(
                    [
                        stats_row,
                        ft.Divider(),
                        tree_view,
                        ft.Container(height=8),
                        ft.Text(safety_text, color=safety_color, size=12),
                    ],
                    spacing=16,
                    tight=True,
                ),
                width=500,
                height=400,
            ),
            actions=[
                ft.TextButton("返回修改", on_click=self._close_preview_dialog),
                ft.ElevatedButton(
                    "确认执行",
                    on_click=self._on_preview_confirm,
                    style=ft.ButtonStyle(bgcolor=COLORS["primary"], color="white"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.show_dialog(self.preview_dialog)
    
    def _build_stat_card(self, value: str, label: str) -> ft.Card:
        """v3.0 重构：构建统计卡片"""
        return ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(value, size=24, weight=ft.FontWeight.BOLD, color=COLORS["primary"]),
                        ft.Text(label, size=12, color=COLORS["text_secondary"]),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                ),
                padding=ft.padding.all(16),
                width=120,
            ),
            elevation=1,
        )
    
    def _build_preview_tree(self) -> list:
        """v3.0 重构：构建目录树预览"""
        items = []
        
        # 去重后照片目录
        if self.config.get("recognition_enabled", False):
            # 启用了内容识别，显示识别分类
            categories = self.config.get("recognition_categories", [])
            for cat in categories:
                cat_item = ft.ExpansionTile(
                    title=ft.Text(f"📂 去重后照片/{cat}/", color=COLORS["primary"]),
                    controls=[
                        ft.Container(
                            content=ft.Text("  └── 照片将按规则归档", size=12, color=COLORS["text_secondary"]),
                            margin=ft.margin.only(left=16),
                        ),
                    ],
                )
                items.append(cat_item)
        else:
            # 未启用内容识别
            cat_item = ft.ExpansionTile(
                title=ft.Text("📂 去重后照片/", color=COLORS["primary"]),
                controls=[
                    ft.Container(
                        content=ft.Text("  └── 照片将按时间归档", size=12, color=COLORS["text_secondary"]),
                        margin=ft.margin.only(left=16),
                    ),
                ],
            )
            items.append(cat_item)
        
        # 重复文件目录
        if self.config["dedupe_enabled"] and self.duplicate_groups:
            dup_item = ft.ExpansionTile(
                title=ft.Text(f"📂 重复照片/ ({len(self.duplicate_groups)}组重复)", color=COLORS["warning"]),
                controls=[
                    ft.Container(
                        content=ft.Text("  └── 重复文件将保留原目录结构", size=12, color=COLORS["text_secondary"]),
                        margin=ft.margin.only(left=16),
                    ),
                ],
            )
            items.append(dup_item)
        
        if not items:
            items.append(ft.Text("  未启用分类或去重功能", size=12, color=COLORS["text_secondary"]))
        
        return items
    
    def _close_preview_dialog(self, e=None):
        """v3.0 重构：关闭预览对话框"""
        self.page.pop_dialog()
        self.app_state = AppState.SOURCE_SELECTED
    
    def _on_preview_confirm(self, e):
        """v3.0 重构：预览确认后执行"""
        self._close_preview_dialog()
        self._start_organize()
    
    # ========== 执行进度浮层 ==========
    
    def _start_organize(self):
        """v3.0 重构：开始整理"""
        self.app_state = AppState.ORGANIZING
        self.cancel_requested = False
        
        # 显示进度浮层
        self._show_progress_overlay()
        
        # 在后台线程执行
        thread = threading.Thread(target=self._do_organize)
        thread.daemon = True
        thread.start()
        
        # 启动进度更新轮询
        self._poll_progress()
    
    def _show_progress_overlay(self):
        """v3.0 重构：显示进度浮层"""
        # 进度条
        self.progress_bar = ft.ProgressBar(
            value=0,
            width=400,
            color=COLORS["primary"],
            bgcolor=COLORS["border"],
        )
        
        # 状态文本
        self.progress_current_file = ft.Text(
            "准备中...",
            size=14,
            color=COLORS["text_primary"],
            no_wrap=True,
            width=400,
        )
        
        self.progress_stats = ft.Text(
            "已处理: 0/0 张 | 预计剩余: 计算中... | 速度: - 张/秒",
            size=12,
            color=COLORS["text_secondary"],
        )
        
        # 进度卡片
        progress_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("📊 正在整理照片", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(height=16),
                        self.progress_bar,
                        ft.Container(height=8),
                        self.progress_current_file,
                        ft.Container(height=4),
                        self.progress_stats,
                        ft.Container(height=16),
                        ft.Row(
                            [
                                ft.TextButton(
                                    "📋 查看日志",
                                    on_click=self._toggle_log_view,
                                ),
                                ft.TextButton(
                                    "❌ 取消任务",
                                    on_click=self._request_cancel,
                                    style=ft.ButtonStyle(color=COLORS["danger"]),
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=ft.padding.all(32),
                width=480,
            ),
            elevation=12,
        )
        
        # 半透明遮罩 + 中央卡片
        self.progress_overlay = ft.Container(
            content=progress_card,
            bgcolor=with_opacity(0.9, COLORS["background"]),
            alignment=ft.alignment.Alignment(0, 0),
            expand=True,
        )
        
        # 添加到页面 overlay
        self.page.overlay.append(self.progress_overlay)
        self.page.update()
    
    def _hide_progress_overlay(self):
        """v3.0 重构：隐藏进度浮层"""
        if self.progress_overlay in self.page.overlay:
            self.page.overlay.remove(self.progress_overlay)
        self.page.update()
    
    def _update_progress(self, current: int, total: int, message: str):
        """v3.0 重构：更新进度（从后台线程调用）"""
        self.progress_queue.put({
            "type": "progress",
            "current": current,
            "total": total,
            "message": message,
        })
    
    def _poll_progress(self):
        """v3.0 重构：轮询进度更新（100ms间隔）"""
        try:
            while True:
                # 非阻塞获取队列消息
                try:
                    msg = self.progress_queue.get(timeout=0.1)
                    if msg["type"] == "progress":
                        current = msg["current"]
                        total = msg["total"]
                        message = msg["message"]
                        
                        progress = current / total if total > 0 else 0
                        
                        self.progress_bar.value = progress
                        self.progress_current_file.value = f"当前: {message}"
                        self.progress_stats.value = f"已处理: {current}/{total} 张 ({progress*100:.1f}%)"
                        
                        self.page.update()
                    elif msg["type"] == "complete":
                        self._hide_progress_overlay()
                        self._show_complete_dialog(msg["result"])
                        return
                    elif msg["type"] == "error":
                        self._hide_progress_overlay()
                        self._show_error_dialog(msg["message"])
                        return
                except queue.Empty:
                    pass
                
                # 检查是否需要继续轮询
                if self.app_state != AppState.ORGANIZING:
                    return
                
                time.sleep(0.1)
        except Exception as e:
            print(f"进度轮询出错: {e}")
    
    def _do_organize(self):
        """v3.0 重构：执行整理（后台线程）"""
        try:
            # 1. 扫描（如果还没扫描）
            if not self.scanned_photos:
                self._update_progress(0, 100, "扫描照片中...")
                scanner = PhotoScanner()
                self.scanned_photos = list(scanner.scan(self.source_path))
            
            total = len(self.scanned_photos)
            
            # 2. 去重分析
            if self.config["dedupe_enabled"]:
                self._update_progress(0, total, "分析重复文件...")
                dedup = Deduplicator()
                for i, photo in enumerate(self.scanned_photos):
                    dedup.add_photo(photo.path)
                    if i % 10 == 0:
                        self._update_progress(i, total, f"计算哈希: {photo.path.name}")
                
                self.duplicate_groups = dedup.find_all_duplicates(
                    include_similar=self.config["dedupe_fuzzy"]
                )
            
            # 3. 内容识别（仅在启用时）
            if self.config.get("recognition_enabled", False):
                self._update_progress(0, total, "识别照片内容...")
                classifier = PhotoClassifier()
                for i, photo in enumerate(self.scanned_photos):
                    result = classifier.classify(photo.path)
                    self.classified_photos[photo.path] = result.category
                    if i % 10 == 0:
                        self._update_progress(i, total, f"识别: {photo.path.name}")
            
            # 4. 生成并执行整理计划
            format_map = {
                "year": DateFormat.YEAR,
                "year_month": DateFormat.YEAR_MONTH,
                "year_month_day": DateFormat.YEAR_MONTH_DAY,
            }
            
            mode_map = {
                "copy": OrganizeMode.COPY,
                "move": OrganizeMode.MOVE,
            }
            
            organizer = PhotoOrganizer(
                output_dir=self.output_path,
                source_dir=self.source_path,
                date_format=format_map.get(self.config["archive_granularity"], DateFormat.YEAR_MONTH),
                recognition_enabled=self.config.get("recognition_enabled", False),
                recognition_categories=self.config.get("recognition_categories", []),
                mode=mode_map.get(self.config["safety_mode"], OrganizeMode.COPY),
            )
            
            # 设置进度回调
            organizer.set_progress_callback(
                lambda cur, tot, msg: self._update_progress(cur, tot, msg)
            )
            
            # 生成计划（传入重复组）
            plans = organizer.generate_plan(
                self.scanned_photos, 
                duplicate_groups=self.duplicate_groups,
                categories=self.classified_photos
            )
            
            # 执行计划
            result = organizer.execute(plans)
            
            # 发送完成消息
            self.progress_queue.put({
                "type": "complete",
                "result": result,
            })
            
        except Exception as e:
            error_detail = traceback.format_exc()
            self.progress_queue.put({
                "type": "error",
                "message": f"{str(e)}\n\n{error_detail}",
            })
    
    def _request_cancel(self, e=None):
        """v3.0 重构：请求取消任务"""
        self.cancel_requested = True
        self._hide_progress_overlay()
        self.app_state = AppState.SOURCE_SELECTED
    
    def _toggle_log_view(self, e=None):
        """v3.0 重构：切换日志视图"""
        # 简化实现：显示一个 SnackBar 提示
        snack = ft.SnackBar(content=ft.Text("日志功能开发中..."))
        self.page.overlay.append(snack)
        snack.open = True
        self.page.update()
    
    # ========== 完成对话框 ==========
    
    def _show_complete_dialog(self, result):
        """v3.0 重构：显示完成对话框"""
        self.app_state = AppState.COMPLETED
        
        success_count = len(result.success) if hasattr(result, 'success') else 0
        failed_count = len(result.failed) if hasattr(result, 'failed') else 0
        
        self.complete_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.icons.Icons.CHECK_CIRCLE, color=COLORS["secondary"], size=32),
                    ft.Text("整理完成！", size=20, weight=ft.FontWeight.BOLD),
                ],
                spacing=12,
            ),
            content=ft.Column(
                [
                    ft.Text(f"成功处理: {success_count} 张照片", size=14),
                    ft.Text(f"失败: {failed_count} 张照片", size=14),
                    ft.Text(f"输出目录: {self.output_path}", size=12, color=COLORS["text_secondary"]),
                ],
                spacing=8,
                tight=True,
            ),
            actions=[
                ft.TextButton(
                    "打开输出目录",
                    on_click=self._open_output_directory,
                ),
                ft.ElevatedButton(
                    "再次整理",
                    on_click=self._reset_and_close_complete,
                    style=ft.ButtonStyle(bgcolor=COLORS["primary"], color="white"),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.show_dialog(self.complete_dialog)
    
    def _open_output_directory(self, e=None):
        """v3.0 重构：打开输出目录"""
        import subprocess
        import os
        
        try:
            if os.name == 'nt':  # Windows
                subprocess.Popen(['explorer', str(self.output_path)])
            else:  # macOS/Linux
                subprocess.Popen(['open', str(self.output_path)])
        except Exception as e:
            snack = ft.SnackBar(content=ft.Text(f"无法打开目录: {e}"))
            self.page.overlay.append(snack)
            snack.open = True
            self.page.update()
        
        if self.complete_dialog:
            self.page.pop_dialog()
    
    def _reset_and_close_complete(self, e=None):
        """v3.0 重构：重置并关闭完成对话框"""
        self.page.pop_dialog()
        
        # 重置状态
        self.app_state = AppState.IDLE
        self.source_path = None
        self.output_path = None
        self.scanned_photos = []
        self.duplicate_groups = []
        self.classified_photos = {}
        self.inferred_category = "未分类"
        
        # 重置 UI
        self.source_path_text.value = "点击选择或拖拽文件夹"
        self.source_path_text.color = COLORS["text_secondary"]
        self.source_stats_text.value = ""
        self.source_change_btn.text = "选择目录"
        
        self.target_path_text.value = "选择源目录后自动生成"
        self.target_path_text.color = COLORS["text_secondary"]
        self.target_disk_text.value = ""
        self.target_change_btn.visible = False
        
        self._update_ui_state()
        self.page.update()
    
    # ========== 错误处理 ==========
    
    def _show_error_dialog(self, message: str):
        """v3.0 重构：显示错误对话框"""
        self.app_state = AppState.ERROR
        
        error_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.icons.Icons.ERROR, color=COLORS["danger"], size=32),
                    ft.Text("发生错误", size=20, weight=ft.FontWeight.BOLD),
                ],
                spacing=12,
            ),
            content=ft.Column(
                [
                    ft.Text(message, selectable=True),
                ],
                scroll=ft.ScrollMode.AUTO,
                tight=True,
            ),
            actions=[
                ft.TextButton(
                    "返回",
                    on_click=lambda e: self.page.pop_dialog(),
                ),
            ],
        )
        
        self.page.show_dialog(error_dialog)


# ========== 应用入口 ==========

def main(page: ft.Page):
    """v3.0 重构：Flet 应用入口"""
    PhotoOrganizerApp(page)


if __name__ == "__main__":
    ft.app(target=main)
