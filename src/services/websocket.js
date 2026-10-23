export class MarketWebSocketClient {
  constructor(url, { onMessage, onOpen, onClose, onError, reconnectDelay = 1500 } = {}) {
    this.url = url;
    this.onMessage = onMessage || (() => {});
    this.onOpen = onOpen || (() => {});
    this.onClose = onClose || (() => {});
    this.onError = onError || (() => {});
    this.reconnectDelay = reconnectDelay;
    this.socket = null;
    this.isConnected = false;
    this.retryTimer = null;
    this.shouldReconnect = true;
  }

  connect() {
    if (!this.shouldReconnect || !this.url) {
      return;
    }

    if (
      this.socket &&
      [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.socket.readyState)
    ) {
      return;
    }

    let socket;
    try {
      socket = new WebSocket(this.url);
    } catch (error) {
      this.isConnected = false;
      this.onError(error);
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.addEventListener('open', () => {
      if (this.socket !== socket || !this.shouldReconnect) {
        socket.close();
        return;
      }
      this.isConnected = true;
      this.onOpen();
    });

    socket.addEventListener('message', (event) => {
      if (this.socket !== socket) {
        return;
      }

      try {
        const payload = JSON.parse(event.data);
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
          this.onMessage({
            status: 'error',
            error: { code: 'invalid_message', message: 'Server returned an invalid message.' },
          });
          return;
        }
        this.onMessage(payload);
      } catch (error) {
        this.onMessage({
          status: 'error',
          error: { code: 'malformed_message', message: 'Server returned malformed JSON.' },
        });
      }
    });

    socket.addEventListener('error', (event) => {
      if (this.socket !== socket) {
        return;
      }
      this.isConnected = false;
      this.onError(event);
    });

    socket.addEventListener('close', () => {
      if (this.socket !== socket) {
        return;
      }
      this.isConnected = false;
      this.socket = null;
      this.onClose();
      this.scheduleReconnect();
    });
  }

  scheduleReconnect() {
    if (!this.shouldReconnect || this.retryTimer !== null) {
      return;
    }

    this.retryTimer = window.setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.retryTimer) {
      window.clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }

    if (this.socket) {
      const socket = this.socket;
      this.socket = null;
      socket.close();
    }

    this.isConnected = false;
  }

  subscribe(symbols = []) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    const payload = {
      action: 'subscribe',
      symbols: Array.isArray(symbols) ? symbols : [symbols],
    };

    this.socket.send(JSON.stringify(payload));
    return true;
  }

  unsubscribe() {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    this.socket.send(JSON.stringify({ action: 'unsubscribe' }));
    return true;
  }
}
