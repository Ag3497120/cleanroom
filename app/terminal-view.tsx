'use client';
import { useEffect, useRef, useState } from 'react';
import SettingsPanel from './settings-panel';
export default function TerminalView() {
  const element = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState('Preview workspace');
  const [error, setError] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  useEffect(() => {
    let dispose: (() => void) | undefined;
    let cancelled = false;
    import('../lib/terminal-client').then(({ mountTerminal }) => {
      if (!cancelled && element.current) {
        const cleanup = mountTerminal(element.current, setStatus, process.env.PAGES_BASE_PATH || '');
        if (cancelled) cleanup(); else dispose = cleanup;
      }
    }).catch(() => { if (!cancelled) setError('端末を開けませんでした。ページを読み直してください。'); });
    return () => { cancelled = true; dispose?.(); };
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === ',') { event.preventDefault(); setSettingsOpen(true); }
      if (event.key === 'Escape') setSettingsOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return <main className="terminal-shell" aria-label="Cleanroom existing gateway">
    <header className="terminal-title"><strong>Cleanroom / existing gateway</strong><div className="terminal-actions"><output className="terminal-mode">{status}</output><button className="terminal-settings" onClick={() => setSettingsOpen(true)}>Settings <kbd>⌘,</kbd></button></div></header>
    {error ? <p className="terminal-error" role="alert">{error}</p> : <div className="terminal-surface" ref={element}><pre className="terminal-loading">Verantyxを開いています…</pre></div>}
    {settingsOpen ? <SettingsPanel onClose={() => setSettingsOpen(false)} /> : null}
  </main>;
}
