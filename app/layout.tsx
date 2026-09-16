import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'Cleanroom | Build with AI. Keep the experience.',description:'A coding workspace, a learning notebook and a personal skills map that grow with your projects.',icons:{icon:(process.env.PAGES_BASE_PATH||'')+'/favicon.svg'}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>;}
