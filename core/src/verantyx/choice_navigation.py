"""Arrow-key choices with contextual help; no numbered interactive menus."""
import sys
from .interaction_text import LOCALES, locale, tr
from .presentation import safe_text

# Keys are explicit menu values, not classifiers for user requests.
DETAILS = {
"accounts": ("Use your own official CLI login. No API key is copied into the project. Provider plan limits still apply.", "公式CLIで自分のアカウントに接続します。APIキーはプロジェクトへコピーしません。契約の利用制限は残ります。", "使用官方CLI登录，不把API密钥复制到项目。仍受订阅限制。", "공식 CLI 계정으로 연결합니다. API 키를 프로젝트에 복사하지 않습니다. 요금제 제한은 유지됩니다.", "Conecta tu cuenta mediante el CLI oficial. No copia claves al proyecto; se mantienen los límites del plan."),
"codex": ("Use ChatGPT through the official Codex CLI. Sign-in belongs to Codex; model availability depends on your account, not Cleanroom.", "公式Codex CLI経由でChatGPTを利用します。認証はCodexが管理し、使えるモデルは契約によって異なります。", "通过官方Codex CLI使用ChatGPT。认证由Codex管理，可用模型取决于账号。", "공식 Codex CLI로 ChatGPT를 사용합니다. 인증은 Codex가 관리하며 모델 접근은 계정에 따릅니다.", "Usa ChatGPT con el CLI oficial de Codex. Codex gestiona la sesión; el acceso al modelo depende de tu cuenta."),
"claude": ("Use Claude through the official Claude Code login. This is separate from Anthropic API billing and keeps credentials outside this project.", "公式Claude Codeのログインを使います。Anthropic API課金とは別経路で、認証情報をプロジェクト内へ保存しません。", "使用官方Claude Code登录，与Anthropic API计费分开，凭据不保存在项目中。", "공식 Claude Code 로그인을 사용합니다. Anthropic API 과금과 별개이며 인증 정보는 프로젝트 밖에 둡니다.", "Usa el inicio de sesión oficial de Claude Code, separado de la API de Anthropic y sin guardar credenciales en el proyecto."),
"ollama": ("Use a model served by Ollama. Choose the server first, then an installed model. A remote server is not this Mac. Images require a vision model.", "Ollamaで動くモデルを使います。先に接続先を選び、そこにあるモデルを選択します。別Macへの接続はこのMac内の処理ではありません。画像には視覚対応が必要です。", "使用Ollama模型。先选服务器，再选已安装模型。远程服务器不是本机；图片需要视觉模型。", "Ollama 서버를 먼저 고른 뒤 설치된 모델을 선택합니다. 원격 서버는 이 Mac이 아니며 이미지는 비전 모델이 필요합니다.", "Elige primero el servidor Ollama y después su modelo instalado. Un servidor remoto no es este Mac; las imágenes requieren visión."),
"openai": ("Use the OpenAI API, billed separately from a ChatGPT subscription. Read OPENAI_API_KEY from the environment; never paste a key into chat.", "OpenAI APIを使います。ChatGPTサブスクとは別課金です。OPENAI_API_KEYを環境から読み、チャットへキーを貼り付けません。", "使用OpenAI API，与ChatGPT订阅分别计费。从环境读取OPENAI_API_KEY，不要在聊天粘贴密钥。", "OpenAI API를 사용하며 ChatGPT 구독과 별도 과금입니다. 환경의 OPENAI_API_KEY를 읽습니다. 채팅에 키를 붙이지 마세요.", "Usa la API de OpenAI, con facturación separada de ChatGPT. Lee OPENAI_API_KEY del entorno; no pegues claves en el chat."),
"anthropic": ("Use the Anthropic API with ANTHROPIC_API_KEY. This does not use a Claude subscription; data and costs follow your API account.", "ANTHROPIC_API_KEYでAPIへ接続します。Claudeサブスクは使わず、送信データと料金はAPIアカウントの条件に従います。", "使用ANTHROPIC_API_KEY连接API，不使用Claude订阅。数据和费用遵循API账号政策。", "ANTHROPIC_API_KEY로 API에 연결합니다. Claude 구독을 사용하지 않으며 API 계정의 데이터·요금 정책이 적용됩니다.", "Conecta con ANTHROPIC_API_KEY. No utiliza la suscripción Claude; se aplican las condiciones de la cuenta API."),
"gemini": ("Use the Gemini API with GEMINI_API_KEY. Your selected model determines image support, capacity and cost.", "GEMINI_API_KEYでGemini APIを使います。画像対応・容量・料金は選んだモデルに依存します。", "通过GEMINI_API_KEY使用Gemini API，图片支持、容量与费用由所选模型决定。", "GEMINI_API_KEY로 Gemini API를 사용합니다. 이미지 지원·용량·비용은 선택 모델에 따릅니다.", "Usa Gemini API con GEMINI_API_KEY. El modelo elegido determina visión, capacidad y coste."),
"openai_compatible": ("Connect LM Studio or another compatible server. Enter its endpoint and exact model ID. Compatibility does not guarantee image or JSON support.", "LM Studioなどの互換サーバーへ接続します。接続先と正確なモデル名が必要です。互換APIでも画像やJSON出力に対応するとは限りません。", "连接LM Studio等兼容服务器，输入端点与准确模型名。兼容API不保证图片或JSON支持。", "LM Studio 등 호환 서버에 연결합니다. 주소와 정확한 모델 ID가 필요합니다. 호환 API가 이미지·JSON 지원을 보장하지는 않습니다.", "Conecta LM Studio u otro servidor compatible. Usa su endpoint e ID exacto; la compatibilidad no garantiza visión ni JSON."),
"models": ("Choose the Work AI and optional Reflection AI independently. Changing a model preserves earlier records; it does not prove a connection works.", "作業AIと整理AIを別々に選べます。変更しても過去の記録は残ります。設定の保存は接続成功の証明ではありません。", "分别选择工作与整理AI。换模型不删除旧记录；保存设置不等于连接已验证。", "작업 AI와 정리 AI를 따로 선택합니다. 이전 기록은 유지되며 저장만으로 연결 성공을 증명하지 않습니다.", "Elige IA de trabajo y reflexión por separado. Conserva el historial; guardar no demuestra conectividad."),
"work": ("Choose who handles future work requests. This does not run a task or reclassify old work; an explicit parent-role override takes precedence.", "次の仕事を担当するAIを選びます。ここでは実行や過去の再分類はしません。親モデルの明示設定がある場合はそちらが優先されます。", "选择后续工作的AI，不执行任务或重新分类历史。显式父模型设置优先。", "다음 작업 AI를 선택합니다. 작업 실행이나 과거 재분류는 하지 않습니다. 명시한 부모 모델이 우선합니다.", "Elige la IA para el trabajo futuro. No ejecuta tareas ni reclasifica el pasado; un rol padre explícito tiene prioridad."),
"same": ("Reflection follows the Work AI. It organizes recorded work after execution and can use additional model calls; its failure must not erase work.", "整理AIが作業AIに追従します。作業記録を後から整理するため追加呼び出しが発生します。整理失敗で成果物を消しません。", "整理AI跟随工作AI，整理记录会产生额外调用；整理失败不删除成果。", "정리 AI가 작업 AI를 따릅니다. 추가 호출로 기록을 정리하며 실패해도 결과물은 사라지지 않습니다.", "La reflexión sigue a la IA de trabajo. Puede añadir llamadas; un fallo de organización no elimina el resultado."),
"custom": ("Choose a separate Reflection AI. Work and organization have independent outcomes, costs and destinations; this is not a required consensus vote.", "整理専用AIを選びます。作業と整理は結果・費用・送信先が別になります。モデル間の一致を必須にする設定ではありません。", "选择独立整理AI，工作与整理的结果、费用和发送目标独立，不要求模型一致。", "별도의 정리 AI를 선택합니다. 결과·비용·전송 대상은 독립적이며 모델 합의를 요구하지 않습니다.", "Elige otra IA para reflexión: resultados, costes y destino separados. No exige consenso entre modelos."),
"reflection_off": ("Stop post-work Reflection calls. Work and factual receipts remain. Other explicitly enabled personal-learning features are configured separately in My pace.", "作業後のReflection呼び出しを止めます。作業と事実の記録は残ります。別途有効な本人用学習機能はMy paceで調整します。", "停止作业后Reflection调用，保留工作和事实记录。个人学习功能另在My pace设置。", "작업 후 Reflection 호출을 중지합니다. 작업·사실 기록은 유지됩니다. 개인 학습 기능은 My pace에서 따로 설정합니다.", "Detiene las llamadas de reflexión posteriores. Conserva trabajo y hechos; el aprendizaje personal se configura por separado en My pace."),
"organize": ("Create another interpretation of saved work after send approval. Earlier interpretations and your confirmed decisions remain available.", "送信確認の後、保存済みの仕事を別の見方で整理します。以前の整理と人間が決めた内容は上書きしません。", "发送批准后重新整理已保存工作，不覆盖旧解读或人的决定。", "전송 승인 후 저장한 작업을 다시 정리합니다. 이전 해석과 사람의 결정은 덮어쓰지 않습니다.", "Crea otra interpretación tras aprobar el envío. No sobrescribe las anteriores ni tus decisiones."),
"roles": ("Set explicit parent and child model aliases. A parent override takes priority over Work AI. Choosing roles does not launch parallel agents.", "親・子モデルの別名を設定します。親の明示設定は作業AIより優先されます。ここで選んでも並列エージェントは起動しません。", "设置父子模型别名。父模型覆盖工作AI。选角色不会启动并行代理。", "부모·자식 모델 별칭을 설정합니다. 부모 설정이 작업 AI보다 우선하며 병렬 에이전트를 시작하지 않습니다.", "Configura alias padre e hijo. El padre tiene prioridad sobre Work AI; no inicia agentes paralelos."),
"project": ("Edit this project's name and purpose. This is shared project direction, not a rating of your ability or a change to other projects.", "このプロジェクトの名前と目的を編集します。能力の評価ではなく、他のプロジェクトの目的も変更しません。", "编辑当前项目名称与目的，不评价能力，也不改变其他项目。", "현재 프로젝트의 이름과 목적을 수정합니다. 능력 평가가 아니며 다른 프로젝트는 바꾸지 않습니다.", "Edita nombre y propósito de este proyecto; no evalúa tu capacidad ni cambia otros proyectos."),
"profile": ("Record your own experience and interests across projects. Self-report, AI suggestions and confirmed work remain different; you may update or skip.", "プロジェクトを越えて自分の経験や関心を登録します。自己申告・AIの提案・作業事実は分離します。更新もスキップもできます。", "跨项目记录自己的经历与兴趣。自述、AI建议和事实分开，可更新或跳过。", "프로젝트를 넘어 경험과 관심을 기록합니다. 자기 보고·AI 제안·사실을 분리하며 수정하거나 건너뛸 수 있습니다.", "Registra experiencia e intereses entre proyectos. Autoinforme, sugerencia y hecho son distintos; puedes actualizar u omitir."),
"pace": ("Control the amount, timing and sharing of personal learning suggestions. Delegating work is not evidence that you do not understand it.", "本人用の学習提案の量・タイミング・共有範囲を選びます。作業を任せたことを理解不足とは判定しません。", "控制个人学习建议的数量、时机和共享范围。委托不代表不理解。", "개인 학습 제안의 양·시점·공유를 조절합니다. 위임했다고 이해 부족으로 판단하지 않습니다.", "Ajusta cantidad, momento y privacidad del aprendizaje. Delegar no demuestra falta de comprensión."),
"skills": ("Keep AI procedures separate from the skills you choose to develop. Imported or provisional procedures never mean you have mastered them.", "AIが使う手順と、自分が育てたいスキルを分けます。移植・仮生成された手順を習得済みとは扱いません。", "区分AI流程与想培养的技能。导入或临时流程不表示你已掌握。", "AI 절차와 직접 키울 스킬을 구분합니다. 가져오거나 임시 생성된 절차는 습득 완료가 아닙니다.", "Separa procedimientos de IA y habilidades que deseas cultivar. Importar o generar no equivale a dominar."),
"language": ("Choose display language. It changes explanations, not authority rules or past records. Some legacy labels may remain untranslated.", "表示言語を選びます。説明の言語だけを変え、権限や過去の記録は変更しません。一部の旧機能には未翻訳のラベルがあります。", "选择显示语言，不改权限或历史记录。部分旧功能标签可能未翻译。", "표시 언어를 선택합니다. 권한이나 이전 기록은 바꾸지 않으며 일부 기존 라벨은 번역되지 않을 수 있습니다.", "Elige idioma de interfaz, sin cambiar permisos ni historial. Algunas etiquetas heredadas pueden no estar traducidas."),
"learning": ("Project-level display preferences, not mastery or permission settings. Personal learning pace and Reflection calls have separate controls.", "プロジェクト単位の表示設定です。習得判定や権限ではありません。本人用の学習ペースと整理AIの呼び出しは別設定です。", "项目级显示设置，不是掌握程度或权限。个人节奏与Reflection调用另行控制。", "프로젝트별 표시 설정이며 습득·권한 설정은 아닙니다. 개인 학습 속도와 Reflection 호출은 별도입니다.", "Preferencias de visualización del proyecto, no de dominio ni permisos. Ritmo personal y llamadas de reflexión se ajustan aparte."),
"digest": ("Show a brief project suggestion after work, within the selected limit. Displaying it does not mark understanding as achieved.", "作業後に設定件数内の短い提案を表示します。表示・既読だけで理解済みにはなりません。", "工作后按数量限制显示简短建议，显示或阅读不等于掌握。", "작업 후 설정한 수만큼 짧게 제안합니다. 표시나 읽기만으로 이해 완료가 되지 않습니다.", "Muestra sugerencias breves tras trabajar, dentro del límite. Verlas no acredita comprensión."),
"manual": ("Open project suggestions only when wanted. Work continues and existing records are not deleted.", "必要なときだけプロジェクトの提案を開きます。作業は継続し、既存記録も削除しません。", "需要时手动查看项目建议，工作继续且记录不删除。", "원할 때만 프로젝트 제안을 엽니다. 작업과 기존 기록은 유지됩니다.", "Abre sugerencias solo cuando quieras. El trabajo continúa y el historial permanece."),
"display_off": ("Hide automatic project suggestions. This is not Reflection off, and does not erase earlier learning records.", "自動のプロジェクト提案を非表示にします。Reflection停止とは異なり、以前の学習記録も消しません。", "隐藏自动项目建议，不等于关闭Reflection，也不删除旧学习记录。", "자동 프로젝트 제안을 숨깁니다. Reflection 중지와 다르며 이전 학습 기록도 지우지 않습니다.", "Oculta sugerencias automáticas. No desactiva reflexión ni borra aprendizaje previo."),
"workspace": ("View project and data locations. This does not approve external folders or silently widen the file scope.", "プロジェクトと保存先を確認します。外部フォルダの承認や読み取り範囲の拡張はしません。", "查看项目与数据位置，不批准外部文件夹或扩大范围。", "프로젝트·데이터 위치를 확인합니다. 외부 폴더를 승인하거나 범위를 넓히지 않습니다.", "Muestra ubicaciones; no autoriza carpetas externas ni amplía el alcance."),
"boundary": ("Read the permission boundaries. This is not an approval bypass. A model's statement never becomes a real test receipt or human decision.", "権限境界の説明を読みます。承認を迂回する設定ではありません。モデルの文章だけを検査事実・人間判断とは扱いません。", "阅读权限边界，不绕过批准。模型的话不是测试凭据或人的决定。", "권한 경계를 읽습니다. 승인 우회가 아니며 모델의 말은 검사 사실이나 인간 판단이 아닙니다.", "Lee los límites de permiso, sin omitir aprobaciones. La afirmación del modelo no es evidencia ni decisión humana."),
"harness": ("Choose the built-in runtime or a trusted external process. An external harness is not automatically sandboxed and may access its host.", "内蔵実行系か信頼する外部プロセスを選びます。外部ハーネスは自動では隔離されず、ホストへアクセスできる場合があります。", "选择内置或受信任外部进程。外部执行框架不会自动隔离，可能访问宿主机。", "내장 또는 신뢰하는 외부 프로세스를 선택합니다. 외부 하네스가 자동 격리되지는 않으며 호스트 접근이 가능할 수 있습니다.", "Elige runtime interno o proceso externo de confianza. Este no queda aislado automáticamente y puede acceder al anfitrión."),
"sandbox": ("Configure an optional OSS launcher for external work. Saving a launcher does not certify isolation; that backend defines and enforces its boundary.", "外部作業用のOSSランチャーを設定します。保存だけでは隔離の証明になりません。実際の境界は接続するバックエンドが強制します。", "配置外部工作的OSS启动器。保存不证明隔离，由后端执行边界。", "외부 작업용 OSS 런처를 설정합니다. 저장만으로 격리를 증명하지 않으며 백엔드가 경계를 강제합니다.", "Configura un lanzador OSS opcional. Guardarlo no certifica aislamiento; el backend impone el límite."),
"notebook": ("Connect Obsidian, imported skills or original explanations. A linked note remains a source, not automatic permission or proof of learning.", "Obsidian・移植スキル・作業中の解説を接続します。リンクしたノートは出典であり、自動承認や習得の証明にはなりません。", "连接Obsidian、导入技能或原始说明。关联笔记是来源，不是批准或掌握证明。", "Obsidian·가져온 스킬·원본 설명을 연결합니다. 연결된 노트는 출처이며 승인이나 습득 증명은 아닙니다.", "Conecta Obsidian, habilidades importadas o explicaciones originales. Una nota vinculada es fuente, no permiso ni dominio."),
"show": ("Read saved configuration without making a model call. Configured values are not a connectivity test.", "AIを呼ばず保存設定を読みます。設定値の表示は接続テストではありません。", "不调用AI，只看保存的配置。配置值不等于连接测试。", "AI 호출 없이 저장 설정을 읽습니다. 설정 표시는 연결 시험이 아닙니다.", "Lee la configuración sin llamar al modelo. No es una prueba de conectividad."),
"save": ("Save the displayed settings. This changes configuration only, not past work or human mastery.", "表示した設定を保存します。過去の仕事や本人の習得状態は変更しません。", "保存显示的设置，不改变过去工作或掌握状态。", "표시한 설정만 저장하며 과거 작업·습득 상태는 바꾸지 않습니다.", "Guarda lo mostrado, sin cambiar trabajo pasado ni dominio personal."),
"keep": ("Keep the current values; no change is saved for this choice.", "現在の値を維持し、この選択では変更を保存しません。", "保留当前值，不保存本次更改。", "현재 값을 유지하며 이 선택의 변경을 저장하지 않습니다.", "Conserva los valores actuales sin guardar este cambio."),
}


