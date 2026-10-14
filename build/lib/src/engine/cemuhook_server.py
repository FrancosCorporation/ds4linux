"""CemuHook (DSU) UDP motion server — protocol v1001.

Implements the binary DSU wire format documented at
https://github.com/v1993/cemuhook-protocol (README.md):

  Header (16 bytes, little endian):
    0   4  magic      "DSUC" in requests, "DSUS" in replies
    4   2  u16 version (1001)
    6   2  u16 length  = len(packet) - 16 (message type included!)
    8   4  u32 crc32   of the whole packet with this field zeroed
    12  4  u32 sender id (stable per run, random on startup)
    16  4  u32 message type (counts towards length)

  Message types (same value for request and reply):
    0x100000  protocol version (reply payload: u16 max version)
    0x100001  controllers info (reply payload: 12 bytes per slot)
    0x100002  controller data   (reply payload: 80 bytes, 100 total)
    0x110001  motors info       (unofficial, reply payload: 12 bytes)
    0x110002  rumble            (unofficial, incoming only)

The server replies only to the requesting address, streams registered data
at ~100 Hz per (client, slot), expires clients after CLIENT_TIMEOUT_S and
resets rumble motors when rumble packets stop arriving for that long.
"""
from __future__ import annotations

import logging
import math
import random
import select
import socket
import struct
import threading
import time
import zlib

logger = logging.getLogger(__name__)

DSU_VERSION = 1001
DSU_PROTOCOL_VERSION = DSU_VERSION  # backwards-compatible alias
DEFAULT_PORT = 26760

MAGIC_IN = b"DSUC"
MAGIC_OUT = b"DSUS"
HEADER_LEN = 16
TYPE_LEN = 4
MIN_REQUEST_LEN = HEADER_LEN + TYPE_LEN

MSG_VERSION = 0x100000
MSG_INFO = 0x100001
MSG_DATA = 0x100002
MSG_MOTORS_INFO = 0x110001
MSG_RUMBLE = 0x110002

SLOT_DISCONNECTED = 0
SLOT_CONNECTED = 2
MODEL_FULL_GYRO = 2
MOTOR_COUNT_DS4 = 2

CLIENT_TIMEOUT_S = 5.0
STREAM_HZ = 100
MAX_SLOTS = 4
MAX_CLIENTS = 16

# Battery status values (DSU spec)
BATT_DYING = 0x01
BATT_LOW = 0x02
BATT_MEDIUM = 0x03
BATT_HIGH = 0x04
BATT_FULL = 0x05
BATT_CHARGING = 0xEE
BATT_CHARGED = 0xEF


def build_packet(msg_type: int, payload: bytes, sender_id: int) -> bytes:
    """Serialize a server->client DSU packet with a valid CRC32."""
    length = TYPE_LEN + len(payload)
    pkt = bytearray(
        struct.pack(
            "<4sHHI I", MAGIC_OUT, DSU_VERSION, length, 0, sender_id & 0xFFFFFFFF
        )
    )
    pkt += struct.pack("<I", msg_type) + payload
    crc = zlib.crc32(pkt) & 0xFFFFFFFF
    struct.pack_into("<I", pkt, 8, crc)
    return bytes(pkt)


def parse_request(data: bytes) -> tuple[int, bytes] | None:
    """Validate one client->server datagram.

    Returns ``(msg_type, payload)`` or ``None`` when the packet must be
    dropped (bad magic/version/length/CRC).
    """
    if len(data) < MIN_REQUEST_LEN:
        return None
    if data[:4] != MAGIC_IN:
        return None
    version, length = struct.unpack_from("<HH", data, 4)
    if version != DSU_VERSION:
        return None
    total = HEADER_LEN + length
    if total < MIN_REQUEST_LEN:
        return None
    if len(data) < total:
        return None
    data = data[:total]  # truncate when datagram is longer than declared
    crc = struct.unpack_from("<I", data, 8)[0]
    if crc != 0:
        probe = bytearray(data)
        struct.pack_into("<I", probe, 8, 0)
        if (zlib.crc32(probe) & 0xFFFFFFFF) != crc:
            return None
    msg_type = struct.unpack_from("<I", data, HEADER_LEN)[0]
    return msg_type, data[MIN_REQUEST_LEN:]


