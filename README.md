# Nothing Here

**Windows 桌面上的单卡学习容器** — 同一张无边框卡片、同一套嵌入与托盘，可以承载不同的「功能面」。现在可用的是**单词**；**考试**、**小说**等功能面已在架构里预留，后续会接到同一张卡上，而不是另做一套窗口。

Nothing Here 不是又一个全屏背单词 App：卡片可以贴在壁纸层，也可以浮在浏览器之上；学习记录留在本机；抽卡不用间隔重复，也不调用大模型。

---

## 现在能做什么

| 能力 | 说明 |
| --- | --- |
| **单词面** | 雅思词库（可扩展 JSON 词库）、音标、释义、真实英文例句 |
| **每日目标** | 用「不认识」收词，收满后按「今日目标 → 今日目标 → 熟词」轮换 |
| **斩杀与回收站** | 暂时移出抽卡池；可从托盘恢复 |
| **正反面** | 正面看词；展开译文、例句后打分；`Ctrl+Alt+S` 隐藏 / 再显示 |
| **风格** | 浅色、黑底白字、自定义文字色；**卡片底面透明**，不挡壁纸 |
| **桌面嵌入** | 默认贴在桌面图标层；可切换「浮在窗口上」 |
| **收完卡** | 词库抽尽时显示固定提示，仍保留拖动与隐藏 |

托盘名称是 **Nothing Here**（任务栏不会出现「背单词」「雅思」字样）。同一时间只运行一个实例。

---

## 路线图（功能面）

产品形态是 **一张卡片 + 多种功能面**，而不是多个独立小程序：

- **单词** — 已实现（第 0 / 1 阶段）
- **考试** — 预留入口，尚未实现
- **小说** — 预留入口，尚未实现

容器层（嵌入、拖动、热键、风格、单实例、本地 SQLite）与领域规则（抽卡权重、每日名单、封存轮换）分开实现，方便以后在同一窗口里换面。

---

## 环境要求

- Windows 10 及以上
- Python 3.9+（开发环境常用 3.14）
- 依赖见 [`requirements.txt`](requirements.txt)：`PyQt6`、`pynput`

若前台有**管理员权限**的程序占用全局热键，需用管理员身份启动 Nothing Here，或先离开该程序（与许多桌面工具相同）。

---

## 快速开始

```powershell
git clone https://github.com/yuanzal/nothing-here.git
cd nothing_here

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

等价启动方式：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nothing_here
```

启动后看系统托盘：深色圆角图标，悬停显示 **Nothing Here**。右键菜单显示 / 隐藏卡片、每日目标、回收站、风格、功能面、词库等。

学习进度保存在：

`%APPDATA%\NothingHere\study.db`

更细的操作说明见 [`使用教程.md`](使用教程.md)。

---

## 开发与测试

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

主要目录：

```
src/nothing_here/
  app.py           # 组装、生命周期、单实例
  domain/          # 权重、抽卡、每日目标（无 Qt / 无数据库）
  vocab/           # 词库协议、例句来源协议
  storage/         # SQLite
  ui/              # 卡片、托盘
  desktop/         # Windows 桌面嵌入
  input/           # 全局热键
data/ielts.json    # 雅思词条（含例句字段）
scripts/           # 词库构建、例句填充（离线，非运行时爬网）
```

规格与术语：

- [`开发文档.md`](开发文档.md) — 第 0 阶段基线  
- [`需求变更.md`](需求变更.md) — 单卡与每日目标  
- [`需求变更-第1阶段.md`](需求变更-第1阶段.md) — 例句、斩杀、风格、功能面  
- [`GLOSSARY.md`](GLOSSARY.md) — 统一用词（卡片、功能面、斩杀等）

---

## 词库与例句

- 词条来自 ECDICT 导出的 [`data/ielts.json`](data/ielts.json)（带 `ielts` 标签）。
- 例句在**构建词库时**写入 JSON：优先 [Tatoeba](https://tatoeba.org) 英文句库，缺的再用有道双语例句中的英文。**应用运行时不访问网络。**
- 重新生成例句（需自行下载 Tatoeba 导出，见脚本说明）：

  ```powershell
  .\.venv\Scripts\python.exe scripts\example_sentences.py
  ```

---

## 设计原则（摘要）

- **本地优先**：进度、风格、位置、每日状态均落盘 SQLite。  
- **可测领域层**：`domain` 不依赖 PyQt、pynput 或数据库实现细节。  
- **可扩展例句**：`ExampleSource` 协议；当前使用词条 `example` 字段，以后可追加来源。  
- **简单权重**：越熟越不容易被抽到；低正确率且背过多次的会更常出现。

---

## 贡献与许可

欢迎 Issue 与 PR。若你打算扩展新的功能面或词库，请先对照 `GLOSSARY.md` 与变更文档，避免和已有术语、单卡模型冲突。

许可证：本项目采用 MIT License 进行许可。

你可以自由使用、修改、合并、发布、分发、再许可和/或销售本软件的副本，只需在分发时保留上述版权声明和许可声明。详情请参阅项目根目录下的 LICENSE 文件。

第三方组件遵循各自开源协议。
