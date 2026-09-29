"""Tests for the CemuHook (DSU) motion server against protocol v1001.

Spec reference: https://github.com/v1993/cemuhook-protocol (README.md)
Covers: packet codec (magic/version/length/CRC), every message type,
subscription scoping, client expiry, rumble handling, motion parsing
from raw DS4 reports and a real UDP end-to-end round trip.
"""

import socket
import struct
import time
import unittest
import zlib
from unittest import mock

from src.engine.cemuhook_server import (
    CLIENT_TIMEOUT_S,
    DSU_PROTOCOL_VERSION,
    MAX_CLIENTS,
    MSG_DATA,
    MSG_INFO,
    MSG_MOTORS_INFO,
    MSG_RUMBLE,
    MSG_VERSION,
    CemuHookServer,
    MotionProvider,
    build_packet,
    dsu_battery_status,
    parse_request,
)
from src.engine.motion_source import (
    DS4MotionProvider,
    parse_ds4_battery,
    parse_ds4_motion,
)


def client_packet(msg_type, payload=b"", client_id=0x0BADF00D):
    """Build a client->server DSU packet with a valid CRC."""
    length = 4 + len(payload)
    pkt = bytearray(
        struct.pack("<4sHHI I", b"DSUC", DSU_PROTOCOL_VERSION, length, 0, client_id)
    )
    pkt += struct.pack("<I", msg_type) + payload
    crc = zlib.crc32(pkt) & 0xFFFFFFFF
    struct.pack_into("<I", pkt, 8, crc)
    return bytes(pkt)


def decode_server(pkt):
    """Decode a server->client DSU packet into a dict."""
    version, length = struct.unpack_from("<HH", pkt, 4)
    crc = struct.unpack_from("<I", pkt, 8)[0]
    sender = struct.unpack_from("<I", pkt, 12)[0]
    msg_type = struct.unpack_from("<I", pkt, 16)[0]
    payload = pkt[20:16 + length]
    return {
        "magic": pkt[:4],
        "version": version,
        "length": length,
        "crc": crc,
        "sender": sender,
        "msg_type": msg_type,
        "payload": payload,
        "total": len(pkt),
    }


def check_crc(pkt):
    probe = bytearray(pkt)
    struct.pack_into("<I", probe, 8, 0)
    return (zlib.crc32(probe) & 0xFFFFFFFF) == struct.unpack_from("<I", pkt, 8)[0]


class FixedProvider(MotionProvider):
    """Provider returning a known motion sample."""

    def get_motion(self):
        return (0.5, -0.25, 1.0, 1.5, -2.0, 3.0)


class FakeSock:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


def make_server():
    srv = CemuHookServer(port=0, server_id=0x11223344)
    sock = FakeSock()
    srv._sock = sock
    return srv, sock.sent


def data_request(slot=0, flags=0x01, mac=b"\x00" * 6):
    return client_packet(MSG_DATA, bytes((flags, slot)) + mac)


