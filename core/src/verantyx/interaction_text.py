"""Localized interaction help. Presentation never grants execution authority."""
from contextlib import contextmanager
from contextvars import ContextVar
from .i18n import environment_locale

LANG = ContextVar("cleanroom_interaction_language", default=None)
LOCALES = ("en", "ja", "zh-Hans", "ko", "es")


@contextmanager
def language(configuration):
    token = LANG.set(configuration)
    try:
        yield
    finally:
        LANG.reset(token)


def locale():
    value = LANG.get()
    return value.get("ui", {}).get("locale", "en") if isinstance(value, dict) else environment_locale()


TEXT = {
    "editing": (
        "Enter: send | Empty Enter: switch pane | Shift+Enter: newline when supported; Alt+Enter or Ctrl+J also work | Up/Down: session input history (first/last line). Settings and // chats are excluded.",
        "Enter: 送信 | 空欄Enter: 入力欄切替 | Shift+Enter: 対応端末で改行。Alt+EnterまたはCtrl+Jでも改行 | 上下キー: 最初・最後の行でセッション内の入力履歴。設定と//対話は含めません。",
        "Enter：发送 | 空白Enter：切换栏 | Shift+Enter：受支持终端换行，也可Alt+Enter或Ctrl+J | 上下键：首末行浏览本次输入历史，不含设置及//对话。",
        "Enter: 전송 | 빈 Enter: 입력창 전환 | Shift+Enter: 지원 터미널에서 줄바꿈. Alt+Enter 또는 Ctrl+J도 가능 | 위/아래: 첫/마지막 줄에서 세션 입력 기록. 설정과 //대화 제외.",
        "Enter: enviar | Enter vacío: cambiar panel | Shift+Enter: nueva línea si el terminal lo admite; también Alt+Enter o Ctrl+J | Arriba/abajo: historial en primera/última línea, sin ajustes ni charlas //."),

    "answer": ("MODEL ANSWER", "モデルの回答", "模型回答", "모델 답변", "RESPUESTA DEL MODELO"),
    "activity": ("SYSTEM / activity, not the answer", "システム / 操作通知・回答とは別", "系统 / 操作通知，非回答", "시스템 / 답변과 별도의 알림", "SISTEMA / actividad, no respuesta"),
    "settings": ("SETTINGS / not conversation memory", "設定 / 会話の記憶には保存しません", "设置 / 不保存为对话记忆", "설정 / 대화 기억에 저장하지 않음", "AJUSTES / fuera de la memoria de conversación"),
    "active": ("INPUT HERE", "入力先", "当前输入", "현재 입력", "ENTRADA ACTIVA"),
    "back": ("Back / keep unchanged", "戻る / 変更しない", "返回 / 不更改", "뒤로 / 변경하지 않음", "Volver / no cambiar"),
    "keys": ("Up/Down: choose | Enter: select | Esc: back", "上下キー: 選択 | Enter: 決定 | Esc: 戻る", "上下键：选择 | Enter：确定 | Esc：返回", "위/아래: 선택 | Enter: 확인 | Esc: 뒤로", "Arriba/abajo: elegir | Enter: confirmar | Esc: volver"),
    "setting_input": ("Arrows + Enter choose. Or /value answers this setting. Text without / returns to work.",
                      "矢印とEnterで選択。/値 でも設定に回答できます。/なしの文章で通常の仕事へ戻ります。",
                      "方向键和Enter选择，或用 /值 回答设置。不带 / 的文字返回工作。",
                      "화살표와 Enter로 선택하거나 /값으로 설정합니다. / 없는 문장은 일반 작업으로 돌아갑니다.",
                      "Flechas y Enter, o /valor para este ajuste. Texto sin / vuelve al trabajo."),
    "empty": ("Your model's answer appears here. Ask below; /help shows the controls.",
              "モデルの回答をここに表示します。左下から依頼できます。/helpで操作案内。",
              "模型回答显示在这里。在下方提出请求；/help 查看操作。",
              "모델 답변이 여기에 표시됩니다. 아래에서 요청하세요. /help로 사용법을 봅니다.",
              "La respuesta aparecerá aquí. Escribe abajo; /help muestra los controles."),
    "footer": ("Empty Enter: Agent > Memo > Search | arrows + Tab: reference | /help | /model",
               "空欄Enter: Agent > メモ > 検索 | 矢印+Tab: 参照 | /help | /model",
               "空白Enter：Agent > 笔记 > 搜索 | 方向键+Tab：引用 | /help | /model",
               "빈 Enter: Agent > 메모 > 검색 | 화살표+Tab: 참조 | /help | /model",
               "Enter vacío: Agent > Nota > Buscar | flechas+Tab: referencia | /help | /model"),
    "model": ("Configured model", "設定中のモデル", "已配置模型", "설정된 모델", "Modelo configurado"),
    "unconfigured": ("Codex / CLI default (not a resolved model ID)", "Codex / CLI既定（実モデルIDは未確定）",
                     "Codex / CLI默认（具体模型ID未确定）", "Codex / CLI 기본값(실제 모델 ID 미확정)",
                     "Codex / predeterminado del CLI (ID concreto sin resolver)"),
    "private": ("TEMPORARY CHAT / no Cleanroom work, journal, skill or learning memory. Provider retention still applies. No tools.",
                "一時対話 / Cleanroomの仕事・日記・スキル・学習記憶には残しません。接続先の保存方針は別です。ツール操作なし。",
                "临时对话 / 不进入Cleanroom工作、日记、技能或学习记忆。提供方仍有自己的保存政策。不执行工具。",
                "임시 대화 / Cleanroom 작업·일기·스킬·학습 기억에 남기지 않습니다. 제공자의 보관 정책은 별도입니다. 도구 실행 없음.",
                "CHARLA TEMPORAL / sin memoria de trabajo, diario, habilidades o aprendizaje de Cleanroom. Rige la retención del proveedor. Sin herramientas."),
    "send_private": ("Send this temporary message to the configured AI?", "この一時メッセージを設定中のAIへ送りますか？",
                     "将此临时消息发送到已配置AI？", "이 임시 메시지를 설정된 AI에 보낼까요?",
                     "¿Enviar este mensaje temporal al modelo configurado?"),
    "send": ("Send this scope and start", "この送信範囲で開始", "发送此范围并开始", "이 범위를 전송하고 시작", "Enviar este alcance y comenzar"),
    "attachments": ("ATTACHMENTS / these files only; no parent-directory access",
                    "添付 / 選んだファイルのみ。親フォルダへの権限は追加しません",
                    "附件 / 仅所选文件，不授权父文件夹", "첨부 / 선택한 파일만, 상위 폴더 권한은 추가하지 않음",
                    "ADJUNTOS / solo estos archivos; sin acceso a la carpeta superior"),
    "attachment_help": ("Use /attach \"/path/file.pdf\". Optional: --text or --pages 1-3. /detach clears queued files. Image input needs a vision-capable model.",
                        "/attach \"/path/file.pdf\" で添付。--textで本文のみ、--pages 1-3でページ指定。/detachで解除。画像には視覚対応モデルが必要です。",
                        "用 /attach \"/path/file.pdf\" 添加附件。--text 只读文本，--pages 1-3 指定页。/detach 清空。图片需视觉模型。",
                        "/attach \"/path/file.pdf\"로 첨부합니다. --text는 본문만, --pages 1-3은 페이지 선택. /detach로 해제. 이미지에는 비전 모델이 필요합니다.",
                        "Usa /attach \"/ruta/archivo.pdf\". --text: solo texto; --pages 1-3: páginas. /detach vacía la selección. Las imágenes requieren visión."),
    "size": ("For Agent and Owner side by side, widen the terminal to about 140 columns and 24 rows. Smaller windows use stacked panes or tabs. Enter continues at any size; Esc skips.",
             "AgentとOwnerを横に並べるには、端末を目安140桁・24行以上へ広げてください。小さい場合は縦並び・タブ表示です。どのサイズでもEnterで続行、Escでスキップできます。",
             "Agent与Owner并排显示建议至少140列、24行。较小窗口使用上下或标签布局。任意尺寸均可Enter继续，Esc跳过。",
             "Agent와 Owner를 나란히 보려면 약 140열·24행으로 넓히세요. 작은 창은 위아래 또는 탭으로 표시됩니다. 크기와 무관하게 Enter로 계속, Esc로 건너뜁니다.",
             "Para ver Agent y Owner lado a lado, amplía a unas 140 columnas y 24 filas. En ventanas pequeñas se apilan o usan pestañas. Enter continúa a cualquier tamaño; Esc omite."),
    "demo": ("PRACTICE / simulated, no AI call and no notebook writes",
             "操作練習 / 擬似画面・AI呼び出しなし・ノートへの保存なし",
             "操作练习 / 模拟画面，无AI调用，不保存笔记", "조작 연습 / 모의 화면·AI 호출 없음·노트 저장 없음",
             "PRÁCTICA / simulada, sin llamadas a IA ni escritura en el cuaderno"),
    "demo_answer": ("Example answer: the task state is now saved before rendering. This is a demonstration, not an executed fix.",
                    "回答例: タスクの状態を保存してから画面を更新する構成にしました。これは操作練習であり、修正を実行した結果ではありません。",
                    "示例回答：先保存任务状态，再更新画面。这是演示，不是实际修复。",
                    "답변 예시: 작업 상태를 저장한 뒤 화면을 갱신합니다. 실제 수정이 아닌 연습입니다.",
                    "Respuesta de ejemplo: se guarda el estado antes de actualizar la vista. Es una demostración, no una corrección ejecutada."),
    "demo_owner": ("YOUR NOTEBOOK\nPurpose: keep completed tasks after restart.\nReview: where state is saved.\nEvidence: not checked in this practice.\nYou choose what to learn; no mastery score.",
                   "あなたのノート\n目的: 再起動してもタスクの完了を維持する。\n理解候補: 状態をどこに保存するか。\n証拠: この練習では未検査。\n学ぶ項目は自分で選べます。習得の点数は付けません。",
                   "你的笔记\n目的：重启后保留完成状态。\n理解候选：状态保存在哪里。\n证据：练习中未检查。\n由你选择学习项目，不评分。",
                   "나의 노트\n목적: 재시작 후에도 완료 상태 유지.\n이해 후보: 상태를 저장하는 위치.\n증거: 연습에서는 검사하지 않음.\n학습 항목은 직접 선택하며 점수를 매기지 않습니다.",
                   "TU CUADERNO\nPropósito: conservar tareas completadas tras reiniciar.\nPara revisar: dónde se guarda el estado.\nEvidencia: no comprobada en esta práctica.\nTú eliges qué aprender; sin puntuación."),
    "demo_steps": (
        "Type a practice request in Agent. Empty Enter cycles Agent > yellow Memo > green Search > Agent. A memo with text is saved only inside this practice. Search filters your practice notes. In Agent type the first letters of an Owner item, then arrows + Tab. Try /verantyx or /model: arrows show option descriptions; /value answers settings. Plain text leaves settings. //message is temporary chat. /attach queues a PDF or image before send approval. PgUp/PgDn and wheel scroll the active pane. /done or Ctrl+D ends practice.",
        "Agentで練習の依頼を書けます。空欄EnterでAgent→黄色のメモ→緑の検索→Agentと移動します。文章付きメモは練習内だけに残ります。検索は練習のノートだけを絞り込みます。AgentでOwner項目の先頭を入力し、矢印とTabで参照できます。/verantyxや/modelを試してください。矢印で説明を見て、/値でも設定に回答できます。/なしは通常の依頼へ、//文章は一時対話です。/attachはPDF・画像を送信確認の前に添付します。PgUp/PgDn・ホイールは選択中の欄をスクロール。/doneかCtrl+Dで終了。",
        "在Agent输入练习请求。空白Enter循环Agent→黄色笔记→绿色搜索→Agent。有文字的笔记仅保留在练习中。搜索仅筛选练习笔记。在Agent输入Owner项目开头，方向键和Tab引用。试试/verantyx或/model：方向键显示说明，/值回答设置。不带/返回工作，//文字是临时对话。/attach在发送确认前添加PDF或图片。PgUp/PgDn或滚轮滚动当前栏。/done或Ctrl+D结束。",
        "Agent에서 연습 요청을 입력하세요. 빈 Enter로 Agent→노란 메모→초록 검색→Agent를 순환합니다. 메모는 연습 안에서만 남고 검색은 연습 노트만 찾습니다. Agent에서 Owner 항목의 앞부분을 입력하고 화살표와 Tab으로 참조합니다. /verantyx 또는 /model을 사용해 보세요. 화살표로 설명을 보고 /값으로 설정합니다. / 없는 문장은 작업, //문장은 임시 대화입니다. /attach로 전송 승인 전에 PDF·이미지를 첨부합니다. PgUp/PgDn·휠은 현재 창을 스크롤합니다. /done 또는 Ctrl+D로 종료합니다.",
        "Escribe una petición de práctica en Agent. Enter vacío alterna Agent > Nota amarilla > Buscar verde > Agent. Las notas solo existen en esta práctica. La búsqueda filtra estas notas. En Agent escribe el inicio de un elemento Owner y usa flechas + Tab. Prueba /verantyx o /model: las flechas muestran explicaciones y /valor responde al ajuste. Sin / vuelves al trabajo; //mensaje es charla temporal. /attach añade PDF o imágenes antes de aprobar el envío. PgUp/PgDn y la rueda desplazan el panel activo. /done o Ctrl+D termina."),
    "menu_fallback": ("Interactive arrows need a terminal. Type the exact option label, or Enter to cancel.",
                      "矢印選択には端末が必要です。選択肢のラベルを入力、または空欄Enterで戻ります。",
                      "方向键需要终端。输入完整选项名称，或空白Enter取消。",
                      "화살표 선택에는 터미널이 필요합니다. 선택지 이름을 입력하거나 빈 Enter로 취소하세요.",
                      "Las flechas requieren un terminal. Escribe la etiqueta exacta o Enter para cancelar."),
}


