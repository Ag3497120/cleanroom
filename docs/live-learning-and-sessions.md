# Work continues. Understanding can continue with it.

[English](#english) | [日本語](#日本語) | [简体中文](#简体中文) | [한국어](#한국어) | [Español](#español)

## English

Cleanroom does not treat a whole project's completion as the moment to offer understanding. The built-in Work Agent can leave source-linked explanations in each model turn, while the details of a choice, failure or check are still available. These are public explanations, not private chain-of-thought. Missing notes stay missing; no technology-keyword fallback invents lessons.

### During work

- Optional Owner cards carry stable IDs such as `L-000123`. The original explanation, steps, alternatives, pitfalls, verification suggestions and source hashes stay in local storage; the small card is only a view.
- `/insights` displays recently saved cards on demand. Paste `L-000123` into Agent to ask about it, or `L-000123 Why did we choose this?` for a specific question. An unknown ID is not an automatic task rejection.
- The question uses the selected Work AI in a **separate read-only call**. It cannot execute tools, approve changes, complete the original task or mark you as having learned something.
- With work running, questions wait for the next safe model/tool boundary, are answered sequentially, and then work resumes. An in-flight model request or file operation is not killed. This is not a second parallel writer. Up to four side questions can be queued per active work run; a retained draft can be sent later.
- No popup steals Owner focus. Automatic cards require the person's enabled learning preference, non-on-demand mode and **at breaks** timing. The daily and per-work exposure budgets are shared with later suggestions, with at most two live cards per work. On-demand and disabled preferences are respected. Opening a card is not a mastery assessment.
- New profiles default to at-break timing, but learning mode remains on-demand until the person chooses otherwise. Existing explicit preferences are not overwritten. Not every model emits a useful note at every turn, and long single tool/model calls have no intermediate host boundary.

### Time estimates are forecasts

The Work AI is asked by default for separate remaining implementation and testing ranges, a short basis and uncertainties, as part of the ordinary work response. It can return no estimate. The UI labels estimates as AI forecasts, not test receipts, deadlines or proof of progress.

After a side question, the measured elapsed question time shifts the previous forecast; the next work turn asks the AI to re-estimate using the interruptions and actual progress. An exceeded range is shown as overdue, not as zero minutes until guaranteed completion. The first response, missing metadata and unsupported external runtimes can leave the time estimate unavailable.

### Two independent histories

| Control | Result |
| --- | --- |
| `verantyx new [name]` / Agent `/verantyx new [name]` | New Agent conversation. Owner Cleanroom and old records remain. |
| Owner memo or search: `/verantyx new [name]` | Confirm creation of a new named Owner Cleanroom. Agent conversation remains. |
| `verantyx new name --owner` | CLI equivalent of creating an Owner Cleanroom. |
| `verantyx cleanroom` / `/verantyx cleanroom` | List Owner Cleanrooms. |
| `/verantyx cleanroom "name"` or a completed `/name` | Confirm switch; choose Rename below Switch/Cancel if needed. |
| `verantyx compact` / `/verantyx compact` | Ask the selected AI for a source-backed summary of the current Agent session. |
| `verantyx setup context` / `/verantyx setup context` | Enable/disable automatic compaction; default off. |
| `/verantyx models` | Subscription, API, Ollama, LM Studio, model tuning and role settings. |
| `/approvals` | Revoke workspace or permanent isolated-candidate edit grants. |

Owner Cleanroom names are unique after Unicode normalization and case folding within the personal database. Both memo and search accept the session commands; the `/vernatyx cleanroom` spelling is also accepted. Pane headings show independent names. Switching/resetting waits while a work run, queued request or memo save is active, rather than moving live writes into a different session.

A new interactive workspace asks before reading project contents. Trusting that directory does not authorize external transmission, arbitrary shell commands, deletion, publication or adoption. Automation can explicitly pass `--trust-workspace`; this UI consent is not a replacement for the tool/sandbox authority layer.

### Model settings and tutorial

Local endpoints can discover available model IDs. Reasoning controls use the provider's native options; not every model supports every offered level, and provider rejections stay explicit. Context capacity can come from available model metadata, radio presets or manual entry. An unknown maximum is not guessed. Setting a number does not expand a model's real capacity. Existing parent-role choices continue to override Work AI.

The five-language practice tour explains normal input, empty-Enter pane cycling, yellow memo, green search, references, `//` temporary conversation and inline settings. Type `verantyx` in practice to finish it and enter the real workspace. The terminal-size message is advisory, not a size gate. Practice calls no model and does not add real notes.

### Storage, privacy and limits

- Project events already use SQLite at `.verantyx/state.db`; append-only events and hashes remain authoritative.
- The personal SQLite file is `profile.sqlite3` under the existing personal data home (on macOS, normally `~/Library/Application Support/Verantyx/Personal/`). Console sessions, timestamps, memo archives, local grants, insight IDs, side answers and summary indexes use separate host-owned tables, not importable skill permissions.
- Previous project memo JSONL is imported once without deleting its original file. Owner reads at most 200 memos per page. Scrolling past the first/last edge loads newer/older pages. Search runs against the stored archive, not just the visible page.
- Learning-history browsing is bounded and source lookups use IDs rather than loading every trace. Full explicit exports remain lossless. Notebook-vault sync is deferred to a work boundary rather than exporting on every tool receipt.
- Compaction streams one run at a time and summarizes bounded chunks. Original events, explicit instructions and permissions are not rewritten. Coverage is indexed by source ID/hash; large uncompressible events remain identifiable and incomplete compaction is reported.
- Side answers are AI explanations, not evidence or understanding certificates. Private Owner memos are not automatically sent. Only the selected explanation and already-shareable profile context enter an insight question.
- `//` conversations bypass this learning/estimate/summary path. Provider-side retention is outside the local temporary-conversation guarantee.
- Indexed paging reduces display memory growth; it does not promise unlimited disk space or constant-time full-project replay. Full-work projection and large-scale load performance still need separate evaluation. No automatic deletion of personal history is introduced.

### Scope of this change

This page describes implemented paths, not results of an end-to-end test run. In particular, external harness internals cannot always be paused at each of their own tool boundaries, and API reasoning options depend on the chosen model. Connection, migration, real-terminal focus and long-history load tests should be run before treating this as a verified release.

## 日本語

**「プロジェクト全体が完成してから学ぶ」方式にはしません。** 内蔵Work Agentが各応答で、実装上の選択・失敗・検査について、その場で説明と出典を残します。非公開の思考過程ではなく、利用者向けの説明です。出力がない場合は、技術名やキーワードから学習項目を捏造しません。

### 実装中の使い方

- Ownerに `L-000123` のような一意で固定の番号を付けます。短いカードの裏には、説明全文・前提・省略された手順・代替案・失敗条件・確認方法・出典ハッシュが残ります。
- `/insights` で最近の説明を開きます。Agentへ `L-000123` だけ送ると解説を求められます。`L-000123 この方式を選んだ理由は？` のように質問も加えられます。
- 質問は通常の追加実装指示とは別の読み取り専用AI呼び出しです。ツールは実行せず、採用・許可・元の仕事の完了・本人の習得を確定しません。
- 実装中は、実行中のモデル呼び出しや書き込みを壊さず、**次の安全な区切りで質問に答えて元の実装へ戻ります**。並列の書き込みエージェントは増やしません。1作業で最大4件を受け付け、それ以上は下書きを残して後から送れます。
- Ownerの入力を奪いません。自動提示は本人の学習設定が有効で、「求めたときだけ」以外、かつ「区切りで」の場合だけです。日次・1作業の上限は終了後の提案と共用し、途中のカードは最大2件です。読む・スキップするだけで理解済みにはしません。
- 新しいプロフィールの提示タイミングは「区切りで」ですが、モードは本人が選ぶまで「求めたときだけ」のままです。既存設定を勝手に書き換えません。1回の長いモデル処理や外部ツールの内部まで途中表示できるわけではありません。

### 予想時間

作業AIには通常応答の一部として、**残りの実装時間とテスト時間を別々の幅で**見積もるよう求めます。根拠と不確実な点も保持し、見積もれない場合は未見積もりと表示します。テストの成功記録や締切保証ではありません。

質問に使った実測時間を前回の予想到着時刻へ加算し、次の作業応答で進捗と割り込みを踏まえて再見積もりします。予想を超えた場合は「超過・再見積もり待ち」とし、残り0分だから完成したとは扱いません。

### 会話とCleanroomは独立

| 操作 | 動作 |
| --- | --- |
| `verantyx new [名前]` / Agentの `/verantyx new [名前]` | Agentだけを新しい会話へ。Ownerと過去の記録は維持。 |
| Ownerメモ・検索の `/verantyx new [名前]` | 確認後に新しいOwner Cleanroomを作成。Agentは維持。 |
| `verantyx new 名前 --owner` | 同じ操作をCLIから実行。 |
| `verantyx cleanroom` / `/verantyx cleanroom` | Owner Cleanroomの一覧。 |
| `/verantyx cleanroom "名前"` / 補完した `/名前` | 確認後に切替。「名前変更」も選択可能。 |
| `verantyx compact` / `/verantyx compact` | 原記録を残し、現在のAgent会話をAIで出典付き要約。 |
| `verantyx setup context` / `/verantyx setup context` | 自動圧縮の設定。初期値はOFF。 |
| `/verantyx models` | サブスク・API・Ollama・LM Studio・モデルの推論と文脈容量・親子設定。 |
| `/approvals` | ワークスペース・永久の候補編集許可の取り消し。 |

名前は個人DB内でUnicode正規化・大文字小文字の違いを除いて重複できません。Ownerは黄色・緑どちらもセッションコマンドに対応し、`/vernatyx cleanroom` の綴りも受け付けます。各欄の上には別々の名前を表示します。作業・予約・メモ保存が進行中の場合は切替を待ち、書き込みの所属を途中で変えません。

新しい対話ワークスペースでは、プロジェクトの中身を読む前に確認します。閲覧の許可と、外部送信・シェル・削除・公開・本体採用は別です。自動操作は `--trust-workspace` で明示できますが、UIの確認はツールの権限制御やサンドボックスの代わりではありません。

### モデル・体験画面

モデル設定は取得できるメタデータ、ラジオボタンの候補、手入力を用います。取得できない最大容量は推測しません。数字を大きく設定してもモデルの本当の容量は増えません。推論レベルはモデル・提供元によって対応が異なり、未対応エラーを成功扱いしません。親モデルの設定があれば引き続き優先します。

5言語の体験画面では通常入力、空欄Enter、黄色メモ、緑の検索、参照、`//`、画面内設定を案内します。練習で `verantyx` と入力すると、練習を終えて実ワークスペースへ入ります。端末サイズの案内は警告のみで、拡大するまで止める仕組みではありません。練習ではAIを呼ばず、実ノートに保存しません。

### DBと増え続ける記憶

- 作業イベントは従来から `.verantyx/state.db` のSQLiteです。追記型の原記録とハッシュを残します。
- 個人用は既存の保存ホーム内の `profile.sqlite3`。macOSの通常位置は `~/Library/Application Support/Verantyx/Personal/` です。セッション・メモ・時刻・権限・理解メモID・質問回答・要約索引は、移植スキルとは別のホスト管理テーブルです。
- 過去のメモJSONLは一度だけ取り込み、原本を削除しません。Ownerは1ページ最大200件を読み、端からさらにスクロールすると新しい・古いページへ移ります。検索は表示中のページだけでなく保存済み全体に対して行います。
- 学習履歴は件数を限定して読み、参照された出典IDだけを索引から取得します。明示的な全件エクスポートは原記録を落としません。ノート連携への同期は毎ツール操作ではなく作業の区切りに回します。
- 圧縮は1作業ずつ、さらに小さな塊で行います。元の判断・権限・イベントを消したり書き換えたりしません。要約の対象はIDとハッシュで追跡し、容量超過で要約できないイベントや未処理部分は未処理として残します。
- 質問回答はAIの説明であり、証拠・習得認定ではありません。選択した説明と共有済みプロフィール文脈だけを使い、Ownerの私的メモを自動送信しません。`//` 対話はこの保存・見積もり・学習・要約の対象外です。
- ページングは表示メモリの増大を抑える対策です。ディスク容量が無限になるわけではなく、プロジェクト全件の再構築と大規模負荷は別途評価が必要です。古い個人記録を勝手に削除しません。

この説明は実装経路の説明であり、E2E試験の合格報告ではありません。実端末のフォーカス、移行、モデル接続、長い履歴の負荷は、公開前に別途確認が必要です。

## 简体中文

学习不必等待整个项目完成。内置工作AI在每次回复中保存与实际事件关联的说明；Owner卡片使用固定编号，例如 `L-000123`。原始解释、步骤、取舍、风险与来源哈希保留，卡片只是简短视图。不会根据关键词捏造课程或推断个人已经掌握。

用 `/insights` 查看近期说明，把编号或“编号 + 问题”发送给Agent。提问是独立、只读的AI调用；在安全的模型/工具边界回答后恢复原任务，不强制中断写入、不增加并行写入者、不授予权限。每个工作最多排入4个问题。自动卡片需学习已启用、非按需模式、时机为工作间隙；共享每天/每工作预算，最多2张。已有个人偏好不覆盖，学习仍是可选的。

时间是AI对剩余实现与测试时间的分别估计，附带范围与不确定性。无法估计时明确显示未知；提问实耗时间加入原预测，下一工作步骤再估计。超时不是完成，不以预测代替测试凭据。

Agent的 `/verantyx new` 只新建对话；Owner备忘或搜索中的同命令确认后新建Cleanroom。CLI用 `verantyx new 名称 --owner` 新建Owner。`/verantyx cleanroom` 列表，`/verantyx cleanroom "名称"` 或补全的 `/名称` 确认切换，并可重命名。名称规范化后在个人数据库中唯一。工作、队列或备忘保存时等待切换，不改写旧记录。

`verantyx compact` 或 `/verantyx compact` 生成有来源的独立摘要；`verantyx setup context` 设置自动压缩，默认关闭。`/verantyx models` 选择订阅、API、Ollama或LM Studio并调整推理/上下文。元数据未知就手动输入而不猜测；输入更大数字不会扩展模型能力。权限提供一次、工作区、永久与拒绝，保存的候选编辑授权可用 `/approvals` 撤销，不涵盖删除、发布或采用。

首次交互工作区询问读取许可，不代替工具权限；明确自动化可用 `--trust-workspace`。五语言教程不调用模型、不写实际备忘；输入 `verantyx` 结束练习，进入真实工作区。尺寸提示不阻止继续。

项目事件已使用 `.verantyx/state.db`，个人索引使用 `profile.sqlite3`。备忘按200条分页，滚过边缘加载下一页，搜索覆盖存档。旧JSONL一次导入且不删除原件。学习历史分页、来源按ID读取，摘要逐工作、分块处理并保留来源哈希。原始事件、个人判断、权限和未压缩部分不删除。`//` 不进入此路径。分页不等于无限磁盘，也不保证全项目重建恒定耗时；大规模性能和真实终端操作仍需独立测试。

## 한국어

프로젝트 전체가 끝날 때까지 학습을 기다리지 않습니다. 내장 작업 AI는 각 응답에서 실제 사건에 연결된 설명을 남깁니다. Owner의 `L-000123` 같은 고정 번호 뒤에는 설명 전문, 단계, 대안, 위험, 확인 방법과 출처 해시가 보존됩니다. 키워드로 학습을 만들어 내거나 이해 완료를 추측하지 않습니다.

`/insights`로 최근 설명을 보고 번호 또는 번호와 질문을 Agent에 보냅니다. 별도의 읽기 전용 호출로, 안전한 모델/도구 경계에서 답한 뒤 원래 구현으로 돌아갑니다. 쓰기를 강제 중단하거나 병렬 작성자를 만들거나 권한을 늘리지 않습니다. 작업당 질문은 최대4개입니다. 자동 카드는 학습 활성화, 요청 시만이 아닌 모드, 작업 사이 타이밍을 선택했을 때만 표시하며 기존 일일/작업 예산을 공유하고 최대2개입니다. 기존 설정은 유지되고 학습은 선택입니다.

시간은 남은 구현과 테스트를 따로 예상한 범위와 근거입니다. 알 수 없으면 미예상으로 표시합니다. 질문의 실측 시간은 기존 예상에 더하고 다음 작업 단계에서 재예상합니다. 초과는 완료가 아니며 예상은 테스트 증거가 아닙니다.

Agent의 `/verantyx new`는 대화만 새로 만들고 Owner의 같은 명령은 확인 후 새 Cleanroom을 만듭니다. CLI에서는 `verantyx new 이름 --owner`입니다. `/verantyx cleanroom`은 목록, 이름을 붙이거나 `/이름`을 완성하면 전환 확인과 이름 변경을 제공합니다. 이름은 정규화한 뒤 개인DB에서 중복할 수 없습니다. 작업·예약·메모 저장 중에는 전환을 기다립니다.

`verantyx compact` 또는 `/verantyx compact`는 출처가 있는 요약을 별도 저장합니다. `verantyx setup context`의 자동 요약은 기본OFF입니다. `/verantyx models`에서 구독·API·Ollama·LM Studio 및 추론·문맥을 설정합니다. 알 수 없는 용량은 추측하지 않고 수동 입력도 가능하나 모델의 실제 용량을 늘리지는 않습니다. 후보 편집은 한 번·작업 공간·항상 허용·거부이며 `/approvals`로 저장 허용을 취소합니다. 삭제·공개·본체 적용과는 별개입니다.

처음 들어가는 대화형 작업 공간은 읽기를 확인합니다. 자동화는 `--trust-workspace`로 명시할 수 있지만 도구 권한을 대신하지 않습니다.5언어 모의 연습은 모델 호출과 실제 기록 없이 작동하며 `verantyx`를 입력하면 실제 작업 공간으로 갑니다. 크기 안내는 차단 조건이 아닙니다.

작업 사건은 기존 SQLite `.verantyx/state.db`, 개인 데이터는 `profile.sqlite3`입니다. 메모는200개씩 읽고 경계에서 더 스크롤하면 다음 페이지로 이동하며 검색은 보관 기록 전체를 대상으로 합니다. 기존JSONL은 한 번 가져오고 원본을 지우지 않습니다. 학습 이력은 제한하여 읽고 출처는ID로 조회합니다. 요약은 작업별 작은 묶음이며 출처 해시, 판단, 권한과 원기록을 보존합니다. `//`는 이 경로에서 제외됩니다. 페이지 처리는 무한 디스크나 일정한 전체 재생 시간을 보장하지 않으며 실제 단말·대규모 부하 검증은 별도로 필요합니다.

## Español

No hay que esperar al final del proyecto para comprenderlo. El agente integrado conserva explicaciones vinculadas a hechos en cada respuesta. Las tarjetas Owner reciben IDs estables, como `L-000123`; detrás quedan la explicación completa, pasos, alternativas, riesgos, verificaciones propuestas y hashes. No se inventan lecciones por palabras clave ni se presume dominio.

Abre `/insights` y envía el ID a Agent, solo o seguido de una pregunta. Es una llamada independiente de solo lectura: se responde en un punto seguro entre modelos/herramientas y se reanuda la implementación, sin matar escrituras, añadir escritores paralelos ni conceder permisos. Se admiten4preguntas por trabajo activo. Las tarjetas automáticas requieren aprendizaje habilitado, modo distinto de bajo demanda y momento entre pasos; comparten el presupuesto diario/por trabajo y muestran como máximo2. Se mantienen las preferencias anteriores y aprender es opcional.

La IA estima por separado los rangos restantes de implementación y pruebas, con fundamento e incertidumbre. Puede no estimar. El tiempo medido de preguntas se añade al pronóstico anterior y el siguiente paso lo reestima. Superar el rango no significa terminar y una previsión no es evidencia de pruebas.

`/verantyx new` en Agent renueva solo la conversación; en Nota/Buscar de Owner confirma un Cleanroom nuevo. Desde CLI: `verantyx new nombre --owner`. `/verantyx cleanroom` lista; con un nombre o `/nombre` completado confirma cambiar y permite renombrar. Los nombres normalizados son únicos en la base personal. Se espera antes de cambiar mientras haya trabajo, cola o guardado activo.

`verantyx compact` o `/verantyx compact` crea un resumen independiente con fuentes. `verantyx setup context` configura compresión automática, desactivada inicialmente. `/verantyx models` ofrece suscripción, API, Ollama y LM Studio, razonamiento y contexto. La capacidad desconocida no se inventa y un valor manual no amplía la capacidad real. Los permisos de candidatos pueden ser una vez, por espacio, permanentes o rechazo; `/approvals` revoca los guardados. No incluyen eliminar, publicar ni adoptar.

Un espacio interactivo nuevo solicita lectura; `--trust-workspace` permite autorización explícita de automatización, sin reemplazar permisos de herramientas. El tutorial en5idiomas no llama modelos ni crea notas reales; escribe `verantyx` para entrar al espacio real. El aviso de tamaño no bloquea.

Los eventos ya usan SQLite `.verantyx/state.db`; los datos personales usan `profile.sqlite3`. Las notas se leen en páginas de200, desplazándose más allá de un borde para cargar otra; la búsqueda abarca el archivo. JSONL anterior se importa una vez sin eliminarlo. El historial de aprendizaje se lee acotado y las fuentes por ID. La compresión procesa un trabajo y pequeños bloques, conservando originales, hashes, decisiones y permisos. `//` queda fuera. La paginación no garantiza disco infinito ni reconstrucción constante del proyecto; las pruebas de carga y terminal real siguen siendo independientes.
