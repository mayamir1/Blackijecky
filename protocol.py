# protocol.py
import struct

MAGIC_COOKIE = 0xABCDCDBA  # 0xabcdcdba
TYPE_OFFER = 0x2            # Message type: UDP offer broadcast.
TYPE_REQUEST = 0x3          # Message type: TCP request (client -> server) to start session.
TYPE_PAYLOAD = 0x4          # Message type: gameplay payloads (both directions).


RESULT_NOT_OVER = 0x0      # Round still in progress (dealer must keep drawing).
RESULT_TIE = 0x1           # Round ended in a tie.
RESULT_LOSS = 0x2          # Client lost the round.
RESULT_WIN = 0x3           # Client won the round.

UDP_OFFER_PORT = 13122     # Fixed UDP port used for server discovery offers.


def pack_name_32(name: str) -> bytes:
    # Encode name as UTF-8, truncate to 32 bytes, then NUL-pad to exactly 32 bytes.
    b = name.encode("utf-8", errors="ignore")[:32]
    return b + b"\x00" * (32 - len(b))


def unpack_name_32(b: bytes) -> str:
    # Take first 32 bytes, cut at first NUL, decode back to UTF-8 for display/logging.
    b = b[:32].split(b"\x00", 1)[0]
    return b.decode("utf-8", errors="ignore")


# offer: cookie(4) | type(1) | tcp_port(2) | server_name(32)
def pack_offer(tcp_port: int, server_name: str) -> bytes:
    # Build a 39-byte UDP offer: magic cookie + offer type + TCP port + fixed-size server name.
    return struct.pack("!IBH32s", MAGIC_COOKIE, TYPE_OFFER, tcp_port, pack_name_32(server_name))


def unpack_offer(data: bytes):
    # Validate offer length and header, then return (tcp_port, server_name).
    if len(data) < 39:
        raise ValueError("Offer too short")
    cookie, mtype, tcp_port, name_bytes = struct.unpack("!IBH32s", data[:39])
    if cookie != MAGIC_COOKIE or mtype != TYPE_OFFER:
        raise ValueError("Invalid offer")
    return tcp_port, unpack_name_32(name_bytes)


# request: cookie(4) | type(1) | num_rounds(1) | team_name(32)
def pack_request(num_rounds: int, team_name: str) -> bytes:
    # Build a 38-byte TCP request: magic cookie + request type + rounds (1 byte) + fixed-size team name.
    if not (1 <= num_rounds <= 255):
        raise ValueError("num_rounds must be 1..255")
    return struct.pack("!IBB32s", MAGIC_COOKIE, TYPE_REQUEST, num_rounds, pack_name_32(team_name))


def unpack_request(data: bytes):
    # Validate request length and header, then return (num_rounds, team_name).
    if len(data) < 38:
        raise ValueError("Request too short")
    cookie, mtype, num_rounds, name_bytes = struct.unpack("!IBB32s", data[:38])
    if cookie != MAGIC_COOKIE or mtype != TYPE_REQUEST:
        raise ValueError("Invalid request")
    return num_rounds, unpack_name_32(name_bytes)


# payload client: cookie(4) | type(1) | decision(5)  ("Hittt" / "Stand")
def pack_payload_client(decision: str) -> bytes:
    # Client gameplay command is exactly 5 ASCII bytes; enforce allowed strings to match server logic.
    if decision not in ("Hittt", "Stand"):
        raise ValueError("decision must be 'Hittt' or 'Stand'")
    return struct.pack("!IB5s", MAGIC_COOKIE, TYPE_PAYLOAD, decision.encode("ascii"))


def unpack_payload_client(data: bytes) -> str:
    # Validate payload length and header, then return decision string (best-effort decode).
    if len(data) < 10:
        raise ValueError("Payload(client) too short")
    cookie, mtype, decision = struct.unpack("!IB5s", data[:10])
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        raise ValueError("Invalid payload")
    return decision.decode("ascii", errors="ignore")


# payload server: cookie(4) | type(1) | result(1) | rank(2) | suit(1)
# rank: 1..13, suit: 0..3 (H,D,C,S)
def pack_payload_server(result: int, rank: int, suit: int) -> bytes:
    # Server gameplay payload includes game status (result) plus a card (rank,suit).
    if result not in (RESULT_NOT_OVER, RESULT_TIE, RESULT_LOSS, RESULT_WIN):
        raise ValueError("bad result")
    if not (1 <= rank <= 13):
        raise ValueError("rank must be 1..13")
    if not (0 <= suit <= 3):
        raise ValueError("suit must be 0..3")
    return struct.pack("!IBBHB", MAGIC_COOKIE, TYPE_PAYLOAD, result, rank, suit)


def unpack_payload_server(data: bytes):
    # Validate payload length and header, then return (result, rank, suit).
    if len(data) < 9:
        raise ValueError("Payload(server) too short")
    cookie, mtype, result, rank, suit = struct.unpack("!IBBHB", data[:9])
    if cookie != MAGIC_COOKIE or mtype != TYPE_PAYLOAD:
        raise ValueError("Invalid payload")
    return result, rank, suit
