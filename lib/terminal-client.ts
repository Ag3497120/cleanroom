import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { hostedSample } from './hosted-sample';
import { remoteTerminal } from './remote-terminal';

export function mountTerminal(element: HTMLElement, status: (text: string) => void, basePath = '') {
  element.replaceChildren();
  const terminal = new Terminal({
    fontFamily: 'Menlo, Monaco, "SFMono-Regular", Consolas, monospace', fontSize: 15,
    lineHeight: 1.18, cursorBlink: !matchMedia('(prefers-reduced-motion: reduce)').matches,
    cursorStyle: 'block', scrollback: 10000, screenReaderMode: true, allowProposedApi: false,
    disableStdin: true,
    theme: { background:'#101012',foreground:'#e6e6e6',cursor:'#e6e6e6',selectionBackground:'#3b526a',black:'#101012',red:'#f07878',green:'#90c792',yellow:'#e7cf86',blue:'#82b2ea',magenta:'#c9a0dc',cyan:'#56c8d8',white:'#dedee3',brightBlack:'#85858f',brightRed:'#ffa0a0',brightGreen:'#a9e0ad',brightYellow:'#f6e9af',brightBlue:'#a7ccff',brightMagenta:'#e0b4f2',brightCyan:'#8adee9',brightWhite:'#ffffff' },
  });
  const fit = new FitAddon();
  terminal.loadAddon(fit); terminal.open(element);
  const fitTerminal = () => { fit.fit(); terminal.resize(Math.max(20, Math.min(500, terminal.cols)), Math.max(6, Math.min(200, terminal.rows))); };
  fitTerminal();
  let disposed = false;
  let ready = false;
  let ws: WebSocket | undefined;
  let sample: ReturnType<typeof hostedSample> | undefined;
  let terminalError = false;
  const abort = new AbortController();
  const send = (data: string) => {
    if (disposed || !ready) return;
    if (sample) sample.input(data);
    else if (ws?.readyState === WebSocket.OPEN) {
      // Split large pastes at Unicode code point boundaries; the PTY sees one bracketed paste.
      let part = ''; let bytes = 0;
      for (const char of data) {
        const size = char.codePointAt(0)! > 0xffff ? 4 : char.charCodeAt(0) > 0x7ff ? 3 : char.charCodeAt(0) > 0x7f ? 2 : 1;
        if (bytes + size > 65536) { ws.send(JSON.stringify({type:'input',data:part})); part = ''; bytes = 0; }
        part += char; bytes += size;
      }
      if (part) ws.send(JSON.stringify({type:'input',data:part}));
    }
  };
  // Model/program output must not write the OS clipboard using an OSC escape.
  const clipboard = terminal.parser.registerOscHandler(52, () => true);
  const input = terminal.onData(send);
  let composing = false;
  const compositionStart = () => { composing = true; };
  const compositionEnd = () => { composing = false; };
  element.addEventListener('compositionstart', compositionStart, true);
  element.addEventListener('compositionend', compositionEnd, true);
  terminal.attachCustomKeyEventHandler(event => {
    // Safari can signal IME conversion through legacy 229 before isComposing is set.
    // oxlint-disable-next-line typescript/no-deprecated
    if (event.isComposing || composing || event.keyCode === 229) return true;
    if (event.type === 'keydown' && event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === 'j') {
      event.preventDefault(); send('\n'); return false;
    }
    // Copy remains Cmd+C on macOS, or Ctrl+Shift+C. Ctrl+C is always the CLI interrupt.
    return true;
  });
  const resized = terminal.onResize(({cols, rows}) => {
    if (sample) sample.resize();
    else if (ready && ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'resize',cols,rows}));
  });
  const observer = new ResizeObserver(fitTerminal); observer.observe(element);
  const fail = (message: string) => {
    if (disposed) return;
    terminalError = true; ready = false; terminal.options.disableStdin = true;
    status('CLIに接続できません');
    terminal.writeln('\r\n\x1b[31m' + message + '\x1b[0m');
  };
  const connect = async () => {
    status('CLIに接続しています');
    const settingsResponse = await fetch(new URL(basePath + '/compute-config.json', location.origin), {signal:abort.signal,cache:'no-store'});
    if (disposed) return;
    if (settingsResponse.ok) {
      const settings = await settingsResponse.json() as {public_mode?:boolean;gateway_url?:string};
      if (disposed) return;
      if (settings.public_mode) {
        const gateway = settings.gateway_url ?? '';
        if (gateway) {
          const target = new URL(gateway);
          if (target.protocol !== 'https:' || target.username || target.password || target.search || target.hash || target.pathname !== '/') throw Error('Invalid compute gateway URL');
        }
        sample = remoteTerminal(terminal, gateway.replace(/\/$/,''), status);
        ready = true; terminal.options.disableStdin = false; return;
      }
    }
    const local = ['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname);
    if (!local) { sample = hostedSample(terminal, status); ready = true; terminal.options.disableStdin = false; return; }
    const response = await fetch('/terminal/session', {signal:abort.signal,cache:'no-store',credentials:'same-origin'});
    if (disposed) return;
    if (response.status === 404) { sample = hostedSample(terminal, status); ready = true; terminal.options.disableStdin = false; return; }
    if (!response.ok) throw new Error('ローカルの接続を確認し、ページを読み直してください。');
    const config = await response.json() as {format?: string; token?: string; websocket?: string};
    if (disposed) return;
    if (config.format !== 'verantyx.terminal.v1' || typeof config.token !== 'string' || config.websocket !== '/terminal/ws') throw new Error('CLIの接続情報を確認できませんでした。');
    const url = new URL(config.websocket, location.href); url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(url); ws.binaryType = 'arraybuffer';
    ws.onopen = () => ws?.send(JSON.stringify({type:'attach',token:config.token,cols:terminal.cols,rows:terminal.rows}));
    ws.onmessage = event => {
      if (disposed) return;
      if (event.data instanceof ArrayBuffer) { terminal.write(new Uint8Array(event.data)); return; }
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'ready') { ready = true; terminal.options.disableStdin = false; status('手元のCLIに接続中'); }
        else if (message.type === 'error') fail(message.message);
        else if (message.type === 'exit') { ready = false; terminal.options.disableStdin = true; status('CLI終了'); terminal.writeln('\r\n\x1b[90mCLIが終了しました。再開するにはページを読み直してください。\x1b[0m'); }
      } catch { fail('CLIからの接続情報を読み取れませんでした。'); ws?.close(); }
    };
    ws.onerror = () => fail('CLIへ接続できませんでした。ローカルの起動状態を確認してください。');
    ws.onclose = () => {
      if (disposed) return;
      if (ready && !terminalError) {
        terminal.writeln('\r\n\x1b[90m接続が切れました。実行結果はCLIの記録で確認してください。再接続はページを読み直します。\x1b[0m');
        status('切断');
      }
      ready = false; terminal.options.disableStdin = true;
    };
  };
  void connect().catch(error => { if (!disposed && error?.name !== 'AbortError') fail(error?.message || 'CLIへ接続できませんでした。'); });
  terminal.focus();
  return () => {
    disposed = true; abort.abort(); ws?.close(); sample?.dispose();
    observer.disconnect(); resized.dispose(); input.dispose(); clipboard.dispose();
    element.removeEventListener('compositionstart', compositionStart, true);
    element.removeEventListener('compositionend', compositionEnd, true);
    terminal.dispose();
  };
}
