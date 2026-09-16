"""Fixed presentation copy only. Never translate or classify a user's records."""
from .interaction_text import LOCALES, locale

PHRASES = {
  "Choose a setting": [
    "Choose a setting",
    "設定を選択",
    "选择设置",
    "설정 선택",
    "Elige un ajuste"
  ],
  "Keep your project understanding and decisions here. Let AI carry the implementation work.": [
    "Keep your project understanding and decisions here. Let AI carry the implementation work.",
    "実装はAIに任せながら、プロジェクトの理解と判断を手元に残します。",
    "让AI承担实现，把项目理解和判断留在自己手中。",
    "구현은 AI에 맡기고 프로젝트 이해와 판단은 내 것으로 남깁니다.",
    "Deja la implementación a la IA y conserva la comprensión y las decisiones."
  ],
  "Project: {name}": [
    "Project: {name}",
    "プロジェクト: {name}",
    "项目：{name}",
    "프로젝트: {name}",
    "Proyecto: {name}"
  ],
  "Language / notebook display": [
    "Language / notebook display",
    "言語 / 画面とガイド",
    "语言 / 界面与指南",
    "언어 / 화면과 안내",
    "Idioma / interfaz y guía"
  ],
  "Accounts / connect ChatGPT or Claude subscription": [
    "Accounts / connect ChatGPT or Claude subscription",
    "アカウント / ChatGPT・Claudeの契約を接続",
    "账号 / 连接ChatGPT或Claude订阅",
    "계정 / ChatGPT·Claude 구독 연결",
    "Cuentas / conectar suscripción de ChatGPT o Claude"
  ],
  "Models & organization / Work AI and Reflection AI": [
    "Models & organization / Work AI and Reflection AI",
    "モデルと整理 / 作業AIと整理AI",
    "模型与整理 / 工作AI与整理AI",
    "모델과 정리 / 작업 AI와 정리 AI",
    "Modelos y organización / IA de trabajo y reflexión"
  ],
  "Parent / child models": [
    "Parent / child models",
    "親モデル・助言用モデル",
    "主模型与辅助模型",
    "부모 모델·보조 모델",
    "Modelos principal y auxiliares"
  ],
  "Notebook / Obsidian, imported skills, original learning records": [
    "Notebook / Obsidian, imported skills, original learning records",
    "ノート接続 / Obsidian・スキル移植・元の記録",
    "笔记连接 / Obsidian、导入技能和原始记录",
    "노트 연결 / Obsidian·스킬 가져오기·원본 기록",
    "Cuaderno / Obsidian, habilidades importadas y fuentes"
  ],
  "Work harness / built-in or trusted external proposal adapter": [
    "Work harness / built-in or trusted external proposal adapter",
    "作業ハーネス / 内蔵または信頼する外部アダプター",
    "工作运行环境 / 内置或可信外部适配器",
    "작업 하네스 / 내장 또는 신뢰하는 외부 어댑터",
    "Harness / interno o adaptador externo de confianza"
  ],
  "Sandbox backend / optional OSS launcher for external Work": [
    "Sandbox backend / optional OSS launcher for external Work",
    "サンドボックス接続 / 外部作業用のOSSランチャー",
    "沙箱连接 / 外部工作的OSS启动器",
    "샌드박스 연결 / 외부 작업용 OSS 런처",
    "Sandbox / lanzador OSS opcional para trabajo externo"
  ],
  "My skills / AI procedures and my personal board": [
    "My skills / AI procedures and my personal board",
    "自分のスキル / AIの手順と自分が選ぶ盤面",
    "我的技能 / AI步骤与个人面板",
    "내 스킬 / AI 절차와 개인 보드",
    "Mis habilidades / procedimientos de IA y tablero personal"
  ],
  "Project / name and purpose": [
    "Project / name and purpose",
    "プロジェクト / 名前と目的",
    "项目 / 名称与目标",
    "프로젝트 / 이름과 목적",
    "Proyecto / nombre y propósito"
  ],
  "My profile / personal experience, journal and portfolio": [
    "My profile / personal experience, journal and portfolio",
    "プロフィール / 自分の経験・日記・実績",
    "个人档案 / 经验、日记与作品",
    "프로필 / 경험·일지·성과",
    "Mi perfil / experiencia, diario y trabajos"
  ],
  "My pace / person-wide learning, sharing and quiet mode": [
    "My pace / person-wide learning, sharing and quiet mode",
    "自分のペース / 学習提案・共有・静かなモード",
    "我的节奏 / 学习建议、分享与安静模式",
    "내 페이스 / 학습 제안·공유·조용한 모드",
    "Mi ritmo / aprendizaje, compartir y modo silencioso"
  ],
  "Project learning / legacy display preferences": [
    "Project learning / legacy display preferences",
    "学習表示 / このプロジェクトの提案設定",
    "学习显示 / 此项目的建议设置",
    "학습 표시 / 이 프로젝트의 제안 설정",
    "Aprendizaje / preferencias de este proyecto"
  ],
  "Workspace / project location and local data": [
    "Workspace / project location and local data",
    "作業場所 / プロジェクトとローカルデータ",
    "工作区 / 项目位置与本地数据",
    "작업 공간 / 프로젝트 위치와 로컬 데이터",
    "Espacio / ubicación del proyecto y datos locales"
  ],
  "Authority / permissions and boundaries": [
    "Authority / permissions and boundaries",
    "権限 / 操作の許可と境界",
    "权限 / 操作许可与边界",
    "권한 / 작업 허용과 경계",
    "Autoridad / permisos y límites"
  ],
  "View saved settings / no model call": [
    "View saved settings / no model call",
    "保存した設定を見る / AI呼び出しなし",
    "查看已保存设置 / 不调用AI",
    "저장 설정 보기 / AI 호출 없음",
    "Ver ajustes guardados / sin llamar a la IA"
  ],
  "Notebook language": [
    "Notebook language",
    "画面とガイドの言語",
    "界面与指南语言",
    "화면과 안내 언어",
    "Idioma de la interfaz y la guía"
  ],
  "Save these project settings?": [
    "Save these project settings?",
    "この設定を保存しますか？",
    "保存这些设置？",
    "이 설정을 저장할까요?",
    "¿Guardar estos ajustes?"
  ],
  "Save changes": [
    "Save changes",
    "変更を保存",
    "保存更改",
    "변경 저장",
    "Guardar cambios"
  ],
  "Keep current settings": [
    "Keep current settings",
    "今の設定を維持",
    "保留当前设置",
    "현재 설정 유지",
    "Conservar los ajustes"
  ],
  "Proposed settings": [
    "Proposed settings",
    "変更する設定",
    "准备更改的设置",
    "변경할 설정",
    "Ajustes propuestos"
  ],
  "Saved: {path}": [
    "Saved: {path}",
    "保存先: {path}",
    "已保存：{path}",
    "저장됨: {path}",
    "Guardado: {path}"
  ],
  "Display and guide language changed. Recorded conversations remain in their original language.": [
    "Display and guide language changed. Recorded conversations remain in their original language.",
    "画面とガイドの言語を切り替えました。記録済みの会話は元の言語のままです。",
    "界面与指南语言已切换，已有对话保留原语言。",
    "화면과 안내 언어를 바꿨습니다. 저장된 대화는 원래 언어로 유지됩니다.",
    "Idioma de interfaz y guía cambiado. Las conversaciones conservan su idioma original."
  ],
  "This change was not completed: {reason}": [
    "This change was not completed: {reason}",
    "変更を完了できませんでした: {reason}",
    "未完成更改：{reason}",
    "변경을 완료하지 못했습니다: {reason}",
    "No se completó el cambio: {reason}"
  ],
  "Previously saved settings remain available. No AI work was started.": [
    "Previously saved settings remain available. No AI work was started.",
    "保存済みの設定は保持しています。AIの作業は開始していません。",
    "已保存的设置仍保留，未启动AI工作。",
    "기존 설정은 유지됩니다. AI 작업을 시작하지 않았습니다.",
    "Se conservan los ajustes anteriores. No se inició trabajo de IA."
  ],
  "Initialized project-local settings: {path}": [
    "Initialized project-local settings: {path}",
    "プロジェクト用の設定を作成しました: {path}",
    "已建立项目本地设置：{path}",
    "프로젝트 설정을 만들었습니다: {path}",
    "Ajustes locales creados: {path}"
  ],
  "Settings closed. Earlier saved changes are retained.": [
    "Settings closed. Earlier saved changes are retained.",
    "設定を閉じました。保存済みの変更は保持しています。",
    "设置已关闭，已保存的更改仍保留。",
    "설정을 닫았습니다. 저장한 변경은 유지됩니다.",
    "Ajustes cerrados. Se conservan los cambios guardados."
  ],
  "Settings closed. Run verantyx to open the notebook.": [
    "Settings closed. Run verantyx to open the notebook.",
    "設定を閉じました。verantyxで作業画面を開けます。",
    "设置已关闭，运行verantyx打开工作界面。",
    "설정을 닫았습니다. verantyx로 작업 화면을 여세요.",
    "Ajustes cerrados. Ejecuta verantyx para abrir el espacio."
  ],
  "PROJECT / Enter keeps the current value. :clear removes the purpose.": [
    "PROJECT / Enter keeps the current value. :clear removes the purpose.",
    "プロジェクト / Enterで現在の値を維持。:clearで目的を空にします。",
    "项目 / Enter保留当前值，:clear清空目标。",
    "프로젝트 / Enter로 현재 값 유지. :clear로 목적 삭제.",
    "PROYECTO / Enter conserva el valor; :clear elimina el propósito."
  ],
  "Project name": [
    "Project name",
    "プロジェクト名",
    "项目名称",
    "프로젝트 이름",
    "Nombre del proyecto"
  ],
  "Project purpose": [
    "Project purpose",
    "プロジェクトの目的",
    "项目目标",
    "프로젝트 목적",
    "Propósito del proyecto"
  ],
  "When should learning suggestions appear?": [
    "When should learning suggestions appear?",
    "学習の提案をいつ表示しますか？",
    "何时显示学习建议？",
    "언제 학습 제안을 표시할까요?",
    "¿Cuándo mostrar sugerencias de aprendizaje?"
  ],
  "Briefly after work": [
    "Briefly after work",
    "作業後に短く表示",
    "工作后简短显示",
    "작업 후 짧게 표시",
    "Brevemente después del trabajo"
  ],
  "Only when I open them": [
    "Only when I open them",
    "自分が開いたときだけ",
    "仅主动打开时",
    "직접 열었을 때만",
    "Solo cuando las abra"
  ],
  "Do not show automatic suggestions": [
    "Do not show automatic suggestions",
    "自動提案を表示しない",
    "不自动显示建议",
    "자동 제안 표시 안 함",
    "No mostrar sugerencias automáticas"
  ],
  "Maximum suggestions per task": [
    "Maximum suggestions per task",
    "1作業あたりの提案上限",
    "每项工作的建议上限",
    "작업당 제안 한도",
    "Máximo de sugerencias por tarea"
  ],
  "LEARNING / Display preferences only; this does not mark understanding as achieved.": [
    "LEARNING / Display preferences only; this does not mark understanding as achieved.",
    "学習 / 表示の設定です。本人の習得済みとは扱いません。",
    "学习 / 仅调整显示，不代表已经掌握。",
    "학습 / 표시 설정이며 습득 완료로 처리하지 않습니다.",
    "APRENDIZAJE / Solo visualización, no acredita comprensión."
  ],
  "To stop model-based organization, choose Reflection: off in Models & organization.": [
    "To stop model-based organization, choose Reflection: off in Models & organization.",
    "AIによる整理を止めるには、モデル設定で整理AIをオフにします。",
    "要停止AI整理，请在模型设置中关闭整理AI。",
    "AI 정리를 중단하려면 모델 설정에서 정리 AI를 끄세요.",
    "Para detener la organización con IA, desactiva Reflexión en Modelos."
  ],
  "Models & organization": [
    "Models & organization",
    "モデルと整理",
    "模型与整理",
    "모델과 정리",
    "Modelos y organización"
  ],
  "Choose Work AI": [
    "Choose Work AI",
    "作業AIを選ぶ",
    "选择工作AI",
    "작업 AI 선택",
    "Elegir IA de trabajo"
  ],
  "Parent / child model roles": [
    "Parent / child model roles",
    "親モデル・助言モデルの役割",
    "主模型与辅助模型的角色",
    "부모·보조 모델 역할",
    "Roles de modelos principal y auxiliares"
  ],
  "Reflection: same as Work AI (default)": [
    "Reflection: same as Work AI (default)",
    "整理AI: 作業AIと同じ",
    "整理AI：与工作AI相同",
    "정리 AI: 작업 AI와 동일",
    "Reflexión: misma IA que el trabajo"
  ],
  "Reflection: choose a different AI": [
    "Reflection: choose a different AI",
    "整理AI: 別のAIを選ぶ",
    "整理AI：选择其他AI",
    "정리 AI: 다른 AI 선택",
    "Reflexión: elegir otra IA"
  ],
  "Reflection: off; keep work facts only": [
    "Reflection: off; keep work facts only",
    "整理AI: オフ。作業の事実は保存",
    "整理AI：关闭，保留工作事实",
    "정리 AI: 끄기. 작업 사실은 저장",
    "Reflexión: desactivada; conservar hechos"
  ],
  "Organize recorded work again": [
    "Organize recorded work again",
    "記録した仕事を再整理",
    "重新整理已记录的工作",
    "기록한 작업 다시 정리",
    "Organizar de nuevo el trabajo registrado"
  ],
  "Confirm the displayed operation only": [
    "Confirm the displayed operation only",
    "表示された操作だけを確認して進める",
    "只确认所显示的操作",
    "표시된 작업만 확인",
    "Confirmar solo la operación mostrada"
  ],
  "How would you like to start?": [
    "How would you like to start?",
    "どのように始めますか？",
    "想如何开始？",
    "어떻게 시작할까요?",
    "¿Cómo quieres empezar?"
  ],
  "Your experience can grow alongside your projects.": [
    "Your experience can grow alongside your projects.",
    "プロジェクトと一緒に、自分の経験も育てられます。",
    "让自己的经验与项目一起成长。",
    "프로젝트와 함께 내 경험도 키워 갑니다.",
    "Tu experiencia puede crecer con tus proyectos."
  ],
  "This is not an exam. Delegating or leaving this blank never removes features.": [
    "This is not an exam. Delegating or leaving this blank never removes features.",
    "試験ではありません。AIに任せたり未記入でも、使える機能は減りません。",
    "这不是考试，委托AI或留空不会减少功能。",
    "시험이 아닙니다. 위임하거나 비워 두어도 기능이 줄지 않습니다.",
    "No es un examen. Delegar o dejarlo vacío no elimina funciones."
  ],
  "Describe your experience in your own words; you can change it at any time.": [
    "Describe your experience in your own words; you can change it at any time.",
    "経験の基準は人それぞれで構いません。いつでも自分の言葉で変更できます。",
    "用自己的话描述经验，随时可以修改。",
    "자신의 말로 경험을 적고 언제든 바꿀 수 있습니다.",
    "Describe tu experiencia con tus palabras; puedes cambiarla cuando quieras."
  ],
  "Stored in your personal area on this computer, shared across your projects.": [
    "Stored in your personal area on this computer, shared across your projects.",
    "このパソコンの本人用領域に保存し、プロジェクトを越えて使います。",
    "保存在本机个人区域，跨项目使用。",
    "이 컴퓨터의 개인 영역에 저장해 프로젝트 간 사용합니다.",
    "Se guarda en tu espacio personal de este equipo y se usa entre proyectos."
  ],
  "Light / one suggestion per day; only your chosen excerpts are shared": [
    "Light / one suggestion per day; only your chosen excerpts are shared",
    "軽く / 1日1つまで。共有を選んだ抜粋だけを送る",
    "轻量 / 每天最多一条，仅分享所选摘录",
    "가볍게 / 하루 한 개, 선택한 발췌만 공유",
    "Ligero / una sugerencia al día; compartir solo tus extractos elegidos"
  ],
  "Private / local journal; open learning suggestions yourself": [
    "Private / local journal; open learning suggestions yourself",
    "自分用 / 日記はローカルだけ。学習提案は自分から開く",
    "私密 / 日记仅本地，学习建议由自己打开",
    "비공개 / 일지는 로컬에만, 학습 제안은 직접 열기",
    "Privado / diario local; abrir tú las sugerencias"
  ],
  "Together / small examples, at most once per day": [
    "Together / small examples, at most once per day",
    "一緒に / 小さな実例で進める。1日1つまで",
    "一起 / 用小例子推进，每天最多一次",
    "함께 / 작은 예시로, 하루 최대 한 번",
    "Juntos / pequeños ejemplos, como máximo una vez al día"
  ],
  "Skip / start working; open My profile later": [
    "Skip / start working; open My profile later",
    "スキップ / まず仕事へ。プロフィールは後から",
    "跳过 / 先工作，稍后打开档案",
    "건너뛰기 / 먼저 작업, 프로필은 나중에",
    "Omitir / empezar a trabajar; abrir el perfil después"
  ]
}


