import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Verantyx — Terminal', description: 'VerantyxのCLIを、ターミナルと同じ入力で使う画面。', icons: { icon: (process.env.PAGES_BASE_PATH || '') + '/favicon.svg' } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ja"><body>{children}</body></html>; }
