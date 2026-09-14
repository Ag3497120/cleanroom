import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Vera — Cleanroom Notebook', description: 'AIに作らせても、プロジェクトの判断と理解を人間側へ残すCleanroom Notebook。', icons: { icon: (process.env.PAGES_BASE_PATH || '') + '/favicon.svg' } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="ja"><body>{children}</body></html>; }
