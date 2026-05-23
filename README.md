# Signal Compass

A-share & US market signal monitoring system. Terminal-first, zero AI dependency.

双击 `.bat` 出报告。纯 Python 脚本，不联网也能跑。

## Quick Start

```bash
pip install requests akshare wcwidth
python compass.py          # 交互菜单
python compass.py a        # A股大盘
python compass.py us       # 美股大盘
python compass.py portfolio # 自选组合池
python compass.py review   # 复盘趋势
```

## What It Does

```
核心指数矩阵 (SS/SZ/HS/CY/STAR50/CSI500)
├── 市场成交额 + 涨跌家数 + 风格成交量
├── 板块轮动 (银行/半导体/上证50/医药 vs 科技)
├── 主力资金 + 北向/南向资金
├── 中国10Y国债 + 涨停分布 + 热点板块
├── 双轨评分 (趋势压力 + 偏离极值)
├── 升级/降级条件 (实时检测)
└── 子信号自验证 (T日触发 → T+1实际涨跌 → 自动降权)
```

## Features

- **零 AI 依赖**: compass.py 无任何 LLM 调用，双击即跑
- **双市场**: A 股 + 美股信号监控
- **自选组合池**: 逐只 K 线信号 + 事件检测 + 相对大盘强弱
- **复盘趋势**: 近 30 天得分趋势 + 异常窗口 + 信号准确率
- **子信号自验证** (v2.3): 每个信号触发后隔天回验，命中率低自动降权
- **CJK 等宽对齐**: 终端表格中英文 emoji 完美对齐
- **交互菜单**: 无需记忆命令行参数

## Files

```
compass.py       核心 (~1978行)
cjk_table.py     CJK表格对齐工具
compass.bat      双击启动器
portfolio.json   自选池配置
rules.json       信号权重 (自动生成)
```

## Data Sources

全部国内信源，无需梯子：
- Sina Finance (`hq.sinajs.cn`) — 实时行情
- AkShare — K线 / 北向资金 / 国债 / 涨停板
- 东财 push2 API — 涨跌家数

## Design Principles

- 每个信号必须有可验证锚 → 锚失效就砍信号
- 异动公告次数是最高优先级风险指标
- 不输出确定性叙事，只标记异常
- 表格=标签化，提示=详细展开
