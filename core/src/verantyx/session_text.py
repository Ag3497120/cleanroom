"""Localized session, permission and context controls."""

LANGS = ("en", "ja", "zh-Hans", "ko", "es")
TEXT = {
  "allow_once": [
    "Allow once",
    "一度だけ許可",
    "仅允许一次",
    "한 번만 허용",
    "Permitir una vez"
  ],
  "allow_workspace": [
    "Allow in this workspace",
    "このワークスペース内で許可",
    "在此工作区允许",
    "이 워크스페이스에서 허용",
    "Permitir en este espacio"
  ],
  "allow_permanent": [
    "Allow permanently",
    "永久に許可",
    "永久允许",
    "항상 허용",
    "Permitir permanentemente"
  ],
  "deny": [
    "Deny",
    "拒否",
    "拒绝",
    "거부",
    "Rechazar"
  ],
  "once_detail": [
    "Apply this exact candidate change only. Later changes ask again.",
    "今回表示した候補の変更だけを許可します。次の変更は再確認します。",
    "仅允许本次展示的候选修改。之后仍会询问。",
    "표시된 후보 변경만 허용합니다. 다음 변경은 다시 확인합니다.",
    "Solo este cambio exacto del candidato. Los siguientes requieren confirmación."
  ],
  "workspace_detail": [
    "Allow candidate edits in this workspace until revoked. Does not authorize adoption, shell, deletion or publication.",
    "取り消すまで、このワークスペースの候補編集を許可します。本体採用・シェル・削除・公開は別の許可です。",
    "允许此工作区的候选编辑，直至撤销。不授权采纳、命令行、删除或发布。",
    "취소할 때까지 이 공간의 후보 편집을 허용합니다. 적용, 셸, 삭제, 공개 권한은 별개입니다.",
    "Permite editar candidatos aquí hasta revocar. No autoriza adopción, shell, borrado ni publicación."
  ],
  "permanent_detail": [
    "Allow future candidate edits across workspaces on this computer until revoked in Permissions. Workspace reading, adoption, shell, deletion and publication still need their own permission.",
    "このPCの各ワークスペースで今後の候補編集を許可します。権限設定から取り消せます。閲覧・本体採用・シェル・削除・公開の許可は含みません。",
    "允许此电脑上所有工作区未来的候选编辑，可在权限设置撤销。阅读、采纳、命令、删除与发布仍需单独授权。",
    "이 컴퓨터의 모든 공간에서 후보 편집을 허용합니다. 권한 설정에서 취소할 수 있습니다. 읽기, 적용, 셸, 삭제, 공개는 포함하지 않습니다.",
    "Permite futuros cambios de candidatos en este equipo hasta revocar en Permisos. Lectura, adopción, shell, borrado y publicación siguen separados."
  ],
  "deny_detail": [
    "Do not apply this candidate change. Keep the draft and other recorded work.",
    "この候補変更を適用しません。下書きと既存の作業記録は残します。",
    "不应用此候选修改，保留草稿与已有记录。",
    "이 후보 변경을 적용하지 않습니다. 초안과 기존 기록은 유지합니다.",
    "No aplica este cambio. Conserva el borrador y el trabajo registrado."
  ],
  "permissions": [
    "Permissions / candidate edits",
    "権限 / 候補の編集",
    "权限 / 候选编辑",
    "권한 / 후보 편집",
    "Permisos / cambios de candidatos"
  ],
  "revoke_workspace": [
    "Revoke workspace permission",
    "ワークスペースの許可を取り消す",
    "撤销此工作区权限",
    "워크스페이스 허용 취소",
    "Revocar permiso del espacio"
  ],
  "revoke_permanent": [
    "Revoke permanent permission",
    "永久許可を取り消す",
    "撤销永久权限",
    "항상 허용 취소",
    "Revocar permiso permanente"
  ],
  "permission_revoked": [
    "Permission revoked. Unexecuted changes ask again.",
    "許可を取り消しました。未実行の変更は再確認します。",
    "已撤销权限。尚未执行的修改将再次询问。",
    "권한을 취소했습니다. 미실행 변경은 다시 확인합니다.",
    "Permiso revocado. Los cambios pendientes volverán a preguntar."
  ],
  "read_title": [
    "May Cleanroom read this workspace?",
    "このワークスペースを閲覧してよいですか？",
    "允许 Cleanroom 读取此工作区吗？",
    "이 워크스페이스를 읽어도 될까요?",
    "¿Puede Cleanroom leer este espacio?"
  ],
  "read_detail": [
    "This allows local project/configuration reading. It does not send files to AI, trust external executables, or allow writes. AI sending is reviewed separately.",
    "プロジェクトと設定のローカル閲覧を許可します。AIへの送信・外部プログラムの信頼・書き込みは許可しません。送信範囲は別に確認します。",
    "仅允许本地读取项目与配置，不授权发送给 AI、信任外部程序或写入。发送范围将单独确认。",
    "프로젝트와 설정의 로컬 읽기만 허용합니다. AI 전송, 외부 실행 파일 신뢰, 쓰기는 별도입니다.",
    "Permite leer el proyecto y su configuración localmente. No envía archivos, confía en ejecutables externos ni permite escribir."
  ],
  "read_allow": [
    "Allow reading this workspace",
    "このワークスペースの閲覧を許可",
    "允许读取此工作区",
    "이 공간 읽기 허용",
    "Permitir lectura de este espacio"
  ],
  "read_denied": [
    "Workspace not opened. No project files were read.",
    "ワークスペースは開いていません。プロジェクト内のファイルは読み取っていません。",
    "未打开工作区，未读取项目文件。",
    "공간을 열지 않았습니다. 프로젝트 파일을 읽지 않았습니다.",
    "No se abrió el espacio ni se leyeron sus archivos."
  ],
  "agent_session": [
    "Agent session",
    "Agentの会話",
    "Agent 会话",
    "Agent 대화",
    "Sesión de Agent"
  ],
  "owner_room": [
    "Owner Cleanroom",
    "OwnerのCleanroom",
    "Owner Cleanroom",
    "Owner Cleanroom",
    "Cleanroom de Owner"
  ],
  "new_agent": [
    "Start a new Agent conversation? Owner notes stay here.",
    "Agentの会話を新しくしますか？Ownerのノートはそのままです。",
    "新建 Agent 会话？Owner 笔记保持不变。",
    "Agent 대화를 새로 시작할까요? Owner 노트는 유지됩니다.",
    "¿Nueva conversación de Agent? Las notas de Owner se conservan."
  ],
  "new_room": [
    "Create a new Cleanroom? The Agent conversation stays here.",
    "新しくクリーンルームを作りますか？Agentの会話はそのままです。",
    "创建新 Cleanroom？Agent 会话保持不变。",
    "새 Cleanroom을 만들까요? Agent 대화는 유지됩니다.",
    "¿Crear un Cleanroom nuevo? La conversación de Agent se conserva."
  ],
  "confirm": [
    "Confirm",
    "承認する",
    "确认",
    "승인",
    "Confirmar"
  ],
  "cancel": [
    "Cancel / keep current",
    "拒否 / 現在のまま",
    "取消 / 保持当前",
    "취소 / 현재 유지",
    "Cancelar / mantener"
  ],
  "name_prompt": [
    "Name (unique; blank cancels)",
    "名前（重複不可・空欄で中止）",
    "名称（不可重复；留空取消）",
    "이름 (중복 불가, 빈칸은 취소)",
    "Nombre (único; vacío cancela)"
  ],
  "name_invalid": [
    "Choose a unique name of 1-80 characters, without slashes or command names.",
    "1〜80文字の重複しない名前にしてください。スラッシュやコマンド名は使えません。",
    "请选择 1-80 字符的不重复名称，不含斜线或命令名称。",
    "1~80자의 고유한 이름을 사용하세요. 슬래시와 명령 이름은 사용할 수 없습니다.",
    "Elige un nombre único de 1-80 caracteres, sin barras ni nombres de comandos."
  ],
  "room_list": [
    "Saved Cleanrooms in this workspace / type / then a name",
    "このワークスペースのCleanroom /「/」に続けて名前で選択",
    "本工作区的 Cleanroom / 输入 / 后接名称",
    "이 공간의 Cleanroom / / 다음에 이름 입력",
    "Cleanrooms del espacio / escribe / y un nombre"
  ],
  "switch_room": [
    "Switch Owner to {name}? Agent is unchanged.",
    "Ownerを「{name}」に切り替えますか？Agentは変わりません。",
    "将 Owner 切换为 {name}？Agent 不变。",
    "Owner를 {name}(으)로 전환할까요? Agent는 그대로입니다.",
    "¿Cambiar Owner a {name}? Agent no cambia."
  ],
  "switch": [
    "Switch",
    "切り替える",
    "切换",
    "전환",
    "Cambiar"
  ],
  "rename": [
    "Rename this Cleanroom",
    "このCleanroomの名前を変更",
    "重命名此 Cleanroom",
    "이 Cleanroom 이름 변경",
    "Cambiar nombre del Cleanroom"
  ],
  "busy_session": [
    "Finish or pause the current work before changing sessions. Your input is retained.",
    "セッション変更は現在の処理が終わってから行えます。入力は保持しています。",
    "请等待当前工作结束再切换会话，输入已保留。",
    "현재 작업이 끝난 후 세션을 변경하세요. 입력은 유지됩니다.",
    "Espera a que termine el trabajo antes de cambiar sesiones. Se conserva la entrada."
  ],
  "memo_archive": [
    "Memo archive / local, never sent automatically",
    "メモの全履歴 / ローカル保存・自動送信しません",
    "完整备忘历史 / 仅本地，不自动发送",
    "전체 메모 기록 / 로컬 저장, 자동 전송 없음",
    "Archivo de notas / local, sin envío automático"
  ],
  "context": [
    "Context & compaction",
    "文脈とコンテキスト圧縮",
    "上下文与压缩",
    "문맥 및 압축",
    "Contexto y compactación"
  ],
  "auto_on": [
    "Automatic summaries: on",
    "自動要約: オン",
    "自动摘要：开启",
    "자동 요약: 켜기",
    "Resúmenes automáticos: sí"
  ],
  "auto_off": [
    "Automatic summaries: off",
    "自動要約: オフ",
    "自动摘要：关闭",
    "자동 요약: 끄기",
    "Resúmenes automáticos: no"
  ],
  "auto_detail": [
    "Summarize approved work history near the input budget using the selected Work AI. Extra model calls may use your plan/API quota. Original records remain. Private memos are not added.",
    "入力予算に近づいたら、承認済みの作業履歴を選択中のAIで要約します。追加呼び出しで利用枠を消費する場合があります。原記録は残り、非公開メモは加えません。",
    "接近输入预算时，用所选 AI 总结已批准的工作历史，可能消耗额外额度。原记录保留，不加入私人备忘。",
    "입력 예산에 가까워지면 선택한 AI로 승인된 기록을 요약합니다. 추가 사용량이 발생할 수 있습니다. 원본은 보존하고 개인 메모는 넣지 않습니다.",
    "Resume el historial autorizado cerca del presupuesto con tu IA. Puede consumir cuota adicional. Conserva originales y no añade notas privadas."
  ],
  "context_window": [
    "Context window / input budget",
    "コンテキストウィンドウ / 入力予算",
    "上下文窗口 / 输入预算",
    "컨텍스트 창 / 입력 예산",
    "Ventana de contexto / presupuesto"
  ],
  "window_detail": [
    "An input budget, not a way to expand a model's real capacity. Reported maximum and currently loaded size may differ. Unknown limits are not guessed.",
    "実際のモデル容量を増やす設定ではなく入力予算です。最大容量とロード中の容量は異なることがあります。不明な値は推測しません。",
    "这是输入预算，不会扩大模型的真实容量。最大值与已加载容量可能不同，未知值不会猜测。",
    "모델 용량 자체를 늘리는 설정이 아닌 입력 예산입니다. 최대 용량과 로드된 용량은 다를 수 있으며 모르는 값은 추측하지 않습니다.",
    "Es un presupuesto, no aumenta la capacidad real. El máximo y la capacidad cargada pueden diferir; no se inventan límites."
  ],
  "discover": [
    "Read model metadata (no project files sent)",
    "モデル情報を取得（プロジェクトの内容は送信しません）",
    "获取模型信息（不发送项目文件）",
    "모델 정보 조회 (프로젝트 파일 전송 없음)",
    "Leer metadatos del modelo (sin archivos del proyecto)"
  ],
  "manual": [
    "Enter a custom value",
    "数値を入力する",
    "自定义数值",
    "직접 값 입력",
    "Introducir valor"
  ],
  "provider_default": [
    "Provider default / unknown capacity",
    "プロバイダの既定 / 容量は未確認",
    "服务默认 / 容量未确认",
    "제공자 기본값 / 용량 미확인",
    "Predeterminado / capacidad desconocida"
  ],
  "metadata_unknown": [
    "No usable capacity metadata was returned. Keep the provider default or enter a documented value.",
    "容量を確認できる情報が返りませんでした。既定値のまま使うか、仕様で確認した値を入力してください。",
    "未返回可用容量信息。保留默认值，或输入已查证的数值。",
    "확인 가능한 용량 정보가 없습니다. 기본값을 유지하거나 문서의 값을 입력하세요.",
    "No se obtuvo una capacidad verificable. Conserva el valor por defecto o introduce uno documentado."
  ],
  "effort": [
    "Reasoning effort / model-dependent",
    "推論レベル / モデルごとに対応が異なります",
    "推理级别 / 取决于模型",
    "추론 수준 / 모델별 지원",
    "Esfuerzo de razonamiento / según modelo"
  ],
  "effort_detail": [
    "Default sends no override. Lower levels favor speed; higher levels can use more time/quota. Only select a level the provider and model support; unsupported requests are reported, not silently retried.",
    "既定では上書きしません。低いレベルは速度重視、高いレベルは時間や利用枠を多く使う場合があります。対応している値だけを選んでください。非対応時に黙って別設定へ変えません。",
    "默认不覆盖。低级别偏重速度，高级别可能消耗更多时间与额度。只选择支持的级别，不支持时会报错而非静默更改。",
    "기본값은 덮어쓰지 않습니다. 낮으면 속도, 높으면 더 많은 시간과 사용량이 필요할 수 있습니다. 미지원 설정은 조용히 바꾸지 않고 알립니다.",
    "El valor por defecto no impone cambios. Niveles altos pueden consumir más tiempo/cuota. Selecciona solo opciones compatibles; no se reintenta silenciosamente con otras."
  ],
  "tune_model": [
    "Tune current model / effort and context",
    "使用モデルの調整 / 推論と文脈",
    "调整当前模型 / 推理与上下文",
    "현재 모델 조정 / 추론과 문맥",
    "Ajustar modelo / razonamiento y contexto"
  ],
  "compact_confirm": [
    "Summarize this Agent session with the selected Work AI?",
    "このAgent会話を選択中の作業AIで要約しますか？",
    "用当前工作 AI 总结此 Agent 会话？",
    "현재 작업 AI로 이 Agent 대화를 요약할까요?",
    "¿Resumir esta sesión con la IA de trabajo?"
  ],
  "compact_detail": [
    "Only recorded work from this Agent session is used. Memos and other sessions are excluded. Summary is AI reference text, not a new approval or verified fact. Original records are preserved.",
    "このAgent会話に紐づく作業記録だけを使用します。メモや別会話は除外します。要約はAIの参照情報であり承認・検証済み事実にはなりません。原記録は保持します。",
    "仅使用此 Agent 会话的工作记录，不含备忘和其他会话。摘要仅为 AI 参考，不构成授权或已验证事实。原记录保留。",
    "이 Agent 세션의 작업 기록만 사용합니다. 메모와 다른 세션은 제외합니다. 요약은 참고 정보이며 승인이나 검증 사실이 아닙니다. 원본은 보존합니다.",
    "Solo utiliza registros de esta sesión, sin notas ni otras sesiones. Es una referencia de IA, no una aprobación ni prueba. Conserva originales."
  ],
  "compact_empty": [
    "No recorded Agent work to summarize yet.",
    "要約するAgentの作業記録がまだありません。",
    "尚无可总结的 Agent 工作记录。",
    "아직 요약할 Agent 작업 기록이 없습니다.",
    "Todavía no hay trabajo registrado para resumir."
  ],
  "compact_saved": [
    "Context summary saved. Original history remains available.",
    "文脈の要約を保存しました。元の履歴も残っています。",
    "已保存上下文摘要，原始历史仍保留。",
    "문맥 요약을 저장했습니다. 원본 기록은 유지됩니다.",
    "Resumen guardado. El historial original sigue disponible."
  ],
  "compact_failed": [
    "Summary not completed. Work and original records are retained; no automatic retry.",
    "要約は完了していません。作業結果と原記録は保持し、自動再送しません。",
    "摘要未完成。工作与原记录已保留，不自动重试。",
    "요약이 완료되지 않았습니다. 작업과 원본은 유지하며 자동 재시도하지 않습니다.",
    "No se completó el resumen. Se conservan trabajo y originales; sin reintento automático."
  ],
  "saved": [
    "Saved",
    "保存しました",
    "已保存",
    "저장됨",
    "Guardado"
  ],
  "tour_start": [
    "Type verantyx to finish the tutorial and open your real workspace.",
    "verantyx と入力するとチュートリアルを終了して実際の画面を開きます。",
    "输入 verantyx 结束教程并打开真实工作区。",
    "verantyx를 입력하면 튜토리얼을 마치고 실제 공간을 엽니다.",
    "Escribe verantyx para terminar el tutorial y abrir el espacio real."
  ],
  "tour_chat": [
    "1 / Agent input below: type a request and press Enter. This is a simulation; no AI call.",
    "1 / 下のAgent入力欄: 依頼を入力してEnter。練習なのでAIは呼び出しません。",
    "1 / 下方 Agent 输入框：输入请求后按 Enter。仅模拟，不调用 AI。",
    "1 / 아래 Agent 입력창: 요청을 쓰고 Enter. 연습이며 AI는 호출하지 않습니다.",
    "1 / Campo Agent abajo: escribe una petición y pulsa Enter. Es una simulación sin IA."
  ],
  "tour_memo": [
    "2 / Empty Enter moves to Owner. Write a yellow memo and press Enter.",
    "2 / 空欄でEnterを押すとOwnerへ。黄色の欄でメモを書きEnter。",
    "2 / 空白 Enter 移到 Owner。在黄色栏写备忘后按 Enter。",
    "2 / 빈칸에서 Enter로 Owner로 이동. 노란 칸에 메모 후 Enter.",
    "2 / Enter vacío mueve a Owner. Escribe una nota amarilla y pulsa Enter."
  ],
  "tour_search": [
    "3 / Empty Enter changes yellow Memo to green Search. Type part of your memo.",
    "3 / 空欄Enterで黄色のメモから緑の検索へ。メモの一部を入力します。",
    "3 / 空白 Enter 从黄色备忘切到绿色搜索，输入备忘的一部分。",
    "3 / 빈 Enter로 노란 메모에서 초록 검색으로. 메모 일부를 입력하세요.",
    "3 / Enter vacío cambia Nota amarilla a Búsqueda verde. Escribe parte de la nota."
  ],
  "tour_private": [
    "4 / Clear Search, then empty Enter returns to Agent. Try // followed by a question. It is not saved in your notebook.",
    "4 / 検索を空にしてEnterでAgentへ。「//質問」でノートに保存しない対話を試せます。",
    "4 / 清空搜索后 Enter 回到 Agent。试试 // 后接问题，此对话不存入笔记。",
    "4 / 검색을 비운 후 Enter로 Agent 복귀. //질문을 입력하면 노트에 저장하지 않는 대화입니다.",
    "4 / Vacía Buscar y pulsa Enter para volver a Agent. Prueba // seguido de una pregunta: no se guarda en el cuaderno."
  ],
  "tour_settings": [
    "5 / In Agent, type /verantyx models. Use arrows and Enter; settings are not chat memory.",
    "5 / Agentで /verantyx models。矢印とEnterで選びます。設定操作は会話の記憶に入りません。",
    "5 / 在 Agent 输入 /verantyx models。用方向键与 Enter，设置不进入对话记忆。",
    "5 / Agent에서 /verantyx models. 방향키와 Enter로 선택하며 설정은 대화 기억에 남지 않습니다.",
    "5 / En Agent, escribe /verantyx models. Usa flechas y Enter; los ajustes no son memoria de chat."
  ],
  "tour_complete": [
    "Tutorial complete. Optional: type a memo prefix in Agent, then arrows + Tab to insert a reference. Empty Enter cycles Agent > Memo > Search.",
    "練習完了。Agentでメモの先頭文字を入力し、矢印+Tabで参照を挿入できます。空欄EnterでAgent→メモ→検索。",
    "教程完成。可在 Agent 输入备忘开头，方向键+Tab 插入引用。空白 Enter 循环 Agent > 备忘 > 搜索。",
    "연습 완료. Agent에 메모 앞부분을 쓰고 방향키+Tab으로 참조를 넣습니다. 빈 Enter: Agent > 메모 > 검색.",
    "Tutorial completo. Escribe un prefijo de nota en Agent y usa flechas + Tab para insertar referencia. Enter vacío recorre Agent > Nota > Buscar."
  ],
  "session_commands": [
    "/verantyx new: new Agent conversation here; in Owner: new Cleanroom.\n/verantyx cleanroom: list, switch or rename Owner Cleanrooms.\n/verantyx compact: summarize this Agent session, keeping originals.\n//message: temporary chat. /approvals: revoke candidate-edit grants.",
    "/verantyx new: Agentでは新しい会話、Ownerでは新しいCleanroom。\n/verantyx cleanroom: Ownerの一覧・切り替え・名前変更。\n/verantyx compact: 原記録を残してAgentの文脈を要約。\n//文章: 一時対話。/approvals: 候補編集の許可を取り消す。",
    "/verantyx new：Agent 中新建会话，Owner 中新建 Cleanroom。\n/verantyx cleanroom：列出、切换或重命名 Owner。\n/verantyx compact：总结 Agent 上下文，保留原记录。\n//消息：临时对话。/approvals：撤销候选编辑授权。",
    "/verantyx new: Agent는 새 대화, Owner는 새 Cleanroom.\n/verantyx cleanroom: Owner 목록, 전환, 이름 변경.\n/verantyx compact: 원본을 남기고 Agent 문맥 요약.\n//메시지: 임시 대화. /approvals: 후보 편집 허용 취소.",
    "/verantyx new: nueva conversación en Agent, nuevo Cleanroom en Owner.\n/verantyx cleanroom: listar, cambiar o renombrar Owner.\n/verantyx compact: resumir Agent conservando originales.\n//mensaje: chat temporal. /approvals: revocar permisos de candidatos."
  ]
}


