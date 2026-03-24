# UI Design Specification - Photo Organizer v3.0
**文档版本：** v3.0  
**生成日期：** 2026-03-22 10:10  
**技术栈：** Flet (Python)  
**设计目标：** 极简操作、智能默认、安全兜底

---

## 1. 输入材料清单

### 1.1 上游需求文档
- `@docs/02-requirements/PRD-v1.0.md` —— 提取 P0 功能（时间归档/去重/分类）和安全底线（零删除承诺）
- `@docs/03-architecture/tech-stack-decision.md` —— 确认 Flet 技术限制（无原生拖拽 API/无 WebSocket 真推送）

### 1.2 会话决策记录（本次设计依据）
- **用户指令（2026-03-22 09:18）：** "减少用户配置，默认配置可修改，可用齿轮图标打开配置页面"
- **用户指令（2026-03-22 09:58）：** "用户主要选择待整理的目录和输出目录，点击执行即可"
- **设计共识：** 从 v2.0 四步流程（配置→策略→预览→执行）简化为"一键启动→智能分析→确认执行"三步

### 1.3 现有代码参考
- `@src/photo_organizer/gui.py` —— 当前 Flet 界面实现（v2.0 四步流程版本，需重构）
- `@DEVELOPMENT.md` —— 模块架构说明（scanner/deduplicator/classifier/organizer_v2）
- `@SESSION_SUMMARY.md` —— v2.0 改造总结（Flet 技术栈确认、色彩系统）
- `@ui.md` —— 历史 UI 设计规范（色彩/token 参考）
- `@web.doc` —— 当前软件页面截图/描述（需简化）

---

## 2. 设计系统（Design Tokens）

继承并简化 v2.0 色彩系统，保持品牌一致性：

