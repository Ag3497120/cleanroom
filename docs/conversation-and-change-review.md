# Conversation, scheduling and change review

[English](#english) | [日本語](#日本語) | [简体中文](#简体中文) | [한국어](#한국어) | [Español](#español)

## English

Fresh setup starts in English, independent of the operating-system language. A saved project language, `--lang`, or an explicit `VERANTYX_LANG` setting takes precedence. Select **Language** in `verantyx setup` or `/verantyx setup language` to change interface guidance. Existing user and AI records keep their original language. Legacy advanced screens may still have untranslated labels.

Agent keeps a continuous session conversation. Your messages have a soft background; model answers do not. Operational notifications remain separate. Up to 80 conversation pages are kept in this session view; older saved work remains accessible through History. This is a display limit, not a deletion of the ledger.

While work runs, a spinner and gentle input pulse indicate activity, not correctness. `VERANTYX_REDUCE_MOTION=1` disables animation. `NO_COLOR` keeps textual roles and statuses without relying on color.

Submitting another instruction offers two choices:

- **Queue**: run after successful completion of the current task, in this open CLI only. It is not a timed or durable scheduler. Failure or an unresolved owner decision pauses the queue. `/queue` lists, resumes or removes requests.
- **Next model step**: record and send the instruction before the next model invocation. It does not interrupt an in-flight tool or model call. If that boundary has passed, the unsent instruction is kept as a paused queued request. New attachments require their own next-task send approval.

Before the built-in runtime writes a candidate file, Agent displays its diff, destination, hashes and candidate parent folders. The choices appear at the Agent composer:

- **Allow once**: only the displayed candidate version.
- **Allow in this workspace**: remember permission for isolated candidate edits here until revoked.
- **Allow permanently**: remember permission for isolated candidate edits across workspaces until revoked.
- **Deny**: leave this operation unapplied. `/approvals` can revoke saved grants.

These choices do not authorize deletion, shell commands, publication, external tools or adoption into the original project. New parent folders are created only inside the isolated candidate version. If the original is outside the approved read scope, the screen explicitly shows proposed content rather than claiming a verified source diff. Binary files show sizes and hashes, not an invented text diff.

**Owner focus is never taken by a candidate-change review.** Continue writing or searching. Empty Enter still cycles Agent > Memo > Search > Agent. After returning to Agent, arrows choose and Enter confirms. PgUp/PgDn and the wheel scroll the active pane even while an inline review waits.

External harnesses can perform their own host operations. This interface does not intercept those operations or claim to review their writes; the external harness and sandbox retain their own permission controls. Change receipts preserve the selected mode and candidate hashes. A reopened historical conversation shows those receipts without fabricating an old diff from a newer file.

## 日本語

未設定の初回起動はOSの言語にかかわらず英語です。保存済みの言語、`--lang`、明示的な`VERANTYX_LANG`は優先します。`verantyx setup`のLanguage、または`/verantyx setup language`でガイドの言語を変えられます。保存済みの会話は翻訳・上書きしません。一部の旧詳細画面には未翻訳の表示が残ります。

Agentでは会話が続いて表示されます。自分の発言は淡い背景、AIの回答は通常の背景、操作通知は別欄です。このセッションの表示は最大80ページで、古い仕事の台帳はHistoryから開けます。削除ではありません。

作業中はスピナーと入力欄の穏やかな明滅を表示します。成功を意味する表示ではありません。`VERANTYX_REDUCE_MOTION=1`で動きを抑え、`NO_COLOR`でも文字で状態を確認できます。

- 作業中の追加依頼は、完了後の**予約**か、**次のモデル呼び出しで渡す**かを矢印とEnterで選びます。
- 予約はこのCLIを開いている間だけの順次実行です。時刻指定・永続予約ではありません。失敗や判断待ちでは保留し、`/queue`で確認・再開・削除します。
- 即時反映を選んでも、実行中のモデルやツールを強制停止しません。間に合わなかった未送信の指示は保留した予約へ残します。新しい添付には次の仕事での送信確認が必要です。
- 内蔵ツールの候補書き込み前に、差分・対象パス・ハッシュ・候補の親フォルダを表示します。Agentの入力欄付近で「一度だけ許可」「このワークスペース内で許可」「永久に許可」「拒否」を選べます。
- ワークスペース・永久の許可は取り消すまで保存されます。`/approvals`で取り消し、以後の編集確認を戻せます。本体採用・削除・公開・シェル・外部ツールの許可には変わりません。
- Ownerでメモや検索をしていてもカーソルを奪いません。空欄EnterでAgent→メモ→検索→Agentを巡回し、Agentへ戻ってから矢印とEnterで選びます。確認中も選択側のスクロールは使えます。
- 元ファイルを読む権限がなければ「元ファイルは未読」とし、提案内容を検証済みの差分とは呼びません。バイナリはサイズとハッシュを表示します。
- 外部ハーネス独自のファイル操作は、この確認画面で捕捉・制御できるとは限りません。そのハーネスとサンドボックス側の権限管理が必要です。過去の記録は承認モードとハッシュを保持し、新しいファイルから昔の差分を捏造しません。

## 简体中文

首次未配置时默认英语，不跟随操作系统语言；已保存语言、`--lang`或显式`VERANTYX_LANG`优先。在`verantyx setup`的Language或`/verantyx setup language`切换指南语言。历史对话保留原语言，部分旧高级界面可能尚未翻译。

Agent连续显示会话：用户消息有柔和背景，模型回答无背景，操作通知分开。本次视图最多保留80页，更早的已保存工作仍在History中。旋转指示与输入栏缓慢变化表示工作中，不表示成功。`VERANTYX_REDUCE_MOTION=1`关闭动画，`NO_COLOR`不依赖颜色。

- 运行中提交新请求，可选择**排队**或**下次模型调用传入**。不会强制中断模型或工具。
- 队列只存在于当前打开的CLI，不是定时或持久计划；失败或等待个人决定时暂停。`/queue`查看、恢复或移除。错过当前边界的指示保留为暂停队列，不静默重发。新附件单独确认发送。
- 内置候选写入前显示差异、路径、哈希与候选父文件夹。在Agent输入区选择允许一次、在本工作区允许、永久允许或拒绝。后两项保存到撤销为止，`/approvals`可撤销。
- 此授权不包含删除、发布、命令、外部工具或应用到原项目。源文件未获准读取时，只显示提议内容；二进制显示大小与哈希。
- 确认等待不会抢走Owner焦点。空白Enter循环Agent、笔记、搜索、Agent；返回Agent后用方向键与Enter选择。等待时仍能滚动当前栏。
- 外部运行器的独立操作由其自身权限与沙盒管理；本界面不保证拦截。历史凭据保留批准方式与哈希，不从新版文件伪造旧差异。

## 한국어

처음 설정하지 않은 상태에서는 OS 언어와 무관하게 영어로 시작합니다. 저장된 언어, `--lang`, 명시적 `VERANTYX_LANG`가 우선합니다. `verantyx setup`의 Language 또는 `/verantyx setup language`에서 안내 언어를 바꿉니다. 기존 대화는 원래 언어로 남고 일부 고급 구형 화면은 미번역일 수 있습니다.

Agent 대화는 이어서 표시됩니다. 내 메시지는 부드러운 배경, 모델 답변은 기본 배경이며 작업 알림은 별도입니다. 세션 화면은 최대 80페이지이고 이전 기록은 History에 남습니다. 스피너와 입력란의 느린 변화는 진행 중 표시이지 성공 증명이 아닙니다. `VERANTYX_REDUCE_MOTION=1`로 애니메이션을 끄고 `NO_COLOR`로 색 없이 사용할 수 있습니다.

- 작업 중 요청은 **예약** 또는 **다음 모델 호출에 전달**을 선택합니다. 실행 중 모델이나 도구를 강제 중지하지 않습니다.
- 예약은 열린 CLI에서만 순차 실행하며 시간 지정·영구 예약이 아닙니다. 실패·사람의 판단 대기 시 멈추고 `/queue`로 확인·재개·삭제합니다. 전달 시점을 지난 지시는 미전송 예약으로 보류합니다. 새 첨부는 별도 전송 확인이 필요합니다.
- 내장 후보 쓰기 전에 차이·경로·해시·후보 상위 폴더를 보여 줍니다. Agent 입력란에서 한 번 허용, 이 작업 공간에서 허용, 항상 허용, 거부를 선택합니다. 저장한 허용은 취소할 때까지 유지되며 `/approvals`로 취소합니다.
- 삭제·공개·명령·외부 도구·본체 적용 권한은 주지 않습니다. 원본 읽기가 허용되지 않았다면 제안 내용으로 표시하고, 바이너리는 크기와 해시로 표시합니다.
- 확인 대기는 Owner 포커스를 빼앗지 않습니다. 빈 Enter로 Agent→메모→검색→Agent를 이동한 뒤 화살표·Enter로 선택합니다. 대기 중에도 현재 창을 스크롤할 수 있습니다.
- 외부 하네스 자체 작업은 해당 하네스·샌드박스가 관리합니다. 이 화면이 모든 쓰기를 차단한다고 보장하지 않습니다. 과거 기록은 승인 방식과 해시를 보존하고 최신 파일로 과거 차이를 만들어 내지 않습니다.

## Español

La primera configuración sin preferencias empieza en inglés, independientemente del idioma del sistema. Tienen prioridad el idioma guardado, `--lang` o `VERANTYX_LANG` explícito. Cambia las guías en Language de `verantyx setup` o con `/verantyx setup language`. Las conversaciones conservan su idioma; algunas pantallas avanzadas heredadas pueden no estar traducidas.

Agent mantiene una conversación continua: tus mensajes tienen fondo suave y las respuestas no. Las notificaciones quedan separadas. La vista conserva hasta 80 páginas por sesión; History mantiene el trabajo guardado anterior. El indicador y el pulso suave significan actividad, no éxito. `VERANTYX_REDUCE_MOTION=1` desactiva la animación y `NO_COLOR` evita depender del color.

- Durante una tarea puedes **poner en cola** o **enviar al siguiente paso del modelo**, sin interrumpir llamadas o herramientas en curso.
- La cola solo existe en esta CLI abierta; no es persistente ni por hora. Se pausa ante fallos o decisiones pendientes; `/queue` permite revisar, reanudar o quitar solicitudes. Una instrucción que llegó tarde queda en cola pausada, sin reenvío silencioso. Los adjuntos nuevos requieren aprobación de envío.
- Antes de escribir candidatos internos se muestran diff, ruta, hashes y carpetas padre. En el compositor Agent puedes permitir una vez, en este espacio, permanentemente o rechazar. Los permisos guardados duran hasta revocarlos con `/approvals`.
- Esto no concede permisos de eliminación, publicación, comandos, herramientas externas ni aplicación al original. Sin lectura autorizada del original se muestra contenido propuesto, no un diff verificado; los binarios muestran tamaño y hashes.
- La revisión no roba el foco de Owner. Enter vacío alterna Agent, Nota, Buscar y Agent; al volver, flechas y Enter seleccionan. El panel activo sigue permitiendo desplazamiento.
- Los arneses externos controlan sus propias operaciones y su sandbox. Esta interfaz no garantiza interceptar todas sus escrituras. Los recibos históricos conservan modo y hashes, sin inventar diffs antiguos con archivos nuevos.


[Independent sessions, live insights, estimates and storage / セッション・実装中の理解・見積もり・保存](live-learning-and-sessions.md)
