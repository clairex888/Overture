'use client';

import { useEffect } from 'react';
import { initWebSocket, cleanupWebSocket } from '@/lib/websocket';

export default function WebSocketProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  useEffect(() => {
    initWebSocket();
    return () => {
      cleanupWebSocket();
    };
  }, []);

  return <>{children}</>;
}
