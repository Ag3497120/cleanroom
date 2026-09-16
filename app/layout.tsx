import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'Cleanroom | Keep being the developer',description:'Build with AI while keeping your decisions, understanding, evidence and experience.',icons:{icon:(process.env.PAGES_BASE_PATH||'')+'/favicon.svg'}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="en"><body>{children}</body></html>;}
