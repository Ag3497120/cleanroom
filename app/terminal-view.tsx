'use client';
import { useEffect, useRef, useState } from 'react';
export default function TerminalView() {
  const element = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('表示サンプル');
  const [error, setError] = useState('');
  useEffect(() => {
    let dispose: (() => void) | undefined;
    let cancelled = false;
    import('../lib/terminal-client').then(({ mountTerminal }) => {
      if (!cancelled && element.current) {
        const cleanup = mountTerminal(element.current, setStatus);
        if (cancelled) cleanup(); else dispose = cleanup;
      }
    }).catch(() => { if (!cancelled) setError('端末を開けませんでした。ページを読み直してください。'); });
    return () => { cancelled = true; dispose?.(); };
  }, []);
  return <main className="terminal-shell" aria-label="Verantyx ターミナル">
    <header className="terminal-title"><strong>Verantyx — terminal</strong><output className="terminal-mode">{status}</output></header>
    {error ? <p className="terminal-error" role="alert">{error}</p> : <div className="terminal-surface" ref={element}><pre className="terminal-loading">Verantyxを開いています…</pre></div>}
  </main>;
}