```yaml
colors:
  primary: "#2563EB"        # Blue-600 — 主按钮、进度条、关键操作
  secondary: "#10B981"      # Emerald-500 — 完成状态、安全模式指示
  warning: "#F59E0B"        # Amber-500 — 注意事项、移动模式警告
  danger: "#EF4444"         # Red-500 — 磁盘空间不足、错误状态
  background: "#F9FAFB"     # Gray-50 — 主页面背景
  surface: "#FFFFFF"        # 卡片背景、抽屉背景
  text_primary: "#111827"   # Gray-900 — 主文本、目录路径
  text_secondary: "#6B7280" # Gray-500 — 策略摘要、辅助说明
  border: "#E5E7EB"         # Gray-200 — 卡片边框、分隔线

typography:
  font_family: "Inter, system-ui, sans-serif"  # Flet 默认系统字体栈
  heading_1: "20px"         # AppBar 标题
  heading_2: "16px"         # 卡片标题、对话框标题
  body: "14px"              # 正文、按钮文字、路径显示
  caption: "12px"           # 策略摘要、统计标签、时间预估
  mono: "JetBrains Mono, monospace"  # 日志输出、文件哈希显示

spacing:
  unit: "8px"
  xs: "8px"                 # Chip 间距、图标与文字间距
  sm: "16px"                # 卡片内边距、按钮内边距
  md: "24px"                # 模块间距（目录卡片与执行按钮之间）
  lg: "32px"                # 主要区域分隔
  xl: "48px"                # 页面垂直居中留白

elevation:
  card: 1                   # 目录选择卡片（轻微上浮）
  button_hover: 4           # 主按钮悬停阴影
  drawer: 8                 # 设置抽屉（明显层叠）
  dialog: 12                # 确认对话框（最高层级）

radius:
  sm: "4px"                 # 输入框、小按钮
  md: "8px"                 # 卡片
  lg: "12px"                # 主执行按钮（大圆角强调）
  xl: "16px"                # 抽屉顶部圆角
  3. 页面清单与布局规范
3.1 主界面（Main Page）— 唯一核心页面
设计目标： 单屏完成 80% 操作，零干扰、零学习成本
plain
复制
┌─────────────────────────────────────────────────────────────┐
│  📷 Photo Organizer                                [⚙️]  │  ← AppBar (56px)
├─────────────────────────────────────────────────────────────┤
│                                                             │
│     ┌─────────────────────────────────────────┐            │
│     │  📁 源照片目录                          │            │
│     │                                         │            │
│     │  [点击选择或拖拽文件夹到此处]            │            │  ← 目录卡片 1
│     │                                         │            │
│     │  D:\备份\手机照片  [更换]               │            │
│     │  💾 1,250张照片 | 占用 4.2GB            │            │
│     └─────────────────────────────────────────┘            │
│                      (间距 24px)                            │
│     ┌─────────────────────────────────────────┐            │
│     │  📂 输出目录 (自动创建子目录)            │            │
│     │                                         │            │
│     │  D:\照片整理_20260322   [修改]          │            │  ← 目录卡片 2
│     │  💿 磁盘剩余: 156GB (充足)              │            │
│     └─────────────────────────────────────────┘            │
│                      (间距 32px)                            │
│     ┌─────────────────────────────────────────┐            │
│     │                                         │            │
│     │        🚀 开始智能整理                   │            │  ← 主执行按钮
│     │                                         │            │
│     │   将自动执行: 去重 → 时间归档 → 分类    │            │
│     │   预计耗时: 2-3分钟 | 安全模式(复制+备份)│            │
│     │                                         │            │
│     └─────────────────────────────────────────┘            │
│                                                             │
│  ─────────────────────────────────────────────────────    │
│                                                             │
│      整理策略: [精确去重] [年月归档] [自动分类]            │  ← 策略摘要（可点击）
│      点击齿轮图标可调整默认设置                              │
└─────────────────────────────────────────────────────────────┘
区域详解：
表格
区域	位置/尺寸	Flet 组件	交互说明	技术限制处理
AppBar	顶部固定，56px 高	ft.AppBar	左侧 ft.Text("📷 Photo Organizer")，右侧 ft.IconButton(icon=ft.icons.SETTINGS, tooltip="高级设置", on_click=open_settings)	背景色 bgcolor=ft.colors.BACKGROUND，阴影 elevation=0（扁平化）
源目录卡片	上部，宽度 600px（大屏）/90%（小屏），居中	ft.Card > ft.Container	点击整体唤起 ft.FilePicker(directory=True)；支持 on_drag_enter/over/drop 事件模拟拖拽（视觉反馈：边框变蓝）；已选状态下显示 ft.ListTile(leading=ft.Icon(ft.icons.FOLDER), title=路径, subtitle=统计信息, trailing=ft.TextButton("更换"))	Flet 无原生拖拽 API，使用 ft.Container 监听事件并改变 border 属性模拟
目标目录卡片	中部，同上宽度	ft.Card > ft.Container	默认自动生成 {源目录名}_已整理_{YYYYMMDD}；点击"修改"唤起 ft.FilePicker；磁盘空间检查：<50GB 显示黄色警告图标，<10GB 显示红色错误图标并禁用执行按钮	使用 shutil.disk_usage() 在 Python 层计算，通过 ft.Row 组合 ft.Icon+ft.Text 显示状态
主执行按钮	中下部，视觉焦点	ft.ElevatedButton 包装在 ft.Container 中	尺寸：宽 400px（大屏）/100%（小屏），高 56px，圆角 12px；主色填充 bgcolor=ft.colors.PRIMARY，文字白色 16px 加粗；悬停效果：轻微放大（scale 1.02）+ 阴影提升；点击后若设置允许预览 → 弹出确认对话框；若关闭预览 → 直接进入执行状态并显示进度	使用 ft.Container 包装实现 scale 动画（ft.animation.Animation(300, ft.AnimationCurve.EASE_IN_OUT)）；使用 ft.AnimatedSwitcher 在按钮和进度条之间切换
策略摘要	底部居中，距底 24px	ft.Row > ft.Chip × 3	显示当前生效策略："精确去重"、"年月归档"、"自动分类"；颜色 ft.colors.GREY_500，字号 12px；点击任意 Chip 直接打开设置抽屉并定位到对应选项卡	Chips 使用 on_click 回调，通过 page.show_bottom_sheet() 或 end_drawer 打开设置
进度浮层（执行时显示）	覆盖中部，非模态	ft.Container 半透明遮罩 + ft.Card	显示 ft.LinearProgressIndicator(确定性进度 0-100%)、当前文件名（单行截断）、ETA 倒计时、实时吞吐率（照片/秒）；右上角 ft.IconButton(ft.icons.CLOSE) 可取消任务	使用 page.overlay.append() 添加，避免阻塞；通过 page.update() 每 100ms 轮询更新进度（Flet 无 WebSocket 真推送）
3.2 设置抽屉（Settings Drawer）— 齿轮图标触发
实现方式： ft.NavigationDrawer（从右侧滑出，桌面端习惯）或 ft.BottomSheet（从底部滑出，移动端友好）
建议： 桌面端使用 ft.NavigationDrawer（end=True 从右向左滑出）
plain
复制
┌───────────────────────────────────────────┐
│  ⚙️ 整理设置                    [恢复默认] │  ← 标题栏（48px）
├───────────────────────────────────────────┤
│                                           │
│  📋 整理策略                               │
│  ┌─────────────────────────────────────┐ │
│  │ 智能去重              [Switch: ON]   │ │  ← 默认开启
│  │ └─ 模糊匹配(>90%)    [Switch: ON]   │ │  ← 子选项，缩进 16px
│  └─────────────────────────────────────┘ │
│                                           │
│  ┌─────────────────────────────────────┐ │
│  │ 时间归档              [Switch: ON]   │ │  ← 默认开启
│  │ └─ 归档粒度: [年仅归档 ○]            │ │  ← RadioGroup
│  │             [年月归档 ●]             │ │
│  │             [年月日归档 ○]           │ │
│  └─────────────────────────────────────┘ │
│                                           │
│  ┌─────────────────────────────────────┐ │
│  │ 内容分类              [Switch: ON]   │ │  ← 默认开启
│  │ └─ 模式: [自动识别目录名 ●]          │ │  ← 默认
│  │          [全部归为"未分类" ○]        │ │
│  │          [手动指定: [人物 ▼] ○]      │ │
│  └─────────────────────────────────────┘ │
│                                           │
│  🛡️ 安全设置                               │
│  ┌─────────────────────────────────────┐ │
│  │ 操作模式: [复制模式(安全) ●]         │ │  ← Radio，默认
│  │           [移动模式(有风险) ○]       │ │  ← 选择时弹出 Banner 警告
│  └─────────────────────────────────────┘ │
│  [x] 执行前预览（推荐首次开启）            │  ← Checkbox，默认勾选
│  [x] 生成详细操作日志(CSV)                │  ← Checkbox，默认勾选
│                                           │
├───────────────────────────────────────────┤
│      [保存设置]              [取消]      │  ← 底部按钮栏
└───────────────────────────────────────────┘
区域详解：
表格
区域	布局	Flet 组件	交互说明
标题栏	顶部固定	ft.Row(alignment=spaceBetween)	左侧 ft.Text("⚙️ 整理设置", size=16, weight=bold)，右侧 ft.TextButton("恢复默认", on_click=reset_defaults)
策略分区	上部，可滚动	ft.ListView(spacing=16px) 包含 3 个 ft.Card	每个策略一个卡片，包含主 ft.Switch 和子选项；子选项使用 ft.Container(margin=ft.margin.only(left=16)) 缩进
去重子选项	去重卡片内	ft.Row > ft.Switch + ft.Slider(min=80, max=99, divisions=19, label="{value}%")	模糊匹配阈值，默认 90%；仅当主开关开启时可用 disabled=False
归档粒度	时间卡片内	ft.RadioGroup 包含 3 个 ft.Radio	选项："year"、"year_month"、"year_month_day"；默认选中 "year_month"（符合 PRD 验收标准）
分类模式	分类卡片内	ft.RadioGroup 包含 3 个 ft.Radio，第三个带 ft.Dropdown	自动识别（默认）/ 全部未分类 / 手动指定（下拉选择人物/景物/其他）
安全设置	下部独立卡片	ft.RadioGroup + ft.Banner	选择"移动模式"时，下方动态显示 ft.Banner(bgcolor=ft.colors.AMBER_100, leading=ft.Icon(ft.icons.WARNING), content=ft.Text("移动模式将直接重定位源文件，建议先执行一次复制模式确认无误后再使用"))
复选框区	底部	ft.Column > ft.Checkbox × 2	"执行前预览"默认勾选（P0.3 安全底线），"生成日志"默认勾选（P0.4 审计要求）
底部按钮	底部固定，距底 16px	ft.Row(alignment=spaceEvenly)	"保存设置"（主色按钮）保存到 page.client_storage 并关闭抽屉；"取消"（文字按钮）直接关闭不保存
智能默认配置（用户无感知）：
Python
复制
DEFAULT_CONFIG = {
    "dedupe_enabled": True,           # 去重总开关
    "dedupe_fuzzy": True,             # 模糊匹配（pHash）
    "dedupe_threshold": 90,           # 相似度阈值
    
    "archive_enabled": True,          # 时间归档总开关
    "archive_granularity": "year_month",  # 默认年月（PRD 要求支持 year/year_month/year_month_day）
    
    "classify_enabled": True,         # 分类总开关
    "classify_mode": "auto",          # 自动识别目录名（关键词：人/自拍/合影/portrait→人物；景/风景/旅游/scenery→景物；其他→未分类）
    
    "safety_mode": "copy",            # 复制模式（安全）
    "preview_before_run": True,       # 执行前预览（首次强制）
    "generate_log": True,             # 生成 CSV 日志
    
    "output_suffix": "_已整理",       # 自动命名后缀
    "conflict_resolution": "rename"   # 冲突自动重命名（不覆盖）
}
3.3 执行确认对话框（Confirm Dialog）— 执行前预览
触发条件： 点击主按钮且 preview_before_run=True（默认）
plain
复制
┌───────────────────────────────────────────┐
│  📋 执行预览                      [X]    │  ← 标题栏
├───────────────────────────────────────────┤
│                                           │
│  📊 整理统计                               │
│  ┌──────────┬──────────┬──────────┐      │
│  │ 1,250张  │ 35组     │ 120MB    │      │
│  │ 总照片   │ 重复照片 │ 预计释放 │      │
│  └──────────┴──────────┴──────────┘      │
│                                           │
│  📁 将创建以下目录结构：                    │
│  ┌─────────────────────────────────────┐ │
│  │  📂 人物/                            │ │
│  │     └── 📂 2024/                    │ │
│  │         └── 📂 2024-03/             │ │
│  │             └── 156张照片           │ │
│  │  📂 景物/                            │ │
│  │     └── 89张照片                    │ │
│  │  📂 重复待确认/                      │ │
│  │     └── 35张照片 (将被隔离)         │ │
│  └─────────────────────────────────────┘ │
│                                           │
│  ⚠️ 安全提示：将在复制模式下执行，源文件保留  │
│                                           │
├───────────────────────────────────────────┤
│  [返回修改]                  [确认执行]    │  ← 底部按钮（右主左次）
└───────────────────────────────────────────┘
区域详解：
表格
区域	布局	Flet 组件	交互说明
统计卡片	上部，横向三列	ft.Row(alignment=spaceEvenly) 包含 3 个 ft.Card	每个卡片 ft.Column 居中，大号数字（24px，主色）+ 小号标签（12px，灰色）；显示：总照片数、发现重复组数、预计释放磁盘空间
目录树预览	中部，可折叠	ft.ExpansionTile(initially_expanded=True, title=ft.Text("📁 将创建以下目录结构"))	使用 ft.TreeView（Flet 0.25+）或自定义缩进 ft.Column 展示层级；不同颜色标记：人物/景物（蓝色）、重复（黄色）；仅展示结构不展示完整文件名（避免大数据量卡顿）
安全提示	底部条件显示	ft.Banner 或 ft.Row	若当前为复制模式：绿色勾选图标 + "安全模式：源文件将保留"；若为移动模式：黄色警告图标 + "移动模式：操作不可撤销"
操作按钮	底部固定	ft.Row(alignment=spaceBetween)	左侧 ft.TextButton("返回修改") 关闭对话框；右侧 ft.ElevatedButton("确认执行", bgcolor=ft.colors.PRIMARY) 关闭对话框并启动执行流程，按钮上可显示 ft.ProgressRing(直径 16px) 表示加载中
3.4 执行进度页面（执行状态覆盖层）
触发条件： 点击"确认执行"后
plain
复制
┌───────────────────────────────────────────┐
│                                           │
│            📊 正在整理照片                 │
│                                           │
│     ████████████████████░░░░  78%        │
│                                           │
│     当前: IMG_20240321_143022.jpg         │
│     已处理: 978/1,250 张                  │
│     预计剩余: 45秒 | 速度: 12张/秒        │
│                                           │
│     [📋 查看实时日志]  [❌ 取消任务]       │
│                                           │
└───────────────────────────────────────────┘
实现： 使用 ft.Stack 层叠在主页面上，ft.Container(bgcolor=ft.colors.with_opacity(0.9, ft.colors.BACKGROUND)) 作为半透明遮罩，中央 ft.Card 包含进度信息。
4. 响应式策略
基于 Flet 跨平台特性，优先桌面端（Windows）：
yaml
复制
breakpoints:
  compact: "< 800px"        # 小窗口/移动端：单列，目录卡片宽度 100%-32px，按钮全宽
  medium: "800-1200px"     # 平板/小屏笔记本：目录卡片宽度 80%，居中
  expanded: "> 1200px"      # 桌面大屏：目录卡片固定 600px，两侧留白

adaptive_rules:
  - "目录卡片: compact 模式垂直内边距增大（触控友好），expanded 模式水平布局（图标左文字右）"
  - "主执行按钮: compact 模式宽度 calc(100% - 32px)，expanded 模式固定 400px"
  - "设置抽屉: compact 模式使用 ft.BottomSheet（全屏），expanded 模式使用 ft.NavigationDrawer（右侧 400px）"
  - "策略摘要 Chips: compact 模式垂直排列，expanded 模式水平排列"
  - "确认对话框统计卡片: compact 模式垂直堆叠（3行），expanded 模式水平排列（3列）"
5. 交互状态定义
5.1 主界面状态机
Python
复制
class AppState(Enum):
    IDLE = "idle"                    # 初始状态：等待选择源目录，执行按钮禁用
    SOURCE_SELECTED = "source_ready" # 已选源目录，自动生成目标目录，执行按钮启用
    TARGET_MODIFIED = "target_ready" # 手动修改了目标目录，执行按钮启用
    SCANNING = "scanning"            # 点击执行后、预览前：快速扫描元数据（轻量进度）
    PREVIEWING = "previewing"        # 显示确认对话框（若开启预览）或直接进入 ORGANIZING
    ORGANIZING = "organizing"        # 执行文件操作：显示全屏进度浮层，可取消
    COMPLETED = "completed"          # 完成：显示成功对话框，提供"打开目录"和"再次整理"
    ERROR = "error"                  # 错误：显示错误对话框（权限/磁盘满等），提供重试/返回
5.2 状态视觉表现
表格
状态	视觉元素	Flet 实现
IDLE	执行按钮 disabled=True，颜色灰色；源目录卡片显示提示文字"请先选择照片目录"	ft.ElevatedButton(disabled=True, bgcolor=ft.colors.GREY_300)
SCANNING	按钮变为进度环 + "分析中..."；策略摘要隐藏	ft.AnimatedSwitcher 切换为 ft.Row([ft.ProgressRing(), ft.Text("分析中...")])
ORGANIZING	全屏半透明遮罩，中央白色卡片，进度条 0-100%，实时更新	page.overlay.append(progress_overlay)，ft.LinearProgressIndicator 每 100ms 更新 value
COMPLETED	弹出 ft.AlertDialog，显示 ✅ 图标，统计结果（整理耗时、释放空间、生成目录数），按钮"打开输出目录"、"再次整理"	使用 ft.TextButton + ft.ElevatedButton 组合
6. 与上游文档对齐检查
6.1 PRD-v1.0 对齐确认
[x] P0.1 时间归档： 默认开启，支持 year/year_month/year_month_day，默认 year_month（在设置抽屉中通过 RadioGroup 配置）
[x] P0.2 去重： 默认开启（MD5+pHash），重复文件隔离到 /{类型}/重复待确认/，不在主界面暴露复杂去重参数，仅提供开关和阈值滑块
[x] P0.3 安全移动： 默认复制模式（safety_mode="copy"），移动模式需在设置中切换并二次确认；零删除承诺（界面无删除按钮，仅"隔离"到重复目录）
[x] P0.4 审计日志： 默认开启生成 CSV 日志，在设置中提供开关控制
[x] P0.5 元数据修复： 异常时间照片自动移动到 /{类型}/时间异常/，不提示用户选择（后台处理），在日志中记录
6.2 DEVELOPMENT.md 架构对齐
分类推断： 主界面不暴露 classify_mode，默认使用 classifier.py 的启发式规则（目录名关键词识别），匹配关键词库：
人物：["人", "自拍", "合影", "portrait", "family", "face", "photo"]
景物：["景", "风景", "旅游", "travel", "scenery", "landscape", "view"]
其他：未匹配时默认 UNKNOWN
去重器： 调用 deduplicator.py，默认启用双重哈希，模糊匹配阈值 90%
整理器： 调用 organizer_v2.py，默认 mode="copy"，事务日志支持回滚
7. 阻断条件（进入开发前确认）
[ ] 目录关键词库确认： 自动分类的触发词（人物/景物）是否足够覆盖中文场景？是否需要支持用户自定义关键词（可在 P1 阶段添加）？
[ ] 预览强制策略： 首次使用是否强制弹出预览（无论设置如何），后续才允许"一键执行"？这关系到 P0.3 安全底线的实现方式
[ ] 抽屉实现选择： 桌面端使用 ft.NavigationDrawer（右侧滑出）还是 ft.BottomSheet（底部弹出）？建议桌面端用 NavigationDrawer（更专业）
[ ] 进度更新频率： Flet 使用 page.update() 轮询，建议 100ms-200ms 间隔，避免过于频繁导致界面卡顿，是否接受？
[ ] 输出目录命名： 默认 {源目录名}_已整理_{日期} 是否可接受？是否允许"原地整理"（输出=输入，仅分类子目录，风险较高）？
8. 执行指令（代码调整步骤）
基于本 ui-spec-v3.0.md 重构现有 gui.py 的步骤：
保留基础： 读取当前 gui.py，保留 Flet 应用初始化（ft.app(target=main)）和页面配置（page.title, page.theme）
删除 Stepper： 移除 v2.0 的四步 ft.Stepper 控件及相关状态管理
重构布局： 改为垂直 ft.Column 布局，依次添加：AppBar → 源目录卡片 → 目标目录卡片 → 主执行按钮容器 → 策略摘要 Chips
添加设置抽屉： 实现 open_settings() 函数，创建 ft.NavigationDrawer 或 ft.BottomSheet，包含策略配置控件（Switch/Radio/Checkbox）
实现智能默认： 在 on_source_selected 事件中，自动调用 classifier.infer_category(source_path.name) 推断分类类型，更新策略摘要显示
整合执行流程： 将"预览"和"执行"合并为 on_organize_click()，根据设置决定是否弹出确认对话框，或直接显示进度浮层
添加进度浮层： 实现 show_progress_overlay() 和 hide_progress_overlay()，使用 page.overlay 管理，配合后台线程更新进度
状态持久化： 使用 page.client_storage 保存用户设置，下次启动自动恢复（除首次强制预览外）
