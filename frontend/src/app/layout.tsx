import type { Metadata } from 'next';
import './globals.css';
import AuthProvider from '@/components/providers/AuthProvider';
import AuthenticatedShell from '@/components/layout/AuthenticatedShell';
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
        <AuthProvider>
          <WebSocketProvider>
            <AuthenticatedShell>{children}</AuthenticatedShell>
          </WebSocketProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
