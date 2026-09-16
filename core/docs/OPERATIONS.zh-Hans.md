# Cleanroom 操作指南

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroom 是以 Vera Kernel 为基础的协作开发空间。即使 AI 承担大部分实现工作，项目目标、设计判断、验证方法、失败经验和技术理解仍留在你手中。

## 01 / 在本机开始

每台电脑都应新建 Python 3.11+ 虚拟环境。Linux 提供源码安装路径，不代表所有发行版均已验证。Windows 请用 WSL2，而不是原生 Windows。激活环境后进入自己的项目。

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

```sh
source /absolute/path/to/cleanroom/.venv/bin/activate
cd /absolute/path/to/your-project
verantyx
```

## 02 / 左侧 Agent，右侧 Owner

在左下方 Agent 输入框用自然语言提出任务，无需记住新命令。

| 简体中文 | Key |
|---|---|
| 提出任务 | Agent: Enter |
| 本地备忘 | Empty Enter → MEMO |
| 本地搜索 | Empty Enter → SEARCH |
| 引用记录 | 2+ characters → ↑/↓ → Tab |
| 操作菜单 | F2 |
| 滚动 | F3 |
| 理解视图 | F4 |
| 分屏 | Alt+0 |
| 换行 | Ctrl+J / Esc then Enter |
| 退出 | Ctrl+D |

在空输入框按 Enter，依次切换：Agent → 黄色 Owner 备忘 → 绿色 Owner 搜索 → Agent。

输入 Owner 条目的前两个或更多字符，用上下方向键选择，再按 Tab 插入引用。候选列表打开时，Enter 只选择候选，不提交任务。

左右分屏需要至少140列、24行；90列、36行时上下排列；更小的终端显示当前输入侧。Mac 的功能键可能需要 Fn，Option 可能需要设置为发送 Escape。也可用 F2 菜单。

```sh
VERANTYX_REDUCE_MOTION=1 verantyx
NO_COLOR=1 verantyx
verantyx --plain
verantyx watch
```

Ctrl+C: clear the current draft / cancel the current question; with no draft, request closure. It is not a guarantee of forcibly stopping an external program. Esc closes a menu or suggestion without accepting it.

## 03 / Commands

设置菜单以英语为主。这份翻译不表示 CLI 的每一条信息都已支持五种语言。以 `verantyx --help` 和 `verantyx commands NAME` 的实际注册信息为准。

| Command | 简体中文 / scope |
|---|---|
| `verantyx` | Open workspace / 作業を始める / 开始工作 / 작업 시작 / Abrir espacio |
| `verantyx commands` | List actual registered commands / 実装済みコマンド一覧 / 命令列表 / 명령 목록 / Catálogo de comandos |
| `verantyx commands setup --json` | Read command details / 詳細 / 详情 / 상세 / Detalles |
| `verantyx setup accounts` | ChatGPT/Codex, Claude Code, API, local |
| `verantyx setup models` | Work / reflection |
| `verantyx setup roles` | Parent / child model roles |
| `verantyx setup language` | en / ja / zh-Hans / ko / es |
| `verantyx setup profile` | Voluntary experience / 任意の経験 / 自愿填写经验 / 자율 경험 기록 / Experiencia voluntaria |
| `verantyx setup pace` | Suggestion load / 提案の負荷 / 建议量 / 제안량 / Carga de sugerencias |
| `verantyx my-skills` | Your choices / 本人の選択 / 本人选择 / 나의 선택 / Tus elecciones |
| `verantyx my-learning` | Notes captured during work / 実装中の記録 / 实现时记录 / 구현 중 기록 / Notas durante el trabajo |
| `verantyx my-journal` | Journal / 日記 / 日记 / 일지 / Diario |
| `verantyx web --no-open` | Local Atlas URL / ローカルAtlas / 本地Atlas / 로컬 Atlas / Atlas local |
| `verantyx setup notebook` | Obsidian / MCP / skill imports |
| `verantyx setup harness` | External work adapter |
| `verantyx setup sandbox` | OSS isolation adapter |
| `verantyx toolbox status` | MCP tools |
| `verantyx watch` | Read-only / 閲覧専用 / 只读 / 읽기 전용 / Solo lectura |