PHRASES.update({
    "Notebook language": [
        "Notebook language",
        "画面・ガイドの言語",
        "界面与指南语言",
        "화면·안내 언어",
        "Idioma de interfaz y guía"
    ],
    "Shared experience and short learning records are sent only to your selected Work and Reflection AI.": [
        "Shared experience and short learning records are sent only to your selected Work and Reflection AI.",
        "共有を選んだ経験と短い学習記録を、選択中の作業AI・整理AIへ送ります。",
        "仅向所选工作与整理AI发送你同意共享的经历和简短学习记录。",
        "공유를 선택한 경험과 짧은 학습 기록을 선택한 작업·정리 AI에 전송합니다.",
        "Solo se envían las experiencias y notas que compartes a las IA de trabajo y reflexión elegidas."
    ],
    "Organization may add model calls after work. Sensitive notes can stay private.": [
        "Organization may add model calls after work. Sensitive notes can stay private.",
        "整理を有効にすると追加のAI呼び出しが発生する場合があります。機密のメモは自分用にできます。",
        "整理可能带来额外模型调用，敏感笔记可保持私密。",
        "정리에 추가 모델 호출이 생길 수 있습니다. 민감한 메모는 비공개로 둘 수 있습니다.",
        "Organizar puede añadir llamadas al modelo; las notas sensibles pueden ser privadas."
    ],
    "Enable this personal context?": [
        "Enable this personal context?",
        "本人用の文脈共有を有効にしますか？",
        "启用个人背景共享？",
        "개인 맥락 공유를 켤까요?",
        "¿Activar este contexto personal?"
    ],
    "Enable / share only this scope": [
        "Enable / share only this scope",
        "有効にする / この範囲だけ共有",
        "启用 / 仅共享此范围",
        "켜기 / 이 범위만 공유",
        "Activar / compartir solo este alcance"
    ],
    "Private / start without sharing": [
        "Private / start without sharing",
        "自分用 / 送信せず始める",
        "私密 / 不分享直接开始",
        "비공개 / 전송 없이 시작",
        "Privado / empezar sin compartir"
    ],
    "You do not need to fill everything in. Experience gained with AI is welcome too.": [
        "You do not need to fill everything in. Experience gained with AI is welcome too.",
        "最初からすべて書く必要はありません。AIと一緒に使った経験も、そのままで大丈夫です。",
        "无需一次填完，与AI一起获得的经验也可以记录。",
        "처음부터 모두 쓸 필요 없습니다. AI와 함께 얻은 경험도 좋습니다.",
        "No tienes que rellenarlo todo; también cuenta la experiencia con IA."
    ],
    "Your notebook can be set up later. Work can continue: {reason}": [
        "Your notebook can be set up later. Work can continue: {reason}",
        "本人用ノートは後で準備できます。作業は続けられます: {reason}",
        "个人笔记可稍后设置，工作可继续：{reason}",
        "개인 노트는 나중에 준비해도 됩니다. 작업은 계속됩니다: {reason}",
        "Puedes preparar tu cuaderno después; el trabajo continúa: {reason}"
    ],
    "One technology you have used (Enter to skip)": [
        "One technology you have used (Enter to skip)",
        "使った技術を1つ（空欄Enterで後にする）",
        "用过的一项技术（Enter跳过）",
        "사용한 기술 하나(빈 Enter로 건너뛰기)",
        "Una tecnología que hayas usado (Enter para omitir)"
    ],
    "No experience statement is recorded yet. This does not mean you lack experience.": [
        "No experience statement is recorded yet. This does not mean you lack experience.",
        "経験はまだ記録されていません。未経験という意味ではありません。",
        "尚未记录经验，不代表没有经验。",
        "아직 경험 기록이 없습니다. 경험이 없다는 뜻이 아닙니다.",
        "Todavía no hay una declaración de experiencia; no significa que te falte."
    ],
    "Connection to this work: {reason}": [
        "Connection to this work: {reason}",
        "今回とのつながり: {reason}",
        "与本次工作的关系：{reason}",
        "이번 작업과의 연결: {reason}",
        "Relación con este trabajo: {reason}"
    ],
    "For example: built a small app with AI; can read it but want design help; use it regularly.": [
        "For example: built a small app with AI; can read it but want design help; use it regularly.",
        "例: AIと小さなアプリを作った、読めるが設計は相談したい、普段使っている。",
        "例如：和AI做过小应用；能阅读但希望获得设计帮助；经常使用。",
        "예: AI와 작은 앱을 만들었다, 읽을 수 있지만 설계는 도움받고 싶다, 자주 쓴다.",
        "Ejemplo: hice una app con IA; puedo leer el código pero quiero ayuda de diseño; lo uso habitualmente."
    ],
    "No precise level is required. Leaving this blank does not stop work.": [
        "No precise level is required. Leaving this blank does not stop work.",
        "正確な段階分けは不要です。空欄でも仕事は進められます。",
        "不必精确分级，留空也能继续工作。",
        "정확한 단계는 필요 없습니다. 비워 두어도 작업은 진행됩니다.",
        "No se exige un nivel exacto; dejarlo vacío no detiene el trabajo."
    ],
    "Your experience, in your own words": [
        "Your experience, in your own words",
        "今の感覚を自分の言葉で",
        "用自己的话描述经验",
        "내 말로 적는 경험",
        "Tu experiencia, con tus palabras"
    ],
    "This statement will be shared as context with your selected AI.": [
        "This statement will be shared as context with your selected AI.",
        "この記録は、選択したAIにも文脈として渡します。",
        "此记录将作为背景传给所选AI。",
        "이 기록은 선택한 AI의 맥락으로 공유됩니다.",
        "Esta declaración se compartirá como contexto con la IA elegida."
    ],
    "This statement stays private and is not sent to AI.": [
        "This statement stays private and is not sent to AI.",
        "この記録は自分用に保存し、AIには送りません。",
        "此记录仅个人保存，不发送给AI。",
        "이 기록은 개인용으로 저장하며 AI에 보내지 않습니다.",
        "Esta declaración es privada y no se envía a la IA."
    ],
    "Workspace / project location and local data": [
        "Workspace / project location and local data",
        "ワークスペース / プロジェクトと保存先",
        "工作区 / 项目和本地数据",
        "작업 공간 / 프로젝트와 저장 위치",
        "Espacio / proyecto y datos locales"
    ],
    "Authority / permissions and boundaries": [
        "Authority / permissions and boundaries",
        "権限 / 操作の許可と境界",
        "权限 / 操作授权与边界",
        "권한 / 작업 허용과 경계",
        "Autoridad / permisos y límites"
    ],
    "View saved settings / no model call": [
        "View saved settings / no model call",
        "保存した設定を見る / AI呼び出しなし",
        "查看设置 / 不调用模型",
        "저장된 설정 보기 / 모델 호출 없음",
        "Ver ajustes guardados / sin llamada al modelo"
    ]
})


