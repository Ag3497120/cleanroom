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


def tr(key, lang=None, **values):
    lang = lang or locale()
    index = LOCALES.index(lang) if lang in LOCALES else 0
    return TEXT[key][index].format(**values)


def help_text(lang=None):
    return "\n\n".join([
        tr("footer", lang), tr("editing", lang), tr("demo_steps", lang),
        "/help  /commands  /verantyx  /verantyx setup models  /model\n"
        "/verantyx setup language  /verantyx setup profile  /verantyx setup pace\n"
        "/verantyx setup accounts  /verantyx setup codex  /verantyx setup claude\n"
        "/history  /scope  /details  /attach  /detach  /tutorial  /close  /quit",
        tr("setting_input", lang), tr("private", lang), tr("attachment_help", lang),
    ])