## 04 / Models

订阅通过官方 Codex 或 Claude Code 的本地登录使用。不要把订阅令牌粘贴到网页。API 计费与订阅不同。本地模型需要正在运行的服务和可用模型。工作与整理模型可以不同，也可关闭整理而保留工作结果。

```sh
verantyx setup accounts
verantyx setup codex
verantyx setup claude
verantyx setup models
verantyx setup roles
verantyx settings --show
```

## 05 / My profile · My pace · My skills

F2 > My profile 可简短描述经验，也可跳过。My pace 调整建议量和负担。My skills 区分 AI 步骤草稿、本人想探索的内容及本人记录的解释或应用。无需填满所有格子。请 AI 推送代码并不代表不懂 Git。

工作结果与 AI 整理相互独立。不同模型可以提出不同观点，而不覆盖旧记录。AI 保存的步骤不代表本人已经掌握。跳过、委托或求助不会被认定为能力不足。

```sh
verantyx setup profile
verantyx setup pace
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx my-journal
verantyx my-learning
```

## 06 / Owner · Privacy

Owner 备忘默认留在本机。只有主动选中的引用才插入请求，外发范围另行确认。备忘、引用或学习选择不会授予执行权限。

Owner 备忘和搜索本身不会调用 AI。主动插入请求的引用会进入发送范围。不要将项目或个人私密记录提交到公共 GitHub。

## 07 / My Atlas

`verantyx web` 在本地回环地址打开私人 My Atlas。保持终端运行。图表展示已记录经验，不评分，也不列出所谓能力缺口。同一系统用户的个人记录可跨项目使用，但不会自动跨 Mac 同步。

```sh
verantyx web
verantyx web --no-open
verantyx --lang zh-Hans web
```

The actual view follows its supported language catalogue; untranslated items may fall back. These guides do not claim complete five-language runtime localization.

## 08 / Work · Reflection

遇到工作区外路径时不要绕过边界。选择明确授权的范围或另一个项目。整理失败仍保留工作结果；之后可用 `verantyx organize RUN_ID` 重新整理，`verantyx perspectives RUN_ID` 查看旧版本。

## 09 / Obsidian · MCP · Harness

F2 > Notebook bridge 连接本人指定的 Obsidian 库。导入技能仍为带来源的草稿，不是已掌握证明或执行许可。MCP 和外部运行器需明确配置。沙箱已配置不等于隔离已获验证。

[Connections](NOTEBOOK_CONNECTIONS.en.md) · [日本語](NOTEBOOK_CONNECTIONS.ja.md) · [Sandbox boundary](SANDBOX_BACKENDS.en.md)

## 10 / Web preview

公开 Pages 和 GIF 使用演示数据，不调用 AI、不修改项目、不登录订阅、不证明检查成功。可选网关是独立服务，需要配置及所有者批准。公共网站不应直接继承个人 Codex 执行权限。

> 这是源码预览，不是 MVP 全部达标的认证。GIF 使用真实 CLI 渲染器和脚本化演示数据，不是实际模型的成功测试。网页体验区仅在内存中模拟交互，不是远程终端。

[Publication & privacy](../../docs/PUBLICATION.md) · [Recording recipe](../../docs/DEMO_RECORDING.md) · [Origins](origins/README.md)

## Active-pane scrolling / AI beta

[Independent scrolling and terminal limitations](../../docs/SCROLLING.md)

Wheel / PageUp / PageDown operate on the currently selected pane. Empty Enter changes the input and scroll destination together. The other pane keeps its viewport. This does not control the terminal emulator's native history scrollbar.

The Pages beta additionally offers **Copy handoff**, **Direct API** (OpenAI-compatible / Ollama), and **Import answer**. Direct API is explicit, may be blocked by browser networking rules, and does not run tools or change files. Keys are kept only in tab memory and cleared from the field at send time or on dialog close. AI answers remain unverified proposals, not successful execution receipts. Use the local CLI for subscription-based development.