TEXT.update({
  "insight_heading": [
    "While work continues / optional",
    "作業の合間に / 読まなくても進みます",
    "工作进行中 / 可选",
    "작업 중 / 선택 사항",
    "Mientras continúa el trabajo / opcional"
  ],
  "insight_hint": [
    "Paste an L-ID into Agent to ask. Your implementation stays in place; no mastery is inferred.",
    "L番号をAgentへ送ると質問できます。実装の状態は保持し、理解済みとは判定しません。",
    "将 L 编号发到 Agent 即可提问。保留实现状态，不推断已掌握。",
    "L 번호를 Agent에 보내 질문하세요. 구현 상태는 유지되며 이해 완료로 판단하지 않습니다.",
    "Envía el ID L a Agent para preguntar. Se conserva el trabajo; no se presume dominio."
  ],
  "insight_available": [
    "Insights saved during work. /insights opens them when you want.",
    "実装中の説明を保存しています。見たいときに /insights。",
    "实现过程的说明已保存，需要时用 /insights。",
    "구현 중 설명이 저장되었습니다. 원할 때 /insights.",
    "Explicaciones guardadas durante el trabajo. Ábrelas con /insights cuando quieras."
  ],
  "insight_queued": [
    "Question queued for the next safe step. Work will resume unchanged.",
    "次の安全な区切りで回答します。その後は元の実装へ戻ります。",
    "将在下一个安全节点回答，然后继续原来的实现。",
    "다음 안전한 단계에서 답변한 뒤 원래 구현으로 돌아갑니다.",
    "Se responderá en el siguiente punto seguro y se reanudará el trabajo."
  ],
  "insight_answer": [
    "Insight answer / separate from implementation",
    "理解についての回答 / 実装への変更指示ではありません",
    "理解问题的回答 / 不修改实现指令",
    "이해를 위한 답변 / 구현 변경 지시와 별개",
    "Respuesta de comprensión / separada de la implementación"
  ],
  "insight_running": [
    "Answering an insight / work paused safely",
    "理解の質問に回答中 / 実装は安全な区切りで待機",
    "正在回答 / 实现在安全节点暂停",
    "이해 질문 답변 중 / 구현은 안전한 단계에서 대기",
    "Respondiendo / trabajo pausado en un punto seguro"
  ],
  "insight_wait": [
    "This work cannot accept another side question now. Your draft is retained; send it after this step.",
    "今は追加の質問を受け取れません。入力は残しています。この処理後に送信できます。",
    "当前无法接收更多问题。已保留输入，请在此步骤后发送。",
    "지금은 추가 질문을 받을 수 없습니다. 입력을 유지했으니 처리 후 보내세요.",
    "No se admiten más preguntas ahora. Se conserva el borrador; envíalo después de este paso."
  ],
  "insight_failed": [
    "Explanation unavailable ({code}). Work and original notes are unchanged; resend the ID to retry.",
    "説明を取得できませんでした（{code}）。実装と元の記録は保持しています。番号の再送で再試行できます。",
    "无法获取说明（{code}）。实现和原记录不变，可重发编号重试。",
    "설명을 가져오지 못했습니다({code}). 구현과 원본은 유지됩니다. 번호를 다시 보내 재시도하세요.",
    "No se pudo explicar ({code}). Trabajo y notas intactos; reenvía el ID para reintentar."
  ],
  "eta": [
    "AI estimate: {low}–{high} min remaining",
    "AI予想: 残り {low}〜{high} 分",
    "AI 估计：剩余 {low}–{high} 分钟",
    "AI 예상: {low}–{high}분 남음",
    "Estimación IA: faltan {low}–{high} min"
  ],
  "eta_unknown": [
    "Time estimate not available yet",
    "所要時間はまだ見積もれていません",
    "尚无时间估计",
    "아직 시간 예상 없음",
    "Todavía no hay estimación"
  ],
  "eta_overdue": [
    "Estimate exceeded; awaiting a new estimate, not a completion claim",
    "予想を超過 / 再見積もり待ち・完了ではありません",
    "已超出预估，等待更新，并非已完成",
    "예상 시간 초과 / 재예상 대기, 완료가 아님",
    "Estimación superada; esperando actualización, no finalizado"
  ],
  "eta_update": [
    "Question time added; AI will re-estimate at the next step",
    "質問時間を加算 / 次の手順でAIが再見積もり",
    "已加入提问时间，下个步骤重新估算",
    "질문 시간 반영 / 다음 단계에서 AI가 재예상",
    "Tiempo de pregunta añadido; se reestimará en el siguiente paso"
  ],
  "eta_parts": [
    "At last estimate: implementation {il}–{ih} min; testing {tl}–{th} min. A forecast, not test evidence.",
    "前回見積もり: 実装 {il}〜{ih} 分 / テスト {tl}〜{th} 分。予想であり検査の証拠ではありません。",
    "上次估计：实现 {il}–{ih} 分钟，测试 {tl}–{th} 分钟。是预测，不是测试证据。",
    "마지막 예상: 구현 {il}–{ih}분, 테스트 {tl}–{th}분. 예상이지 검증 증거가 아닙니다.",
    "Última estimación: implementación {il}–{ih} min; pruebas {tl}–{th} min. No es evidencia de pruebas."
  ],
  "memo_paging": [
    "Memo archive {first}–{last} / {total}. Scroll past an edge for the next page; search covers the archive.",
    "メモ {first}〜{last} / {total} 件。端までスクロールすると次のページへ。検索は保存済み全体が対象です。",
    "备忘 {first}–{last} / {total}。滚过边缘加载下一页；搜索覆盖存档。",
    "메모 {first}–{last} / {total}. 끝에서 더 스크롤하면 다음 페이지. 검색은 전체 보관 기록 대상.",
    "Notas {first}–{last} / {total}. Desplázate más allá del borde para otra página; búsqueda en todo el archivo."
  ],
  "live_help": [
    "/insights: optional notes recorded during implementation. Send L-000123, optionally followed by a question, to ask at the next safe step without changing the work. AI time ranges are estimates; questions add measured time. Learning remains opt-in and follows your pace.",
    "/insights: 実装中に保存した説明。L-000123、または番号に続けて質問を送ると、次の安全な区切りで回答して実装を続けます。所要時間はAIの予想で、質問の実時間を加算します。学習は任意で本人のペース設定に従います。",
    "/insights：实现过程中保存的说明。发送 L-000123 或编号加问题，在安全节点回答后继续实现。时间是 AI 预测，会加入提问耗时。学习可选，遵循个人节奏。",
    "/insights: 구현 중 저장한 설명. L-000123 또는 번호와 질문을 보내면 안전한 단계에서 답하고 구현을 계속합니다. 시간은 AI 예상이며 질문 소요 시간을 더합니다. 학습은 선택 사항입니다.",
    "/insights: explicaciones guardadas durante la implementación. Envía L-000123 y, opcionalmente, una pregunta; se responde en un punto seguro y continúa el trabajo. El tiempo es estimado y suma las preguntas. Aprender es opcional."
  ]
})

