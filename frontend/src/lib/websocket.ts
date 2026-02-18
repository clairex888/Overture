type MessageHandler = (data: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<MessageHandler>> = new Map();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private url: string;
  private channels: string[] = [];

  constructor() {
    const wsBase =
      process.env.NEXT_PUBLIC_WS_URL ||
      (process.env.NEXT_PUBLIC_API_URL
        ? process.env.NEXT_PUBLIC_API_URL.replace(/^http/, 'ws')
        : 'ws://localhost:8000');
    this.url = `${wsBase}/ws/dashboard`;
  }

  connect(channels: string[] = []) {
    if (typeof window === 'undefined') return;

    this.channels = channels;

    try {
      const params = channels.length > 0
        ? `?channels=${channels.join(',')}`
        : '';
      this.ws = new WebSocket(`${this.url}${params}`);

      this.ws.onopen = () => {
        console.log('[WS] Connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
      };

      this.ws.onmessage = (event: MessageEvent) => {
        this.handleMessage(event);
      };

      this.ws.onclose = (event) => {
        console.log('[WS] Disconnected', event.code, event.reason);
        if (event.code !== 1000) {
          this.reconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error);
      };
    } catch (err) {
      console.error('[WS] Connection failed:', err);
      this.reconnect();
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.reconnectAttempts = 0;
  }

  subscribe(channel: string, callback: MessageHandler) {
    if (!this.listeners.has(channel)) {
      this.listeners.set(channel, new Set());
    }
    this.listeners.get(channel)!.add(callback);

    // Return unsubscribe function
    return () => this.unsubscribe(channel, callback);
  }

  unsubscribe(channel: string, callback: MessageHandler) {
    const channelListeners = this.listeners.get(channel);
    if (channelListeners) {
      channelListeners.delete(callback);
      if (channelListeners.size === 0) {
        this.listeners.delete(channel);
      }
    }
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('[WS] Cannot send - not connected');
    }
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  private handleMessage(event: MessageEvent) {
    try {
      const message = JSON.parse(event.data);
      const channel = message.channel || message.type || 'default';
      const data = message.data || message;

      // Notify channel-specific listeners
      const channelListeners = this.listeners.get(channel);
      if (channelListeners) {
        channelListeners.forEach((callback) => {
          try {
            callback(data);
          } catch (err) {
            console.error(`[WS] Listener error on channel '${channel}':`, err);
          }
        });
      }

      // Notify wildcard listeners
      const wildcardListeners = this.listeners.get('*');
      if (wildcardListeners) {
        wildcardListeners.forEach((callback) => {
          try {
            callback({ channel, data });
          } catch (err) {
            console.error('[WS] Wildcard listener error:', err);
          }
        });
      }
    } catch (err) {
      console.error('[WS] Failed to parse message:', err);
    }
  }

  private reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached');
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1),
      30000
    );

    console.log(
      `[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );

    this.reconnectTimer = setTimeout(() => {
      this.connect(this.channels);
    }, delay);
  }
}

// Singleton instance
export const wsClient = new WebSocketClient();

// React hook helper
export function useWebSocket(channel: string, callback: MessageHandler) {
  if (typeof window !== 'undefined') {
    // This is a simple helper - in a real app, use useEffect in the component
    return wsClient.subscribe(channel, callback);
  }
  return () => {};
}
