# Cleanroom 사용 안내

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroom은 Vera Kernel을 기반으로 하는 공동 개발 공간입니다. AI가 구현 대부분을 맡아도 프로젝트의 목적, 설계 판단, 검증 방법, 실패 경험, 기술적 이해는 사람에게 남습니다.

## 01 / 내 컴퓨터에서 시작

컴퓨터마다 Python 3.11+ 가상 환경을 새로 만드세요. Linux는 소스 설치 경로이며 모든 배포판의 검증을 뜻하지 않습니다. Windows는 네이티브가 아닌 WSL2를 사용합니다. 환경을 활성화한 뒤 작업할 프로젝트로 이동하세요.

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

## 02 / 왼쪽 Agent, 오른쪽 Owner

왼쪽 아래 Agent 입력란에 자연스러운 문장으로 요청하세요. 새로운 명령어를 외울 필요가 없습니다.

| 한국어 | Key |
|---|---|
| 작업 요청 | Agent: Enter |
| 로컬 메모 | Empty Enter → MEMO |
| 로컬 검색 | Empty Enter → SEARCH |
| 기록 참조 | 2+ characters → ↑/↓ → Tab |
| 작업 메뉴 | F2 |
| 스크롤 | F3 |
| 이해 화면 | F4 |
| 분할 화면 | Alt+0 |
| 줄바꿈 | Ctrl+J / Esc then Enter |
| 종료 | Ctrl+D |

빈 입력란에서 Enter를 누르면 Agent → 노란색 Owner 메모 → 초록색 Owner 검색 → Agent 순서로 이동합니다.

Owner 항목의 앞 두 글자 이상을 입력하고 위아래 화살표로 고른 뒤 Tab으로 참조를 넣습니다. 후보가 열려 있을 때 Enter는 선택만 하고 요청을 보내지 않습니다.

좌우 분할에는 140열·24행 이상이 필요합니다. 90열·36행에서는 위아래로, 더 작은 화면에서는 현재 입력 쪽만 표시됩니다. Mac 기능키는 Fn이 필요할 수 있고 Option을 Escape로 보내도록 설정해야 할 수 있습니다. F2 메뉴도 사용할 수 있습니다.

```sh
VERANTYX_REDUCE_MOTION=1 verantyx
NO_COLOR=1 verantyx
verantyx --plain
verantyx watch
```

Ctrl+C: clear the current draft / cancel the current question; with no draft, request closure. It is not a guarantee of forcibly stopping an external program. Esc closes a menu or suggestion without accepting it.

## 03 / Commands

설정 메뉴는 영어 중심입니다. 이 번역은 모든 CLI 문구의 5개 언어 지원을 뜻하지 않습니다. 실제 등록 정보는 `verantyx --help`, `verantyx commands NAME`이 기준입니다.

| Command | 한국어 / scope |
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

구독은 공식 Codex 또는 Claude Code의 로컬 로그인을 사용합니다. 웹에 구독 토큰을 붙여 넣지 마세요. API 요금과 구독은 별도입니다. 로컬 모델에는 실행 중인 서버와 사용 가능한 모델이 필요합니다. 작업과 정리 모델을 다르게 선택하거나 정리를 꺼도 결과는 유지됩니다.

```sh
verantyx setup accounts
verantyx setup codex
verantyx setup claude
verantyx setup models
verantyx setup roles
verantyx settings --show
```

## 05 / My profile · My pace · My skills

F2 > My profile에서 경험을 짧게 쓰거나 건너뛸 수 있습니다. My pace는 제안의 양과 무게를 조절합니다. My skills는 AI 절차 초안, 탐색하고 싶은 항목, 본인의 설명·적용 사례를 구분합니다. 모든 칸을 채울 필요가 없습니다. AI에게 push를 부탁했다고 Git을 모른다고 판단하지 않습니다.

작업 결과와 AI의 정리는 독립적입니다. 모델의 관점이 달라도 이전 기록은 유지됩니다. AI의 절차가 저장되었다고 사용자가 배웠다고 판단하지 않습니다. 건너뛰기, 위임, 도움 요청은 능력 부족의 근거가 아닙니다.

