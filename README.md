# Nothing Here

**Windows 桌面上的工作时摸鱼容器** — 无边框透明卡片，多种「功能面」共用同一张卡。现在可用的是**单词**（含拼写测试）；托盘里的**考试**、**小说**只是预留入口，尚未实现。

Nothing Here 不是全屏背单词 App，而是贴在壁纸层（或浮在窗口上）的轻量卡片；学习记录只落在本机。

---

## 现在能做什么

| 能力 | 说明 |
| --- | --- |
| **背单词** | 雅思 / 四级 / 六级 / 考研；音标、释义、真实英文例句 |
| **拼写测试** | 达标后可邀请进入；逐格输入 |
| **每日目标** | 「不认识」收入名单，收满后按「目标 → 目标 → 熟词」轮换抽查 |
| **斩杀与回收站** | 熟练词可移出抽卡池，托盘里恢复 |
| **正反面** | 正面只看词；译文/例句后认识或不认识；`Ctrl+Alt+S` 显隐卡片 |
| **风格** | 浅色、黑底白字、自定义文字色；底面透明 |
| **桌面嵌入** | 默认贴桌面图标层；可「浮在窗口上」 |

托盘名称是 **Nothing Here**（任务栏不出现「背单词」「雅思」）。同一时间只运行一个实例。

---

## 环境要求

- Windows 10 及以上
- Python 3.9+（开发常用 3.12 / 3.14）
- 依赖见 [`requirements.txt`](requirements.txt)：`PyQt6`、`pynput`

若前台有**管理员权限**程序占用全局热键，需用管理员身份启动，或先离开该程序。

---

## 快速部署

```powershell
git clone https://github.com/yuanzal/nothing-here.git
cd nothing_here

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

等价：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m nothing_here
```

系统托盘：深色圆角图标，悬停 **Nothing Here**。右键可显隐卡片、改每日目标、回收站、风格、功能面、词库等。

进度文件：`%APPDATA%\NothingHere\study.db`

操作说明：[`使用教程.md`](使用教程.md)。

---

## 开发与测试

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

```
src/nothing_here/
  app.py           # 组装、生命周期、单实例
  domain/          # 权重、抽卡、每日目标、拼写规则（无 Qt / 无库）
  vocab/           # 词库协议、例句来源协议
  storage/         # SQLite
  ui/              # 卡片、托盘
  desktop/         # Windows 桌面嵌入
  input/           # 全局热键、拼写键钩子
data/*.json        # 词库 JSON
scripts/           # 词库构建、例句填充（离线；运行时不联网）
```

规格：[`开发文档.md`](开发文档.md)、[`需求变更.md`](需求变更.md)、[`需求变更-第1阶段.md`](需求变更-第1阶段.md)、[`需求变更-第2阶段.md`](需求变更-第2阶段.md)、[`需求变更-第3阶段.md`](需求变更-第3阶段.md)（阅读）、[`GLOSSARY.md`](GLOSSARY.md)。

---

## 扩展性一览

| 扩展点 | 现在好不好扩 | 说明 |
| --- | --- | --- |
| **词库** | 好扩 | `VocabSource` 协议 + `load_sources()` 注册表；加 JSON 或自写实现即可 |
| **例句来源** | 好扩 | `ExampleSource` 协议；可串联多个来源，先命中先用 |
| **功能面**（考试/小说） | 只留了口 | 托盘有菜单、`surface_id` 会落库，但**没有**独立 Surface 协议；切到非单词目前无效 |
| **拼写测试** | 挂在单词面下 | 是单词功能面里的卡态，不是第四个功能面；规则在 `domain/spell.py` |

结论：**词库 / 例句已经是可插拔接口**；**新功能面还要自己接 `app` / `ui` / `domain`，不是注册一项就跑起来。**

术语以 [`GLOSSARY.md`](GLOSSARY.md) 为准：卡片、功能面、斩杀、拼写测试等。

---

## 词库接口教程

### 协议

```python
# src/nothing_here/vocab/protocol.py
@dataclass(frozen=True)
class Entry:
    word: str
    phonetic: str
    translation: str
    example: str = ""

class VocabSource(Protocol):
    source_id: str      # 唯一，如 "cet4"
    display_name: str   # 托盘显示，如 "四级"
    def iter_entries(self) -> Iterable[Entry]: ...
```

- 进度键是 `word.casefold()`，**不**带 `source_id`；换词库共用同一进度行。
- 应用只通过协议读词，不要在 `app` 里写死某个 JSON 路径。

### 方式 A：加一份 ECDICT JSON（最常见）

1. 准备 ECDICT 的 `ecdict.csv`（勿提交进仓库）。
2. 导出（tag 须在 CSV 的 `tag` 字段里按空白切开后**精确匹配**）：

   ```powershell
   .\.venv\Scripts\python.exe scripts\build_ecdict.py path\to\ecdict.csv --tag toefl -o data\toefl.json
   # 或一次导出已知 tag：
   .\.venv\Scripts\python.exe scripts\build_ecdict.py path\to\ecdict.csv --all
   ```

3. 补例句（Tatoeba + 有道双语；**不**生成模板句）：

   ```powershell
   .\.venv\Scripts\python.exe scripts\example_sentences.py data\toefl.json
   ```

4. 注册到 [`src/nothing_here/vocab/registry.py`](src/nothing_here/vocab/registry.py)：

   ```python
   def load_sources() -> list[VocabSource]:
       return [
           # ...已有...
           JsonVocabSource("toefl", "托福", data_file("toefl.json")),
       ]
   ```