def build_slot_begin(
    slot: int,
    state: int,
    model: int,
    connection_type: int,
    mac: bytes,
    battery: int,
) -> bytes:
    """The 11-byte 'shared response beginning' used by info/data/motors."""
    mac6 = bytes(mac[:6]).ljust(6, b"\x00")
    return bytes((slot & 0xFF, state & 0xFF, model & 0xFF, connection_type & 0xFF)) + mac6 + bytes((battery & 0xFF,))


def dsu_battery_status(capacity: int, charging: bool) -> int:
    """Map a DS4 battery capacity (0..11) + cable state to a DSU value.

    Cable first: 0xEE/0xEF describe the charging state, which only exists
    with the cable plugged in; a full battery running on battery power is
    0x05 (full), not "charged".
    """
    if charging:
        return BATT_CHARGED if capacity >= 11 else BATT_CHARGING
    if capacity >= 11:
        return BATT_FULL
    if capacity <= 1:
        return BATT_DYING
    if capacity <= 4:
        return BATT_LOW
    if capacity <= 7:
        return BATT_MEDIUM
    if capacity <= 9:
        return BATT_HIGH
    return BATT_FULL


def _sanitize_meta(provider) -> tuple[int, int, bytes, int]:
    """Read (model, connection_type, mac, battery) from a provider safely."""
    try:
        model = int(getattr(provider, "device_model", MODEL_FULL_GYRO))
    except (TypeError, ValueError):
        model = MODEL_FULL_GYRO
    try:
        conn = int(getattr(provider, "connection_type", 1))
    except (TypeError, ValueError):
        conn = 1
    mac = getattr(provider, "mac", b"\x00" * 6)
    if not isinstance(mac, (bytes, bytearray)):
        mac = b"\x00" * 6
    try:
        battery = int(getattr(provider, "battery", BATT_HIGH))
    except (TypeError, ValueError):
        battery = BATT_HIGH
    return (
        model if 0 <= model <= 3 else MODEL_FULL_GYRO,
        conn if 0 <= conn <= 2 else 1,
        bytes(mac[:6]).ljust(6, b"\x00"),
        battery if 0 <= battery <= 0xFF else BATT_HIGH,
    )


