"""Versioned, source-labelled curricula. Frozen on explicit registration.

Existing template-candidate prose is deliberately unchanged so pre-0.4 history
keeps replaying. These lessons supplement that history through new events.
"""
from .errors import LedgerError

LANGUAGES = ("en", "ja", "zh-Hans", "ko", "es")
CONSTITUTION = {"title": "Verantyx Constitution v0.1", "locator": "docs/CONSTITUTION.v0.1.ja.md",
                "version": "2026-09-06 / v0.1", "sha256": "b8130ed72a8eef1166326a86297f4695c979bace893a1f932bd5fbd7d7690d3e"}
GIT = {"title": "Git worktree manual", "locator": "https://git-scm.com/docs/git-worktree/2.54.0",
       "version": "2.54.0; consulted 2026-09-06", "sha256": None}

# Each language uses the same stable answer identifiers, with localized teaching
# content. No locale participates in the project permission or proof machinery.
MATERIALS = {
    "parallel_writers": {
        "en": (
            "Separate writers' working state", "A branch identifies a line of commits. Each linked worktree has its own working files and index, while repository objects and most refs remain shared.",
            "Alice and Bob start from the same commit in separate worktrees. Each keeps unfinished files in their own directory. Their results are reviewed before integration.",
            "Two processes using different branch names in one directory still edit the same working files. Two worktrees that write one external database can still interfere.",
            "A worktree is not a security sandbox. Shared refs, external services and final integration need their own coordination.",
            "What does a separate worktree provide?", ["Separate working files and index", "Only a different branch label", "Automatic isolation of every external resource"],
            "Which resources can still need coordination between separate worktrees? Select all that apply.", ["Shared repository refs", "One external database", "Ordinary files confined to each distinct worktree"],
            "Choose a setup for two writers and the treatment of their completed candidates.", ["Working location", "Integration"],
            [["A dedicated worktree for each writer", "Both writers in one directory"], ["Review and separately authorize integration", "Integrate automatically whenever one test passes"]]),
        "ja": (
            "writerの作業状態を分ける", "branchはコミットの系列を参照します。linked worktreeごとに作業ファイルとindexが分かれますが、リポジトリのobjectと多くの参照は共有されます。",
            "AとBが同じコミットを基準に別のworktreeで作業します。未完了のファイルはそれぞれの場所に保持し、結果を確認してから統合します。",
            "同じ場所でbranch名だけを分けても、二つのプロセスは同じ作業ファイルを編集します。別worktreeでも同じ外部DBへ書けば干渉します。",
            "worktreeは安全隔離環境ではありません。共有参照、外部サービス、最後の統合には別の調整が必要です。",
            "worktreeを分けると、何が分かれますか。", ["作業ファイルとindex", "branchの表示名だけ", "あらゆる外部資源が自動的に隔離される"],
            "別worktreeでも調整が必要になり得る資源を全て選んでください。", ["共有されたリポジトリ参照", "同じ外部DB", "各worktree内だけにある別々の通常ファイル"],
            "二人のwriterの場所と、完成した候補の扱いを選んでください。", ["作業場所", "統合"],
            [["writerごとに専用worktree", "二人とも同じディレクトリ"], ["確認して別途許可した上で統合", "一つのテストが成功したら自動統合"]]),
        "zh-Hans": (
            "隔离写入者的工作状态", "分支引用一系列提交。每个关联工作树有自己的工作文件和索引，但仓库对象和大部分引用仍然共享。",
            "甲和乙从同一提交开始，在不同工作树中开发。未完成的文件保留在各自目录，结果经过检查后再集成。",
            "在同一目录使用不同分支名的两个进程仍然编辑相同文件。不同工作树写入同一外部数据库也会互相影响。",
            "工作树不是安全沙箱。共享引用、外部服务和最终集成仍需单独协调。",
            "独立工作树提供什么？", ["独立工作文件和索引", "仅不同的分支名称", "自动隔离所有外部资源"],
            "不同工作树之间，哪些资源仍可能需要协调？选择所有适用项。", ["共享仓库引用", "同一个外部数据库", "仅存在于各自工作树内的不同普通文件"],
            "为两个写入者选择工作位置和候选成果的集成方式。", ["工作位置", "集成"],
            [["每个写入者使用专用工作树", "两人共用一个目录"], ["审查并单独授权集成", "一个测试成功就自动集成"]]),
        "ko": (
            "작성자의 작업 상태 분리", "브랜치는 커밋의 흐름을 가리킵니다. 연결된 워크트리는 작업 파일과 인덱스를 각각 가지지만 저장소 객체와 대부분의 참조는 공유합니다.",
            "A와 B가 같은 커밋에서 별도 워크트리로 시작합니다. 미완료 파일은 각 디렉터리에 보존하고 결과를 검토한 뒤 통합합니다.",
            "한 디렉터리에서 브랜치 이름만 다르게 사용하면 두 프로세스는 여전히 같은 파일을 수정합니다. 별도 워크트리라도 외부 DB를 공유하면 충돌할 수 있습니다.",
            "워크트리는 보안 샌드박스가 아닙니다. 공유 참조, 외부 서비스와 최종 통합에는 별도 조정이 필요합니다.",
            "워크트리를 분리하면 무엇이 분리되나요?", ["작업 파일과 인덱스", "브랜치 표시 이름만", "모든 외부 자원이 자동으로 격리됨"],
            "별도 워크트리에서도 조정이 필요할 수 있는 자원을 모두 고르세요.", ["공유 저장소 참조", "동일한 외부 데이터베이스", "각 워크트리 내부에만 있는 서로 다른 일반 파일"],
            "두 작성자의 작업 위치와 완성된 후보의 처리 방식을 고르세요.", ["작업 위치", "통합"],
            [["작성자마다 전용 워크트리", "두 작성자가 같은 디렉터리 사용"], ["검토 후 별도 승인으로 통합", "테스트 하나가 성공하면 자동 통합"]]),
        "es": (
            "Separar el estado de trabajo de los escritores", "Una rama referencia una línea de commits. Cada árbol enlazado tiene sus archivos e índice; los objetos del repositorio y la mayoría de referencias siguen compartidos.",
            "Ana y Luis parten del mismo commit en árboles distintos. Conservan los archivos pendientes en sus directorios y revisan los resultados antes de integrarlos.",
            "Dos procesos con nombres de rama distintos en un directorio siguen editando los mismos archivos. Dos árboles que escriben en una base de datos externa también pueden interferir.",
            "Un árbol de trabajo no es un entorno de seguridad aislado. Las referencias compartidas, los servicios externos y la integración necesitan coordinación adicional.",
            "¿Qué proporciona un árbol de trabajo separado?", ["Archivos de trabajo e índice separados", "Solo otra etiqueta de rama", "Aislamiento automático de todo recurso externo"],
            "¿Qué recursos aún pueden requerir coordinación entre árboles separados? Selecciona todos los aplicables.", ["Referencias compartidas del repositorio", "Una misma base de datos externa", "Archivos ordinarios distintos limitados a cada árbol"],
            "Elige dónde trabajan dos escritores y cómo se integran sus candidatos terminados.", ["Ubicación de trabajo", "Integración"],
            [["Un árbol dedicado para cada escritor", "Ambos en un mismo directorio"], ["Revisar y autorizar la integración por separado", "Integrar automáticamente cuando pase una prueba"]]),
    },
    "scoped_rule": {
        "en": (
            "Reuse a decision within its recorded scope", "A reusable rule binds a decision to a project, component, workload, risk and decision type. Check its validity, exceptions and review date before applying it.",
            "A rule for parallel writers in project A matches a second task only when its recorded conditions match. Project B needs its own supported decision or explicit scope change.",
            "A familiar request or a model's recollection does not extend a rule to a different project. A retired rule is not current authority.",
            "A scope match checks recorded applicability, not the truth or wisdom of the decision. Evidence and authorization remain separate.",
            "What must happen before reusing a rule?", ["Check its recorded scope, exceptions and validity", "Apply it to every similar sentence", "Ask the model whether it remembers approval"],
            "Which conditions prevent unconditional reuse? Select all that apply.", ["A different project outside the scope", "The rule has been retired", "All recorded conditions match and no exception applies"],
            "Handle an out-of-scope task and a candidate whose tests pass.", ["Out-of-scope decision", "Candidate adoption"],
            [["Obtain a new decision or explicit scope change", "Silently broaden the rule"], ["Obtain separate adoption authorization", "Treat test success as adoption permission"]]),
        "ja": (
            "判断を記録した範囲で再利用する", "再利用する規則は、判断をプロジェクト・構成要素・作業形態・リスク・判断種別に結び付けます。適用前に有効性、例外、見直し期限も確認します。",
            "プロジェクトAの並列writer規則は、記録した条件が一致する二つ目のタスクに使えます。プロジェクトBには別の判断か、明示した範囲変更が必要です。",
            "依頼の文章が似ていることやモデルの記憶は、規則の範囲を広げる根拠になりません。撤回済みの規則も現在の権限にはなりません。",
            "範囲照合で確かめるのは記録した適用条件です。判断の正しさは証明しません。証拠と実行許可も別に扱います。",
            "規則を再利用する前に何を確認しますか。", ["記録した範囲、例外、有効性", "似た文章なら全てに適用する", "モデルが承認を覚えているか"],
            "無条件の再利用を認められない条件を全て選んでください。", ["範囲外の別プロジェクト", "規則が撤回されている", "全ての記録条件が一致して例外もない"],
            "範囲外のタスクと、テストが成功した候補を扱ってください。", ["範囲外の判断", "候補の採用"],
            [["新しい判断か明示した範囲変更を得る", "暗黙に規則を広げる"], ["別の採用許可を得る", "テスト成功を採用許可として使う"]]),
        "zh-Hans": (
            "在已记录范围内复用判断", "可复用规则将判断绑定到项目、组件、工作负载、风险和判断类型。应用前还须检查有效性、例外和复查日期。",
            "项目A的并行写入规则，只有在记录条件匹配时才能用于第二个任务。项目B需要新的判断或明确的范围变更。",
            "请求文字相似或模型记得批准，都不能扩大规则范围。已撤回规则也不代表当前权限。",
            "范围匹配检查的是记录的适用条件，不是判断本身是否正确。证据与授权仍然独立。",
            "复用规则前需要什么？", ["检查记录的范围、例外和有效性", "应用于所有相似语句", "询问模型是否记得批准"],
            "哪些条件阻止无条件复用？选择所有适用项。", ["范围外的另一个项目", "规则已撤回", "所有记录条件匹配且无例外"],
            "处理范围外任务与测试通过的候选。", ["范围外判断", "候选采纳"],
            [["获得新判断或明确的范围变更", "悄悄扩大规则范围"], ["获得单独的采纳授权", "把测试通过当作采纳许可"]]),
        "ko": (
            "기록된 범위 안에서 판단 재사용", "재사용 규칙은 판단을 프로젝트, 구성 요소, 작업 형태, 위험, 판단 유형에 연결합니다. 적용 전에 유효성, 예외와 재검토 기한도 확인합니다.",
            "프로젝트 A의 병렬 작성자 규칙은 기록 조건이 일치할 때만 다음 작업에 적용됩니다. 프로젝트 B에는 새 판단이나 명시적인 범위 변경이 필요합니다.",
            "요청 문장이 비슷하거나 모델이 승인을 기억한다고 해서 규칙 범위가 넓어지지는 않습니다. 철회된 규칙도 현재 권한이 아닙니다.",
            "범위 일치는 기록된 적용 조건만 확인하며 판단의 옳음을 증명하지 않습니다. 증거와 권한은 별도로 다룹니다.",
            "규칙을 재사용하기 전에 무엇을 확인하나요?", ["기록된 범위, 예외와 유효성", "모든 비슷한 문장에 적용", "모델이 승인을 기억하는지 질문"],
            "무조건적인 재사용을 막는 조건을 모두 고르세요.", ["범위 밖의 다른 프로젝트", "규칙이 철회됨", "모든 기록 조건이 맞고 예외가 없음"],
            "범위 밖 작업과 테스트를 통과한 후보를 처리하세요.", ["범위 밖 판단", "후보 채택"],
            [["새 판단 또는 명시적인 범위 변경 받기", "암묵적으로 규칙 확대"], ["별도의 채택 승인 받기", "테스트 성공을 채택 허가로 취급"]]),
        "es": (
            "Reutilizar decisiones dentro del alcance registrado", "Una regla vincula la decisión con proyecto, componente, carga de trabajo, riesgo y tipo de decisión. Antes de aplicarla se revisan vigencia, excepciones y fecha de revisión.",
            "Una regla de escritores paralelos del proyecto A se reutiliza si coinciden sus condiciones. El proyecto B necesita otra decisión o un cambio explícito del alcance.",
            "Una petición parecida o el recuerdo del modelo no amplían el alcance. Una regla retirada tampoco concede autoridad actual.",
            "La coincidencia comprueba la aplicabilidad registrada, no la verdad ni la calidad de la decisión. La evidencia y la autorización siguen separadas.",
            "¿Qué se debe hacer antes de reutilizar una regla?", ["Comprobar alcance, excepciones y vigencia", "Aplicarla a toda frase similar", "Preguntar si el modelo recuerda la aprobación"],
            "¿Qué condiciones impiden reutilizarla sin más? Selecciona todas las aplicables.", ["Otro proyecto fuera del alcance", "La regla fue retirada", "Todas las condiciones coinciden y no hay excepciones"],
            "Trata una tarea fuera del alcance y un candidato cuyas pruebas pasan.", ["Decisión fuera del alcance", "Adopción del candidato"],
            [["Obtener otra decisión o un cambio explícito de alcance", "Ampliar la regla sin indicarlo"], ["Obtener autorización de adopción separada", "Usar el éxito de pruebas como permiso"]]),
    },
    "evidence_scope": {
        "en": (
            "Keep evidence within the tested boundary", "A result is tied to the tested artifact, property, data and oracle. A finite test result supports only its stated boundary; it does not prove every input or a person's understanding.",
            "A fixed suite passes for commit A. Record that suite and A. If the candidate changes, check again; a matching summary is not the same tested artifact.",
            "Two tests generated from the same mistaken expectation may agree. Their agreement alone does not establish an independent oracle.",
            "A harness failure can leave the claim unknown. REFUTED below assumes a valid counterexample to the stated property, not merely a crashed test process.",
            "What closure fits successful fixed tests with no complete proof?", ["BOUNDED to the tested scope", "PROVED for every possible case", "The human fully understands it"],
            "What should be bound to the result? Select all that apply.", ["The exact artifact identity", "The origin of the expected answer", "An enthusiastic summary as sole evidence"],
            "A valid in-scope counterexample was found by a completed check. Classify it and keep adoption separate.", ["Property status", "Adoption"],
            [["REFUTED within that scope", "SUPPORTED because a person agreed"], ["Requires its own authorization", "Automatically authorized by the check"]]),
        "ja": (
            "証拠を検査した範囲へ結び付ける", "結果は、検査した成果物、性質、データ、期待値の出所に結び付きます。有限のテスト結果が支えるのは明示した範囲であり、全入力や本人の理解を証明しません。",
            "固定したテストがコミットAで成功したら、そのテストとAを記録します。候補が変われば検査をやり直します。説明が同じでも検査対象が同じとは限りません。",
            "同じ誤った期待値から作った二つのテストは一致し得ます。一致だけでは期待値の独立性は確認できません。",
            "検査器の異常終了なら主張は不明のままになり得ます。下のREFUTEDは、検査器の停止ではなく、性質に対する有効な反例を確認した場合です。",
            "完全な証明がない固定テストの成功に合う閉包はどれですか。", ["検査範囲に限定したBOUNDED", "全ての場合についてPROVED", "本人が全て理解した"],
            "結果に結び付けるべきものを全て選んでください。", ["成果物そのものの識別情報", "期待値の出所", "意欲的な要約だけを証拠にする"],
            "完了した検査で範囲内の有効な反例が見つかりました。主張と採用を分けて扱ってください。", ["性質の状態", "採用"],
            [["その範囲でREFUTED", "人が同意したのでSUPPORTED"], ["別の許可が必要", "検査により自動的に許可される"]]),
        "zh-Hans": (
            "把证据限定在检查范围内", "结果绑定到被测产物、性质、数据和预期结果来源。有限测试只支持声明的范围，不能证明所有输入或一个人的理解。",
            "固定测试在提交A上通过，就记录该测试与A。候选改变后应重新检查；说明相同不代表测试产物相同。",
            "两个测试可能源于同一错误预期并给出一致结果。一致本身不能确立独立判定依据。",
            "检查器异常可能使主张仍然未知。下面的REFUTED指确认了性质的有效反例，而非测试进程崩溃。",
            "没有完整证明时，固定测试成功适合哪种闭包？", ["限于被测范围的BOUNDED", "覆盖所有情况的PROVED", "本人已经完全理解"],
            "应把哪些信息绑定到结果？选择所有适用项。", ["产物的准确身份", "预期答案的来源", "仅用积极的总结作为证据"],
            "已完成的检查找到范围内有效反例。分类主张并保持采纳独立。", ["性质状态", "采纳"],
            [["在该范围内REFUTED", "有人同意所以SUPPORTED"], ["需要单独授权", "检查自动授予权限"]]),
        "ko": (
            "증거를 검사 범위에 연결", "결과는 검사한 산출물, 속성, 데이터와 기대값의 출처에 연결됩니다. 유한한 테스트는 명시된 범위만 뒷받침하며 모든 입력이나 개인의 이해를 증명하지 않습니다.",
            "고정 테스트가 커밋 A에서 통과하면 테스트와 A를 기록합니다. 후보가 바뀌면 다시 검사합니다. 설명이 같아도 검사 대상이 같다는 뜻은 아닙니다.",
            "같은 잘못된 기대값으로 만든 두 테스트는 서로 일치할 수 있습니다. 일치만으로 독립적인 판정 기준이 확인되지는 않습니다.",
            "검사기 오류는 주장을 미확인 상태로 남길 수 있습니다. 아래 REFUTED는 프로세스 중단이 아니라 속성에 대한 유효한 반례를 확인한 경우입니다.",
            "완전한 증명 없이 고정 테스트가 성공하면 어떤 범위가 적절한가요?", ["검사 범위로 제한한 BOUNDED", "모든 경우에 대한 PROVED", "본인이 모두 이해함"],
            "결과에 연결해야 할 정보를 모두 고르세요.", ["정확한 산출물 식별 정보", "기대 답의 출처", "긍정적인 요약만을 증거로 사용"],
            "완료된 검사에서 범위 내 유효한 반례가 나왔습니다. 주장 상태와 채택을 분리하세요.", ["속성 상태", "채택"],
            [["해당 범위에서 REFUTED", "사람이 동의했으니 SUPPORTED"], ["별도 승인이 필요함", "검사가 자동으로 승인함"]]),
        "es": (
            "Vincular la evidencia al límite comprobado", "El resultado se vincula al artefacto, propiedad, datos y origen de la expectativa. Una prueba finita respalda su alcance declarado; no demuestra todas las entradas ni la comprensión de una persona.",
            "Una batería fija pasa para el commit A. Registra la batería y A. Si cambia el candidato, vuelve a comprobarlo; un resumen igual no identifica el mismo artefacto.",
            "Dos pruebas pueden coincidir al compartir una expectativa errónea. Esa coincidencia no establece un criterio independiente.",
            "Un fallo del comprobador puede dejar la afirmación sin resolver. REFUTED abajo supone un contraejemplo válido de la propiedad, no simplemente un proceso de prueba que falla.",
            "¿Qué cierre corresponde a pruebas fijas exitosas sin demostración completa?", ["BOUNDED al alcance probado", "PROVED para todos los casos", "La persona lo comprende por completo"],
            "¿Qué debe vincularse al resultado? Selecciona todo lo aplicable.", ["La identidad exacta del artefacto", "El origen de la respuesta esperada", "Un resumen entusiasta como única evidencia"],
            "Una comprobación terminada encuentra un contraejemplo válido dentro del alcance. Clasifica la propiedad y separa la adopción.", ["Estado de la propiedad", "Adopción"],
            [["REFUTED dentro de ese alcance", "SUPPORTED porque alguien estuvo de acuerdo"], ["Necesita autorización propia", "La comprobación la autoriza automáticamente"]]),
    },
}


