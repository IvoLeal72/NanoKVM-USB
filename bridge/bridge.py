#!/usr/bin/env python3
"""
NanoKVM-USB bridge server for Raspberry Pi.

Both endpoints are served on the same port:
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
import threading

import serial
import websockets
from websockets.http11 import Request, Response
from websockets.datastructures import Headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyUSB0")
VIDEO_DEVICE = os.environ.get("VIDEO_DEVICE", "/dev/video0")
PORT = int(os.environ.get("PORT", "8080"))
BAUD_RATE = 57600
BOUNDARY = "frame"

_ws_lock = asyncio.Lock()
_current_ws = None


# ---------------------------------------------------------------------------
# MJPEG streaming (runs in a thread, writes to a raw socket-like writer)
# ---------------------------------------------------------------------------

def _stream_mjpeg(writer_transport):
    """Spawns ffmpeg, parses JPEG frames, writes multipart chunks to transport."""
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"

    ffmpeg = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "quiet",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-i", VIDEO_DEVICE,
            "-c:v", "copy",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    buf = b""
    try:
        while True:
            chunk = ffmpeg.stdout.read(65536)
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
                frame = buf[start : end + 2]
                buf = buf[end + 2 :]

                header = (
                    f"--{BOUNDARY}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n\r\n"
                ).encode()
                try:
                    writer_transport.write(header + frame + b"\r\n")
                except Exception:
                    return
    finally:
        ffmpeg.kill()
        ffmpeg.wait()


# ---------------------------------------------------------------------------
# WebSocket serial relay
# ---------------------------------------------------------------------------

async def serial_ws_handler(websocket):
    global _current_ws

    async with _ws_lock:
        if _current_ws is not None:
            try:
                await _current_ws.close()
            except Exception:
                pass
        _current_ws = websocket

    log.info("WebSocket client connected: %s", websocket.remote_address)

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0)
    except serial.SerialException as exc:
        log.error("Cannot open serial port %s: %s", SERIAL_PORT, exc)
        await websocket.close()
        return

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def read_serial():
        while not stop_event.is_set():
            try:
                data = ser.read(256)
                if data:
                    asyncio.run_coroutine_threadsafe(websocket.send(data), loop)
            except serial.SerialException:
                stop_event.set()
                break

    reader_thread = threading.Thread(target=read_serial, daemon=True)
    reader_thread.start()

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                ser.write(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        stop_event.set()
        ser.close()
        log.info("WebSocket client disconnected: %s", websocket.remote_address)
        async with _ws_lock:
            if _current_ws is websocket:
                _current_ws = None


# ---------------------------------------------------------------------------
# HTTP request interceptor (handles /video before WebSocket upgrade)
# ---------------------------------------------------------------------------

async def process_request(connection, request):
    """Called for every incoming HTTP request before WebSocket upgrade."""
    if request.path == "/video":
        log.info("Video stream request from %s", connection.remote_address)

        headers = Headers([
            ("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}"),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "no-cache"),
            ("Connection", "close"),
        ])

        # Return a 200 response — websockets will send headers and close the WS handshake path
        response = Response(200, "OK", headers, b"")

        # Stream frames in a background thread using the raw transport
        transport = connection.transport

        def stream():
            _stream_mjpeg(transport)
            transport.close()

        threading.Thread(target=stream, daemon=True).start()

        return response

    # For all other non-/serial paths return 404
    if request.path != "/serial":
        return Response(404, "Not Found", Headers([("Content-Length", "0")]), b"")

    # Return None to let websockets continue with the upgrade handshake
    return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    log.info(
        "NanoKVM-USB bridge starting — serial=%s  video=%s  port=%d",
        SERIAL_PORT, VIDEO_DEVICE, PORT,
    )
    async with websockets.serve(
        serial_ws_handler,
        "0.0.0.0",
        PORT,
        process_request=process_request,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
