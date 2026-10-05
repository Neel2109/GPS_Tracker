/**
 * TrackGuard WebSocket Service
 * Manages real-time communication with the backend for dashboard updates.
 */
import { getAccessToken } from './api';
import type { WSMessage } from '../types';

const WS_BASE = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

type MessageHandler = (message: WSMessage) => void;

class WebSocketService {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private globalHandlers: Set<MessageHandler> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 2000;
  private maxReconnectDelay = 30000;
  private userId: string | null = null;
  private isConnecting = false;

  connect(userId: string) {
    this.userId = userId;
    this._connect();
  }

  private _connect() {
    if (this.isConnecting || !this.userId) return;
    this.isConnecting = true;

    const token = getAccessToken();
    if (!token) {
      this.isConnecting = false;
      return;
    }

    const url = `${WS_BASE}/ws/dashboard/${this.userId}?token=${token}`;

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        console.log('[WS] Connected to TrackGuard');
        this.isConnecting = false;
        this.reconnectDelay = 2000;
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data);
          this._dispatch(message);
        } catch (err) {
          console.error('[WS] Parse error:', err);
        }
      };

      this.ws.onclose = () => {
        console.log('[WS] Disconnected');
        this.isConnecting = false;
        this._scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        this.isConnecting = false;
      };
    } catch (err) {
      console.error('[WS] Connection error:', err);
      this.isConnecting = false;
      this._scheduleReconnect();
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
      this._connect();
    }, this.reconnectDelay);
  }

  private _dispatch(message: WSMessage) {
    // Dispatch to type-specific handlers
    const typeHandlers = this.handlers.get(message.type);
    if (typeHandlers) {
      typeHandlers.forEach(handler => handler(message));
    }

    // Dispatch to global handlers
    this.globalHandlers.forEach(handler => handler(message));
  }

  on(type: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set());
    }
    this.handlers.get(type)!.add(handler);

    return () => {
      this.handlers.get(type)?.delete(handler);
    };
  }

  onAny(handler: MessageHandler): () => void {
    this.globalHandlers.add(handler);
    return () => {
      this.globalHandlers.delete(handler);
    };
  }

  send(message: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.handlers.clear();
    this.globalHandlers.clear();
    this.userId = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsService = new WebSocketService();
