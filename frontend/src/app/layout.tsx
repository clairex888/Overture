import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/layout/Sidebar';
import WebSocketProvider from '@/components/providers/WebSocketProvider';

export const metadata: Metadata = {
  title: 'Overture - AI Hedge Fund Dashboard',
  description: 'AI-powered hedge fund management dashboard with autonomous trading agents',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-dark-800 text-text-primary antialiased">
        <WebSocketProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 ml-60">
              <div className="p-6 max-w-[1600px]">{children}</div>
            </main>
          </div>
        </WebSocketProvider>
      </body>
    </html>
  );
}
