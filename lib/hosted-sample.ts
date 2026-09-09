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
    cyan('✣  VERANTYX') + '  ' + record.runtime_version,
    '一度決めた方針を、次のAI作業にも。',
    '',
    dim('表示サンプル · AI未接続 · 入力は保存されません'),
    '/help 操作案内  ·  /demo 記録した実行例',
    '実際の作業は、手元で同じ画面を開くと利用できます。',
    '',
  ];
  status('表示サンプル · AI未接続');
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
        prompt += '\r\n' + dim('Enter 送信 · Ctrl+J 改行 · ↑↓ 履歴 · Tab 補完 · Ctrl+C 中断');
        prompt += '\r\n' + dim('表示サンプル · ' + editor.text.split('\n').length + '行 · ' + Array.from(editor.text).length + '文字') + '\x1b8';
        terminal.write(prompt, () => { drawing = false; if (pending) draw(); });
      });
    });
  };
  const reply = (text: string) => {
    if (!text.trim()) return;
    output.push(cyan('❯ ') + text.replace(/\n/g, '\r\n  · '));
    switch (text.trim()) {
      case '/help':
        output.push('入力: Enter 送信、Ctrl+J / Alt+Enter 改行、↑↓ 履歴、Tab 補完、Ctrl+C 中断。',
          '複数行の貼り付けは一つの下書きになります。Enterで送信します。',
          '表示サンプル: /demo 実行例 · /dictionary 残る方針 · /learn 学ぶ項目 · /flow 流れ',
          '実際のCLIのコマンド: ' + COMMANDS.join(' '),
          'このサイトは表示サンプルです。モデル・プロジェクトへの接続はローカル起動で行います。'); break;
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
      case '/status': case '/model': case '/editor':
        output.push('表示サンプル · AI未接続 · 保存先なし',
          'ローカル起動時は、既存のCLIがプロジェクトと提案・編集モデルの設定を読み込みます。'); break;
      case '/new': output = [cyan('✣  VERANTYX'), dim('表示サンプル · AI未接続'), '']; break;
      case '/quit': output.push('表示サンプルの入力を消しました。タブを閉じると終了します。'); break;
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