TEXT.update({
    "conversation": [
        "Conversation",
        "会話",
        "对话",
        "대화",
        "Conversación"
    ],
    "you": [
        "You",
        "あなた",
        "你",
        "나",
        "Tú"
    ],
    "assistant": [
        "Agent",
        "Agent",
        "Agent",
        "Agent",
        "Agent"
    ],
    "working": [
        "Working",
        "作業中",
        "工作中",
        "작업 중",
        "Trabajando"
    ],
    "model_running": [
        "Waiting for the model response",
        "モデルの応答を待っています",
        "等待模型响应",
        "모델 응답 대기 중",
        "Esperando la respuesta del modelo"
    ],
    "review_wait": [
        "Change approval is waiting in Agent. Keep writing here; empty Enter cycles back when you are ready.",
        "Agentで変更の確認を待っています。ここでの作業は続けられます。準備ができたら空欄EnterでAgentへ戻れます。",
        "Agent中有更改待确认。可继续当前操作，准备好后用空白Enter循环返回。",
        "Agent에서 변경 승인을 기다립니다. 현재 작업을 계속하고 준비되면 빈 Enter로 돌아가세요.",
        "Hay un cambio pendiente en Agent. Sigue aquí; vuelve con Enter vacío cuando quieras."
    ],
    "change_title": [
        "Review candidate change",
        "候補の変更を確認",
        "确认候选更改",
        "후보 변경 확인",
        "Revisar cambio de candidato"
    ],
    "allow_once": [
        "Allow this change",
        "この変更だけ許可",
        "仅允许此更改",
        "이 변경만 허용",
        "Permitir este cambio"
    ],
    "bypass_run": [
        "Skip further candidate-edit approvals for this task",
        "この作業中の候補編集は確認を省略",
        "本任务后续候选编辑不再确认",
        "이 작업의 이후 후보 편집 확인 생략",
        "Omitir confirmaciones de edición de candidatos en esta tarea"
    ],
    "deny_change": [
        "Do not apply this change",
        "この変更を行わない",
        "不执行此更改",
        "이 변경 거부",
        "No aplicar este cambio"
    ],
    "allow_detail": [
        "Write exactly the displayed candidate version. Source adoption, deletion, commands and publication stay separately controlled.",
        "表示した版の候補だけを書き込みます。本体採用・削除・コマンド実行・公開の許可は別です。",
        "只写入显示的候选版本。采用到源项目、删除、命令和发布仍单独授权。",
        "표시한 후보 버전만 씁니다. 본체 적용·삭제·명령·공개 권한은 별도입니다.",
        "Escribe solo la versión mostrada. Aplicación al original, eliminación, comandos y publicación requieren otros permisos."
    ],
    "bypass_detail": [
        "Only this running task's built-in candidate writes. Ends with this task; not a global bypass or an external-harness permission. You can restore prompts with /approvals.",
        "今の作業で内蔵ツールが候補へ書く変更だけが対象です。作業終了で解除され、全権限や外部ハーネスには及びません。/approvalsで確認を戻せます。",
        "仅当前任务内置工具的候选写入，任务结束即失效。不是全局或外部运行器授权。/approvals可恢复确认。",
        "현재 작업의 내장 후보 쓰기만 대상입니다. 작업 종료 시 해제되며 외부 하네스 권한이 아닙니다. /approvals로 확인을 복구합니다.",
        "Solo escrituras de candidatos internas de esta tarea; caduca al terminar. No autoriza un arnés externo. /approvals restaura las confirmaciones."
    ],
    "deny_detail": [
        "Keep the candidate unchanged for this operation. The agent receives a refusal and may propose an alternative.",
        "この操作では候補を変更せず、Agentへ拒否を返します。Agentは代案を提案できます。",
        "本次不改变候选，向Agent返回拒绝，可继续提出替代方案。",
        "이 작업의 후보 변경을 막고 Agent에 거부를 전달합니다. 대안을 제안할 수 있습니다.",
        "No cambia el candidato; el agente recibe el rechazo y puede proponer otra opción."
    ],
    "candidate_only": [
        "Candidate files only; not adoption into the source project.",
        "候補ファイルだけの変更です。本体への採用ではありません。",
        "只改候选文件，不应用到源项目。",
        "후보 파일만 변경하며 본체에 적용하지 않습니다.",
        "Solo candidatos; no se aplican al proyecto original."
    ],
    "base_unknown": [
        "Original content was not read: this is proposed content, not a verified comparison with the source file.",
        "元ファイルは未読です。これは提案内容であり、元ファイルとの検証済みの差分ではありません。",
        "未读取原文件：以下为提议内容，不是与原文件核实后的差异。",
        "원본을 읽지 않았습니다. 원본과 확인된 차이가 아닌 제안 내용입니다.",
        "No se leyó el original: es contenido propuesto, no una comparación verificada."
    ],
    "candidate_folders": [
        "Candidate parent folders (created in the isolated version if needed):",
        "候補の親フォルダ（隔離版の中で必要に応じて作成）:",
        "候选父文件夹（在隔离版本内按需创建）：",
        "후보 상위 폴더(격리 버전 안에 필요 시 생성):",
        "Carpetas padre del candidato (creadas en la versión aislada si hace falta):"
    ],
    "binary_diff": [
        "Binary content: compare byte counts and SHA-256 below; no text diff is available.",
        "バイナリです。下記のバイト数・SHA-256で変更対象を示します。テキスト差分はありません。",
        "二进制内容：以字节数和SHA-256标识，无文本差异。",
        "바이너리입니다. 바이트 수·SHA-256으로 구분하며 텍스트 차이는 없습니다.",
        "Contenido binario: se muestran tamaño y SHA-256; sin diff de texto."
    ],
    "no_changes": [
        "No content difference.",
        "内容の差分はありません。",
        "内容无差异。",
        "내용 차이가 없습니다.",
        "Sin diferencias de contenido."
    ],
    "queue_choice": [
        "When should this instruction be used?",
        "この指示をいつ使いますか？",
        "何时使用此指示？",
        "이 지시를 언제 사용할까요?",
        "¿Cuándo usar esta instrucción?"
    ],
    "queue_later": [
        "Queue after the current task",
        "現在の作業の後に予約",
        "当前任务后排队执行",
        "현재 작업 다음에 예약",
        "Poner en cola después de esta tarea"
    ],
    "steer_now": [
        "Send to the current task at its next model step",
        "現在の作業の次のモデル呼び出しで反映",
        "在当前任务的下一次模型调用传入",
        "현재 작업의 다음 모델 호출에 전달",
        "Enviar al siguiente paso del modelo en esta tarea"
    ],
    "queue_detail": [
        "Run sequentially in this open CLI, after a successful task. Not a timed or persistent schedule. File/send approvals still apply; failures or owner decisions pause the queue.",
        "このCLIを開いている間、作業成功後に順番に実行します。時刻指定・永続予約ではありません。送信・変更の確認は維持し、失敗や判断待ちでは予約を止めます。",
        "仅在本CLI打开时于任务成功后顺序运行，不是定时或持久计划。仍需发送与更改授权，失败或待决策时暂停。",
        "이 CLI가 열린 동안 성공 후 순차 실행합니다. 시간 지정·영구 예약이 아닙니다. 전송·변경 승인은 유지하며 실패나 판단 대기 시 큐를 멈춥니다.",
        "Ejecución secuencial en esta CLI abierta tras el éxito. No es programación persistente ni por hora. Se mantienen permisos; errores o decisiones pendientes pausan la cola."
    ],
    "steer_detail": [
        "Does not interrupt a running model or tool. Added as your instruction before the next model call, within existing permissions. If that boundary has passed, keep it queued instead.",
        "実行中のモデルやツールは中断しません。次のモデル呼び出し前にあなたの指示として渡し、既存の権限内で扱います。間に合わなければ予約へ残します。",
        "不打断正在运行的模型或工具；下次调用前作为你的指示传入，不扩大权限。若错过边界则保留为队列。",
        "실행 중 모델·도구를 중단하지 않습니다. 다음 호출 전에 내 지시로 전달하며 권한은 늘지 않습니다. 늦으면 큐에 남깁니다.",
        "No interrumpe el modelo ni las herramientas. Añade tu instrucción al siguiente paso sin ampliar permisos; si ya terminó, queda en cola."
    ],
    "queued": [
        "Queued in this CLI",
        "このCLI内で予約中",
        "已在本CLI排队",
        "이 CLI에 예약됨",
        "En cola en esta CLI"
    ],
    "pending_instruction": [
        "Waiting for the next model step; not yet sent",
        "次のモデル呼び出し待ち・まだ未送信",
        "等待下一次模型调用，尚未发送",
        "다음 모델 단계 대기·미전송",
        "Esperando el siguiente paso; aún no enviada"
    ],
    "recorded_instruction": [
        "Recorded as your instruction",
        "あなたの追加指示として記録済み",
        "已记为你的补充指示",
        "추가 지시로 기록됨",
        "Registrada como instrucción tuya"
    ],
    "queue_paused": [
        "Queue paused. Use /queue to inspect, resume or remove entries. No automatic retry.",
        "予約を保留しています。/queueで確認・再開・削除できます。自動で再試行しません。",
        "队列已暂停。/queue查看、继续或移除，不自动重试。",
        "예약 대기 중입니다. /queue로 확인·재개·삭제하세요. 자동 재시도하지 않습니다.",
        "Cola pausada. /queue permite revisar, reanudar o quitar. Sin reintentos automáticos."
    ],
    "queue_empty": [
        "No queued requests.",
        "予約された依頼はありません。",
        "没有排队请求。",
        "예약된 요청이 없습니다.",
        "No hay solicitudes en cola."
    ],
    "queue_resume": [
        "Run the next queued request",
        "次の予約を実行",
        "运行下一项",
        "다음 예약 실행",
        "Ejecutar la siguiente"
    ],
    "queue_clear": [
        "Remove all queued requests",
        "予約をすべて取り消す",
        "取消所有排队请求",
        "모든 예약 취소",
        "Quitar todas las solicitudes"
    ],
    "queue_close": [
        "Queued drafts exist only in this CLI. Close and discard them?",
        "予約の下書きはこのCLI内だけにあります。破棄して閉じますか？",
        "队列草稿仅在本CLI中，丢弃并关闭吗？",
        "예약 초안은 이 CLI에만 있습니다. 버리고 닫을까요?",
        "Los borradores en cola solo existen en esta CLI. ¿Descartar y cerrar?"
    ],
    "queue_discard": [
        "Discard queued drafts and close",
        "予約の下書きを破棄して閉じる",
        "丢弃队列并关闭",
        "예약 초안 버리고 닫기",
        "Descartar cola y cerrar"
    ],
    "queue_full": [
        "The queue is full (12 requests), or this draft is too large. Your input is retained.",
        "予約は12件まで、または入力が上限を超えています。下書きは残しています。",
        "队列最多12项或输入过大，已保留草稿。",
        "예약 한도 12건 또는 입력 크기를 초과했습니다. 초안을 유지합니다.",
        "Cola llena (12 solicitudes) o borrador demasiado grande. Se conserva la entrada."
    ],
    "queue_fallback": [
        "The current task no longer accepts instructions. Kept as a paused queued request, not silently sent.",
        "現在の作業では追加指示を受け取れません。未送信のまま予約へ保留しました。",
        "当前任务不再接收指示，已暂停保留在队列中，未静默发送。",
        "현재 작업이 추가 지시를 받지 않습니다. 미전송 상태로 큐에 보류했습니다.",
        "La tarea ya no acepta instrucciones. Se conserva en cola pausada, sin envío silencioso."
    ],
    "chat_limit": [
        "Older conversation pages are outside this session view. Saved work remains in History.",
        "古い会話はこのセッション表示の範囲外です。保存済みの仕事はHistoryで開けます。",
        "旧对话超出本次显示范围，已保存工作仍可在History打开。",
        "이전 대화는 현재 표시 범위 밖입니다. 저장된 작업은 History에서 볼 수 있습니다.",
        "Conversaciones antiguas fuera de esta vista; el trabajo guardado sigue en History."
    ],
    "owner_title": [
        "Owner / Your notebook",
        "Owner / 自分のノート",
        "Owner / 我的笔记",
        "Owner / 나의 노트",
        "Owner / Tu cuaderno"
    ],
    "owner_purpose": [
        "Your request and purpose",
        "あなたの依頼と目的",
        "你的请求与目标",
        "내 요청과 목적",
        "Tu petición y propósito"
    ],
    "owner_decisions": [
        "Your recorded decisions",
        "あなたが残した判断",
        "已记录的个人决定",
        "내가 남긴 결정",
        "Tus decisiones registradas"
    ],
    "owner_proposals": [
        "Ideas to keep / AI proposals, not mastery",
        "持ち帰る候補 / AIの提案・習得の認定ではありません",
        "可保留的想法 / AI建议，不代表掌握",
        "남길 후보 / AI 제안·습득 인증 아님",
        "Ideas para conservar / propuestas de IA, no dominio"
    ],
    "owner_facts": [
        "Recorded work / bounded observations",
        "作業の記録 / 観測した範囲だけ",
        "工作记录 / 限于已观察范围",
        "작업 기록 / 관측 범위만",
        "Trabajo registrado / observaciones limitadas"
    ],
    "owner_unknown": [
        "Still open / assumptions and unknowns",
        "まだ分からないこと・AIの仮定",
        "待确认 / 假设与未知",
        "미확인 사항·AI 가정",
        "Pendiente / supuestos e incógnitas"
    ],
    "owner_notes": [
        "Your notes / not automatically shared",
        "自分のメモ / 自動送信しません",
        "个人笔记 / 不自动发送",
        "내 메모 / 자동 전송 없음",
        "Tus notas / no se comparten automáticamente"
    ],
    "owner_index": [
        "References / type the first letters in Agent",
        "参照 / Agentで先頭の文字から選択",
        "引用 / 在Agent输入开头文字",
        "참조 / Agent에서 앞 글자로 선택",
        "Referencias / escribe las primeras letras en Agent"
    ],
    "owner_question": [
        "Your choice is needed",
        "あなたの判断を待っています",
        "等待你的决定",
        "내 판단 대기 중",
        "Se necesita tu decisión"
    ],
    "owner_empty": [
        "Your requests and local notes will appear here.",
        "依頼や自分用メモがここに残ります。",
        "请求与本地笔记会显示在这里。",
        "요청과 개인 메모가 여기에 남습니다.",
        "Tus peticiones y notas locales aparecerán aquí."
    ],
    "owner_guard": [
        "AI proposals, execution receipts and your understanding are separate. Reading or skipping is not a mastery assessment.",
        "AIの提案・実行記録・本人の理解は別です。読むことやスキップで習得を判定しません。",
        "AI建议、执行凭据和个人理解各自独立，不以阅读或跳过认定掌握。",
        "AI 제안·실행 기록·본인 이해는 별개입니다. 읽기나 건너뛰기로 습득을 판단하지 않습니다.",
        "Propuestas, recibos de ejecución y comprensión son distintos. Leer u omitir no acredita dominio."
    ],
    "owner_counts": [
        "Reads: {reads} / candidate writes: {writes} / checks run: {checks} / refused: {refused}",
        "読み取り: {reads} / 候補書き込み: {writes} / 実行した検査: {checks} / 拒否: {refused}",
        "读取：{reads} / 候选写入：{writes} / 检查执行：{checks} / 拒绝：{refused}",
        "읽기: {reads} / 후보 쓰기: {writes} / 실행 검사: {checks} / 거부: {refused}",
        "Lecturas: {reads} / escrituras candidatas: {writes} / comprobaciones: {checks} / rechazadas: {refused}"
    ],
    "owner_no_audit": [
        "Host receipts describe recorded candidate operations, not a whole-project or external-process audit.",
        "ホストの記録は候補への操作を表します。本体全体や外部プロセスの監査ではありません。",
        "主机记录仅描述候选操作，并非对整个项目或外部进程的审计。",
        "호스트 기록은 후보 작업만 나타내며 전체 프로젝트·외부 프로세스 감사가 아닙니다.",
        "Los recibos describen operaciones candidatas, no una auditoría del proyecto ni de procesos externos."
    ],
    "owner_personal": [
        "My progress / at my own pace",
        "自分の歩み / 自分のペースで",
        "我的积累 / 按自己的节奏",
        "나의 성장 / 내 속도로",
        "Mi progreso / a mi ritmo"
    ],
    "personal_counts": [
        "Journal: {journal} / revisit later: {later} / AI procedures: {skills}. F2 opens My profile and My skills.",
        "日記: {journal} / 次の機会に: {later} / AI手順: {skills}。F2からMy profile・My skillsを開けます。",
        "日记：{journal} / 留待下次：{later} / AI流程：{skills}。F2打开个人档案与技能。",
        "일지: {journal} / 다음 기회: {later} / AI 절차: {skills}. F2로 프로필·스킬을 엽니다.",
        "Diario: {journal} / para después: {later} / procedimientos IA: {skills}. F2 abre My profile y My skills."
    ],
    "approvals_restored": [
        "Candidate-edit prompts restored for this task. External tools and adoption keep their own permissions.",
        "この作業の候補編集の確認を戻しました。外部ツール・本体採用の権限は別です。",
        "已恢复本任务候选编辑确认，外部工具和采用权限独立。",
        "이 작업의 후보 편집 확인을 복구했습니다. 외부 도구·본체 적용 권한은 별도입니다.",
        "Confirmaciones de candidatos restauradas. Herramientas externas y adopción mantienen sus permisos."
    ],
    "workflow_guide": [
        "During work, Enter on a new request offers Queue or Next model step. /queue manages session-only requests. Candidate changes show a diff beside the Agent composer: allow once, decline, or skip further candidate-edit prompts for this task. Owner memo/search keeps focus while approval waits; empty Enter cycles back to Agent. /approvals restores edit prompts. None of these choices grants deletion, publication, external-tool or source-adoption permission.",
        "作業中に依頼を入力してEnterを押すと、予約か次のモデル呼び出しへの反映を選べます。/queueはこのCLI内の予約を管理します。候補変更はAgent入力欄のそばに差分と、今回だけ許可・拒否・この作業中の候補編集確認を省略する選択肢を表示します。確認待ちでもOwnerのメモ・検索は続けられ、空欄EnterでAgentへ戻れます。/approvalsで編集確認を戻せます。削除・公開・外部ツール・本体採用の権限は追加しません。",
        "工作中输入请求并Enter可选择排队或传入下一次模型调用。/queue管理本CLI内的队列。候选更改在Agent输入栏旁显示差异，可允许一次、拒绝或省略本任务后续候选编辑确认。等待批准时Owner仍可记笔记与搜索，用空白Enter返回Agent。/approvals恢复确认。不增加删除、发布、外部工具或采用到源项目的权限。",
        "작업 중 새 요청에 Enter를 누르면 예약 또는 다음 모델 단계 전달을 고릅니다. /queue는 이 CLI의 예약을 관리합니다. 후보 변경은 Agent 입력란 곁에 차이를 보여 주고 한 번 허용·거부·이 작업 후보 편집 확인 생략을 선택합니다. Owner 메모·검색은 계속할 수 있고 빈 Enter로 Agent에 돌아옵니다. /approvals로 확인을 복구합니다. 삭제·공개·외부 도구·본체 적용 권한은 늘지 않습니다.",
        "Durante el trabajo, Enter ofrece Cola o Siguiente paso del modelo. /queue gestiona solicitudes de esta sesión. Los candidatos muestran un diff junto al compositor Agent: permitir una vez, rechazar u omitir confirmaciones de candidatos de esta tarea. Owner conserva el foco; Enter vacío vuelve a Agent. /approvals restaura las confirmaciones. No se conceden permisos de eliminación, publicación, herramientas externas ni aplicación al original."
    ]
})


