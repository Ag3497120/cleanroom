# Reading Cleanroom comfortably

[English](#english) · [日本語](#日本語) · [简体中文](#简体中文) · [한국어](#한국어) · [Español](#español)

## English

At 120 columns × 28 rows, the CLI uses two equal-width panes; at 80 × 48 it can stack them. Smaller windows show the active pane without blocking work. Empty Enter still cycles Agent → Memo → Search. Terminal font size belongs to your terminal application; the browser demo has its own text-size controls.

User requests have a shaded background; AI responses do not. System activity is a separate area. Owner labels distinguish notes, proposals and unknowns. The active pane has both a thicker outline and a text label; color is not the only cue. No ability score is implied.

The website keeps body text at readable sizes, uses equal-width panels on wide displays, and switches to the selected panel below 960 CSS pixels. Agent / Memo / Search buttons remain visible. Both panes stay mounted, so changing input does not erase drafts, notes or scroll position. Browser text-size buttons adjust 16–22 px; browser zoom remains available. The terminal itself cannot independently change font sizes in its two panes.

Use `VERANTYX_REDUCE_MOTION=1 verantyx`, `NO_COLOR=1 verantyx`, or `verantyx --plain` when preferred. The website follows `prefers-reduced-motion`. The video has playback controls; the optional animated GIF is behind an explicit disclosure, with a static-image link. README GIF playback depends on the GitHub client, so a static alternative is linked next to it.

The browser rehearsal mirrors input switching, references, private memos, continuous messages and example review choices. It keeps data in this tab, not in the CLI database. Its scripted estimates and results are not live work or evidence. Subscription execution, actual compaction, durable sessions and project edits belong to the local CLI; Ask your AI is a separate explicit connection.

These source changes are not a claim of cross-platform visual, accessibility or live-model test coverage.

## 日本語

横120文字 × 縦28行以上では同じ幅の左右2欄、横80文字 × 縦48行以上では上下表示、それより小さい場合は操作中の欄を表示します。サイズを理由に進行を止めません。空EnterによるAgent → メモ → 検索は同じです。端末の文字サイズは端末アプリ側で変更し、Web体験版では画面内の文字サイズボタンも使えます。

依頼は背景色付き、AI回答は背景色なし、システム通知は別欄です。Ownerはメモ・AI提案・未確認事項をラベルでも区別します。入力先は太い枠と文字で示し、色だけに依存しません。

Webは960 CSS px未満で選択中の欄を広く表示します。切り替えても欄を破棄しないため、下書き・メモ・スクロール位置を保持します。文字ボタンは16〜22px、ブラウザの拡大表示も利用できます。端末の左右それぞれに異なるフォントサイズを設定する機能ではありません。

動きを減らす場合は`VERANTYX_REDUCE_MOTION=1 verantyx`、色なしは`NO_COLOR=1 verantyx`、通常表示は`verantyx --plain`です。WebはOSの動きを減らす設定に従います。動画は操作ボタン付き、GIFは明示的に開く形式で静止画も用意します。READMEのGIF再生はGitHubクライアントに依存するため、横に静止画リンクを置いています。

ブラウザ体験版は入力先の切り替え、参照、メモ、連続した会話、許可選択の例を再現します。保存先はそのタブ内であり、CLIのDBではありません。例の予想時間や結果は実作業・証拠ではありません。サブスク実行・実際の圧縮・永続セッション・ファイル編集はローカルCLIで行い、「AIに頼む」の接続は明示操作として分けます。

今回のソース変更は、全OSの表示・アクセシビリティ・実モデル検証済みを意味しません。

## 简体中文

120列 × 28行起使用等宽左右面板；80列 × 48行起可上下排列；更小时显示活动面板，不阻止使用。空Enter仍在Agent、备忘和搜索之间循环。终端字体由终端应用设置；浏览器体验版提供字号按钮。

网页小于960 CSS px时显示选中的面板，保留草稿和滚动位置。字号按钮可调16–22px。请求有底色，回答无底色，系统状态另列。活动位置以边框和文字共同标识。可使用减少动态效果、无色或纯文本模式；视频可暂停，GIF可选择打开，另有静态图片。

浏览器体验复现切换输入、引用、备忘、连续对话和示例授权。数据仅留在此标签页，不是CLI数据库。脚本估时与结果不是真实工作或证据。订阅执行、实际压缩、持久会话及文件编辑需要本地CLI；“请求我的AI”单独明确连接。

## 한국어

120열 × 28행부터 같은 너비의 좌우 패널을, 80열 × 48행부터 상하 패널을 사용합니다. 더 작으면 활성 패널만 보여주며 진행을 막지 않습니다. 빈 Enter 전환은 같습니다. 터미널 글꼴 크기는 터미널 앱에서, 웹 체험 글자 크기는 화면 버튼에서 바꿉니다.

웹은 960 CSS px 미만에서 선택한 패널을 표시하며 초안과 스크롤 위치를 유지합니다. 글자 버튼은 16–22px입니다. 요청 배경, 응답, 시스템 상태를 분리하고 활성 위치를 테두리와 글자로 함께 표시합니다. 동작 감소, 무색, 일반 텍스트 모드를 제공하며 영상 제어와 선택형 GIF, 정지 이미지를 사용합니다.

브라우저는 입력 전환, 참조, 메모, 연속 대화와 허용 선택 예시를 재현합니다. 데이터는 이 탭에만 있으며 CLI DB가 아닙니다. 대본의 예상 시간과 결과는 실제 작업이나 증거가 아닙니다. 구독 실행, 실제 압축, 영구 세션, 파일 편집은 로컬 CLI에서 하며 AI 연결은 별도 명시적 조작입니다.

## Español

Desde 120 columnas × 28 filas se usan paneles iguales en paralelo; desde 80 × 48 pueden apilarse. Las ventanas menores muestran el panel activo sin bloquear. Enter vacío sigue recorriendo Agent, Nota y Buscar. La fuente del terminal se cambia en su aplicación; el ensayo web tiene controles de tamaño.

Por debajo de 960 píxeles CSS, la web muestra el panel seleccionado y conserva borradores y posición. Los botones ajustan 16–22px. Las peticiones tienen fondo, las respuestas no; la actividad va aparte. Borde y etiqueta identifican el panel activo. Hay movimiento reducido, modo sin color y texto plano; el vídeo tiene controles, el GIF es opcional y hay imagen estática.

El ensayo reproduce cambios de entrada, referencias, notas, conversación continua y elecciones de ejemplo. Los datos permanecen en esta pestaña, no en la base de la CLI. Las estimaciones y resultados del guion no son trabajo real ni evidencia. Suscripciones, compactación real, sesiones duraderas y edición requieren la CLI local; Pedir a mi IA es una conexión explícita aparte.