def builtin_exercise(concept_id, locale):
    if concept_id not in MATERIALS or locale not in LANGUAGES:
        raise LedgerError("LEARNING_MATERIAL_NOT_FOUND")
    (title, principle, example, counterexample, limit, prompt1, options1, prompt2, options2,
     prompt3, parts, options3) = MATERIALS[concept_id][locale]
    from copy import deepcopy
    from .learning_exercises import validate_exercise
    choice = lambda ids, labels: [{"id": identity, "label": label} for identity, label in zip(ids, labels)]
    spec = {"schema_version": 1, "id": concept_id + "-v1-" + locale, "concept_id": concept_id, "locale": locale,
            "lesson": {"title": title, "principle": principle, "worked_example": example,
                       "counterexample": counterexample, "limitations": [limit],
                       "sources": deepcopy([CONSTITUTION, GIT] if concept_id == "parallel_writers" else [CONSTITUTION])},
            "questions": [
                {"id": "principle", "mode": "single_choice", "competency": "SELF_EXPLANATION", "prompt": prompt1,
                 "choices": choice(("bounded", "overclaim", "authority"), options1), "rubric": {"expected": "bounded"}},
                {"id": "boundary", "mode": "select_all", "competency": "COUNTEREXAMPLE", "prompt": prompt2,
                 "choices": choice(("first", "second", "unrelated"), options2), "rubric": {"expected": ["first", "second"]}},
                {"id": "application", "mode": "structured", "competency": "APPLICATION", "prompt": prompt3,
                 "parts": [{"id": "scope", "prompt": parts[0], "choices": choice(("bounded", "overclaim"), options3[0])},
                           {"id": "authority", "prompt": parts[1], "choices": choice(("separate", "automatic"), options3[1])}],
                 "rubric": {"expected": {"scope": "bounded", "authority": "separate"}}}],
            "passing_score": 3,
            "provenance": {"author": {"kind": "EXTERNAL_MODEL", "identity": "Verantyx implementation agent",
                                      "model": "UNRECORDED", "provider": "OpenAI"},
                           "oracle": "Source-based teaching rubric, written with the lesson by the implementation agent",
                           "data": "Three fixed, synthetic scenarios; no live learner data",
                           "review": "Implementation tests; independent educational review and learning efficacy not established"}}
    return validate_exercise(spec)