class MotionProvider:
    """Source of motion data for a single controller slot.

    ``get_motion()`` must return a 6-tuple:
        (accel_x, accel_y, accel_z, gyro_pitch, gyro_yaw, gyro_roll)
    accel in g (1.0 == 1g), gyro in degrees/second.

    Optional attributes read by the server: ``device_model``,
    ``connection_type``, ``mac``, ``battery``.
    """

    device_model = MODEL_FULL_GYRO
    connection_type = 1  # 0 n/a, 1 USB, 2 bluetooth
    mac = b"\x00" * 6
    battery = BATT_HIGH

    def get_motion(self) -> tuple[float, float, float, float, float, float]:
        return (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


class CemuHookServer:
    """CemuHook (DSU) UDP server streaming DS4 motion data to emulators."""

    def __init__(self, port: int = DEFAULT_PORT, server_id: int | None = None):
        self.port = port
        self.server_id = (
            server_id & 0xFFFFFFFF if server_id is not None else random.getrandbits(32)
        )
        self.running = False
        self.thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._providers: dict[int, MotionProvider] = {}
        self._providers_lock = threading.Lock()
        # Client state (address -> ...) — only mutated from the server thread
        # except set_provider()/set_rumble_handler(), which are lock-guarded.
        self._subs: dict[tuple[str, int], set[int] | None] = {}
        self._last_seen: dict[tuple[str, int], float] = {}
        self._packet_no: dict[tuple[tuple[str, int], int], int] = {}
        self._rumble_state: dict[int, dict[int, int]] = {}
        self._rumble_last: dict[int, float] = {}
        self._rumble_handler = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> bool:
        if self.running:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Loopback only: the spec targets localhost:26760, and motion
            # data / rumble must not be reachable from the LAN.
            self._sock.bind(("127.0.0.1", self.port))
            self._sock.setblocking(False)
            if self.port == 0:
                self.port = self._sock.getsockname()[1]
        except OSError as ex:
            logger.error(f"CemuHook: cannot bind UDP port {self.port}: {ex}")
            self._sock = None
            return False

        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="cemuhook-server"
        )
        self.thread.start()
        logger.info(f"CemuHook server started on UDP port {self.port}")
        return True

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._subs.clear()
        self._last_seen.clear()
        self._packet_no.clear()
        self._rumble_state.clear()
        self._rumble_last.clear()
        logger.info("CemuHook server stopped")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def set_provider(self, slot: int, provider: MotionProvider | None):
        # Public API: an out-of-range slot would be stored and later sent
        # with a truncated byte (slot & 0xFF), colliding with a legit slot
        # on the client side.
        if not 0 <= int(slot) < MAX_SLOTS:
            logger.warning("set_provider: slot %r out of range", slot)
            return
        with self._providers_lock:
            if provider is None:
                self._providers.pop(slot, None)
            else:
                self._providers[slot] = provider

    def set_rumble_handler(self, handler):
        """``handler(slot, motor_id, intensity 0..255)`` or None to disable."""
        self._rumble_handler = handler

    def _providers_snapshot(self) -> dict[int, MotionProvider]:
        with self._providers_lock:
            return dict(self._providers)

    # ------------------------------------------------------------------
    # Server loop (non-blocking socket + select; no busy wait)
    # ------------------------------------------------------------------
    def _run(self):
        interval = 1.0 / STREAM_HZ
        next_stream = time.monotonic()

        while self.running and self._sock is not None:
            now = time.monotonic()
            timeout = min(max(next_stream - now, 0.0), 0.25)
            try:
                readable, _, _ = select.select([self._sock], [], [], timeout)
            except (OSError, ValueError):
                break
            if readable:
                self._drain_requests()

            now = time.monotonic()
            if now >= next_stream:
                next_stream += interval
                if next_stream < now - 1.0:  # fell far behind
                    next_stream = now + interval
                try:
                    self._stream_tick(now)
                except Exception:
                    logger.exception("CemuHook: motion stream error")

    def _drain_requests(self):
        for _ in range(64):
            try:
                data, addr = self._sock.recvfrom(4096)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            try:
                self._handle_request(data, addr)
            except Exception:
                logger.exception("CemuHook: request handling error from %s", addr)

    # ------------------------------------------------------------------
    # Request handling
    # ------------------------------------------------------------------
    def _handle_request(self, data: bytes, addr: tuple[str, int]):
        parsed = parse_request(data)
        if parsed is None:
            return
        msg_type, payload = parsed
        now = time.monotonic()
        self._touch(addr, now)
        if msg_type == MSG_VERSION:
            self._send(MSG_VERSION, struct.pack("<H", DSU_VERSION), addr)
        elif msg_type == MSG_INFO:
            self._handle_info(payload, addr)
        elif msg_type == MSG_DATA:
            self._handle_data(payload, addr, now)
        elif msg_type == MSG_MOTORS_INFO:
            self._handle_motors_info(payload, addr)
        elif msg_type == MSG_RUMBLE:
            self._handle_rumble(payload, addr, now)

    def _touch(self, addr: tuple[str, int], now: float):
        # Bound the table: sources that send one datagram and vanish must
        # not grow _last_seen without limit within the 5 s expiry window.
        if addr not in self._last_seen and len(self._last_seen) >= MAX_CLIENTS * 4:
            oldest = min(self._last_seen, key=self._last_seen.get)
            self._last_seen.pop(oldest, None)
            self._subs.pop(oldest, None)
            for key in [k for k in self._packet_no if k[0] == oldest]:
                self._packet_no.pop(key, None)
        self._last_seen[addr] = now

    def _handle_info(self, payload: bytes, addr: tuple[str, int]):
        """Reply with one 12-byte controller info packet per requested slot."""
        if len(payload) < 4:
            return
        count = struct.unpack_from("<i", payload, 0)[0]
        if not 0 < count <= MAX_SLOTS:
            return
        if len(payload) < 4 + count:
            return
        providers = self._providers_snapshot()
        for slot in payload[4 : 4 + count]:
            if slot >= MAX_SLOTS:
                continue
            provider = providers.get(slot)
            if provider is None:
                body = build_slot_begin(
                    slot, SLOT_DISCONNECTED, 0, 0, b"\x00" * 6, 0
                )
            else:
                model, conn, mac, battery = _sanitize_meta(provider)
                body = build_slot_begin(slot, SLOT_CONNECTED, model, conn, mac, battery)
            self._send(MSG_INFO, body + b"\x00", addr)

    def _resolve_slot(self, flags: int, slot: int, mac: bytes) -> int | None:
        """Resolve an 8-byte controller identification header to a slot."""
        providers = self._providers_snapshot()
        if flags & 0x01:
            return slot if slot < MAX_SLOTS else None
        if flags & 0x02:
            if mac == b"\x00" * 6:
                return None
            for s, provider in providers.items():
                p_model, p_conn, p_mac, p_batt = _sanitize_meta(provider)
                if p_mac == bytes(mac[:6]):
                    return s
            return None
        # No bits: identification carried in the slot byte itself
        return slot if slot < MAX_SLOTS else None

    def _handle_data(self, payload: bytes, addr: tuple[str, int], now: float):
        """Register the client for a slot-based, MAC-based or all-slots stream."""
        if len(payload) < 8:
            return
        flags, slot = payload[0], payload[1]
        mac = bytes(payload[2:8])
        providers = self._providers_snapshot()

        if flags & 0x03:
            resolved = set()
            if flags & 0x01:
                if slot >= MAX_SLOTS or slot not in providers:
                    return  # requested controller not connected -> ignore
                resolved.add(slot)
            if flags & 0x02:
                mac_slot = self._resolve_slot(flags & 0x02, slot, mac)
                if mac_slot is None or mac_slot not in providers:
                    if not resolved:
                        return
                else:
                    resolved.add(mac_slot)
            sub: set[int] | None = resolved
        else:
            sub = None  # subscribe to all controllers

        self._last_seen[addr] = now
        self._subs[addr] = sub
        self._enforce_client_cap(addr, now)

    def _enforce_client_cap(self, addr: tuple[str, int], now: float):
        if len(self._subs) <= MAX_CLIENTS:
            return
        for stale in sorted(
            (a for a in self._subs if a != addr),
            key=lambda a: self._last_seen.get(a, now),
        )[: len(self._subs) - MAX_CLIENTS]:
            self._subs.pop(stale, None)
            self._last_seen.pop(stale, None)
            for key in [k for k in self._packet_no if k[0] == stale]:
                self._packet_no.pop(key, None)

    def _handle_motors_info(self, payload: bytes, addr: tuple[str, int]):
        """Reply with 11-byte slot beginning + motor count."""
        if len(payload) < 8:
            return
        flags, slot = payload[0], payload[1]
        mac = bytes(payload[2:8])
        resolved = self._resolve_slot(flags, slot, mac)
        if resolved is None:
            body = build_slot_begin(0, SLOT_DISCONNECTED, 0, 0, b"\x00" * 6, 0)
            self._send(MSG_MOTORS_INFO, body + bytes((0,)), addr)
            return
        provider = self._providers_snapshot().get(resolved)
        if provider is None:
            body = build_slot_begin(resolved, SLOT_DISCONNECTED, 0, 0, b"\x00" * 6, 0)
            motor_count = 0
        else:
            model, conn, mac6, battery = _sanitize_meta(provider)
            body = build_slot_begin(resolved, SLOT_CONNECTED, model, conn, mac6, battery)
            motor_count = MOTOR_COUNT_DS4
        self._send(MSG_MOTORS_INFO, body + bytes((motor_count,)), addr)

    def _handle_rumble(self, payload: bytes, addr: tuple[str, int], now: float):
        """Store motor intensity and forward it to the registered handler."""
        if len(payload) < 10:
            return
        flags, slot = payload[0], payload[1]
        mac = bytes(payload[2:8])
        motor_id, intensity = payload[8], payload[9]
        resolved = self._resolve_slot(flags, slot, mac)
        if resolved is None or resolved not in self._providers_snapshot():
            return
        if motor_id >= MOTOR_COUNT_DS4:
            return
        self._rumble_state.setdefault(resolved, {})[motor_id] = intensity
        self._rumble_last[resolved] = now
        handler = self._rumble_handler
        if handler is not None:
            try:
                handler(resolved, motor_id, intensity)
            except Exception:
                logger.exception("CemuHook: rumble handler failed")

    # ------------------------------------------------------------------
    # Streaming / expiry
    # ------------------------------------------------------------------
    def _stream_tick(self, now: float | None = None):
        now = time.monotonic() if now is None else now
        self._expire(now)
        if not self._subs:
            return
        providers = self._providers_snapshot()
        for addr, sub in list(self._subs.items()):
            for slot in sorted(providers):
                if sub is not None and slot not in sub:
                    continue
                provider = providers[slot]
                try:
                    motion = provider.get_motion()
                except Exception:
                    logger.exception("CemuHook: provider for slot %s failed", slot)
                    continue
                key = (addr, slot)
                pkt_no = (self._packet_no.get(key, 0) + 1) & 0xFFFFFFFF
                self._packet_no[key] = pkt_no
                payload = self._build_data_payload(slot, provider, pkt_no, motion, now)
                self._send(MSG_DATA, payload, addr)

    def _build_data_payload(
        self,
        slot: int,
        provider: MotionProvider,
        pkt_no: int,
        motion,
        now: float,
    ) -> bytes:
        """Build the 80-byte DATA payload.

        Scope decision: motion-only. Buttons (16..19), analog buttons
        (24..35) and touches (36..47) stay zero — emulators using the DSU
        for gyro/accel (Cemu/Yuzu/Dolphin) are the target; button state
        flows through the emulated uinput device instead.
        """
        buf = bytearray(80)
        model, conn, mac, battery = _sanitize_meta(provider)
        buf[0:11] = build_slot_begin(slot, SLOT_CONNECTED, model, conn, mac, battery)
        buf[11] = 1  # connected
        struct.pack_into("<I", buf, 12, pkt_no)
        # Buttons 16..19 stay 0 (released).
        buf[20:24] = b"\x80\x80\x80\x80"  # sticks neutral (Y: plus upward)
        # Analog buttons 24..35 stay 0; touches 36..47 stay inactive.
        timestamp_us = int(time.time() * 1_000_000) & 0xFFFFFFFFFFFFFFFF
        struct.pack_into("<Q", buf, 48, timestamp_us)
        try:
            ax, ay, az, pitch, yaw, roll = (float(v) for v in motion)
        except (TypeError, ValueError):
            ax = ay = az = pitch = yaw = roll = 0.0
        values = (ax, ay, az, pitch, yaw, roll)
        if not all(math.isfinite(v) for v in values):
            values = (0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        struct.pack_into("<6f", buf, 56, *values)
        return bytes(buf)

    def _expire(self, now: float):
        """Drop silent clients and reset stale rumble motors to zero."""
        # list() snapshot: stop() may clear the dict from another thread if
        # its join timed out (RuntimeError during iteration otherwise).
        dead = [a for a, t in list(self._last_seen.items()) if now - t > CLIENT_TIMEOUT_S]
        for addr in dead:
            self._last_seen.pop(addr, None)
            self._subs.pop(addr, None)
            for key in [k for k in self._packet_no if k[0] == addr]:
                self._packet_no.pop(key, None)

        for slot, last in list(self._rumble_last.items()):
            if now - last <= CLIENT_TIMEOUT_S:
                continue
            state = self._rumble_state.pop(slot, {})
            self._rumble_last.pop(slot, None)
            handler = self._rumble_handler
            if handler is None:
                continue
            for motor_id, intensity in state.items():
                if intensity == 0:
                    continue
                try:
                    handler(slot, motor_id, 0)
                except Exception:
                    logger.exception("CemuHook: rumble handler failed")

    # ------------------------------------------------------------------
    def _send(self, msg_type: int, payload: bytes, addr: tuple[str, int]):
        if self._sock is None:
            return
        try:
            self._sock.sendto(build_packet(msg_type, payload, self.server_id), addr)
        except OSError:
            logger.debug("CemuHook: sendto failed for %s", addr)
