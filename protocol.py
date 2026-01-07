# protocol.py
import struct

MAGIC_COOKIE = 0xABCDCDBA  # 0xabcdcdba
TYPE_OFFER = 0x2
TYPE_REQUEST = 0x3
TYPE_PAYLOAD = 0x4

RESULT_NOT_OVER = 0x0
RESULT_TIE = 0x1
RESULT_LOSS = 0x2
RESULT_WIN = 0x3

UDP_OFFER_PORT = 13122


def pack_name_32(name: str) -> bytes:
    b = name.encode("utf-8", errors="ignore")[:32]
    return b + b"\x00" * (32 - len(b))


def unpack_name_32(b: bytes) -> str:
    b = b[:32].split(b"\x00", 1)[0]
    return b.decode("utf-8", errors="ignore")


# offer: cookie(4) | type(1) | tcp_port(2) | server_name(32)
def pack_offer(tcp_port: int, server_name: str) -> bytes:
    return struct.pack("!IBH32s", MAGIC_COOKIE, TYPE_OFFER, tcp_port, pack_name_32(server_name))


def unpack_offer(data: bytes):
    if len(data) < 39:
        raise ValueError("Offer too short")
    cookie, mtype, tcp_port, name_bytes = struct.unpack("!IBH32s", data[:39])
    if cookie != MAGIC_COOKIE or mtype != TYPE_OFFER:
        raise ValueError("Invalid offer")
    return tcp_port, unpack_name_32(name_bytes)


# request: cookie(4) | type(1) | num_rounds(1) | team_name(32)
def pack_request(num_rounds: int, team_name: str) -> bytes:
    if not (1 <= num_rounds <= 255):
        raise ValueError("num_rounds must be 1..255")
    return struct.pack("!IBB32s", MAGIC_COOKIE, TYPE_REQUEST, num_rounds, pack_name_32(team_name))


def unpack_request(data: bytes):
    if len(data) < 38:
        raise ValueError("Request too short")
    cookie, mtype, num_rounds, name_bytes = struct.unpack("!IBB32s", data[:38])
    if cookie != MAGIC_COOKIE or mtype != TYPE_REQUEST:
        raise ValueError("Invalid request")
    return num_rounds, unpack_name_32(name_bytes)


# payload client: cookie(4) | type(1) | decision(5)  ("Hittt" / "Stand")
def pack_payload_client(decision: str) -> bytes:
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hittt' or 'Stand'")
    return struct.pack("!IB5s", MAGIC_COOKIE, TYPE_PAYLOAD, decision.encode("ascii"))


def unpack_payload_client(data: bytes) -> str:
    if len(data) < 10:
        raise ValueError("Payload(client) too short")
    cookie, mtype, decision = struct.unpack("!IB5s", data[:10])
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        raise ValueError("Invalid payload")
    return decision.decode("ascii", errors="ignore")


# payload server: cookie(4) | type(1) | result(1) | rank(2) | suit(1)
# rank: 1..13, suit: 0..3 (H,D,C,S)
def pack_payload_server(result: int, rank: int, suit: int) -> bytes:
    if result not in (RESULT_NOT_OVER, RESULT_TIE, RESULT_LOSS, RESULT_WIN):
        raise ValueError("bad result")
    if not (1 <= rank <= 13):
        raise ValueError("rank must be 1..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return struct.pack("!IBBHB", MAGIC_COOKIE, TYPE_PAYLOAD, result, rank, suit)


def unpack_payload_server(data: bytes):
    if len(data) < 9:
        raise ValueError("Payload(server) too short")
    cookie, mtype, result, rank, suit = struct.unpack("!IBBHB", data[:9])
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        raise ValueError("Invalid payload")
    return result, rank, suit