5. 把 JSON 加进 [`scripts/nothing_here.spec`](scripts/nothing_here.spec) 的 `datas`，否则打包版里没有该文件。

JSON 形态：

```json
[
  {
    "word": "abandon",
    "phonetic": "əˈbændən",
    "translation": "放弃；抛弃",
    "example": "He decided to abandon the project."
  }
]
```

### 方式 B：自写 `VocabSource`

实现 `source_id` / `display_name` / `iter_entries()`，在 `load_sources()` 里追加即可。数据可以来自别的文件格式或只读远程镜像，只要返回 `Entry`；**运行时是否联网由你自己约束**（现有词库约定：运行时不联网）。

### 例句来源

```python
# src/nothing_here/vocab/examples.py
class ExampleSource(Protocol):
    source_id: str
    def example_for(self, word: str) -> str: ...
```

当前只有 `EntryExampleSource`（读词条上的 `example` 字段）。要加第二来源：实现协议 → 放进 `load_example_sources()` 列表；`resolve_example` 按顺序取第一个非空结果。

### 已带词库

| source_id | 托盘名 | 文件 | ECDICT tag |
| --- | --- | --- | --- |
| `ielts` | 雅思 | `data/ielts.json` | `ielts` |
| `cet4` | 四级 | `data/cet4.json` | `cet4` |
| `cet6` | 六级 | `data/cet6.json` | `cet6` |
| `ky` | 考研 | `data/ky.json` | `ky` |

---

## 增加功能面：现状与接口教程

### 现状（诚实版）

第 1 阶段约定：托盘「功能面」下有「单词 / 考试 / 小说」，`app_state.surface_id` 可持久化，但**第 1～2 阶段只允许 `word`**。点考试或小说会被打回单词。

卡片（`CardWindow`）、桌面嵌入、热键、风格是**容器级**能力；单词抽卡、打分、拼写都写在「单词」这条链路里（`domain/daily.py`、`domain/spell.py`、`app` 的 grade / render）。**还没有**类似 `VocabSource` 的 `Surface` 注册表。

因此：预留的是产品与菜单口子，**不是**「实现一个类 + 注册一行就出新功能面」。

### 若要真正加一个功能面（建议步骤）

下面以「考试」为例，按现有分层做；细节以变更文档为准，做前先改规格再写代码。

1. **定术语与规格**  
   在 `GLOSSARY.md` 和对应 `需求变更-*.md` 写清：卡上有什么、和单词进度是否隔离、托盘项、持久化字段。

2. **领域规则（可选独立模块）**  
   在 `domain/` 增加纯函数 / 状态（不依赖 Qt、不直接碰 DB），并配 `tests/`。

3. **持久化**  
   若需要独立进度，在 `storage/db.py` 加表或列；`surface_id` 已有，业务数据另定。

4. **卡片 UI**  
   在 `ui/card_window.py` 增加该面的展示与按钮信号，或拆成子组件由 `CardWindow` 切换；容器行为（拖动、透明、嵌入）尽量复用。

5. **托盘**  
   在 `ui/tray.py` 把该项设为可用，`surface_chosen` 发出真实 `surface_id`（如 `"exam"`）。

6. **组装**  
   在 `app.py` 的 `choose_surface` / `_render` 按 `surface_id` 分支：换面时销毁或切换内容，避免单词态与新面串状态。拼写属于单词面，不要占新的 `surface_id`。

7. **回归**  
   显隐、浮层、换词库、跨日、单实例等仍应只作用于「当前面」或按规格明确忽略。

在出现稳定的 `Surface` 协议之前，**每加一面都要改 `app` + `tray` + `card`**；这是有意保持单卡简单，而不是插件总线。

### 和「拼写测试」的区别

拼写是单词功能面下的**卡态**（邀请 / 拼写中），见 `需求变更-第2阶段.md`。扩展拼写规则改 `domain/spell.py` 与卡片拼写 UI 即可，不必新开功能面。

---

## 词库与例句（运维）

- 重建词库：`python scripts/build_ecdict.py path/to/ecdict.csv --all`
- 补例句：`python scripts/example_sentences.py data/cet4.json data/cet6.json data/ky.json`  
  （会下载/使用 `data/cache/` 下的 Tatoeba 导出；该目录已 gitignore）
- **应用运行时不访问网络。**

---

## 设计原则（摘要）

- **本地优先**：进度、风格、位置、每日状态落 SQLite。  
- **可测领域层**：`domain` 不依赖 PyQt、pynput 或具体 DB。  
- **词库 / 例句可插拔**：协议 + 注册表。  
- **功能面渐进**：先单词跑通，再按规格加面，而不是先做空框架。

---

## 发布（GitHub Release）

推送 `v*` tag 会触发 Actions：打包 Windows zip 并挂到 Release。

```powershell
git tag v0.3.0
git push origin v0.3.0
```

本地试打包：`.\scripts\build_release.ps1` → `dist\NothingHere-win64.zip`。

Tag 页上的 Source code zip 只是源码；安装包在 **Releases** 的 Assets 里。

---

## 贡献与许可

欢迎 Issue 与 PR。扩展词库或功能面前请对照 `GLOSSARY.md` 与变更文档，避免和单卡模型、已有术语冲突。

许可证：MIT。详见 [`LICENSE`](LICENSE)。第三方组件遵循各自协议。
