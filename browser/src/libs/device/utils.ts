export function raceWithTimeout<T>(promise: Promise<T>, ms: number): Promise<T | undefined> {
  return Promise.race([
    promise,
    new Promise<undefined>((resolve) => setTimeout(() => resolve(undefined), ms))
  ]);
}

export function getScreenElement(): HTMLElement | null {
  const mode = localStorage.getItem('nanokvm-usb-connection-mode');
  return mode === 'bridge'
    ? document.getElementById('bridge-video')
    : document.getElementById('video');
}

export function isDisconnectError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;

  const { name, message = '' } = err;
  const msg = message.toLowerCase();

  return (
    name === 'NetworkError' ||
    name === 'InvalidStateError' ||
    name === 'NotFoundError' ||
    msg.includes('disconnected') ||
    msg.includes('device has been lost') ||
    msg.includes('the device has been closed')
  );
}
