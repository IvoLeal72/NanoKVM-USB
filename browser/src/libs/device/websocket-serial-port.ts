import { raceWithTimeout } from './utils';

export type WsSerialOptions = {
  url: string;
  onDisconnect?: () => void;
};

export class WebSocketSerialPort {
  readonly READ_TIMEOUT = 500;
  readonly CONNECT_TIMEOUT = 5000;

  private ws: WebSocket | null = null;
  private recvBuffer: number[] = [];
  private pendingRead: { minSize: number; resolve: (data: number[]) => void } | null = null;
  private onDisconnect?: () => void;

  async init(options: WsSerialOptions): Promise<void> {
    if (this.ws) {
      await this.close();
    }

    this.onDisconnect = options.onDisconnect;

    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('WebSocket connection timed out'));
      }, this.CONNECT_TIMEOUT);

      const ws = new WebSocket(options.url);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        clearTimeout(timeout);
        this.ws = ws;
        resolve();
      };

      ws.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('WebSocket connection failed'));
      };

      ws.onmessage = (event: MessageEvent) => {
        this.onMessage(event.data as ArrayBuffer);
      };

      ws.onclose = () => {
        this.onClose();
      };
    });
  }

  async write(data: number[]): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }
    this.ws.send(new Uint8Array(data));
  }

  async read(minSize: number, delayAfterRead: number = 0): Promise<number[]> {
    if (!this.ws) {
      throw new Error('WebSocket not connected');
    }

    if (this.recvBuffer.length >= minSize) {
      const result = this.recvBuffer.splice(0, this.recvBuffer.length);
      if (delayAfterRead > 0) {
        await new Promise((resolve) => setTimeout(resolve, delayAfterRead));
      }
      return result;
    }

    const data = await raceWithTimeout(
      new Promise<number[]>((resolve) => {
        this.pendingRead = { minSize, resolve };
      }),
      this.READ_TIMEOUT
    );

    this.pendingRead = null;

    if (delayAfterRead > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayAfterRead));
    }

    return data ?? [];
  }

  async close(): Promise<void> {
    this.pendingRead = null;
    if (this.ws) {
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.recvBuffer = [];
    this.onDisconnect = undefined;
  }

  private onMessage(buf: ArrayBuffer): void {
    const bytes = Array.from(new Uint8Array(buf));
    this.recvBuffer.push(...bytes);

    if (this.pendingRead && this.recvBuffer.length >= this.pendingRead.minSize) {
      const result = this.recvBuffer.splice(0, this.recvBuffer.length);
      this.pendingRead.resolve(result);
      this.pendingRead = null;
    }
  }

  private onClose(): void {
    if (this.pendingRead) {
      this.pendingRead.resolve([]);
      this.pendingRead = null;
    }
    this.ws = null;
    this.recvBuffer = [];
    if (this.onDisconnect) {
      this.onDisconnect();
      this.onDisconnect = undefined;
    }
  }
}
