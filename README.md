<p align="center"><img src="public/cleanroom/logo.svg" width="440" alt="cleanroom"></p>

<p align="center"><strong>Let AI build. Keep being the developer.</strong></p>

<p align="center"><a href="#en">English</a> · <a href="#ja">日本語</a> · <a href="#zh-Hans">简体中文</a> · <a href="#ko">한국어</a> · <a href="#es">Español</a></p>

![Actual split CLI with scripted demonstration data](public/cleanroom/cli-demo.gif)

**Recorded CLI / scripted fixtures / no model calls.** [Recording recipe](docs/DEMO_RECORDING.md) · [MP4](public/cleanroom/cli-demo.mp4) · [Interactive preview](https://ag3497120.github.io/cleanroom/) · [Website](https://verantyx.ai)

<a id="en"></a>

## English

### Let AI build. Keep being the developer.

Cleanroom is a collaborative development workspace powered by the Vera Kernel. AI can do most of the implementation while your purpose, decisions, understanding, verification methods, and experience stay with you.

### Start locally

Python **3.11+** · macOS / Linux · Windows: **WSL2**. CLI command: `verantyx`.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

[Operating guide](core/docs/OPERATIONS.en.md) · [Commands](#commands) · [About the author](docs/AUTHOR.md#en)

### Split CLI: Agent on the left, Owner on the right

- Ask in the lower-left Agent field. No new command language to learn.
- Empty Enter moves to the yellow Owner memo, then the green Owner search, then back to Agent.
- Type at least the first two characters of an Owner item, choose with Up/Down, and press Tab to insert that reference. Enter selects an open suggestion, rather than sending the task.
- F2 opens actions; F3 scrolls; F4 opens learning; Alt+0 restores the split. Ctrl+J adds a line. Ctrl+D closes at a safe boundary.

### What stays with you

- Your decisions and their reasons
- AI assumptions, actual receipts, and remaining unknowns
- Skills you choose to explore, reference, or delegate
- Implementation-time notes, source links, and a journal that can carry into later work

Work results and AI reflection are independent. Different models can offer different interpretations without erasing previous ones. AI procedure drafts are not proof that you have learned a skill. Skipping, delegating, or asking for help is not an ability judgment.

Owner notes and search do not call AI. Explicitly inserted references enter the request's send scope. Private project and personal records are not meant for public GitHub commits.

The name comes from the author's personal image of a cleanroom: an isolated sanctuary for human judgment. It is a metaphor, not an OS sandbox guarantee. This independently developed, non-commercially motivated project grew from a Japanese X post and the author's own unease about losing the experience of making things with AI.

Personal motivation is not a restriction on use under the repository's actual license.

> Source preview, not a certification of MVP completeness. The GIF uses scripted fixtures in the real CLI renderer; it is not a successful model benchmark. The browser playground is an in-memory interaction demo, not a remote shell.

[↑ English / Languages](#en)

<a id="ja"></a>

## 日本語

### AIに作らせても、開発者であることまで手放さない。

Cleanroomは、Vera Kernelを基盤とする共同開発空間です。AIが実装の大部分を担っても、プロジェクトの目的、設計判断、検証方法、失敗、技術的理解を人間側に残し、一緒に育て続けられるようにします。

### 手元で始める

Python **3.11+** · macOS / Linux · Windows: **WSL2**. CLI command: `verantyx`.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

[操作ガイド](core/docs/OPERATIONS.ja.md) · [Commands](#commands) · [本西航大とは](docs/AUTHOR.md#ja)

### 左はAgent、右はOwner

- 左下のAgent欄へ普通の文章で依頼します。独自のコマンドを覚える必要はありません。
- 空欄でEnterを押すと、Agent → 黄色のOwnerメモ → 緑色のOwner検索 → Agentを巡回します。
- Owner項目の先頭2文字以上を入力し、上下矢印で選び、Tabで参照を挿入します。補完候補が開いている間のEnterは選択だけで、依頼は送りません。
- F2は操作一覧、F3はスクロール、F4は理解の画面、Alt+0は分割表示。Ctrl+Jで改行し、Ctrl+Dで操作の区切りに終了します。

### 仕事の後、手元に残るもの

- 自分が決めたことと、その理由
- AIの仮定、実際の検査記録、残っている不明点
- 必要な分だけ選ぶ、学習・参照・委譲の候補
- 作業途中の説明、出典、次の仕事へ続く日記

作業結果とAIによる整理は別状態です。モデルごとの見方が違っても過去の整理を消しません。AIの手順が保存されたことを、本人の習得とは数えません。スキップ、委譲、相談を理解不足と推定しません。

Ownerのメモと検索だけではAIを呼びません。依頼に明示的に挿入した参照は送信範囲に入ります。プロジェクトと個人の私的な記録を公開GitHubへ追加しないでください。

私は日本語の「クリーンルーム」に、隔離された聖域のような、人間の判断が守られる場所を重ねて、このプロジェクトを始めました。これは私自身の比喩であり、一般的な語義やOSの隔離保証ではありません。ある日本語のX投稿と、AIを使う最近の開発や将来への不安が出発点です。

個人の非商用的な制作動機を示すもので、リポジトリの実際のライセンスを変更・制限する表明ではありません。

> ソース版のプレビューであり、MVP全項目の合格宣言ではありません。GIFは実際のCLI描画に台本付きのデモデータを流したものです。実モデルの成功記録ではありません。Webの体験欄はメモリ内だけの操作デモで、リモートシェルではありません。

[↑ English / Languages](#en)

<a id="zh-Hans"></a>

## 简体中文

### 让 AI 编写代码，但不放弃开发者的角色。

Cleanroom 是以 Vera Kernel 为基础的协作开发空间。即使 AI 承担大部分实现工作，项目目标、设计判断、验证方法、失败经验和技术理解仍留在你手中。

### 在本机开始

Python **3.11+** · macOS / Linux · Windows: **WSL2**. CLI command: `verantyx`.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

[操作指南](core/docs/OPERATIONS.zh-Hans.md) · [Commands](#commands) · [关于作者](docs/AUTHOR.md#zh-Hans)

### 左侧 Agent，右侧 Owner

- 在左下方 Agent 输入框用自然语言提出任务，无需记住新命令。
- 在空输入框按 Enter，依次切换：Agent → 黄色 Owner 备忘 → 绿色 Owner 搜索 → Agent。
- 输入 Owner 条目的前两个或更多字符，用上下方向键选择，再按 Tab 插入引用。候选列表打开时，Enter 只选择候选，不提交任务。
- F2 打开操作菜单，F3 滚动，F4 打开理解视图，Alt+0 返回分屏。Ctrl+J 换行，Ctrl+D 在安全的操作边界退出。

### 工作完成后，留下什么

- 你的选择与理由
- AI 假设、真实验证记录及未知事项
- 由本人选择的学习、查阅或委托候选
- 实现过程中的说明、来源和可延续的开发日记

工作结果与 AI 整理相互独立。不同模型可以提出不同观点，而不覆盖旧记录。AI 保存的步骤不代表本人已经掌握。跳过、委托或求助不会被认定为能力不足。

Owner 备忘和搜索本身不会调用 AI。主动插入请求的引用会进入发送范围。不要将项目或个人私密记录提交到公共 GitHub。

作者把 cleanroom 想象成保护人类判断的隔离空间。这是个人的比喻，不是操作系统沙箱保证。项目源于一篇日语 X 帖子，以及作者对 AI 开发中经验流失和未来的担忧。

个人的非商业创作动机不改变仓库实际许可证的使用条件。

> 这是源码预览，不是 MVP 全部达标的认证。GIF 使用真实 CLI 渲染器和脚本化演示数据，不是实际模型的成功测试。网页体验区仅在内存中模拟交互，不是远程终端。

[↑ English / Languages](#en)

<a id="ko"></a>

## 한국어

### AI에게 구현을 맡겨도, 개발자의 역할까지 놓지 마세요.

Cleanroom은 Vera Kernel을 기반으로 하는 공동 개발 공간입니다. AI가 구현 대부분을 맡아도 프로젝트의 목적, 설계 판단, 검증 방법, 실패 경험, 기술적 이해는 사람에게 남습니다.

### 내 컴퓨터에서 시작

Python **3.11+** · macOS / Linux · Windows: **WSL2**. CLI command: `verantyx`.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

[사용 안내](core/docs/OPERATIONS.ko.md) · [Commands](#commands) · [작성자 소개](docs/AUTHOR.md#ko)

### 왼쪽 Agent, 오른쪽 Owner

- 왼쪽 아래 Agent 입력란에 자연스러운 문장으로 요청하세요. 새로운 명령어를 외울 필요가 없습니다.
- 빈 입력란에서 Enter를 누르면 Agent → 노란색 Owner 메모 → 초록색 Owner 검색 → Agent 순서로 이동합니다.
- Owner 항목의 앞 두 글자 이상을 입력하고 위아래 화살표로 고른 뒤 Tab으로 참조를 넣습니다. 후보가 열려 있을 때 Enter는 선택만 하고 요청을 보내지 않습니다.
- F2는 작업 메뉴, F3는 스크롤, F4는 이해 화면, Alt+0은 분할 화면입니다. Ctrl+J로 줄바꿈, Ctrl+D로 안전한 작업 경계에서 종료합니다.

### 작업 뒤에도 내게 남는 것

- 나의 선택과 그 이유
- AI의 가정, 실제 검증 기록, 남은 미확인 사항
- 내가 선택하는 학습·참조·위임 후보
- 구현 도중의 설명, 출처, 다음 작업으로 이어지는 일지

작업 결과와 AI의 정리는 독립적입니다. 모델의 관점이 달라도 이전 기록은 유지됩니다. AI의 절차가 저장되었다고 사용자가 배웠다고 판단하지 않습니다. 건너뛰기, 위임, 도움 요청은 능력 부족의 근거가 아닙니다.

Owner 메모와 검색만으로 AI를 호출하지 않습니다. 요청에 직접 넣은 참조는 전송 범위에 포함됩니다. 개인 기록과 프로젝트 비공개 기록을 공개 GitHub에 올리지 마세요.

작성자는 cleanroom을 인간의 판단이 보호되는 격리된 공간으로 생각했습니다. 개인적인 비유이지 OS 샌드박스 보장이 아닙니다. 일본어 X 게시물과 AI 개발 과정에서 경험을 잃을지 모른다는 걱정에서 시작했습니다.

개인의 비상업적 제작 동기는 저장소의 실제 라이선스를 바꾸거나 제한하지 않습니다.

> 소스 미리보기이며 MVP 전체 통과를 보장하지 않습니다. GIF는 실제 CLI 렌더러에 시나리오 데이터를 넣어 녹화한 것으로, 실제 모델의 성공 기록이 아닙니다. 웹 체험은 메모리 안의 상호작용 데모이며 원격 셸이 아닙니다.

[↑ English / Languages](#en)

<a id="es"></a>

## Español

### Deja que la IA construya. Sigue siendo quien desarrolla.

Cleanroom es un espacio de desarrollo colaborativo basado en Vera Kernel. Aunque la IA realice gran parte de la implementación, conservas el propósito, las decisiones, los métodos de verificación, los fallos y la comprensión técnica del proyecto.

### Empezar en tu equipo

Python **3.11+** · macOS / Linux · Windows: **WSL2**. CLI command: `verantyx`.

```sh
git clone https://github.com/Ag3497120/cleanroom.git cleanroom
cd cleanroom
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./core
verantyx setup accounts
verantyx
```

[Guía de uso](core/docs/OPERATIONS.es.md) · [Commands](#commands) · [Sobre el autor](docs/AUTHOR.md#es)

### Agent a la izquierda, Owner a la derecha

- Escribe una petición normal en el campo Agent, abajo a la izquierda. No hace falta aprender un nuevo lenguaje de comandos.
- Pulsa Enter con el campo vacío: Agent → nota Owner amarilla → búsqueda Owner verde → Agent.
- Escribe al menos los dos primeros caracteres de un elemento Owner, elige con las flechas y pulsa Tab para insertar la referencia. Con sugerencias abiertas, Enter selecciona; no envía la petición.
- F2 abre acciones; F3 permite desplazarte; F4 abre la vista de comprensión; Alt+0 restaura la división. Ctrl+J añade una línea y Ctrl+D cierra al terminar la operación en curso.

### Lo que se queda contigo

- Tus decisiones y sus razones
- Supuestos de la IA, comprobaciones reales y cuestiones abiertas
- Opciones de aprendizaje, consulta o delegación que tú eliges
- Notas durante la implementación, fuentes y un diario que continúa entre proyectos

El resultado del trabajo y la reflexión de la IA son independientes. Los modelos pueden ofrecer interpretaciones distintas sin borrar las anteriores. Un procedimiento de IA no certifica una habilidad humana. Delegar, omitir o pedir ayuda no implica falta de capacidad.

Las notas y búsquedas Owner no llaman a la IA. Las referencias que insertas expresamente forman parte del contenido a enviar. No publiques registros privados del proyecto ni personales en GitHub.

El nombre nace de la imagen personal del autor: un espacio aislado que protege el juicio humano. Es una metáfora, no una garantía de aislamiento del sistema operativo. El proyecto surgió de una publicación japonesa en X y de sus inquietudes sobre desarrollar con IA y perder experiencia.

La motivación personal no comercial no modifica ni restringe la licencia real del repositorio.

> Vista previa del código fuente, no certificación de un MVP completo. El GIF usa datos preparados en el renderizador real de la CLI; no es una prueba exitosa de un modelo. La demo web funciona en memoria y no es un shell remoto.

[↑ English / Languages](#en)

<a id="commands"></a>

## Commands / コマンド / 命令 / 명령어 / Comandos

The F2 menu is the everyday entry. The live command catalogue comes from the installed CLI, not a separate hand-maintained registry.

| Command | Purpose |
|---|---|
| `verantyx` | Split Agent / Owner workspace |
| `verantyx --plain` | Plain terminal interface |
| `verantyx commands` | Registered commands |
| `verantyx commands setup --json` | Details from the actual parser |
| `verantyx setup` | Settings |
| `verantyx setup accounts` | Official CLI account connections |
| `verantyx setup models` | Work / reflection models |
| `verantyx setup roles` | Model role configuration |
| `verantyx setup profile` | Your voluntary experience profile |
| `verantyx setup pace` | Suggestion amount, timing and weight |
| `verantyx my-skills` | AI procedures and your chosen experience records |
| `verantyx my-learning` | Implementation-time notes and explanations |
| `verantyx my-journal` | Personal development journal |
| `verantyx web` | Private, local My Atlas |
| `verantyx watch` | Read-only view; not another agent |
| `verantyx setup notebook` | Obsidian / notebook bridge |
| `verantyx setup harness` | Trusted external work adapter |
| `verantyx setup sandbox` | External isolation launcher configuration |
| `verantyx toolbox status` | MCP / tool connections |

## Detailed documentation

- [Operating guide (English)](core/docs/OPERATIONS.en.md)
- [操作ガイド (日本語)](core/docs/OPERATIONS.ja.md)
- [操作指南 (简体中文)](core/docs/OPERATIONS.zh-Hans.md)
- [사용 안내 (한국어)](core/docs/OPERATIONS.ko.md)
- [Guía de uso (Español)](core/docs/OPERATIONS.es.md)
- [Origins: original material, translations and development history](core/docs/origins/README.md)
- [Privacy, preview boundaries and publication architecture](docs/PUBLICATION.md)
- [Personal profile and learning pace](core/docs/PERSONAL_GROWTH.ja.md)
- [Skills and harnesses](core/docs/SKILLS_AND_HARNESSES.ja.md)
- [Implementation-time learning](core/docs/LEARNING_CONTINUITY.en.md)
- [Obsidian, MCP, skill import and model handoff](core/docs/NOTEBOOK_CONNECTIONS.en.md)
- [Sandbox responsibilities](core/docs/SANDBOX_BACKENDS.en.md)
- [Live evaluation and limitations](core/docs/LIVE_EVALUATION.en.md)

## Contribution boundaries

Meaning is proposed by the chosen AI. Authority, provenance, actual execution facts and asset states are maintained by Vera. Human understanding is not inferred from usage or delegation. Work survives reflection failure. Different interpretations remain versioned rather than forced into identical answers.

This publication updates presentation and documentation. It does not turn a failed evaluation into a pass, certify human mastery, offer a production-safe public shell, or claim that a configured external sandbox has been independently verified. The CLI remains the primary product; browser previews and the existing IDE are complementary surfaces.