TEXT.update({
  "compact_partial": [
    "Summary saved for a bounded part. Original events and remaining work are retained.",
    "一部の範囲を要約しました。原記録と未処理部分は保持しています。",
    "已保存部分范围的摘要，原记录和未处理部分保留。",
    "일부 범위의 요약을 저장했습니다. 원본과 미처리 부분은 유지됩니다.",
    "Se resumió una parte acotada. Se conservan los originales y lo pendiente."
  ],
  "remaining_sources": [
    "Remaining source events: {count}",
    "未要約の出典イベント: {count} 件",
    "未摘要的来源事件：{count}",
    "미요약 출처 이벤트: {count}개",
    "Eventos de origen pendientes: {count}"
  ],
  "tune_detail": [
    "Adjust supported reasoning effort and a context budget. Provider/model limitations still apply; saving is not a connection test.",
    "対応する推論レベルと文脈予算を設定します。提供元・モデルの制限は残り、保存だけでは接続確認になりません。",
    "设置支持的推理等级与上下文预算。仍受模型限制，保存不代表连接测试。",
    "지원되는 추론 수준과 문맥 예산을 설정합니다. 모델 제한은 유지되며 저장은 연결 테스트가 아닙니다.",
    "Ajusta razonamiento compatible y presupuesto de contexto. Siguen los límites del modelo; guardar no prueba la conexión."
  ],
  "local_detail": [
    "Use a model served by your configured local endpoint. Model files and the server must already be available.",
    "設定したローカルサーバー上のモデルを使います。モデル本体とサーバーは先に用意してください。",
    "使用配置的本地端点提供的模型。需先准备模型文件和服务器。",
    "설정한 로컬 서버의 모델을 사용합니다. 모델 파일과 서버가 먼저 준비되어 있어야 합니다.",
    "Usa un modelo de tu servidor local configurado. Los archivos y servidor deben estar preparados."
  ]
})

def t(key, locale="en", **values):
    return TEXT[key][LANGS.index(locale) if locale in LANGS else 0].format(**values)