```sh
verantyx setup profile
verantyx setup pace
verantyx my-skills
verantyx my-skills quiet --scope TODAY
verantyx my-journal
verantyx my-learning
```

## 06 / Owner · Privacy

Owner 메모는 기본적으로 로컬에 남습니다. 직접 고른 참조만 요청에 들어가며 외부 전송 범위는 별도로 확인합니다. 메모·참조·학습 선택으로 실행 권한이 늘어나지 않습니다.

Owner 메모와 검색만으로 AI를 호출하지 않습니다. 요청에 직접 넣은 참조는 전송 범위에 포함됩니다. 개인 기록과 프로젝트 비공개 기록을 공개 GitHub에 올리지 마세요.

## 07 / My Atlas

`verantyx web`은 루프백 주소에서 비공개 My Atlas를 엽니다. 터미널을 계속 실행해 두세요. 점수나 능력 부족이 아닌 기록된 경험을 보여줍니다. 같은 OS 사용자의 기록은 프로젝트 간 공유되지만 Mac 간 자동 동기화는 없습니다.

```sh
verantyx web
verantyx web --no-open
verantyx --lang ko web
```

The actual view follows its supported language catalogue; untranslated items may fall back. These guides do not claim complete five-language runtime localization.

## 08 / Work · Reflection

프로젝트 밖 경로는 우회하지 말고 명시적으로 허용한 범위나 다른 프로젝트를 사용하세요. 정리가 실패해도 작업 결과는 남습니다. 이후 `verantyx organize RUN_ID`로 다시 정리하고 `verantyx perspectives RUN_ID`로 이전 관점을 볼 수 있습니다.

## 09 / Obsidian · MCP · Harness

F2 > Notebook bridge에서 지정한 Obsidian 보관함에 연결합니다. 가져온 스킬은 출처가 있는 초안이며 습득 인증이나 실행 허가가 아닙니다. MCP와 외부 하네스는 명시적으로 설정해야 합니다. 샌드박스 설정 완료는 격리 검증 완료가 아닙니다.

[Connections](NOTEBOOK_CONNECTIONS.en.md) · [日本語](NOTEBOOK_CONNECTIONS.ja.md) · [Sandbox boundary](SANDBOX_BACKENDS.en.md)

## 10 / Web preview

공개 Pages와 GIF는 시나리오 데이터를 사용하며 AI 실행, 프로젝트 변경, 구독 로그인, 검사 성공 인증을 하지 않습니다. 선택적 게이트웨이는 별도 서비스로 설정과 소유자 승인이 필요합니다. 개인 Codex 실행 권한을 공개 웹에 그대로 넘기지 않습니다.

> 소스 미리보기이며 MVP 전체 통과를 보장하지 않습니다. GIF는 실제 CLI 렌더러에 시나리오 데이터를 넣어 녹화한 것으로, 실제 모델의 성공 기록이 아닙니다. 웹 체험은 메모리 안의 상호작용 데모이며 원격 셸이 아닙니다.

[Publication & privacy](../../docs/PUBLICATION.md) · [Recording recipe](../../docs/DEMO_RECORDING.md) · [Origins](origins/README.md)

## Active-pane scrolling / AI beta

[Independent scrolling and terminal limitations](../../docs/SCROLLING.md)

Wheel / PageUp / PageDown operate on the currently selected pane. Empty Enter changes the input and scroll destination together. The other pane keeps its viewport. This does not control the terminal emulator's native history scrollbar.

The Pages beta additionally offers **Copy handoff**, **Direct API** (OpenAI-compatible / Ollama), and **Import answer**. Direct API is explicit, may be blocked by browser networking rules, and does not run tools or change files. Keys are kept only in tab memory and cleared from the field at send time or on dialog close. AI answers remain unverified proposals, not successful execution receipts. Use the local CLI for subscription-based development.
