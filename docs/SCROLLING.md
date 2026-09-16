# Active-pane scrolling / 入力先に連動するスクロール

## English

Empty Enter still cycles Agent, Owner memo, then Owner search. Wheel events target the selected pane, not whichever column is under the pointer. Clicking text focuses that reading pane for selection. The other pane's scroll position is not moved by the scroll action; work and local recording continue.

| Action | Control |
| --- | --- |
| Scroll one displayed row, including wrapped paragraphs | Wheel or Ctrl+Up / Ctrl+Down |
| Move one screen, overlapping two rows | PageUp / PageDown |
| Beginning of the current view | Ctrl+Home or /top |
| Latest text and resume following new Agent output | Ctrl+End or /latest |
| Focus reading text / return to input | F3 / Enter or Esc |
| Select text | Drag, or Shift+arrows when reading |
| Copy a selection | Ctrl+C |
| Copy the selection or the entire current pane | F6 or /copy |
| Full-width pane / return to split layout | F5, /fullscreen, /split |
| Toggle native terminal selection | F7 or /mouse |

Scrolling up pauses follow mode, not the agent. New events retain the older reading position; return to the bottom or use /latest to follow again. Reflow on resize uses source-text positions rather than counting old wrapped rows. Selection is retained across background updates; copying returns original text without soft-wrap line breaks or decorative padding.

Owner history still pages from its local store at the ends of a loaded page. Top/latest operate on the currently loaded view, not the entire database. Menus and completion lists retain their navigation. Editor drafts remain in place when scrolling.

Small terminals collapse repeated chrome and system activity; /details expands activity without deleting records. F5 offers more width without requiring a larger terminal. Enlarge or maximize the terminal to read both panes more comfortably. Some keyboards need Fn with function keys.

F7 turns off application mouse reporting so your terminal can select text and use its own Copy command. Press F7 again to return to in-app scrolling. Expand one pane first to avoid native selection spanning both columns. Native scrollback, OS scrollbar dragging and terminal modifier overrides remain outside CLI control. These changes do not claim coverage of every terminal emulator, nor equivalent browser clipboard implementation.

## 日本語

空EnterのAgent → メモ → 検索は従来どおりです。ホイールはポインターのある側ではなく、選択中の欄を動かします。本文をクリックすると、その欄で文章を選択できます。反対側のスクロール位置はそのスクロール操作では動かさず、AIの作業・ローカル記録は続きます。

| 操作 | キー |
| --- | --- |
| 折り返しを含む画面上の1行を移動 | ホイール、Ctrl+Up / Ctrl+Down |
| 2行を重ねてページ移動 | PageUp / PageDown |
| 現在の表示の先頭へ | Ctrl+Home、/top |
| 最新へ戻りAgentの新着を追う | Ctrl+End、/latest |
| 本文へ / 入力へ戻る | F3 / Enter、Esc |
| 文章を選択 | ドラッグ、本文でShift+矢印 |
| 選択部分をコピー | Ctrl+C |
| 選択部分、未選択なら現在の欄の全文をコピー | F6、/copy |
| 全幅表示 / 二分割に戻る | F5、/fullscreen、/split |
| 端末自身の文字選択へ切り替え | F7、/mouse |

過去へスクロールすると最新への追従だけを止め、AIの作業は続けます。新着によって閲覧中の位置へ割り込ませません。下端まで戻すか/latestで追従を再開します。画面サイズの変更時は、元の文章の位置を基準に折り返し直します。選択中はその表示を保持し、コピーには画面だけの改行や背景用の余白を混ぜません。

Owner履歴は読み込んだページの端でローカル保存先から次のページを読み込みます。先頭・最新は読み込み中の表示が対象で、DB全体へのジャンプではありません。メニュー・補完の矢印操作、入力中の下書きは維持します。

小さい端末では重複表示と通知を省略します。/detailsで通知、F5で全幅表示を使えます。両欄を広く読みたい場合は端末を拡大・全画面にしてください。大きさを理由に進行を止めません。機種によってはFnキーも必要です。

F7で端末のドラッグ選択とコピー操作へ切り替え、再びF7でアプリ内スクロールへ戻ります。二つの欄を同時に選ばないためには先に全幅表示にしてください。端末自身のスクロールバックやOSのスクロールバーをCLIで制御する機能ではありません。すべての端末で検証済み、またはWeb体験版も同じコピー実装になったという意味ではありません。

See [five-language reading guidance](READABILITY.md) for Chinese, Korean and Spanish guidance.
