class MjpegCamera {
  private currentUrl: string = '';

  open(url: string): void {
    this.currentUrl = url;
    const img = document.getElementById('bridge-video') as HTMLImageElement | null;
    if (img) {
      img.src = url;
    }
  }

  close(): void {
    const img = document.getElementById('bridge-video') as HTMLImageElement | null;
    if (img) {
      img.src = '';
    }
    this.currentUrl = '';
  }

  isOpen(): boolean {
    return this.currentUrl !== '';
  }

  getUrl(): string {
    return this.currentUrl;
  }
}

export const mjpegCamera = new MjpegCamera();
