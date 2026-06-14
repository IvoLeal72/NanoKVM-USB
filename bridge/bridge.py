#!/usr/bin/env python3
"""
NanoKVM-USB bridge server for Raspberry Pi.

Both endpoints on the same port:
  ws://<host>:<PORT>/serial  — bidirectional binary relay to the serial port
  http://<host>:<PORT>/video — MJPEG multipart stream from the USB capture device

Environment variables:
  SERIAL_PORT   path to the NanoKVM-USB serial device (default: /dev/ttyUSB0)
  VIDEO_DEVICE  path to the USB video capture device  (default: /dev/video0)
  PORT          server port                            (default: 8080)
"""

import asyncio
import logging
import os
import subprocess

import aiohttp
from aiohttp import web

import serial as pyserial

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyUSB0")
VIDEO_DEVICE = os.environ.get("VIDEO_DEVICE", "/dev/video0")
PORT = int(os.environ.get("PORT", "8080"))
BAUD_RATE = 57600
BOUNDARY = "frame"

_current_ws = None
_ws_lock = asyncio.Lock()


async def serial_handler(request):
    global _current_ws

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async with _ws_lock:
        if _current_ws is not None and not _current_ws.closed:
            await _current_ws.close()
        _current_ws = ws

    log.info("WebSocket client connected: %s", request.remote)

    try:
        ser = pyserial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0)
    except pyserial.SerialException as exc:
        log.error("Cannot open serial port %s: %s", SERIAL_PORT, exc)
        await ws.close()
        return ws

    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    async def read_serial():
        while not stop.is_set() and not ws.closed:
            data = await loop.run_in_executor(None, lambda: ser.read(256))
            if data:
                try:
                    await ws.send_bytes(data)
                except Exception:
                    break
            else:
                await asyncio.sleep(0.001)

    read_task = asyncio.create_task(read_serial())

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                try:
                    ser.write(msg.data)
                except pyserial.SerialException:
                    break
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                break
    finally:
        stop.set()
        read_task.cancel()
        ser.close()
        log.info("WebSocket client disconnected: %s", request.remote)

    return ws


async def video_handler(request):
    log.info("Video stream request from %s", request.remote)

    response = web.StreamResponse(headers={
        "Content-Type": f"multipart/x-mixed-replace; boundary={BOUNDARY}",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    })
    await response.prepare(request)

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "quiet",
        "-f", "v4l2",
        "-input_format", "mjpeg",
        "-i", VIDEO_DEVICE,
        "-c:v", "copy",
        "-f", "image2pipe",
        "-vcodec", "mjpeg",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"
    buf = b""

    # Single-slot queue: always drop the old frame when a newer one is ready,
    # so a slow client always receives the latest frame rather than lagging.
    frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)

    async def read_frames():
        nonlocal buf
        try:
            while True:
                chunk = await proc.stdout.read(65536)
                if not chunk:
                    break
                buf += chunk

                while True:
                    start = buf.find(SOI)
                    if start == -1:
                        buf = b""
                        break
                    end = buf.find(EOI, start + 2)
                    if end == -1:
                        buf = buf[start:]
                        break
                    frame = buf[start:end + 2]
                    buf = buf[end + 2:]

                    header = (
                        f"--{BOUNDARY}\r\n"
                        "Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(frame)}\r\n\r\n"
                    ).encode()
                    packet = header + frame + b"\r\n"

                    # Drop the previous unsent frame if client is behind
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    await frame_queue.put(packet)
        finally:
            await frame_queue.put(b"")  # sentinel to stop writer

    reader = asyncio.create_task(read_frames())

    try:
        while True:
            packet = await frame_queue.get()
            if not packet:
                break
            try:
                await response.write(packet)
            except (ConnectionResetError, asyncio.CancelledError):
                break
    finally:
        reader.cancel()
        proc.kill()
        await proc.wait()
        log.info("Video stream ended for %s", request.remote)

    return response


app = web.Application()
app.router.add_get("/serial", serial_handler)
app.router.add_get("/video", video_handler)

if __name__ == "__main__":
    log.info(
        "NanoKVM-USB bridge starting — serial=%s  video=%s  port=%d",
        SERIAL_PORT, VIDEO_DEVICE, PORT,
    )
    web.run_app(app, host="0.0.0.0", port=PORT)
