# Reading Cleanroom comfortably

[English](#english) · [日本語](#日本語) · [简体中文](#简体中文) · [한국어](#한국어) · [Español](#español)

## English

With fewer than 40 rows or 120 columns, the CLI collapses repeated frames, long hints and the separate system-activity panel to give the conversation more room. Answers are still complete. Use `/details` for activity, `F2` for views, or `F5` / `/fullscreen` for a full-width reading pane; `F5` / `/split` returns. The footer suggests enlarging or maximizing the terminal, without blocking work.

Drag in Agent, Owner, Evidence, Notebook, Review or an expanded activity panel to select text. `Ctrl+C` copies a selection; `F6` / `/copy` copies the selection or the current pane. Copying removes display-only wrapping and shaded padding. An active choice menu instead copies the highlighted option and its description. If no system clipboard helper is available, the notice explicitly says the copy is internal only. `F7` / `/mouse` enables the terminal's own selection and Copy; press `F7` again for application mouse controls. Expand one pane first to avoid selecting both columns. Some keyboards require `Fn` with function keys.

Hold a drag at the top or bottom edge to scroll and extend the selection; the wheel also keeps its anchor. On Mac, releasing a mouse selection copies it to the system clipboard while retaining the highlight. Command+C is handled by the terminal; F6 copies explicitly. See [Web tools and reading controls](../core/docs/WEB_AND_READING.ja.md).

Scrolling uses displayed rows, with two-row overlap for page moves. Reading older messages holds that position while work continues; a new-text notice points to `Ctrl+End` / `/latest` to resume following. `Ctrl+Home` / `/top` goes to the beginning of the current view. `F3` focuses text; arrows navigate, Shift+arrows select, and Enter or Esc returns to input. These are local CLI controls, not a claim that the browser rehearsal gained identical clipboard behavior.

At 120 columns × 28 rows, the CLI gives about 70% of the width to Agent and 30% to Owner; at 80 × 48 it can stack them. Smaller windows show the active pane without blocking work. Empty Enter still cycles Agent → Memo → Search. Terminal font size belongs to your terminal application; the browser demo has its own text-size controls.

User requests have a shaded background; AI responses do not. System activity is a separate area. Owner labels distinguish notes, proposals and unknowns. The active pane has both a thicker outline and a text label; color is not the only cue. No ability score is implied.

The website keeps body text at readable sizes, uses equal-width panels on wide displays, and switches to the selected panel below 960 CSS pixels. Agent / Memo / Search buttons remain visible. Both panes stay mounted, so changing input does not erase drafts, notes or scroll position. Browser text-size buttons adjust 16–22 px; browser zoom remains available. The terminal itself cannot independently change font sizes in its two panes.

Use `VERANTYX_REDUCE_MOTION=1 verantyx`, `NO_COLOR=1 verantyx`, or `verantyx --plain` when preferred. The website follows `prefers-reduced-motion`. The video has playback controls; the optional animated GIF is behind an explicit disclosure, with a static-image link. README GIF playback depends on the GitHub client, so a static alternative is linked next to it.

The browser rehearsal mirrors input switching, references, private memos, continuous messages and example review choices. It keeps data in this tab, not in the CLI database. Its scripted estimates and results are not live work or evidence. Subscription execution, actual compaction, durable sessions and project edits belong to the local CLI; Ask your AI is a separate explicit connection.

These source changes are not a claim of cross-platform visual, accessibility or live-model test coverage.

## 日本語

縦40行未満または横120文字未満では、重複した枠、長い操作説明、独立したシステム通知欄を省略し、会話を広く表示します。回答本文は省略しません。`/details`で通知を開き、`F2`で表示を選べます。`F5`または`/fullscreen`で今の欄を全幅表示し、`F5`または`/split`で戻ります。端末の拡大・全画面表示は案内だけで、作業の必須条件にはしません。

Agent・Owner・Evidence・Notebook・Review・展開した通知欄の文章をドラッグで選択できます。選択中の`Ctrl+C`はコピーです。`F6`または`/copy`は選択部分、未選択なら今の欄の全文をコピーします。表示上の折り返しや背景用の余白はコピーに混ぜません。選択メニューが有効な場合は、選んでいる項目と説明をコピーします。OSのコピー機能を利用できない場合は、Cleanroom内だけのコピーと明示します。`F7`または`/mouse`では端末自身の文字選択とコピーを使え、再度`F7`で通常操作へ戻ります。左右を同時に選ばないため、先に全幅表示にしてください。キーボードによっては`Fn`キーが必要です。

ドラッグを欄の上端・下端で保持すると、自動スクロールしながら選択を広げます。ホイールでも始点を保持します。Macではマウス選択を離すとシステムのクリップボードへコピーし、ハイライトは残します。Command+Cは端末側が処理するため、この選択時コピーを使います。F6でも明示的にコピーできます。[Web機能と読み取り操作](../core/docs/WEB_AND_READING.ja.md)も参照してください。

スクロールは画面上の折り返し行を単位にし、ページ移動では2行重ねて表示します。過去を読んでいる間は閲覧位置を保持してAIの作業だけを続け、新着時は`Ctrl+End`または`/latest`で最新へ戻れます。`Ctrl+Home`または`/top`は現在の表示の先頭です。`F3`で本文に移動し、矢印で移動、Shift+矢印で選択、EnterまたはEscで入力欄へ戻ります。これはローカルCLIの操作であり、Web体験版のコピー動作も同時に変更したという説明ではありません。

横120文字 × 縦28行以上ではAgent約70%・Owner約30%の左右2欄、横80文字 × 縦48行以上では上下表示、それより小さい場合は操作中の欄を表示します。サイズを理由に進行を止めません。空EnterによるAgent → メモ → 検索は同じです。端末の文字サイズは端末アプリ側で変更し、Web体験版では画面内の文字サイズボタンも使えます。

依頼は背景色付き、AI回答は背景色なし、システム通知は別欄です。Ownerはメモ・AI提案・未確認事項をラベルでも区別します。入力先は太い枠と文字で示し、色だけに依存しません。

Webは960 CSS px未満で選択中の欄を広く表示します。切り替えても欄を破棄しないため、下書き・メモ・スクロール位置を保持します。文字ボタンは16〜22px、ブラウザの拡大表示も利用できます。端末の左右それぞれに異なるフォントサイズを設定する機能ではありません。

動きを減らす場合は`VERANTYX_REDUCE_MOTION=1 verantyx`、色なしは`NO_COLOR=1 verantyx`、通常表示は`verantyx --plain`です。WebはOSの動きを減らす設定に従います。動画は操作ボタン付き、GIFは明示的に開く形式で静止画も用意します。READMEのGIF再生はGitHubクライアントに依存するため、横に静止画リンクを置いています。

ブラウザ体験版は入力先の切り替え、参照、メモ、連続した会話、許可選択の例を再現します。保存先はそのタブ内であり、CLIのDBではありません。例の予想時間や結果は実作業・証拠ではありません。サブスク実行・実際の圧縮・永続セッション・ファイル編集はローカルCLIで行い、「AIに頼む」の接続は明示操作として分けます。

今回のソース変更は、全OSの表示・アクセシビリティ・実モデル検証済みを意味しません。

## 简体中文

少于40行或120列时，CLI折叠重复边框、长提示和独立系统通知，为对话留出空间，不截断回答。用`/details`查看通知，`F2`选择视图，`F5`或`/fullscreen`展开当前面板，再按`F5`或`/split`返回。放大或最大化终端只是建议，不会阻止工作。

拖动正文选择文字，`Ctrl+C`复制选择；`F6`或`/copy`复制选择或当前面板全文，不带显示换行和填充空格。活动菜单会复制当前选项及说明。无法访问系统剪贴板时会明确提示仅内部复制。`F7`或`/mouse`切换终端原生选择与复制，再按`F7`恢复应用鼠标操作。可先展开单栏，避免同时选择两栏；部分键盘需要`Fn`。

滚动按显示行进行，翻页重叠两行。阅读旧消息时保持位置，AI继续工作；`Ctrl+End`或`/latest`回到最新，`Ctrl+Home`或`/top`到当前视图开头。`F3`进入正文，Shift+方向键选择，Enter或Esc返回输入。这些是本地CLI功能，不代表网页体验同步增加了相同复制功能。

120列 × 28行起，Agent约占70%宽度，Owner约占30%；80列 × 48行起可上下排列；更小时显示活动面板，不阻止使用。空Enter仍在Agent、备忘和搜索之间循环。终端字体由终端应用设置；浏览器体验版提供字号按钮。

网页小于960 CSS px时显示选中的面板，保留草稿和滚动位置。字号按钮可调16–22px。请求有底色，回答无底色，系统状态另列。活动位置以边框和文字共同标识。可使用减少动态效果、无色或纯文本模式；视频可暂停，GIF可选择打开，另有静态图片。

浏览器体验复现切换输入、引用、备忘、连续对话和示例授权。数据仅留在此标签页，不是CLI数据库。脚本估时与结果不是真实工作或证据。订阅执行、实际压缩、持久会话及文件编辑需要本地CLI；“请求我的AI”单独明确连接。

## 한국어

40행 또는 120열 미만에서는 중복 테두리, 긴 안내와 별도 시스템 알림을 접어 대화 공간을 확보하며 답변은 자르지 않습니다. `/details`로 알림, `F2`로 뷰를 열고 `F5` 또는 `/fullscreen`으로 현재 패널을 확대합니다. `F5` 또는 `/split`으로 돌아옵니다. 터미널 확대/전체 화면 안내는 작업을 막지 않습니다.

본문을 드래그해 선택하고 `Ctrl+C`로 복사합니다. `F6` 또는 `/copy`는 선택 부분 또는 현재 패널 전체를 복사하며 화면 줄바꿈과 배경 여백은 제외합니다. 활성 메뉴에서는 현재 선택지와 설명을 복사합니다. 시스템 클립보드가 없으면 내부 복사만 했다고 알립니다. `F7` 또는 `/mouse`로 터미널 자체 선택/복사를 사용하고 `F7`로 복귀합니다. 먼저 한 패널을 확대하면 두 열 동시 선택을 피할 수 있습니다. 일부 키보드는 `Fn`이 필요합니다.

화면 표시 행으로 스크롤하며 페이지마다 두 행을 겹칩니다. 이전 글을 읽을 때 위치를 유지하며 작업은 계속됩니다. `Ctrl+End` 또는 `/latest`로 최신, `Ctrl+Home` 또는 `/top`으로 현재 뷰 처음에 갑니다. `F3`으로 본문에 들어가 Shift+화살표로 선택하고 Enter 또는 Esc로 입력에 돌아옵니다. 로컬 CLI 기능이며 웹 체험판도 같은 복사 기능으로 변경했다는 뜻은 아닙니다.

120열 × 28행부터 Agent 약 70%, Owner 약 30% 너비의 좌우 패널을, 80열 × 48행부터 상하 패널을 사용합니다. 더 작으면 활성 패널만 보여주며 진행을 막지 않습니다. 빈 Enter 전환은 같습니다. 터미널 글꼴 크기는 터미널 앱에서, 웹 체험 글자 크기는 화면 버튼에서 바꿉니다.

웹은 960 CSS px 미만에서 선택한 패널을 표시하며 초안과 스크롤 위치를 유지합니다. 글자 버튼은 16–22px입니다. 요청 배경, 응답, 시스템 상태를 분리하고 활성 위치를 테두리와 글자로 함께 표시합니다. 동작 감소, 무색, 일반 텍스트 모드를 제공하며 영상 제어와 선택형 GIF, 정지 이미지를 사용합니다.

브라우저는 입력 전환, 참조, 메모, 연속 대화와 허용 선택 예시를 재현합니다. 데이터는 이 탭에만 있으며 CLI DB가 아닙니다. 대본의 예상 시간과 결과는 실제 작업이나 증거가 아닙니다. 구독 실행, 실제 압축, 영구 세션, 파일 편집은 로컬 CLI에서 하며 AI 연결은 별도 명시적 조작입니다.

## Español

Con menos de 40 filas o 120 columnas, la CLI contrae marcos repetidos, instrucciones largas y actividad del sistema para ampliar la conversación, sin recortar respuestas. Usa `/details` para la actividad, `F2` para las vistas y `F5` o `/fullscreen` para ampliar el panel. `F5` o `/split` vuelve. Maximizar el terminal es una sugerencia, no un requisito.

Arrastra para seleccionar; `Ctrl+C` copia la selección y `F6` o `/copy` copia la selección o todo el panel. Se excluyen los saltos visuales y espacios de relleno. En un menú activo se copia la opción resaltada y su explicación. Si no hay acceso al portapapeles del sistema, se indica que la copia es solo interna. `F7` o `/mouse` permite seleccionar y copiar con el terminal; `F7` restaura los controles. Amplía antes para evitar copiar ambas columnas. Algunos teclados requieren `Fn`.

El desplazamiento usa filas visibles y solapa dos filas entre páginas. Leer mensajes anteriores conserva la posición mientras continúa el trabajo. `Ctrl+End` o `/latest` vuelve al último texto; `Ctrl+Home` o `/top` va al inicio de la vista. `F3` enfoca el texto, Shift+flechas selecciona y Enter o Esc vuelve a escribir. Son controles de la CLI local; no implican cambios equivalentes en la copia del ensayo web.

Desde 120 columnas × 28 filas, Agent ocupa aproximadamente el 70% del ancho y Owner el 30%; desde 80 × 48 pueden apilarse. Las ventanas menores muestran el panel activo sin bloquear. Enter vacío sigue recorriendo Agent, Nota y Buscar. La fuente del terminal se cambia en su aplicación; el ensayo web tiene controles de tamaño.

Por debajo de 960 píxeles CSS, la web muestra el panel seleccionado y conserva borradores y posición. Los botones ajustan 16–22px. Las peticiones tienen fondo, las respuestas no; la actividad va aparte. Borde y etiqueta identifican el panel activo. Hay movimiento reducido, modo sin color y texto plano; el vídeo tiene controles, el GIF es opcional y hay imagen estática.

El ensayo reproduce cambios de entrada, referencias, notas, conversación continua y elecciones de ejemplo. Los datos permanecen en esta pestaña, no en la base de la CLI. Las estimaciones y resultados del guion no son trabajo real ni evidencia. Suscripciones, compactación real, sesiones duraderas y edición requieren la CLI local; Pedir a mi IA es una conexión explícita aparte.
