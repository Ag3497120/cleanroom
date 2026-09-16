# Cleanroom split-pane controls

[English](#english) | [日本語](#日本語) | [简体中文](#简体中文) | [한국어](#한국어) | [Español](#español)

## English

For compact layouts, full-width reading, selection/copy and reading-position controls, see the [five-language reading guide](READABILITY.md) and [scrolling controls](SCROLLING.md). These controls do not change AI permissions or empty-Enter input switching.

| Reading action | Control |
| --- | --- |
| Expand current pane / restore split view | F5, /fullscreen, /split |
| Select and copy text | Drag then Ctrl+C; F6 copies selection or current pane |
| Read older messages / return to latest | Wheel or PgUp/PgDn; Ctrl+End or /latest |
| Native terminal selection | F7 or /mouse |


Agent is on the left; Owner is your notebook on the right, not another AI.
A thick mint border marks Agent input, yellow marks Owner memo, green marks Owner search. A text label also identifies focus.
Model answers and system activity are separate panels. The header displays the configured model, not an identity guessed from model prose. CLI default means the concrete model ID is unresolved.

| Action | Control |
| --- | --- |
| Send text | Enter |
| Cycle empty input | Enter: Agent → Memo → Search → Agent |
| New line | Shift+Enter where supported; Alt+Enter or Ctrl+J |
| Previous / newer input and draft | Up / Down at the first / last line |
| Insert Owner reference | Type the first two letters, arrows, Tab |
| Scroll the active pane | Wheel, PgUp/PgDn; F3 focuses reading |
| Controls and menu | /help, /commands, F2 |
| Inline settings and models | /verantyx, /verantyx setup models, /model |
| Replay practice / finish it | /tutorial, /done |
| Temporary conversation | //your message |
| PDF or image / clear queue | /attach "/path/file.pdf", /detach |
| Expand system activity | /details |
| Close help, settings or temporary chat | /close |

History is session-local, separate for Agent, memo and search. Settings and // messages are excluded.
Completion lists and settings take arrow-key priority. Inside multiline text, arrows move normally until the first or last line.

Some terminals send the same bytes for Enter and Shift+Enter. Cleanroom supports CSI-u and xterm modified-key sequences and requests enhanced reporting, but cannot recover a modifier discarded by a terminal. Alt+Enter and Ctrl+J are the alternatives. Empty Enter still cycles inputs.

### Inline settings

Arrows highlight radio-style options and show explanations in the selected language; Enter chooses.
Inside settings only, /value answers the current question: for example /work then /ollama; a server field accepts /http://127.0.0.1:11434/api/chat.
Explicit /help, /model and /verantyx commands keep their meaning. Plain text without / cancels a pending setting and returns to work. Saved settings remain saved; settings conversation does not become work, learning or skill memory.

Ollama asks for the endpoint before listing models on that server. LM Studio and similar servers use OpenAI-compatible settings.
HTTP is limited to literal loopback addresses; use HTTPS or an SSH tunnel for another Mac.
A saved model choice is not a successful connection test. Explicit parent-model roles override Work AI, and the header reflects this.

### Attachments and privacy

An explicit PDF/image path in a task also becomes a send candidate. Quote paths with spaces. Only the displayed files are authorized, not parent folders.
PDFs supply extracted text and rendered page images, allowing diagrams and scans to reach a vision-capable model.
Use /attach --text "file.pdf" for text only, or /attach --pages 2-4 "file.pdf" for selected pages. Text-only mode does not read diagrams or scans.

Limits: 4 files, 25 MiB per original, 12 selected pages/images total, 120,000 UTF-8 bytes of extracted text, 6 MiB of normalized images. Images have a maximum edge of 1,600 pixels. Oversized or encrypted PDFs and animated images require a smaller, unlocked or static selection; nothing is silently truncated.
Approved normal attachments are stored locally under .verantyx/attachment-inputs with original hashes. Document content grants no tool permissions.
Built-in Codex, Claude Code and API transports carry image inputs; the chosen model/server must support vision. Arbitrary external harnesses do not yet negotiate media and are explicitly refused.

Temporary // conversation uses no project/profile context, tools, work ledger, learning extraction, skill creation or input recall. Recent temporary turns stay in RAM until normal work or /close. Temporary adapter journals, including Codex response caches, are removed after each call. This does not guarantee absence of provider retention, vendor diagnostics, OS swap, crash remnants or terminal capture.

### First run

An advisory recommends about 140 columns × 24 rows for side-by-side use, never blocking on size. Enter starts simulated practice; Esc skips. Practice calls no model and writes no actual notebook entries; only an offered marker is retained.
The tutorial and new option explanations support five languages. Some legacy labels remain untranslated.

## 日本語

左がAgent、右が自分のOwnerノートです。右側は別のAIではありません。
ミント色の太枠はAgent、黄色はOwnerメモ、緑はOwner検索を示します。「入力先」の文字でも識別できます。
モデルの回答とシステム通知は別欄に表示します。上部のモデル名は設定値であり、AIの自己紹介から推測しません。CLI既定の場合は実モデルIDが未確定と表示します。

| 操作 | キー・コマンド |
| --- | --- |
| 文章を送信 | Enter |
| 空欄で入力先を移動 | EnterでAgent → メモ → 検索 → Agent |
| 改行 | 対応端末のShift+Enter、またはAlt+Enter・Ctrl+J |
| 以前の入力・元の下書き | 最初・最後の行で↑・↓ |
| Owner項目の参照 | 先頭2文字以上 → 矢印 → Tab |
| 片方だけスクロール | ホイール・PgUp/PgDn。F3で閲覧へ |
| 説明・メニュー | /help・/commands・F2 |
| 画面内の設定・モデル変更 | /verantyx・/verantyx setup models・/model |
| 練習の再表示・終了 | /tutorial・/done |
| 記憶に残さない対話 | //文章 |
| PDF・画像の添付と解除 | /attach "/絶対パス/課題.pdf"・/detach |
| 操作通知の詳細 | /details |
| 案内・設定・一時対話を閉じる | /close |

入力履歴は起動中のメモリ内でAgent・メモ・検索ごとに保持します。設定入力と//対話は含めません。
補完候補や設定選択中はそちらの矢印操作を優先します。複数行の編集中は通常のカーソル移動を優先し、最初・最後の行で履歴へ移動します。
端末がEnterとShift+Enterを同じ信号で送る場合、アプリには区別できません。CSI-u・xterm形式のShift+Enterに対応し、拡張キー通知を要求します。非対応環境ではAlt+EnterかCtrl+Jで改行してください。空欄Enterの切替は変えません。

### 画面内の設定

矢印でラジオボタン状の項目を移動し、説明を見てEnterで選びます。説明は選択中の言語で表示します。
設定中だけ/値でも回答できます。例は/work → /ollama、サーバー欄では/http://127.0.0.1:11434/api/chatです。
/help・/model・/verantyxなど明示コマンドを優先し、/なしの文章では未決定の設定操作を中止して通常の依頼へ戻ります。保存済み設定は維持しますが、設定のやり取りは仕事・日記・スキル・学習記憶には入れません。

Ollamaは先に接続先を選び、そのサーバーのモデルを一覧表示します。LM StudioなどはOpenAI互換サーバーを選びます。
別MacはHTTPSかSSHトンネルで接続してください。HTTPは数値のループバックアドレスのみ許可します。
モデル設定の保存と接続成功は別です。親モデルの明示設定があれば作業AIより優先し、上部にも反映します。

### 添付と一時対話

依頼文中のPDF・画像のパスも添付候補にします。空白を含むパスは引用符で囲んでください。
送信確認で表示したファイルだけを対象にし、親フォルダの権限は追加しません。
PDFは本文とページ画像を送るため、図表・スキャンも視覚対応モデルへ渡せます。
本文のみは/attach --text "課題.pdf"、ページ指定は/attach --pages 2-4 "課題.pdf"です。本文のみでは図表・スキャンを読めた扱いにはしません。

上限は4ファイル・原本1件25 MiB・合計12ページ/画像・抽出本文120,000 UTF-8バイト・変換画像6 MiBです。画像は長辺1,600px以内に変換します。超過や暗号化PDF、アニメーション画像は小さい範囲・解除済み・静止画で指定してください。黙って切り捨てません。
通常の承認済み添付は.verantyx/attachment-inputsへ原本とハッシュ付きで残します。文書の内容に実行権限はありません。
内蔵のCodex・Claude Code・API接続に画像を渡しますが、モデル側にも視覚対応が必要です。任意の外部ハーネスとのメディア能力の交渉は未対応であり、読めたことにせず拒否します。

//はプロジェクト・プロフィールの文脈やツールを使わず、台帳・学習・スキル・入力履歴にも入れません。直近の一時対話だけをメモリへ持ち、通常の依頼か/closeで破棄します。アダプターの一時記録とCodexの応答キャッシュも一時ディレクトリへ作り、呼び出し後に削除します。
接続先AIや公式CLIの診断ログ、OSのスワップ、クラッシュ残骸、端末録画まで一切保存されないと保証する機能ではありません。

初回は横並びの目安140桁・24行を案内しますが、サイズで止めません。Enterで擬似画面、Escでスキップです。練習はAIを呼ばず、実ノートへ保存しません。案内済みの印だけを残します。新しい案内・選択肢説明は5言語対応ですが、一部の旧機能ラベルは未翻訳です。

## 简体中文

左侧Agent处理工作，右侧Owner是你的笔记。薄荷色粗框表示Agent，黄色是笔记，绿色是搜索；文字也标明焦点。回答与系统通知分栏，顶部显示配置模型而非AI自报身份。

Enter发送；空白Enter循环Agent→笔记→搜索→Agent。Shift+Enter在支持的终端换行，也可Alt+Enter或Ctrl+J；相同的终端信号无法区分。上下键在首末行浏览本次输入历史，设置和//对话不加入。补全和选项优先使用方向键。输入Owner项目前两个字，再用方向键和Tab引用。

/help、/commands、F2显示操作；/verantyx或/model在Agent里设置。方向键查看说明，Enter确认，设置中可输入/值。不带/的文字取消未完成设置并返回工作，已保存配置不变。/close关闭；/details展开通知。
Ollama先选端点再列模型；LM Studio使用OpenAI兼容选项。远程连接使用HTTPS或SSH隧道，HTTP限数字回环地址。父模型优先；保存不是连接验证。

/attach "/路径/文档.pdf"添加附件，/detach清空；请求里的明确路径也成为候选。批准只涵盖所选文件，不授权父文件夹。PDF传递文本和页图像，需要视觉模型。--text只读文本，--pages 2-4选页，不伪称读取扫描文字。
限制：4文件、每原本25 MiB、合计12页/图片、120,000字节UTF-8文本、6 MiB转换图片，最长边1,600px。超限、加密PDF或动画需另选，不静默截断。批准附件和哈希保存在.verantyx/attachment-inputs。内置连接支持媒体传输，任意外部执行框架尚未协商媒体能力。

//临时对话不使用项目或个人文脉、工具、工作台账、学习、技能或输入历史。近期临时对话只在内存保留，普通请求或/close清除；适配器临时记录在调用后删除。提供方、系统及终端录制不在此保证内。

首次建议140列×24行但不强制。Enter开始模拟教程，Esc跳过；无AI调用，不保存练习笔记，仅记住已提示。/tutorial重播，/done结束。部分旧功能标签未翻译。

## 한국어

왼쪽 Agent는 작업, 오른쪽 Owner는 나의 노트입니다. 민트색 굵은 테두리는 Agent, 노란색은 메모, 초록색은 검색을 나타내며 문자로도 표시합니다. 답변과 시스템 알림을 분리하고 상단은 설정 모델을 표시합니다.

Enter는 전송, 빈 Enter는Agent→메모→검색→Agent 전환입니다. 지원 터미널에서는 Shift+Enter로 줄바꿈하며 Alt+Enter·Ctrl+J도 가능합니다. 터미널 신호가 같으면 구분할 수 없습니다. 첫/마지막 줄의 위/아래는 세션 입력 기록이며 설정과//대화는 제외합니다. 자동완성·설정 선택이 우선합니다. Owner 앞 두 글자를 입력하고 화살표·Tab으로 참조합니다.

/help·/commands·F2로 조작을 보고 /verantyx·/model로 Agent 안에서 설정합니다. 화살표로 설명, Enter로 선택, /값으로 답할 수 있습니다. /없는 문장은 미완료 설정을 취소하고 작업으로 돌아가며 저장된 설정은 유지합니다. /close로 닫고 /details로 알림을 펼칩니다.
Ollama는 서버를 먼저 선택합니다. LM Studio 등은 OpenAI 호환 옵션을 씁니다. 원격은 HTTPS·SSH 터널, HTTP는 숫자 루프백만 허용합니다. 부모 모델이 우선하며 설정 저장은 연결 검증이 아닙니다.

/attach "/경로/문서.pdf"로 첨부, /detach로 해제합니다. 요청의 명시적 경로도 후보가 되며 상위 폴더 권한은 주지 않습니다. PDF의 본문과 페이지 이미지를 보내므로 비전 모델이 필요합니다. --text는 텍스트만, --pages 2-4는 페이지 선택이며 스캔을 읽었다고 가정하지 않습니다.
한도는4파일, 원본당25 MiB, 합계12페이지/이미지, UTF-8 본문120,000바이트, 변환 이미지6 MiB·긴 변1,600px입니다. 초과·암호화·애니메이션은 다른 범위를 선택하며 조용히 자르지 않습니다. 승인 첨부와 해시는.verantyx/attachment-inputs에 남습니다. 임의 외부 하네스의 미디어 협상은 미지원입니다.

//는 프로젝트·프로필 문맥과 도구, 작업·학습·스킬·입력 기록을 쓰지 않는 임시 대화입니다. 최근 대화만 메모리에 두며 일반 요청·/close로 비웁니다. 임시 어댑터 기록은 호출 후 삭제하지만 제공자·OS·터미널 기록까지 보장하지 않습니다.

첫 실행은140열·24행을 권장하되 차단하지 않습니다. Enter로 모의 연습, Esc로 건너뜁니다. AI 호출·실제 노트 저장은 없고 안내 여부만 남깁니다. /tutorial로 재시작, /done으로 종료합니다. 일부 기존 라벨은 미번역입니다.

## Español

Agent trabaja a la izquierda; Owner es tu cuaderno a la derecha, no otra IA. El borde menta indica Agent, amarillo Nota, verde Buscar, también con etiqueta de foco. Respuestas y avisos están separados; arriba figura el modelo configurado.

Enter envía; Enter vacío alternaAgent→Nota→Buscar→Agent. Shift+Enter crea línea donde se distingue; Alt+Enter o Ctrl+J son alternativas. Señales idénticas del terminal no pueden distinguirse. Arriba/abajo en primera/última línea recuperan entradas de la sesión, sin ajustes ni//charlas. Sugerencias y selecciones tienen prioridad. Para referenciar Owner, escribe dos letras, flechas y Tab.

/help,/commands,F2 muestran controles. /verantyx o/model abren ajustes dentro de Agent. Flechas muestran explicaciones, Enter elige y/valor responde. Texto sin/ cancela el ajuste pendiente y vuelve al trabajo, conservando cambios guardados. /close cierra y/details amplía avisos.
Ollama pide primero servidor y luego modelo; LM Studio usa la opción compatible con OpenAI. Conexiones remotas requieren HTTPS o túnel SSH; HTTP solo admite bucle local numérico. Un rol padre tiene prioridad. Guardar no verifica conexión.

/attach "/ruta/archivo.pdf" añade un adjunto;/detach vacía. Rutas explícitas en peticiones también son candidatas, sin autorizar carpetas superiores. PDF aporta texto e imágenes de página; requiere visión. --text es solo texto; --pages 2-4 selecciona páginas, sin fingir lectura de escaneos.
Límites:4archivos,25 MiB/original,12páginas/imágenes,120.000bytes UTF-8 de texto,6 MiB de imágenes con lado máximo1.600px. Excesos, cifrado o animación requieren otra selección, sin truncado silencioso. Adjuntos aprobados y hashes quedan en.verantyx/attachment-inputs. Harnesses externos arbitrarios aún no negocian medios.

//es charla temporal sin contexto de proyecto/perfil, herramientas ni registros de trabajo, aprendizaje, habilidades o historial de entrada. Turnos recientes permanecen en RAM hasta una petición normal o/close. Los registros temporales se eliminan tras llamar; esto no garantiza ausencia de registros del proveedor, sistema o terminal.

La primera vez se recomiendan140columnas×24filas sin bloquear. Enter inicia práctica simulada; Esc omite. No llama a IA ni escribe notas reales; solo recuerda que se ofreció. /tutorial repite y/done termina. Algunas etiquetas heredadas no están traducidas.


## Continuous conversation and change review

[English / 日本語 / 简体中文 / 한국어 / Español: conversation, queue, diffs and Owner focus](conversation-and-change-review.md)

Candidate-edit approvals appear inside the Agent composer without taking focus from Owner. Empty Enter continues to cycle inputs. Once, workspace and permanent candidate-edit grants are separate from source adoption, deletion, shell, publication and external-harness permissions. Saved grants can be revoked.


[Live insights, independent Cleanrooms, context and model tuning / 実装中の理解・セッション・文脈・モデル設定](live-learning-and-sessions.md)