# ---------------------------------------------------------------------------
# Packet codec
# ---------------------------------------------------------------------------
class TestDsuPacketCodec(unittest.TestCase):
    def test_server_header_layout(self):
        pkt = build_packet(MSG_VERSION, struct.pack("<H", 1001), 0xAABBCCDD)
        self.assertEqual(pkt[:4], b"DSUS")
        version, length = struct.unpack_from("<HH", pkt, 4)
        self.assertEqual(version, 1001)
        self.assertEqual(length, 4 + 2)  # message type + payload
        self.assertEqual(struct.unpack_from("<I", pkt, 12)[0], 0xAABBCCDD)
        self.assertEqual(struct.unpack_from("<I", pkt, 16)[0], MSG_VERSION)
        self.assertEqual(len(pkt), 16 + length)
        self.assertTrue(check_crc(pkt))

    def test_crc_covers_whole_packet_with_field_zeroed(self):
        pkt = build_packet(MSG_INFO, b"\x01\x02\x03\x04\x05", 42)
        probe = bytearray(pkt)
        struct.pack_into("<I", probe, 8, 0)
        self.assertEqual(
            struct.unpack_from("<I", pkt, 8)[0], zlib.crc32(probe) & 0xFFFFFFFF
        )

    def test_parse_request_roundtrip(self):
        pkt = client_packet(MSG_INFO, struct.pack("<i", 1) + b"\x00")
        parsed = parse_request(pkt)
        self.assertIsNotNone(parsed)
        msg_type, payload = parsed
        self.assertEqual(msg_type, MSG_INFO)
        self.assertEqual(payload, struct.pack("<i", 1) + b"\x00")

    def test_parse_rejects_bad_magic(self):
        pkt = bytearray(client_packet(MSG_VERSION))
        pkt[0:4] = b"XSUX"
        self.assertIsNone(parse_request(bytes(pkt)))

    def test_parse_rejects_wrong_version(self):
        pkt = bytearray(client_packet(MSG_VERSION))
        struct.pack_into("<H", pkt, 4, 999)
        self.assertIsNone(parse_request(bytes(pkt)))

    def test_parse_rejects_short_packet(self):
        self.assertIsNone(parse_request(b"DSUC" + b"\x00" * 10))

    def test_parse_rejects_truncated_length(self):
        pkt = bytearray(client_packet(MSG_VERSION))
        # Declare more bytes than the datagram carries
        struct.pack_into("<H", pkt, 6, 4 + 100)
        self.assertIsNone(parse_request(bytes(pkt)))

    def test_parse_rejects_bad_crc(self):
        pkt = bytearray(client_packet(MSG_INFO, struct.pack("<i", 1) + b"\x00"))
        pkt[-1] ^= 0xFF  # corrupt payload without fixing CRC
        self.assertIsNone(parse_request(bytes(pkt)))

    def test_parse_accepts_zero_crc(self):
        pkt = bytearray(client_packet(MSG_VERSION))
        struct.pack_into("<I", pkt, 8, 0)
        self.assertIsNotNone(parse_request(bytes(pkt)))

    def test_parse_truncates_extra_bytes(self):
        pkt = client_packet(MSG_VERSION) + b"garbage"
        parsed = parse_request(pkt)
        self.assertIsNotNone(parsed)
        msg_type, payload = parsed
        self.assertEqual(msg_type, MSG_VERSION)
        self.assertEqual(payload, b"")


