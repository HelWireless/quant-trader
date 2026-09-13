# 策略命名规范：hoshi-cplus

> 生效日期：2026-09-13
> 适用范围：quant-trader 仓库全部文档与代码

---

## 一、变更说明

2026-09-12 ~ 09-13 的策略研究中，最优方案被记作 **方案 B′（B prime）**。
为便于工程化、代码引用与对外传播，自 2026-09-13 起**统一命名为 `hoshi-cplus`**。

**两者完全等价**，只是名字变了，参数与行为一个字节都没改。

---

## 二、命名对照表

| 现名（推荐） | 历史称呼 | 参数 | 状态 |
|---|---|---|---|
| **hoshi-cplus** | 方案 B′、B'、Bp、B prime、方案C* | 评分9 / 启用日5 / R3关 / 广度20 / **−6.0%** | ✅ **推荐** |
| 方案 B | B、baseline-B | 评分9 / 启用日5 / R3关 / 广度20 / −8.2% | 对照基线 |
| 原版 | base、original、现版 | 评分8 / 启用日15 / R3开 / 广度20 / −8.2% | 对照基线 |

\* 外部 90 窗研究报告中把同一套参数记作 **C 配置**，也是 hoshi-cplus。

---

## 三、代码中的映射

`hoshi_cplus/config.py` 内置别名，历史称呼仍可正常使用：

```python
from hoshi_cplus import get_preset

get_preset('cplus')        # -> hoshi-cplus
get_preset('Bp')           # -> hoshi-cplus（历史名，仍可用）
get_preset("B'")           # -> hoshi-cplus（历史名，仍可用）
get_preset('B')            # -> 方案 B
get_preset('base')         # -> 原版
```

命令行同理：

```bash
python -m hoshi_cplus --data scripts/hoshi_csv_2005 --preset cplus \
    --start 2011-03-01 --end 2016-02-29
```

---

## 四、历史文档的处理

2026-09-13 之前的研究报告（如 `Hoshi_终局报告`、`Hoshi_二次验证_180窗`、
`Hoshi_stoploss_threshold_60w` 等）中仍会出现 **B′ / B' / 方案B** 等旧称呼，
**这些是历史记录，保持原样不做回溯改写**，以免破坏当时的论证上下文。

阅读时按第二节的对照表理解即可；所有新写的文档与代码一律使用 **hoshi-cplus**。

---

## 五、为什么叫 cplus

Hoshi 是原策略名；`cplus` 表示「在方案 B 之上做了一处关键增强」
（硬止损阈值从 −8.2% 收紧到 −6.0%），与 C++ 之于 C 的类比一致 ——
**同源、向后兼容、但更强**。

实测证据（180 窗二次验证）：hoshi-cplus 相对方案 B **+24.39pp**，
胜 **160/179（89%）**，配对 t = 11.83，p = 5.8e-29。

---

_最后更新：2026-09-13_
