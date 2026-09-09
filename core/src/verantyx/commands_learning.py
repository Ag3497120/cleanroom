"""CLI integration for fixed exercises and optional review schedules."""
from datetime import datetime, timezone
from pathlib import Path

from .domain.codec import decode
from .errors import LedgerError

COMMANDS = {"learn-material", "learn-exercise-register", "learn-exercise-answer", "learn-review-schedule",
            "learn-review-cancel", "learn-due"}
READ_COMMANDS = {"learn-material", "learn-due"}
LABELS = {
    "en": {"title": "Optional practice and review", "example": "Example", "counterexample": "Counterexample",
           "limit": "Limit", "source": "Source", "question": "Question", "due": "Due in UTC",
           "none": "No review is due.", "more": "Showing {shown} of {total} due reviews.",
           "score": "{status}: {score}/{maximum} fixed questions", "saved": "Saved with an append-only receipt.",
           "boundary": "Scores assess these fixed answers only. The respondent is not authenticated; independent mastery is not established.",
           "cancelled": "Review cancelled", "scheduled": "Review scheduled", "off": "Learning is off; due items are hidden."},
    "ja": {"title": "任意の課題と復習", "example": "実例", "counterexample": "反例", "limit": "限界",
           "source": "出典", "question": "課題", "due": "復習期限（UTC）", "none": "期限を迎えた復習はありません。",
           "more": "期限を迎えた{total}件のうち{shown}件を表示しています。", "score": "{status}: 固定課題 {score}/{maximum} 問一致",
           "saved": "追記した履歴と受領記録を保存しました。",
           "boundary": "採点はこの固定課題への回答だけを対象にします。回答者の本人確認と、独立した習熟の確認は行っていません。",
           "cancelled": "復習予定を取消しました", "scheduled": "復習予定を保存しました", "off": "学習が停止中のため期限一覧を表示しません。"},
    "zh-Hans": {"title": "可选练习与复习", "example": "实例", "counterexample": "反例", "limit": "限制",
           "source": "来源", "question": "题目", "due": "复习期限（UTC）", "none": "没有到期复习。",
           "more": "显示{total}项到期复习中的{shown}项。", "score": "{status}：固定题目匹配 {score}/{maximum}",
           "saved": "已保存追加历史及回执。", "boundary": "评分只针对这些固定答案。未认证答题者，也未独立确认其掌握程度。",
           "cancelled": "已取消复习", "scheduled": "已安排复习", "off": "学习已关闭，因此隐藏到期项目。"},
    "ko": {"title": "선택형 연습과 복습", "example": "실례", "counterexample": "반례", "limit": "한계",
           "source": "출처", "question": "문제", "due": "복습 기한(UTC)", "none": "기한이 된 복습이 없습니다.",
           "more": "기한이 된 {total}개 중 {shown}개를 표시합니다.", "score": "{status}: 고정 문제 {score}/{maximum}개 일치",
           "saved": "추가 이력과 수신 기록을 저장했습니다.", "boundary": "채점은 고정 문제의 답만 평가합니다. 응답자 인증과 독립적인 숙련도 확인은 수행하지 않았습니다.",
           "cancelled": "복습 취소됨", "scheduled": "복습 예약됨", "off": "학습이 꺼져 있어 기한 목록을 숨깁니다."},
    "es": {"title": "Práctica y repaso opcionales", "example": "Ejemplo", "counterexample": "Contraejemplo", "limit": "Límite",
           "source": "Fuente", "question": "Pregunta", "due": "Fecha de repaso en UTC", "none": "No hay repasos pendientes.",
           "more": "Se muestran {shown} de {total} repasos pendientes.", "score": "{status}: {score}/{maximum} respuestas fijas coinciden",
           "saved": "Se guardaron el historial añadido y el comprobante.",
           "boundary": "La puntuación evalúa solo estas respuestas fijas. No se autentica al participante ni se establece un dominio independiente.",
           "cancelled": "Repaso cancelado", "scheduled": "Repaso programado", "off": "El aprendizaje está desactivado; se ocultan los repasos."},
}
ERRORS = {
    "en": ("The exercise or structured answer does not match the fixed format.", "The exercise identity, concept or frozen rubric differs.",
           "Register this exercise before answering or scheduling it.", "The assessment does not match the recorded answer and rubric.",
           "Use an explicit UTC time at or after scheduling, with valid review intervals.", "No built-in lesson exists for this concept; register a custom exercise."),
    "ja": ("課題または構造化回答が固定形式に一致しません。", "課題の識別子・概念・固定した採点基準が一致しません。",
           "回答や予定の前に、この課題を登録してください。", "採点結果が記録した回答と採点基準に一致しません。",
           "予定操作以降の明示したUTC時刻と、有効な復習間隔を指定してください。", "この概念の組込み教材はありません。独自の課題を登録してください。"),
    "zh-Hans": ("练习或结构化答案不符合固定格式。", "练习标识、概念或冻结的评分标准不一致。", "答题或安排复习前请先注册练习。",
           "评分与已记录答案和标准不一致。", "请使用不早于安排操作的明确UTC时间和有效复习间隔。", "此概念没有内置教材，请注册自定义练习。"),
    "ko": ("문제 또는 구조화된 답이 고정 형식과 일치하지 않습니다.", "문제 식별자, 개념 또는 고정 채점 기준이 다릅니다.",
           "답변하거나 예약하기 전에 문제를 등록하세요.", "채점 결과가 기록된 답과 기준에 맞지 않습니다.",
           "예약 시점 이후의 명시적인 UTC 시각과 유효한 복습 간격을 지정하세요.", "이 개념의 내장 교재가 없습니다. 사용자 문제를 등록하세요."),
    "es": ("El ejercicio o la respuesta estructurada no coincide con el formato fijo.", "Difieren la identidad, el concepto o el criterio fijado.",
           "Registra el ejercicio antes de responder o programarlo.", "La evaluación no coincide con la respuesta y el criterio registrados.",
           "Indica una hora UTC explícita no anterior a la programación e intervalos válidos.", "No hay material integrado para este concepto; registra un ejercicio propio."),
}
ERROR_CODES = ("LEARNING_EXERCISE_INVALID", "LEARNING_EXERCISE_CONFLICT", "LEARNING_EXERCISE_NOT_FOUND",
               "LEARNING_ASSESSMENT_INVALID", "LEARNING_REVIEW_TIME", "LEARNING_MATERIAL_NOT_FOUND")


