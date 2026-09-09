import type { Terminal } from '@xterm/xterm';
import { SampleInput } from './sample-input.ts';

export function commandTerminal(term: Terminal, submit: (input: string) => void, interrupt: () => void) {
  const editor = new SampleInput(['/help','/login','/models','/model','/lang','/status','/cancel','/logout']);
  let anchor: number | null = null, drawing = false, pending = false, closed = false;
  let output: string[] = [], footer = 'Enter · Ctrl+J · ↑↓ · Tab · Ctrl+C';
  const clean = (s: string) => Array.from(s).filter(c => c === '\n' || c === '\t' || (c >= ' ' && c < '\x7f') || c >= '\xa0').join('');
  const draw = () => {
    if (closed) return;
    pending = true; if (drawing) return; drawing = true;
    term.write('', () => {
      if (closed) return;
      pending = false;
      let prefix = '';
      if (anchor !== null) {
        const current = term.buffer.active.baseY + term.buffer.active.cursorY;
        const up = Math.max(0, Math.min(term.buffer.active.cursorY, current - anchor));
        prefix += '\r' + (up ? '\x1b[' + up + 'A' : '') + '\x1b[J';
      }
      if (output.length) { prefix += output.join('\r\n') + '\r\n'; output = []; }
      term.write(prefix, () => {
        if (closed) return;
        anchor = term.buffer.active.baseY + term.buffer.active.cursorY;
        let s = '\x1b[90m' + '─'.repeat(Math.max(10, term.cols - 1)) + '\x1b[0m\r\n\x1b[1;36m❯ \x1b[0m';
        for (let i = 0; i <= editor.value.length; i++) {
          if (i === editor.cursor) s += '\x1b7';
          if (i < editor.value.length) s += editor.value[i] === '\n' ? '\r\n  · ' : editor.value[i];
        }
        s += '\r\n\x1b[90m' + (editor.completion ?? ' ') + '\r\n' + footer + '\x1b[0m\x1b8';
        term.write(s, () => { drawing = false; if (pending) draw(); });
      });
    });
  };
  term.write('\x1b[?2004h');
  draw();
  return {
    input(data: string) { editor.feed(data, value => { output.push('❯ ' + clean(value).replaceAll('\n','\r\n  · ')); submit(value); }, interrupt); draw(); },
    write(value: string) { output.push(clean(value).replaceAll('\n','\r\n')); draw(); },
    footer(value: string) { footer = clean(value); draw(); },
    resize: draw,
    dispose() { closed = true; },
  };
}
