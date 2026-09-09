/** Browser sample and authenticated job editor. Local PTY input goes directly to the real CLI. */
export const COMMANDS = ['/help', '/paste', '/model', '/editor', '/context', '/new', '/dictionary', '/learn', '/status', '/details', '/flow', '/checks', '/work', '/decide', '/target', '/sovereignty', '/quit'];
const segmenter = new Intl.Segmenter('ja', { granularity: 'grapheme' });
export const graphemes = (text: string) => Array.from(segmenter.segment(text), value => value.segment);
export class SampleInput {
  private commands: string[];
  constructor(commands: string[] = COMMANDS) { this.commands = commands; }
  value: string[] = [];
  cursor = 0;
  history: string[] = [];
  historyIndex = 0;
  savedDraft = '';
  pending = '';
  paste = false;
  completion: string | null = null;
  choices: string[] = [];
  choiceIndex = -1;
  get text() { return this.value.join(''); }
  replace(text: string) { this.value = graphemes(text); this.cursor = this.value.length; }
  insert(text: string) {
    // Terminal control bytes in pasted content are data, never output escapes.
    // oxlint-disable-next-line no-control-regex
    const clean = text.replace(/\r\n?/g, '\n').replace(/[\x00-\x08\x0b-\x1f\x7f-\x9f]/g, '');
    const chars = graphemes(clean).slice(0, Math.max(0, 8192 - this.value.length));
    this.value.splice(this.cursor, 0, ...chars); this.cursor += chars.length;
  }
  clearCompletion() { this.completion = null; this.choices = []; this.choiceIndex = -1; }
  moveHistory(direction: number) {
    if (this.historyIndex === this.history.length) this.savedDraft = this.text;
    this.historyIndex = Math.max(0, Math.min(this.history.length, this.historyIndex + direction));
    this.replace(this.history[this.historyIndex] ?? this.savedDraft);
  }
  vertical(direction: number) {
    const before = this.value.slice(0, this.cursor);
    const start = before.lastIndexOf('\n') + 1;
    const endIndex = this.value.indexOf('\n', this.cursor);
    const end = endIndex < 0 ? this.value.length : endIndex;
    if (direction < 0 && start > 0) {
      const previous = this.value.slice(0, start - 1).lastIndexOf('\n') + 1;
      this.cursor = Math.min(previous + this.cursor - start, start - 1);
    } else if (direction > 0 && end < this.value.length) {
      const next = this.value.indexOf('\n', end + 1);
      this.cursor = Math.min(end + 1 + this.cursor - start, next < 0 ? this.value.length : next);
    } else this.moveHistory(direction);
  }
  feed(chunk: string, submit: (text: string) => void, interrupt: () => void) {
    this.pending += chunk;
    const escapes = ['\x1b[200~', '\x1b[201~', '\x1b[A', '\x1b[B', '\x1b[C', '\x1b[D', '\x1b[H', '\x1b[F', '\x1bOH', '\x1bOF', '\x1b[3~', '\x1b[1~', '\x1b[4~', '\x1b\r', '\x1b[Z'];
    while (this.pending) {
      if (this.paste) {
        const end = this.pending.indexOf('\x1b[201~');
        if (end >= 0) {
          this.insert(this.pending.slice(0, end)); this.pending = this.pending.slice(end + 6); this.paste = false;
        } else {
          const prefix = '\x1b[201~';
          let keep = 0;
          for (let n = 1; n < prefix.length; n++) if (this.pending.endsWith(prefix.slice(0, n))) keep = n;
          this.insert(this.pending.slice(0, this.pending.length - keep)); this.pending = this.pending.slice(this.pending.length - keep);
          break;
        }
        continue;
      }
      let key: string;
      if (this.pending.startsWith('\x1b')) {
        const found = escapes.find(sequence => this.pending.startsWith(sequence));
        if (!found && escapes.some(sequence => sequence.startsWith(this.pending))) break;
        // oxlint-disable-next-line no-control-regex -- Deliberately parse terminal escape sequences.
        key = found ?? (this.pending.match(/^\x1b\[[0-9;?]*[ -/]*[@-~]/)?.[0] || this.pending.slice(0, 2));
      } else key = graphemes(this.pending)[0];
      this.pending = this.pending.slice(key.length);
      if (key !== '\t' && key !== '\r' && key !== '\x1b[Z') this.clearCompletion();
      switch (key) {
        case '\x1b[200~': this.paste = true; break;
        case '\x1b[201~': break;
        case '\r':
          if (this.completion) { this.replace(this.completion); this.clearCompletion(); break; }
          if (this.value[this.cursor - 1] === '\\') { this.value.splice(--this.cursor, 1); this.insert('\n'); break; }
          { const text = this.text; if (text.trim()) this.history.push(text); this.historyIndex = this.history.length; this.savedDraft = ''; this.replace(''); this.clearCompletion(); submit(text); }
          break;
        case '\n': case '\x1b\r': this.insert('\n'); break;
        case '\x03':
          if (this.text) this.replace(''); else interrupt();
          break;
        case '\x7f': case '\b': if (this.cursor) this.value.splice(--this.cursor, 1); break;
        case '\x1b[3~': this.value.splice(this.cursor, 1); break;
        case '\x1b[D': this.cursor = Math.max(0, this.cursor - 1); break;
        case '\x1b[C': this.cursor = Math.min(this.value.length, this.cursor + 1); break;
        case '\x1b[A': this.vertical(-1); break;
        case '\x1b[B': this.vertical(1); break;
        case '\x01': case '\x1b[H': case '\x1bOH': case '\x1b[1~': this.cursor = this.value.slice(0, this.cursor).lastIndexOf('\n') + 1; break;
        case '\x05': case '\x1b[F': case '\x1bOF': case '\x1b[4~': { const n = this.value.indexOf('\n', this.cursor); this.cursor = n < 0 ? this.value.length : n; break; }
        case '\x15': this.value.splice(0, this.cursor); this.cursor = 0; break;
        case '\x0b': this.value.splice(this.cursor); break;
        case '\x17':
          while (this.cursor && /\s/.test(this.value[this.cursor - 1])) this.value.splice(--this.cursor, 1);
          while (this.cursor && !/\s/.test(this.value[this.cursor - 1])) this.value.splice(--this.cursor, 1);
          break;
        case '\t': case '\x1b[Z':
          if (!this.choices.length && /^\/\S*$/.test(this.text)) this.choices = this.commands.filter(command => command.startsWith(this.text));
          if (this.choices.length) {
            this.choiceIndex = (this.choiceIndex + (key === '\t' ? 1 : -1) + this.choices.length) % this.choices.length;
            this.completion = this.choices[this.choiceIndex];
          }
          break;
        default: if (key >= ' ' && !key.startsWith('\x1b')) this.insert(key);
      }
    }
  }
}
