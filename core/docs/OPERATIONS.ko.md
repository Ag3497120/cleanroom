# Cleanroom 사용 안내

[English](OPERATIONS.en.md) · [日本語](OPERATIONS.ja.md) · [简体中文](OPERATIONS.zh-Hans.md) · [한국어](OPERATIONS.ko.md) · [Español](OPERATIONS.es.md) · [README](../../README.md)

Cleanroom은 Vera Kernel을 기반으로 하는 공동 개발 공간입니다. AI가 구현 대부분을 맡아도 프로젝트의 목적, 설계 판단, 검증 방법, 실패 경험, 기술적 이해는 사람에게 남습니다.

## 현재 조작을 빠르게 익히기

새로 설치한 `verantyx setup`은 영어로 시작하며 언어를 선택하면 안내와 선택 설명이 바뀝니다. 처음 종료할 때 모의 튜토리얼을 제공합니다. 그 안에서 `verantyx`를 입력하면 실제 CLI로 넘어가며 `/done`으로도 연습 화면을 끝낼 수 있습니다. 크기 안내는 차단하지 않습니다.

120열 × 28행부터 Agent 약 70%, Owner 약 30% 너비의 좌우 패널을, 80열 × 48행부터 상하 패널을 사용합니다. 더 작으면 활성 패널만 보여주며 진행을 막지 않습니다. 빈 Enter 전환은 같습니다. 터미널 글꼴 크기는 터미널 앱에서, 웹 체험 글자 크기는 화면 버튼에서 바꿉니다.

### 완료를 기다리지 않고 작업 중에 이해하기

프로젝트가 끝나야 이해할 내용을 볼 수 있는 것은 아닙니다.

- **이어지는 대화.** Agent의 요청에는 배경색을, 응답에는 배경색 없이 표시합니다. 시스템 상태는 분리하며 실행 중에는 회전 표시와 부드러운 입력창 효과가 보입니다.
- **필요한 설명만.** 안전한 작업 구간에서 설정한 제안량만큼 구현 중 노트를 Owner에 표시할 수 있습니다. `L-000001` 같은 번호로 원래 구현을 바꾸지 않고 질문합니다. 실행 중인 긴 도구 호출은 먼저 마칩니다.
- **예상은 예상으로.** AI가 제시하면 구현과 검사 시간 범위를 따로 보입니다. 질문의 실제 소요 시간을 반영하고 다음 작업에서 다시 예상합니다. 없거나 오래된 예상은 그대로 표시합니다.
- **나의 속도.** 메모, 참조, 위임, 다음 기회 중에서 고르세요. 질문, 건너뛰기, 스킬 가져오기, 권한 허용은 습득 인증이 아닙니다.

Agent의 `/verantyx new`는 Agent 대화만 새로 만듭니다. Owner Cleanroom은 별도 이름과 확인 절차로 관리합니다. 후보 변경은 **한 번／이 작업 공간／영구／거부**이며 본체 채택이나 공개 권한과 다릅니다.

[작업 중 학습, 세션, 권한과 저장](../../docs/live-learning-and-sessions.md) · [대화와 변경 검토](../../docs/conversation-and-change-review.md)

| 입력 | 동작 |
|---|---|
| `verantyx new [name]` | Agent 대화만 새로 만들고 Owner 유지 |
| `verantyx new --owner [name]` | 셸에서 Owner Cleanroom 생성, 먼저 확인 |
| `verantyx cleanroom [name]` | Owner Cleanroom 목록, 전환 전 확인 |
| `verantyx compact` | 원본을 지우지 않고 출처가 있는 문맥을 AI로 압축 |
| `/insights` | 최근 구현 중 설명 보기 |
| `L-000001` | 안전한 구간에서 해당 노트 질문 |
| `/approvals` | 후보 변경 권한 확인 |
| `/queue` | 실행 중 입력을 대기열 또는 다음 안전한 단계로 |

Owner 메모는 시각과 함께 개인 로컬 SQLite에 저장합니다. 화면은 페이지 단위로 읽고 검색은 저장된 노트를 조회합니다. 원래 작업 이벤트는 프로젝트 원장에 남습니다. AI 요약은 원본 대체가 아닌 출처가 있는 추가 보기입니다. 일상 경로의 메모리 부담을 줄이지만 전체 원장 재생과 내보내기의 일정한 메모리 사용을 보장하지 않습니다.

브라우저는 입력 전환, 참조, 메모, 연속 대화와 허용 선택 예시를 재현합니다. 데이터는 이 탭에만 있으며 CLI DB가 아닙니다. 대본의 예상 시간과 결과는 실제 작업이나 증거가 아닙니다. 구독 실행, 실제 압축, 영구 세션, 파일 편집은 로컬 CLI에서 하며 AI 연결은 별도 명시적 조작입니다.

[현재 조작](../../docs/two-pane-interaction.md) · [학습과 세션](../../docs/live-learning-and-sessions.md) · [영어 녹화](../../docs/DEMO_RECORDING.md)


## 01 / 내 컴퓨터에서 시작

컴퓨터마다 Python 3.11+ 가상 환경을 새로 만드세요. Linux는 소스 설치 경로이며 모든 배포판의 검증을 뜻하지 않습니다. Windows는 네이티브가 아닌 WSL2를 사용합니다. 환경을 활성화한 뒤 작업할 프로젝트로 이동하세요.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup
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

120열 × 28행부터 Agent 약 70%, Owner 약 30% 너비의 좌우 패널을, 80열 × 48행부터 상하 패널을 사용합니다. 더 작으면 활성 패널만 보여주며 진행을 막지 않습니다. 빈 Enter 전환은 같습니다. 터미널 글꼴 크기는 터미널 앱에서, 웹 체험 글자 크기는 화면 버튼에서 바꿉니다.

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