def translation_entries():
    """The integrator can merge these keys into the five existing CLI catalogs."""
    return {locale: {**{"learning." + key: value for key, value in labels.items()},
                     **{"error." + key: value for key, value in zip(ERROR_CODES, ERRORS[locale])}}
            for locale, labels in LABELS.items()}


def register(sub):
    for command in sorted(COMMANDS):
        parser = sub.add_parser(command, add_help=False, allow_abbrev=False)
        parser.add_argument("run_id")
        if command != "learn-due":
            parser.add_argument("--candidate", required=True)
            parser.add_argument("--exercise", required=command in ("learn-exercise-answer", "learn-review-schedule", "learn-review-cancel"))
        if command in READ_COMMANDS:
            parser.add_argument("--archive")
        else:
            parser.add_argument("--key", required=True)
            parser.add_argument("--expected-revision", type=int)
        if command == "learn-exercise-register":
            parser.add_argument("--document")
        elif command == "learn-exercise-answer":
            parser.add_argument("--answers", required=True)
            parser.add_argument("--origin", choices=("LOCAL_OPERATOR", "EXTERNAL_MODEL", "MIXED", "UNKNOWN"), default="UNKNOWN")
            parser.add_argument("--identity", default="Unattributed local submission")
            parser.add_argument("--model")
            parser.add_argument("--provider")
        elif command == "learn-review-schedule":
            parser.add_argument("--due", required=True)
            parser.add_argument("--interval-days", action="append", type=int)
            parser.add_argument("--reason", required=True)
        elif command == "learn-review-cancel":
            parser.add_argument("--reason", required=True)
        elif command == "learn-due":
            parser.add_argument("--at")


def utc_timestamp(value):
    if type(value) is not str or not (value.endswith("Z") or value.endswith("+00:00")):
        raise LedgerError("LEARNING_REVIEW_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError("UTC required")
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, OverflowError):
        raise LedgerError("LEARNING_REVIEW_TIME") from None