TEXT.update({
    "memo_input": [
        "MEMO / Enter saves locally. Empty Enter opens Search.",
        "メモ / Enterでローカル保存。空欄Enterで検索へ。",
        "笔记 / Enter本地保存，空白Enter转到搜索。",
        "메모 / Enter로 로컬 저장, 빈 Enter로 검색.",
        "NOTA / Enter guarda localmente; Enter vacío abre Buscar."
    ],
    "search_input": [
        "SEARCH / Search your Owner records only. Empty Enter returns to Agent.",
        "検索 / Ownerの記録だけを検索。空欄EnterでAgentへ。",
        "搜索 / 只搜索Owner记录，空白Enter返回Agent。",
        "검색 / Owner 기록만 검색. 빈 Enter로 Agent 이동.",
        "BUSCAR / Solo registros Owner; Enter vacío vuelve a Agent."
    ],
    "agent_input": [
        "Ask normally. Start an Owner item name, then arrows + Tab to reference it.",
        "普通に依頼できます。Owner項目の先頭を入力し、矢印とTabで参照します。",
        "直接提出请求。输入Owner项目开头，用方向键与Tab引用。",
        "자연스럽게 요청하세요. Owner 항목 앞부분을 입력하고 화살표·Tab으로 참조합니다.",
        "Pide lo que necesitas. Escribe el inicio de un elemento Owner y usa flechas + Tab para citarlo."
    ],
    "busy_input": [
        "Enter on a new request: queue it or pass it to the next model step. Empty Enter: Owner memo.",
        "新しい依頼を書いてEnter: 予約か次のモデル呼び出しへの反映を選択。空欄Enter: Ownerメモへ。",
        "输入新请求后Enter：排队或传到下次模型调用。空白Enter：Owner笔记。",
        "새 요청 후 Enter: 예약 또는 다음 모델 단계에 전달. 빈 Enter: Owner 메모.",
        "Enter en una nueva petición: poner en cola o pasar al siguiente paso del modelo. Enter vacío: nota Owner."
    ],
    "saved_review": [
        "Stored change receipt / full interactive diff is not re-created from a newer source file.",
        "保存済みの変更記録 / 元ファイルの新しい版から以前の差分を捏造しません。",
        "已保存更改凭据 / 不从更新后的原文件伪造历史差异。",
        "저장된 변경 기록 / 더 최신 원본으로 과거 차이를 재구성하지 않습니다.",
        "Recibo guardado / no se reconstruye el diff histórico con un original posterior."
    ],
    "system_candidates": [
        "For next time / reusable proposals",
        "次回へ残すもの / 再利用の候補",
        "留待下次 / 可复用建议",
        "다음에 남길 것 / 재사용 후보",
        "Para la próxima / propuestas reutilizables"
    ],
    "human_words": [
        "Your recorded words / sharing follows your choices",
        "自分が残した言葉 / 共有は本人の選択に従います",
        "已记录的话 / 按你的选择共享",
        "내가 남긴 말 / 공유는 내 선택에 따름",
        "Tus palabras registradas / se comparten según tu elección"
    ],
    "chosen_role": [
        "How you chose to stay involved",
        "自分が選んだ関わり方",
        "你选择的参与方式",
        "내가 선택한 참여 방식",
        "Cómo elegiste participar"
    ]
})


