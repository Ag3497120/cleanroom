'use client';

import { useEffect, useRef, useState } from 'react';

type Section = 'overview' | 'models' | 'workspace' | 'boundary' | 'notebook';

const sections: Array<{ id: Section; label: string; note: string }> = [
  { id: 'overview', label: 'Overview', note: 'The cleanroom at a glance' },
  { id: 'models', label: 'Models', note: 'Providers and two roles' },
  { id: 'workspace', label: 'Workspace', note: 'Project-local context only' },
  { id: 'boundary', label: 'Boundary', note: 'What AI may and may not change' },
  { id: 'notebook', label: 'Notebook', note: 'What stays with you' },
];

const providers = [
  { id: 'codex', name: 'Codex Subscription', detail: 'Reuse the signed-in Codex CLI on this Mac.', kind: 'subscription' },
  { id: 'ollama', name: 'Ollama', detail: 'Choose two local models from your own machine.', kind: 'local' },
  { id: 'openai', name: 'OpenAI API', detail: 'Read OPENAI_API_KEY only at the call boundary.', kind: 'api' },
  { id: 'anthropic', name: 'Anthropic API', detail: 'Read ANTHROPIC_API_KEY only at the call boundary.', kind: 'api' },
  { id: 'gemini', name: 'Gemini API', detail: 'Read GEMINI_API_KEY only at the call boundary.', kind: 'api' },
  { id: 'compatible', name: 'OpenAI-Compatible Local', detail: 'LM Studio, vLLM, llama.cpp, or MLX-style local servers.', kind: 'local' },
];

export default function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [section, setSection] = useState<Section>('overview');
  const [provider, setProvider] = useState('codex');
  const drawer = useRef<HTMLDialogElement>(null);
  useEffect(() => { drawer.current?.showModal(); }, []);
  const selected = providers.find((item) => item.id === provider) ?? providers[0];

  return <dialog ref={drawer} className="settings-drawer" aria-label="Cleanroom Settings" onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <aside className="settings-sidebar">
        <div className="settings-mark" aria-hidden="true"><span className="seal-orbit" /><span>V</span></div>
        <div className="settings-brand">
          <strong>Cleanroom</strong>
          <small>Settings</small>
        </div>
        <nav className="settings-nav" aria-label="Settings sections">
          {sections.map((item) => <button key={item.id} className={section === item.id ? 'is-active' : ''} onClick={() => setSection(item.id)}>
            <span>{item.label}</span><small>{item.note}</small>
          </button>)}
        </nav>
        <div className="settings-sidebar-note">
          <span className="sealed-dot" />
          <span>Connection preview only. External tools may have their own filesystem permissions.</span>
        </div>
      </aside>

      <main className="settings-content">
        <header className="settings-content-header">
          <div><p>LOCAL-FIRST WORKSPACE</p><h1>{sections.find((item) => item.id === section)?.label}</h1></div>
          <button className="settings-close" onClick={onClose} aria-label="Close Settings">Close <kbd>Esc</kbd></button>
        </header>

        {section === 'overview' && <div className="settings-page overview-page">
          <div className="cleanroom-pledge"><span className="pledge-index">01</span><div><p className="eyebrow">THE CLEANROOM PLEDGE</p><h2>AI may prepare work. You decide what enters the project.</h2><p>Vera keeps project intent, decisions, evidence, failures, and your learning outside a provider-specific conversation.</p></div></div>
          <div className="overview-grid">
            <article><span>PROJECT</span><strong>Not observed here</strong><p>AI proposals do not become project changes by implication.</p></article>
            <article><span>CANDIDATE NOTEBOOK</span><strong>Adapter-dependent</strong><p>This preview does not establish an OS sandbox or verify external side effects.</p></article>
            <article><span>HUMAN NOTEBOOK</span><strong>Growing</strong><p>Keep only the decisions and principles worth carrying forward.</p></article>
          </div>
        </div>}

        {section === 'models' && <div className="settings-page models-page">
          <div className="section-intro"><p className="eyebrow">MODEL CONNECTIONS</p><h2>Choose a proposal engine, not a project owner.</h2><p>Credentials never belong in this notebook. The local CLI records connection names and reads an environment variable only when it makes a call.</p></div>
          <div className="provider-grid">
            {providers.map((item, index) => <button key={item.id} className={'provider-card ' + item.kind + (provider === item.id ? ' is-selected' : '')} onClick={() => setProvider(item.id)} aria-pressed={provider === item.id}>
              <span className="provider-number">0{index + 1}</span><strong>{item.name}</strong><p>{item.detail}</p><span className="provider-state">{provider === item.id ? 'Selected for preview' : item.kind}</span>
            </button>)}
          </div>
          <div className="model-route"><span className="route-label">ACTIVE PREVIEW</span><strong>{selected.name}</strong><div className="route-line"><i /><b /></div><p>Creator and reviewer are separate roles. The browser preview does not save credentials or alter a Cleanroom.</p><code>In the local CLI: write “モデルを設定する” to save this kind of connection.</code></div>
        </div>}

        {section === 'workspace' && <div className="settings-page workspace-page">
          <div className="section-intro"><p className="eyebrow">WORKSPACE</p><h2>Context should be deliberate, small, and local.</h2></div>
          <dl className="settings-ledger"><div><dt>Cleanroom root</dt><dd>Current project directory</dd></div><div><dt>Outbound context</dt><dd>Selected project-local files only</dd></div><div><dt>Excluded by default</dt><dd>Secrets, project-external paths, prior notebooks</dd></div><div><dt>Candidate location</dt><dd>Isolated Vera work records</dd></div></dl>
          <p className="quiet-note">A file list is not a permission grant. Sending context and adopting a candidate stay separate actions.</p>
        </div>}

        {section === 'boundary' && <div className="settings-page boundary-page">
          <div className="section-intro"><p className="eyebrow">TRUST BOUNDARY</p><h2>Permissions depend on the execution boundary.</h2></div>
          <div className="boundary-map"><article><span>01</span><strong>Read</strong><p>Vera selects only relevant project-local context.</p></article><div className="boundary-flow" aria-hidden="true"><i /><i /><i /></div><article><span>02</span><strong>Propose</strong><p>Built-in work retains candidates; external harness side effects may be unobserved.</p></article><div className="boundary-flow" aria-hidden="true"><i /><i /><i /></div><article className="human-gate"><span>03</span><strong>Adopt</strong><p>A human explicitly decides what returns to Cleanroom.</p></article></div>
          <div className="boundary-stamp"><span>PROVENANCE</span><p>No model response can convert itself into a human decision, evidence, or accepted project change.</p></div>
        </div>}

        {section === 'notebook' && <div className="settings-page notebook-page">
          <div className="section-intro"><p className="eyebrow">NOTEBOOK</p><h2>Leave with more than a changed file.</h2><p>Vera turns work into records for the project, the system, and the human who owns both.</p></div>
          <div className="notebook-stack"><article><span>PROJECT DELTA</span><strong>What changed, what remains unknown.</strong></article><article><span>SYSTEM DELTA</span><strong>Rules, checks, and failures that can help next time.</strong></article><article><span>HUMAN DELTA</span><strong>What to own, review, reference, or safely delegate.</strong></article></div>
          <p className="quiet-note">Learning is not a gate. A task can be built while understanding remains visible as a future note.</p>
        </div>}
      </main>
  </dialog>;
}
