import type { Terminal } from '@xterm/xterm';
import { COMMANDS, SampleInput } from './sample-input.ts';
import record from './sample-record.json' with { type: 'json' };

const dim = (text: string) => '\x1b[90m' + text + '\x1b[0m';
const cyan = (text: string) => '\x1b[1;36m' + text + '\x1b[0m';
/** Only a display/sample loop. No model calls, files, learning assessment or saved decisions. */
export function hostedSample(terminal: Terminal, status: (text: string) => void) {
  const editor = new SampleInput();
  let closed = false;
  let pending = false;
  let drawing = false;
  let anchor: number | null = null;
  let output = [
    cyan('✣  VERA') + '  CLEANROOM NOTEBOOK  ' + record.runtime_version,
    'AI can prepare work. You decide what enters the project.',
    '',
    dim('Preview workspace · AI disconnected · no notebook is written'),
    'Settings (upper right)  ·  /demo recorded work  ·  /help preview guide',
    'The local CLI owns real model connections and project records.',
    '',
  ];
  status('Preview workspace · AI disconnected');
  terminal.write('\x1b[?2004h');
  const draw = () => {
    if (closed) return;
    pending = true;
    if (drawing) return;
    drawing = true;
    terminal.write('', () => {
      if (closed) return;
      pending = false;
      let text = '';
      if (anchor !== null) {
        const current = terminal.buffer.active.baseY + terminal.buffer.active.cursorY;
        const up = Math.max(0, Math.min(terminal.buffer.active.cursorY, current - anchor));
        text += '\r' + (up ? '\x1b[' + up + 'A' : '') + '\x1b[J';
      }
      if (output.length) { text += output.join('\r\n') + '\r\n'; output = []; }
      terminal.write(text, () => {
        if (closed) return;
        anchor = terminal.buffer.active.baseY + terminal.buffer.active.cursorY;
        let prompt = dim('─'.repeat(Math.max(10, terminal.cols - 1))) + '\r\n' + cyan('❯ ');
        for (let i = 0; i <= editor.value.length; i++) {
          if (i === editor.cursor) prompt += '\x1b7';
          if (i < editor.value.length) prompt += editor.value[i] === '\n' ? '\r\n  · ' : editor.value[i];
        }
        prompt += '\r\n' + dim(editor.completion ? '  ' + editor.completion + '  (Enterで確定)' : ' ');
        prompt += '\r\n' + dim('Enter send · Ctrl+J newline · ↑↓ history · Tab complete · Ctrl+C cancel');
        prompt += '\r\n' + dim('Preview · ' + editor.text.split('\n').length + ' lines · ' + Array.from(editor.text).length + ' characters') + '\x1b8';
        terminal.write(prompt, () => { drawing = false; if (pending) draw(); });
      });
    });
  };
  const reply = (text: string) => {
    if (!text.trim()) return;
    output.push(cyan('❯ ') + text.replace(/\n/g, '\r\n  · '));
    switch (text.trim()) {
      case '/help':
        output.push('Preview input: Enter sends, Ctrl+J / Alt+Enter adds a line, ↑↓ recalls, Tab completes, Ctrl+C cancels.',
          'Open Settings in the upper right or with ⌘, to explore the Cleanroom configuration.',
          'Preview commands: /demo recorded work · /dictionary retained rules · /learn learning note · /flow route',
          'Local CLI commands: ' + COMMANDS.join(' '),
          'This hosted surface does not connect a model, read a project, or store a secret.'); break;
      case '/demo':
        output.push(dim('記録した検査の例 · テスト用生成器 · 実モデルの呼び出しなし'),
          '1. 「並行する作業は別フォルダで進める」と一度判断。',
          '2. 誤った候補を、変更前に固定したテストが検出。',
          '3. 別の生成器で同じ方針を再利用。追加の判断は' + record.metrics.second_human_decisions + '件。',
          '4. 修正候補は固定した条件を通過。本体には未採用。',
          '残ったもの: 次回に使う方針と、期待値を固定する理由を学ぶ項目。',
          dim('0件はこの記録内の値です。汎用的な品質や本人の理解は測定していません。')); break;
      case '/dictionary':
        output.push('記録例から残った方針:',
          '状況: 同じプロジェクトで複数の書き込みがある。',
          '選択: 作業するフォルダを分ける。',
          '確認: 対象と変更を照合し、テストを実行する。',
          dim('この画面の入力から新しい規則は作成しません。')); break;
      case '/learn':
        output.push('記録例から残った学習項目:',
          '期待値を固定して失敗を検出する。',
          '反例: 失敗した後で期待値を書き換え、成功にする。',
          '理解確認: 何を先に固定すれば、誤りを検出できるか説明する。',
          dim('本人の理解: 未確認。表示しただけでは習得済みにしません。')); break;
      case '/flow':
        output.push('依頼 → 既存の方針を確認 → 提案 → 必要な判断 → 別のモデルで編集 → 検査',
          '→ 結果と根拠を記録 → 再利用する方針 / 本人が学ぶ項目',
          '本体への採用は、CLIにある採用の操作で行います。'); break;
      case '/settings': case '/status': case '/model': case '/editor':
        output.push('Open the Settings button in the upper right.',
          'Models, Workspace, Boundary, and Notebook are previewed there. Real settings stay local to the CLI.'); break;
      case '/new': output = [cyan('✣  VERA') + '  CLEANROOM NOTEBOOK', dim('Preview workspace · AI disconnected'), '']; break;
      case '/quit': output.push('The preview input was cleared. Closing this tab ends the preview.'); break;
      default:
        output.push('入力を受け取りました。このサイトは表示サンプルのため、作業は実行していません。',
          '手元のCLIへ接続した画面では、この入力がそのままVerantyxへ渡ります。');
    }
    output.push('');
  };
  draw();
  return {
    input(data: string) { editor.feed(data, reply, () => output.push('^C', '')); draw(); },
    resize: draw,
    dispose() { closed = true; }
  };
}