TEXT["workflow_guide"] = [
  "During work, a new request offers Queue or Next model step. /queue manages requests in this open CLI. Candidate diffs appear by Agent input: allow once, allow in this workspace, allow permanently, or deny. Saved grants cover isolated candidate edits only and /approvals revokes them. Owner keeps focus; empty Enter returns to Agent for arrows and Enter. Deletion, publication, shell, external tools and adoption are separate permissions.",
  "作業中の追加依頼は予約か次のモデル呼び出しへの反映を選べます。/queueでこのCLI内の予約を管理します。Agent入力欄の候補差分では一度だけ許可・このワークスペース内で許可・永久に許可・拒否を選びます。保存した許可は隔離候補の編集だけで、/approvalsで取り消せます。Ownerのカーソルは奪いません。空欄EnterでAgentへ戻り、矢印とEnterで選びます。削除・公開・シェル・外部ツール・本体採用の権限は別です。",
  "工作中的新请求可排队或传给下次模型调用。/queue管理本CLI队列。Agent输入旁显示候选差异，可允许一次、在工作区允许、永久允许或拒绝。保存的授权仅限隔离候选编辑，/approvals可撤销。Owner保留焦点，空白Enter返回Agent后用方向键与Enter选择。删除、发布、命令、外部工具和采用另行授权。",
  "작업 중 새 요청은 예약 또는 다음 모델 호출 전달을 선택합니다. /queue로 이 CLI의 예약을 관리합니다. Agent 후보 차이에서 한 번 허용, 이 작업 공간 허용, 항상 허용, 거부를 고릅니다. 저장한 허용은 격리 후보 편집만 대상이며 /approvals로 취소합니다. Owner 포커스는 유지되고 빈 Enter로 Agent에 돌아와 방향키와 Enter로 선택합니다. 삭제, 공개, 셸, 외부 도구, 본체 적용은 별도 권한입니다.",
  "Una nueva petición durante el trabajo ofrece Cola o Siguiente paso. /queue gestiona esta CLI. Junto a Agent aparecen diffs: permitir una vez, en este espacio, permanentemente o rechazar. Los permisos guardados solo cubren candidatos aislados y /approvals los revoca. Owner conserva el foco; Enter vacío vuelve a Agent, flechas y Enter eligen. Eliminar, publicar, shell, herramientas externas y adoptar requieren permisos separados."
]

def tr(key, lang=None, **values):
    lang = lang or locale()
    index = LOCALES.index(lang) if lang in LOCALES else 0
    return TEXT[key][index].format(**values)


def help_text(lang=None):
    from .session_text import t as session_text
    return "\n\n".join([
        tr("footer", lang), tr("editing", lang), tr("demo_steps", lang), tr("workflow_guide", lang),
        "/help  /commands  /verantyx  /verantyx setup models  /model\n"
        "/verantyx setup language  /verantyx setup profile  /verantyx setup pace\n"
        "/verantyx setup accounts  /verantyx setup codex  /verantyx setup claude\n"
        "/history  /scope  /details  /attach  /detach  /tutorial  /queue  /approvals  /close  /quit",
        session_text("session_commands", lang or locale()), session_text("live_help", lang or locale()),
        tr("setting_input", lang), tr("private", lang), tr("attachment_help", lang),
    ])
