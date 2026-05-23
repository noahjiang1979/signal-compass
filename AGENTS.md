# Hermes Signal Compass — 项目状态

## 核心文件
- `compass.py`（~1400行）— 主程序：US模式 / A股模式 / 组合池 / 复盘
- `cjk_table.py` — CJK感知表格对齐（wcwidth）
- `portfolio.json` — 自选组合池配置
- `compass.bat` — 双击启动器

## 架构速览

### 入口分发
- `python compass.py us` → US大盘模式
- `python compass.py a` → A股大盘模式
- `python compass.py portfolio`（或 `pf` / `po`）→ 自选组合池
- `python compass.py review`（或 `-r`）→ 复盘

### 数据流
```
sina_q() → 实时行情 → 基准计算 → 相对强度 → 观察栏
sina_k() → 日K线 → get_signal() → MACD+BOLL+KDJ → 信号栏
check_events() → 东财直连事件 → _make_event_tag() → 事件栏(标签化)
count_anomaly_ann() → 异动公告计数 → 提示区
```

### Portfolio 模式核心流程
1. 批量 Sina 实时行情 → 相对大盘强弱（⭐抗跌/抗跌/跟跌/领跌）
2. 逐只获取日K线 → get_signal() 组合信号
3. 逐只获取事件 → check_events() 返回三版本（纯emoji/短标签/长描述）
4. 表格显示 → 代码|价格|涨跌|相对大盘|观察(🟢🟡🔴)|信号(⬜🟢🟡🔴)|事件(标签)
5. 提示区 → 按优先级排序，事件详情下沉显示

### 事件系统
- `check_events()`: 东财直连API，返回4值 `(emoji, 纯emoji, 短标签, 长描述)`
- `_make_event_tag(title, typ)`: 关键词→短标签映射
  - zc类: 质押/解质/质押延期
  - qy类: 减持完毕/减持计划/诉讼/立案/冻结/预亏
  - ba类: 中标/增持/回购/预增/扭亏
- 表格事件列只显示短标签（🔒质押 | 👎减持完毕），完整描述放提示区
- `EVT_LONG_DETAILS` 字典：code→长描述，供提示区使用

### 颜色覆盖逻辑
- 当信号为 🔴严重异动/预警/回避 时：
  - 观察栏颜色强制降为 🟡
  - 移除 ⭐ 前缀（"⭐抗跌" → "抗跌"）

### 异常偏离
- 3日累计涨幅≥20% → `anomaly_tag="3日偏离>20%"`
- 表格显示：🟡异常偏离
- 提示区：交易所要求发异动公告 | 近3月触X次（不重复标签）

## 最新改动（2026-05-20）
### P0 BUG 修复：save_nb_cache 崩溃
- `datetime.now()` → `datetime.datetime.now()`（L114/121/122）
- `timedelta(days=7)` → `datetime.timedelta(days=7)`（L122）
- 根因：import datetime（模块级），未 import datetime.now，调用 AttributeError
- 效果：northbound_cache.json 从此可正常写入

### 交互式菜单 + 编辑自选池
- 双击/直接运行 → 显示菜单（5个功能+退出），运行完回到菜单
- CLI 参数模式保持兼容（compass.bat / 命令行依然可用）
- 新增 edit_portfolio()：菜单5，交互式增删股票，智能识别代码格式
  - 600519→sh600519, NVDA→gb_nvda, 也接受完整前缀
  - 编号格式删除：A1=第1只A股, U1=第1只美股
- 命令行 `python compass.py` 现在显示菜单，不再是默认 US 模式

### PyInstaller 打包
- `_app_dir()` 统一路径解析（兼容 frozen exe 和直接运行）
- Windows UTF-8 编码修复（emoji 不崩 GBK）
- 4处 `os.path.dirname(__file__)` → `_app_dir()`
- 打包命令：`pyinstaller --onedir --name compass --add-data "portfolio.json;." compass.py`
- 交付包 ~190MB（akshare + pandas + numpy）
### 事件列重构
- 新增 `_make_event_tag()`: 关键词→短标签（质押/解质/减持完毕/中标等）
- `check_events()` 返回从2值改为4值：emoji/纯emoji/短标签/长描述
- 表格事件列不再显示原始公告标题截断，改为短标签
- 完整事件描述下沉到提示区（45字上限）
- 新增 `EVT_LONG_DETAILS` 字典，分离长描述存储

### 颜色覆盖
- 🔴严重信号时：`col=Y`，`hint=hint.replace("⭐","")`
- 提示区的板块推动判断条件从 `"⭐抗跌" in hint` → `"抗跌" in hint`（兼容颜色覆盖后的hint）

### 冗余消除
- 异常偏离标签在表格显示为 `🟡异常偏离`
- 提示区不再重复标签，只写"交易所要求发异动公告 | 近3月触X次"
- 严重信号分支中 `antag` 子备注改为"异动公告已发"（去标签）

### 双基准
- 上证 + 科创50 + SPY 并排显示
- 科创50用于修正组合偏科创时上证失真的问题

## 最新改动（2026-05-22 — 代码审查修复）
- P0: SPY日涨跌修复: yi["c"][0]→yi["c"][-2] (line 391) — 原来是1年涨幅冒充日涨跌
- P0: 恒指日涨跌修复: hsi["c"][0]→hsi["c"][-2] (line 845) — 同上
- P0: 涨跌家数ratio保护: ratio=99假触发 → brd["up"]>0且<50才参与计算 (line 704)
- P0: 半导体领跌加分: risk.append("半导体领跌")→trend_score+=1;risk.append (line 764)
- P1: 创业板RSI分位: sina_k("sz399006",30)→250天，分位从~16样本→~236样本 (line 619)
- P1: 今日观察去重: 与yesterday_observe相同→改用默认观察 (lines 930-961)
- P1: 拉高出货分级: chg>0.5%才报"拉高出货"，chg≤0.5%改为"观察能否守住" (line 1724)
- 附加: resourceWarning修复 open(os.devnull,'w')→with...as (line 294)
- P1: 信号准确率循环修复: calc_accuracy()重写为T日信号→T+1日验证，新增"注意风险"独立观察档 + by_level分等级明细 (lines 1127-1166)
- P1: SS sina_q vs sina_k交叉校验: 收盘后偏差>1%自动用K线值 (line 1084)
- P1: 上证RSI分位: syk扩展250天，输出加注分位 (line 722)
- P1: 创业板cy_last盘中标注"(K线昨收)" (line 752)
- P1: 科创50 portfolio模式统一用sina_q实时chg (line 1590)
- P1: 信号/强度矛盾消歧: rel>3时标注"⚠️矛盾"替代"拉高出货" (line 1757)
- P2: 清理20260520 review脏数据: ud_ratio=99→null

## 待办/已知问题
- [ ] 涨跌家数API（东财push2）偶尔502 → 回退方案未实现
- [ ] 组合池提示中利通电子出现3次（主行+注+事件），可以考虑缩并
- [ ] 没有monitor.bat（用户说以后再说）
- [ ] 事件标题清洗仍会残留股票名（如"利通电子办理质押的"）

## 设计原则
- 每个信号必须有可验证锚 → 锚失效就砍信号
- 异动公告次数是最高优先级风险指标
- 输出按严重程度排序，分析归子备注
- **不输出确定性叙事**，只标记异常用问句引导
- **表格=标签化，提示=详细展开**（2026-05-20 确立）