from .session_text import TEXT as SESSION_TEXT
PHRASES.update({values[0]: values for values in SESSION_TEXT.values()})
PHRASES.update({
  "Reasoning & context window / current Work AI": [
    "Reasoning & context window / current Work AI",
    "推論とコンテキスト容量 / 現在の作業AI",
    "推理与上下文容量 / 当前工作AI",
    "추론 및 문맥 크기 / 현재 작업 AI",
    "Razonamiento y contexto / IA de trabajo"
  ],
  "Context / automatic compaction": [
    "Context / automatic compaction",
    "文脈 / 自動圧縮",
    "上下文 / 自动压缩",
    "문맥 / 자동 요약",
    "Contexto / compresión automática"
  ],
  "Candidate-edit permissions / revoke saved grants": [
    "Candidate-edit permissions / revoke saved grants",
    "候補編集の権限 / 保存した許可の取り消し",
    "候选编辑权限 / 撤销保存的授权",
    "후보 편집 권한 / 저장한 허용 취소",
    "Permisos de candidatos / revocar autorizaciones"
  ],
  "LM Studio / local model server": [
    "LM Studio / local model server",
    "LM Studio / ローカルモデルサーバー",
    "LM Studio / 本地模型服务器",
    "LM Studio / 로컬 모델 서버",
    "LM Studio / servidor de modelos local"
  ],
  "Use a detected local model or enter its exact identifier. No model is downloaded by this menu.": [
    "Use a detected local model or enter its exact identifier. No model is downloaded by this menu.",
    "検出されたローカルモデルを選ぶか、正確なモデル名を入力します。この画面ではモデルをダウンロードしません。",
    "选择检测到的本地模型或输入完整标识符。此菜单不会下载模型。",
    "감지된 로컬 모델을 선택하거나 정확한 이름을 입력합니다. 이 메뉴는 모델을 다운로드하지 않습니다.",
    "Elige un modelo local detectado o escribe su identificador. Este menú no descarga modelos."
  ]
})

PHRASES.update({label: SESSION_TEXT[key] for label, key in {"Context & compaction":"context","Permissions / candidate edits":"permissions","Tune current model / effort and context":"tune_model","LM Studio / local":"local_models"} .items() if key in SESSION_TEXT})

PHRASES["LM Studio / local"] = PHRASES["LM Studio / local model server"]

def ui_text(message, lang=None, **values):
    lang = lang or locale()
    index = LOCALES.index(lang) if lang in LOCALES else 0
    result = PHRASES.get(message, (message,) * 5)[index]
    return result.format(**values) if values else result
