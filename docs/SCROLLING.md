# Active-pane scrolling / 入力先に連動するスクロール

Enter on an empty input selects Agent, Owner memo, then Owner search.
Wheel events inside the full-screen application are routed to the selected pane's body, even when the pointer is over the other pane. The other viewport and its cursor are not moved by that scroll action. New task events still arrive; this is viewport independence, not pausing the worker.

- Wheel: one line in the active body.
- PageUp / PageDown: a page in the active body, using wrapped-line-aware paging.
- Ctrl+Up / Ctrl+Down: one line without moving editor focus.
- F3: focus the body for keyboard navigation.
- Menus and completion lists retain their own navigation.
- Input drafts remain in their own editors.
- Native terminal scrollback, Shift-wheel overrides and OS scrollbar dragging cannot be intercepted by a CLI. Use the in-app viewport. Mouse reporting must be enabled by the terminal.
- The public browser preview implements the same active-pane routing, but is not the real CLI process.

空欄Enterで入力先を選び、その側だけをホイール・PageUp/PageDownで動かします。反対側の表示位置を維持し、裏の作業は止めません。Mac/Windowsの端末アプリ外枠のスクロールバーそのものを制御する機能ではありません。WindowsではCLIの導入対象はWSL2です。

This change is not a claim that every terminal emulator has been tested.