def description(title, value, label, lang=None):
    key = str(value)
    if isinstance(value, bool):
        key = "save" if value else "keep"
    if key == "off":
        key = "reflection_off" if title == "Models & organization" else "display_off"
    if title == "Notebook language":
        key = "language"
    index = LOCALES.index(lang or locale()) if (lang or locale()) in LOCALES else 0
    if key in DETAILS:
        return DETAILS[key][index]
    return safe_text(str(label), multiline=True) + "\n\n" + tr("keys", lang)


def choose(title, choices, descriptions, lang=None):
    """Return the actual choice value. No index becomes domain authority."""
    if not choices:
        return None
    rows = [(None, tr("back", lang)), *choices]
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(safe_text(title))
        for _, label in choices:
            print("  " + safe_text(label))
        print(tr("menu_fallback", lang))
        try:
            answer = input("> ").strip()
        except EOFError:
            return None
        return next((value for value, label in choices if answer == label), None)
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style
    from prompt_toolkit.data_structures import Point
    index = [1]
    kb = KeyBindings()

    def text():
        return [("class:selected" if i == index[0] else "",
                 (" (o) " if i == index[0] else " ( ) ") + safe_text(label) + "\n")
                for i, (_, label) in enumerate(rows)]

    @kb.add("up")
    @kb.add("s-tab")
    def up(event):
        index[0] = (index[0] - 1) % len(rows)

    @kb.add("down")
    @kb.add("tab")
    def down(event):
        index[0] = (index[0] + 1) % len(rows)

    @kb.add("enter")
    def select(event):
        event.app.exit(result=rows[index[0]][0])

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("c-d")
    def cancel(event):
        event.app.exit(result=None)

    menu = FormattedTextControl(text, focusable=True, get_cursor_position=lambda: Point(0, index[0]))
    detail = lambda: safe_text(descriptions.get(rows[index[0]][0], tr("back", lang)), multiline=True)
    layout = HSplit([
        Window(FormattedTextControl(safe_text(title)), height=1, style="bold"),
        Window(menu, height=min(len(rows) + 1, 13), wrap_lines=True),
        Window(FormattedTextControl(detail), height=5, wrap_lines=True, style="class:detail"),
        Window(FormattedTextControl(tr("keys", lang)), height=2, wrap_lines=True),
    ])
    return Application(layout=Layout(layout, focused_element=menu), key_bindings=kb,
                       full_screen=False, style=Style.from_dict({
                           "selected": "bold fg:#98c8ba", "detail": "fg:#a8bec5",
                       })).run()


from .session_text import TEXT as SESSION_DETAILS
DETAILS.update({name: SESSION_DETAILS[key] for name, key in {
    "tune": "tune_detail", "context": "auto_detail", "permissions": "permanent_detail",
    "lmstudio": "local_detail",
}.items()})