def _document(path):
    from .learning_exercises import MAX_EXERCISE_BYTES
    from .adapters.observations import read_document
    # Use the existing bounded nonblocking regular-file reader. A FIFO or
    # device must not stop the CLI, and symlinks must not select another file.
    return decode(read_document(path, MAX_EXERCISE_BYTES), limit=MAX_EXERCISE_BYTES)


def dispatch(root, configuration, args, locale):
    from .learning_exercises import control_exercises, inspect_exercises
    command = args.command
    if command == "learn-due":
        return inspect_exercises(root, configuration, args.run_id, archive_id=args.archive,
                                 as_of=utc_timestamp(args.at) if args.at is not None else None)
    if command == "learn-material":
        return inspect_exercises(root, configuration, args.run_id, candidate_id=args.candidate,
                                 exercise_id=args.exercise, archive_id=args.archive)
    kwargs = {"candidate_id": args.candidate, "exercise_id": args.exercise,
              "key": args.key, "expected_revision": args.expected_revision}
    if command == "learn-exercise-register":
        return control_exercises(root, configuration, args.run_id, "register",
                                 document=_document(args.document) if args.document else None, **kwargs)
    if command == "learn-exercise-answer":
        return control_exercises(root, configuration, args.run_id, "answer", answers=_document(args.answers),
                                 answer_origin={"kind": args.origin, "identity": args.identity,
                                                "model": args.model, "provider": args.provider}, **kwargs)
    if command == "learn-review-schedule":
        return control_exercises(root, configuration, args.run_id, "schedule", due_at=utc_timestamp(args.due),
                                 intervals_days=args.interval_days, reason=args.reason, **kwargs)
    return control_exercises(root, configuration, args.run_id, "cancel", reason=args.reason, **kwargs)


def display(result, locale, command):
    from .cli import visible
    labels = LABELS[locale]
    print(labels["title"])

    def show_material(material):
        lesson = material["lesson"]
        print(visible(lesson["title"]))
        print(visible(lesson["principle"]))
        for field, key in (("worked_example", "example"), ("counterexample", "counterexample")):
            print(labels[key] + ": " + visible(lesson[field]))
        for limitation in lesson["limitations"]:
            print(labels["limit"] + ": " + visible(limitation))
        for source in lesson["sources"]:
            print(labels["source"] + ": " + visible(source["title"]) + " — " + visible(source["locator"]))
        print(material["id"] + " / " + material["exercise_hash"])
        for question in material["questions"]:
            print(labels["question"] + " " + question["id"] + ": " + visible(question["prompt"]))
            parts = question.get("parts", [{"id": question["id"], "prompt": "", "choices": question.get("choices", [])}])
            for part in parts:
                if part["prompt"]:
                    print("  " + part["id"] + ": " + visible(part["prompt"]))
                for option in part["choices"]:
                    print("  " + option["id"] + ": " + visible(option["label"]))

    if command == "learn-due":
        if result.get("suppressed") == "LEARNING_OFF":
            print(labels["off"])
        elif not result["items"]:
            print(labels["none"])
        else:
            for item in result["items"]:
                print(visible(item["concept"]) + " / " + item["candidate_id"] + " / " + item["exercise_id"])
                print(labels["due"] + ": " + item["due_at"])
            print(labels["more"].format(shown=len(result["items"]), total=result["total_due"]))
    elif result.get("material") is not None:
        show_material(result["material"])
    else:
        candidates = [result["candidate"]] if "candidate" in result else result.get("candidates", [])
        selected = set(result.get("candidate_ids", [result.get("candidate_id")]))
        for candidate in candidates:
            if selected and candidate["id"] not in selected:
                continue
            for exercise in candidate.get("exercises", []):
                if command in ("learn-material", "learn-exercise-register"):
                    show_material(exercise["material"])
                elif command == "learn-exercise-answer" and exercise["assessments"]:
                    result_value = exercise["assessments"][-1]["result"]
                    print(exercise["exercise_id"] + ": " + labels["score"].format(**result_value))
                if exercise["review"] is not None:
                    review = exercise["review"]
                    print(labels["cancelled"] if review["status"] == "CANCELLED" else labels["due"] + ": " + review["due_at"])
        print(labels["saved"])
    print(labels["boundary"])