# ---------------------------------------------------------------------------
# Server request handling (no real socket)
# ---------------------------------------------------------------------------
class TestDsuRequests(unittest.TestCase):
    def test_version_reply(self):
        srv, sent = make_server()
        srv._handle_request(client_packet(MSG_VERSION), ("10.0.0.1", 1234))
        self.assertEqual(len(sent), 1)
        pkt, addr = sent[0]
        self.assertEqual(addr, ("10.0.0.1", 1234))
        d = decode_server(pkt)
        self.assertEqual(d["magic"], b"DSUS")
        self.assertEqual(d["version"], 1001)
        self.assertEqual(d["msg_type"], MSG_VERSION)
        self.assertEqual(d["length"], 6)  # 4 type + 2 payload
        self.assertEqual(d["payload"], struct.pack("<H", 1001))
        self.assertEqual(d["sender"], srv.server_id)
        self.assertTrue(check_crc(pkt))

    def test_info_replies_connected_and_disconnected_slots(self):
        srv, sent = make_server()
        provider = MotionProvider()
        provider.connection_type = 2
        provider.mac = bytes.fromhex("112233445566")
        provider.battery = 0xEE
        srv.set_provider(1, provider)

        req = client_packet(MSG_INFO, struct.pack("<i", 2) + bytes((0, 1)))
        srv._handle_request(req, ("10.0.0.2", 2345))
        self.assertEqual(len(sent), 2)

        # Disconnected slot 0: slot id echoed, everything else zeroed
        d0 = decode_server(sent[0][0])
        self.assertEqual(d0["msg_type"], MSG_INFO)
        self.assertEqual(len(d0["payload"]), 12)
        p0 = d0["payload"]
        self.assertEqual(p0[0], 0)  # slot
        self.assertEqual(p0[1], 0)  # state: disconnected
        self.assertEqual(p0[2:11], bytes(9))
        self.assertEqual(p0[11], 0)  # trailing zero byte

        # Connected slot 1: full 11-byte beginning + zero byte
        p1 = decode_server(sent[1][0])["payload"]
        self.assertEqual(p1[0], 1)  # slot must echo the request
        self.assertEqual(p1[1], 2)  # connected
        self.assertEqual(p1[2], 2)  # full gyro model
        self.assertEqual(p1[3], 2)  # bluetooth
        self.assertEqual(p1[4:10], bytes.fromhex("112233445566"))
        self.assertEqual(p1[10], 0xEE)  # battery
        self.assertEqual(p1[11], 0)

    def test_info_invalid_count_dropped(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        # count must be 1..4
        srv._handle_request(
            client_packet(MSG_INFO, struct.pack("<i", 5) + bytes(5)),
            ("10.0.0.3", 1),
        )
        srv._handle_request(
            client_packet(MSG_INFO, struct.pack("<i", 0)), ("10.0.0.3", 1)
        )
        srv._handle_request(client_packet(MSG_INFO, b"\x01"), ("10.0.0.3", 1))
        srv._handle_request(
            client_packet(MSG_INFO, struct.pack("<i", 1)), ("10.0.0.3", 1)
        )
        self.assertEqual(sent, [])

    def test_info_skips_out_of_range_slot_ids(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        srv._handle_request(
            client_packet(MSG_INFO, struct.pack("<i", 2) + bytes((0, 9))),
            ("10.0.0.4", 1),
        )
        self.assertEqual(len(sent), 1)

    def test_data_registration_and_stream_payload(self):
        srv, sent = make_server()
        srv.set_provider(0, FixedProvider())
        addr = ("10.0.0.5", 5555)

        srv._handle_request(data_request(), addr)
        self.assertIn(addr, srv._subs)
        self.assertEqual(srv._subs[addr], {0})

        srv._stream_tick()
        self.assertEqual(len(sent), 1)
        pkt, dst = sent[0]
        self.assertEqual(dst, addr)
        d = decode_server(pkt)
        self.assertEqual(d["msg_type"], MSG_DATA)
        self.assertEqual(d["total"], 100)  # spec: 100 bytes with header
        body = d["payload"]
        self.assertEqual(len(body), 80)
        self.assertEqual(body[0], 0)  # slot
        self.assertEqual(body[1], 2)  # connected
        self.assertEqual(body[2], 2)  # full gyro
        self.assertEqual(body[11], 1)  # is connected
        self.assertEqual(struct.unpack_from("<I", body, 12)[0], 1)  # packet number
        # Neutral sticks
        self.assertEqual(body[20:24], b"\x80\x80\x80\x80")
        # Motion timestamp in microseconds (wall clock ~1.7e15)
        ts = struct.unpack_from("<Q", body, 48)[0]
        self.assertGreater(ts, 1_600_000_000_000_000)
        self.assertLess(ts, 2_000_000_000_000_000)
        # Motion sample: accel in g, gyro in deg/s
        ax, ay, az, pitch, yaw, roll = struct.unpack_from("<6f", body, 56)
        self.assertAlmostEqual(ax, 0.5, places=5)
        self.assertAlmostEqual(ay, -0.25, places=5)
        self.assertAlmostEqual(az, 1.0, places=5)
        self.assertAlmostEqual(pitch, 1.5, places=5)
        self.assertAlmostEqual(yaw, -2.0, places=5)
        self.assertAlmostEqual(roll, 3.0, places=5)

        # Packet number increments per client/slot
        srv._stream_tick()
        d2 = decode_server(sent[1][0])
        self.assertEqual(struct.unpack_from("<I", d2["payload"], 12)[0], 2)

    def test_data_request_for_missing_slot_ignored(self):
        srv, sent = make_server()
        addr = ("10.0.0.6", 6666)
        srv._handle_request(data_request(slot=2), addr)
        self.assertNotIn(addr, srv._subs)
        srv._stream_tick()
        self.assertEqual(sent, [])

    def test_data_request_short_payload_ignored(self):
        srv, sent = make_server()
        srv._handle_request(client_packet(MSG_DATA, b"\x01"), ("10.0.0.7", 1))
        self.assertEqual(srv._subs, {})

    def test_subscription_scoped_to_requested_slot(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        srv.set_provider(1, MotionProvider())
        addr_a = ("10.0.0.8", 1)
        addr_b = ("10.0.0.9", 1)
        srv._handle_request(data_request(slot=0), addr_a)
        srv._handle_request(data_request(flags=0), addr_b)  # all controllers

        srv._stream_tick()
        slots_a = [
            decode_server(p)["payload"][0] for p, d in sent if d == addr_a
        ]
        slots_b = [
            decode_server(p)["payload"][0] for p, d in sent if d == addr_b
        ]
        self.assertEqual(slots_a, [0])
        self.assertEqual(slots_b, [0, 1])

    def test_mac_based_registration(self):
        srv, sent = make_server()
        provider = MotionProvider()
        provider.mac = bytes.fromhex("aabbccddeeff")
        srv.set_provider(0, provider)
        addr = ("10.0.0.10", 1)
        srv._handle_request(
            data_request(flags=0x02, mac=bytes.fromhex("aabbccddeeff")), addr
        )
        self.assertEqual(srv._subs.get(addr), {0})
        # Unknown MAC → ignored
        addr2 = ("10.0.0.11", 1)
        srv._handle_request(
            data_request(flags=0x02, mac=bytes.fromhex("000000000001")), addr2
        )
        self.assertNotIn(addr2, srv._subs)

    def test_motors_info_connected_and_disconnected(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        ident = bytes((0x01, 0)) + b"\x00" * 6
        srv._handle_request(
            client_packet(MSG_MOTORS_INFO, ident + bytes((0, 0))), ("10.0.0.12", 1)
        )
        d0 = decode_server(sent[0][0])
        self.assertEqual(d0["msg_type"], MSG_MOTORS_INFO)
        self.assertEqual(len(d0["payload"]), 12)
        self.assertEqual(d0["payload"][0], 0)  # slot
        self.assertEqual(d0["payload"][1], 2)  # connected
        self.assertEqual(d0["payload"][11], 2)  # two motors (left/right)

        # Slot 1 has no provider → disconnected, zero motors
        ident1 = bytes((0x01, 1)) + b"\x00" * 6
        srv._handle_request(
            client_packet(MSG_MOTORS_INFO, ident1), ("10.0.0.12", 1)
        )
        p1 = decode_server(sent[1][0])["payload"]
        self.assertEqual(p1[0], 1)
        self.assertEqual(p1[1], 0)
        self.assertEqual(p1[11], 0)

    def test_rumble_forwards_to_handler(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        calls = []
        srv.set_rumble_handler(lambda slot, motor, i: calls.append((slot, motor, i)))
        payload = bytes((0x01, 0)) + b"\x00" * 6 + bytes((0, 200))
        srv._handle_request(
            client_packet(MSG_RUMBLE, payload), ("10.0.0.13", 1)
        )
        self.assertEqual(calls, [(0, 0, 200)])
        self.assertEqual(srv._rumble_state[0][0], 200)

    def test_rumble_ignored_for_unknown_slot_and_motor(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        calls = []
        srv.set_rumble_handler(lambda slot, motor, i: calls.append((slot, motor, i)))
        # Slot 1 has no provider
        srv._handle_request(
            client_packet(
                MSG_RUMBLE, bytes((0x01, 1)) + b"\x00" * 6 + bytes((0, 100))
            ),
            ("10.0.0.14", 1),
        )
        # Motor id out of range
        srv._handle_request(
            client_packet(
                MSG_RUMBLE, bytes((0x01, 0)) + b"\x00" * 6 + bytes((5, 100))
            ),
            ("10.0.0.14", 1),
        )
        # Truncated payload
        srv._handle_request(
            client_packet(MSG_RUMBLE, bytes((0x01, 0))), ("10.0.0.14", 1)
        )
        self.assertEqual(calls, [])

    def test_rumble_reset_after_silence(self):
        """Motors must return to zero after CLIENT_TIMEOUT_S without packets."""
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        calls = []
        srv.set_rumble_handler(lambda slot, motor, i: calls.append((slot, motor, i)))
        payload = bytes((0x01, 0)) + b"\x00" * 6 + bytes((1, 128))
        srv._handle_request(client_packet(MSG_RUMBLE, payload), ("10.0.0.15", 1))
        self.assertEqual(calls, [(0, 1, 128)])

        # Not stale yet: no reset
        srv._rumble_last[0] = time.monotonic()
        srv._stream_tick()
        self.assertEqual(calls, [(0, 1, 128)])

        # Stale: reset to zero exactly once
        srv._rumble_last[0] = time.monotonic() - CLIENT_TIMEOUT_S - 0.1
        srv._stream_tick()
        self.assertEqual(calls, [(0, 1, 128), (0, 1, 0)])
        self.assertNotIn(0, srv._rumble_state)

    def test_client_expires_after_timeout(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        addr = ("10.0.0.16", 1)
        srv._handle_request(data_request(), addr)
        self.assertIn(addr, srv._subs)
        srv._last_seen[addr] = time.monotonic() - CLIENT_TIMEOUT_S - 1
        srv._stream_tick()
        self.assertNotIn(addr, srv._subs)
        self.assertEqual(sent, [])

    def test_client_count_capped(self):
        srv, sent = make_server()
        srv.set_provider(0, MotionProvider())
        newest = None
        for i in range(MAX_CLIENTS + 4):
            addr = (f"10.1.{i // 250}.{i % 250}", 1000 + i)
            srv._handle_request(data_request(), addr)
            srv._last_seen[addr] = float(i)  # strictly increasing age
            newest = addr
        self.assertLessEqual(len(srv._subs), MAX_CLIENTS)
        self.assertIn(newest, srv._subs)

    def test_last_seen_table_capped(self):
        """_touch must not grow without bound from one-shot probes."""
        srv, sent = make_server()
        probe = client_packet(MSG_VERSION)
        for i in range(MAX_CLIENTS * 8):
            srv._handle_request(probe, (f"10.2.{i // 250}.{i % 250}", 53 + i))
        self.assertLessEqual(len(srv._last_seen), MAX_CLIENTS * 4)

    def test_stream_skips_failing_provider(self):
        srv, sent = make_server()

        class Broken(MotionProvider):
            def get_motion(self):
                raise RuntimeError("boom")

        srv.set_provider(0, Broken())
        srv._handle_request(data_request(), ("10.0.0.17", 1))
        srv._stream_tick()  # must not raise
        self.assertEqual(sent, [])

    def test_stream_sanitizes_non_finite_motion(self):
        srv, sent = make_server()

        class NanProvider(MotionProvider):
            def get_motion(self):
                return (float("nan"), 0.0, 1.0, 0.0, 0.0, 0.0)

        srv.set_provider(0, NanProvider())
        srv._handle_request(data_request(), ("10.0.0.18", 1))
        srv._stream_tick()
        body = decode_server(sent[0][0])["payload"]
        ax, ay, az, *_ = struct.unpack_from("<6f", body, 56)
        self.assertEqual(ax, 0.0)
        self.assertEqual(az, 1.0)

    def test_provider_default_motion(self):
        m = MotionProvider().get_motion()
        self.assertEqual(len(m), 6)
        self.assertAlmostEqual(m[2], 1.0)  # accel_z == 1g at rest


# ---------------------------------------------------------------------------
# Real UDP end-to-end
# ---------------------------------------------------------------------------
class TestDsuEndToEnd(unittest.TestCase):
    def test_version_info_and_data_over_udp(self):
        srv = CemuHookServer(port=0, server_id=0x55AA55AA)
        self.assertTrue(srv.start())
        self.addCleanup(srv.stop)
        srv.set_provider(0, MotionProvider())

        # Spec: UDP socket listens on loopback only, never 0.0.0.0.
        self.assertEqual(srv._sock.getsockname()[0], "127.0.0.1")

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(3.0)
        self.addCleanup(client.close)
        addr = ("127.0.0.1", srv.port)

        # Version
        client.sendto(client_packet(MSG_VERSION), addr)
        raw = client.recvfrom(4096)[0]
        d = decode_server(raw)
        self.assertEqual(d["magic"], b"DSUS")
        self.assertEqual(d["msg_type"], MSG_VERSION)
        self.assertEqual(d["payload"], struct.pack("<H", 1001))
        self.assertEqual(d["sender"], srv.server_id)
        self.assertTrue(check_crc(raw))

        # Info for slot 0
        client.sendto(
            client_packet(MSG_INFO, struct.pack("<i", 1) + bytes((0,))), addr
        )
        d = decode_server(client.recvfrom(4096)[0])
        self.assertEqual(d["msg_type"], MSG_INFO)
        self.assertEqual(d["total"], 16 + 4 + 12)
        self.assertEqual(d["payload"][0], 0)
        self.assertEqual(d["payload"][1], 2)  # connected
        self.assertEqual(d["payload"][2], 2)  # full gyro

        # Register for data (slot 0) and expect a 100 Hz stream
        client.sendto(data_request(), addr)
        d1 = decode_server(client.recvfrom(4096)[0])
        self.assertEqual(d1["msg_type"], MSG_DATA)
        self.assertEqual(d1["total"], 100)
        self.assertEqual(len(d1["payload"]), 80)
        self.assertEqual(d1["payload"][11], 1)  # connected

        d2 = decode_server(client.recvfrom(4096)[0])
        self.assertEqual(d2["msg_type"], MSG_DATA)
        n1 = struct.unpack_from("<I", d1["payload"], 12)[0]
        n2 = struct.unpack_from("<I", d2["payload"], 12)[0]
        self.assertGreater(n2, n1)

        srv.stop()
        # Server thread must have terminated (stop() joins it)
        self.assertIsNone(srv.thread)
        self.assertFalse(srv.running)


# ---------------------------------------------------------------------------
# Motion parsing from raw DS4 reports
# ---------------------------------------------------------------------------
def usb_report(gyro=(0, 0, 0), accel=(0, 0, 0), status0=0x04):
    report = bytearray(64)
    report[0] = 0x01
    struct.pack_into("<3h", report, 13, *gyro)   # gyro x/y/z (common @1)
    struct.pack_into("<3h", report, 19, *accel)  # accel x/y/z
    report[30] = status0                          # status[0] at common+29
    return bytes(report)


def bt_report(gyro=(0, 0, 0), accel=(0, 0, 0), status0=0x04):
    report = bytearray(78)
    report[0] = 0x11
    struct.pack_into("<3h", report, 15, *gyro)   # common @3
    struct.pack_into("<3h", report, 21, *accel)
    report[32] = status0
    return bytes(report)


class TestMotionParsing(unittest.TestCase):
    def test_usb_report_scales_and_axis_mapping(self):
        sample = parse_ds4_motion(
            usb_report(gyro=(1024, -2048, 512), accel=(8192, -4096, 0))
        )
        self.assertIsNotNone(sample)
        ax, ay, az, pitch, yaw, roll = sample
        self.assertAlmostEqual(ax, 1.0)      # 8192 LSB / g
        self.assertAlmostEqual(ay, -0.5)
        self.assertAlmostEqual(az, 0.0)
        self.assertAlmostEqual(pitch, -2.0)  # gyro Y / 1024
        self.assertAlmostEqual(yaw, 0.5)     # gyro Z
        self.assertAlmostEqual(roll, 1.0)    # gyro X

    def test_bt_report_uses_shifted_offsets(self):
        sample = parse_ds4_motion(
            bt_report(gyro=(1024, 2048, -1024), accel=(0, 0, 8192))
        )
        self.assertIsNotNone(sample)
        ax, ay, az, pitch, yaw, roll = sample
        self.assertAlmostEqual(az, 1.0)  # flat at rest: +1g on Z
        self.assertAlmostEqual(pitch, 2.0)
        self.assertAlmostEqual(yaw, -1.0)
        self.assertAlmostEqual(roll, 1.0)

    def test_rejects_reports_without_motion(self):
        self.assertIsNone(parse_ds4_motion(b""))
        self.assertIsNone(parse_ds4_motion(b"\x05" + bytes(63)))
        # Minimal BT report (10 bytes, id 0x01) has no motion data
        self.assertIsNone(parse_ds4_motion(bytes([0x01]) + bytes(9)))

    def test_battery_parse_and_dsu_mapping(self):
        report = usb_report(status0=(3 | 0x10))  # capacity 3, cable connected
        self.assertEqual(parse_ds4_battery(report), (3, True))
        self.assertEqual(dsu_battery_status(3, True), 0xEE)    # charging
        self.assertEqual(dsu_battery_status(11, True), 0xEF)   # charged (cable)
        self.assertEqual(dsu_battery_status(11, False), 0x05)  # full, on battery
        self.assertEqual(dsu_battery_status(10, False), 0x05)  # full
        self.assertEqual(dsu_battery_status(0, False), 0x01)   # dying
        self.assertEqual(dsu_battery_status(5, False), 0x03)   # medium
        self.assertEqual(dsu_battery_status(9, False), 0x04)   # high
        self.assertIsNone(parse_ds4_battery(b"\x01" + bytes(9)))

    def test_provider_update_roundtrip(self):
        provider = DS4MotionProvider()
        self.assertEqual(provider.get_motion()[2], 1.0)  # rest default
        provider.update((0.1, 0.2, 0.3, 0.4, 0.5, 0.6))
        self.assertEqual(provider.get_motion(), (0.1, 0.2, 0.3, 0.4, 0.5, 0.6))

    def test_reader_feeds_provider_from_file(self):
        """DS4MotionReader parses reports and stops at EOF."""
        import os
        import tempfile

        from src.engine.motion_source import DS4MotionReader

        with tempfile.NamedTemporaryFile(delete=False) as fh:
            path = fh.name
            # One full BT report; hidraw-style reads deliver one report each
            fh.write(bt_report(gyro=(0, 0, 2048), accel=(8192, 0, 0)))
        try:
            provider = DS4MotionProvider()
            reader = DS4MotionReader(path, provider)
            reader.start()
            reader.join(timeout=3.0)
            self.assertFalse(reader.is_alive(), "reader must exit at EOF")
            ax, ay, az, pitch, yaw, roll = provider.get_motion()
            self.assertAlmostEqual(ax, 1.0)
            self.assertAlmostEqual(az, 0.0)
            self.assertAlmostEqual(yaw, 2.0)  # gyro z 2048 / 1024
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Slot rumble bridge
# ---------------------------------------------------------------------------
class TestSlotExternalRumble(unittest.TestCase):
    def test_set_external_rumble_scales_and_limits(self):
        from src.engine.controller_slot import ControllerSlot

        slot = ControllerSlot(0)
        with mock.patch.object(slot.led_controller, "set_rumble") as set_rumble:
            slot.set_external_rumble(0, 255)
            set_rumble.assert_called_with(65535, 0)
            slot.set_external_rumble(1, 100)
            set_rumble.assert_called_with(65535, 100 * 257)
            slot.set_external_rumble(1, 0)
            set_rumble.assert_called_with(65535, 0)
            set_rumble.reset_mock()
            slot.set_external_rumble(9, 50)  # invalid motor id ignored
            set_rumble.assert_not_called()
            # Out-of-range intensity is clamped
            slot.set_external_rumble(0, 99999)
            set_rumble.assert_called_with(65535, 0)
        slot.cleanup()


if __name__ == "__main__":
    unittest.main()
