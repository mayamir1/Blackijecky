# client.py
import socket
import time

from protocol import (
    UDP_OFFER_PORT,
    RESULT_LOSS,
    RESULT_NOT_OVER,
    RESULT_TIE,
    RESULT_WIN,
    pack_request,
    pack_payload_client,
    unpack_offer,
    unpack_payload_server,
)
from cards import SUITS, rank_to_str


def recv_exact(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def pretty_result(r: int) -> str:
    if r == RESULT_WIN:
        return "WIN"
    if r == RESULT_LOSS:
        return "LOSS"
    if r == RESULT_TIE:
        return "TIE"
    return "NOT_OVER"


def listen_for_offer(timeout_sec: int = 30):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # allow multiple clients on same machine (if supported)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        pass
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", UDP_OFFER_PORT))
    s.settimeout(timeout_sec)

    print(f"Client started, listening for offer requests on UDP {UDP_OFFER_PORT}...", flush=True)

    while True:
        data, addr = s.recvfrom(2048)
        try:
            tcp_port, server_name = unpack_offer(data)
            server_ip = addr[0]
            print(f"Received offer from {server_ip} (server='{server_name}', tcp_port={tcp_port})", flush=True)
            return server_ip, tcp_port, server_name
        except Exception:
            continue


def main():
    team = input("Enter your team name: ").strip() or "TeamClient"
    while True:
        try:
            rounds = int(input("Number of rounds (1-255): ").strip())
            if 1 <= rounds <= 255:
                break
        except Exception:
            pass
        print("Please enter a number between 1 and 255.")

    # 1) Find server via UDP offer
    server_ip, tcp_port, server_name = listen_for_offer(timeout_sec=60)

    # 2) Connect via TCP
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.settimeout(20)
    print(f"Connecting to {server_ip}:{tcp_port} ...", flush=True)
    conn.connect((server_ip, tcp_port))
    print("TCP connected.", flush=True)

    # 3) Send request packet
    req = pack_request(rounds, team)
    conn.sendall(req + b"\n")  # newline is optional; helps match the example

    wins = losses = ties = 0

    try:
        for r in range(1, rounds + 1):
            print(f"\n=== Round {r}/{rounds} ===", flush=True)

            # Initial deal: receive 3 cards (player1, player2, dealer upcard)
            p1 = unpack_payload_server(recv_exact(conn, 9))
            p2 = unpack_payload_server(recv_exact(conn, 9))
            d1 = unpack_payload_server(recv_exact(conn, 9))

            def show_card(tag, payload):
                res, rank, suit = payload
                print(f"{tag}: {rank_to_str(rank)} of {SUITS[suit]}  (msg_result={pretty_result(res)})", flush=True)

            show_card("You", p1)
            show_card("You", p2)
            show_card("Dealer shows", d1)

            # Player turn loop
            while True:
                choice = input("Hit or Stand? ").strip().lower()
                if choice in ("hit", "h"):
                    conn.sendall(pack_payload_client("Hittt"))
                    res, rank, suit = unpack_payload_server(recv_exact(conn, 9))
                    print(f"You drew: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)

                    if res == RESULT_LOSS:
                        print("You busted. Dealer wins this round.", flush=True)
                        losses += 1
                        break
                    else:
                        continue

                elif choice in ("stand", "s"):
                    conn.sendall(pack_payload_client("Stand"))
                    # Dealer turn begins: receive hidden dealer card (NOT_OVER)
                    res, rank, suit = unpack_payload_server(recv_exact(conn, 9))
                    print(f"Dealer reveals: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)

                    # Now receive dealer draws until final result arrives.
                    # Server sends:
                    # - NOT_OVER for each drawn card
                    # - final WIN/LOSS/TIE as a payload (with some card)
                    while True:
                        res, rank, suit = unpack_payload_server(recv_exact(conn, 9))
                        if res == RESULT_NOT_OVER:
                            print(f"Dealer draws: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)
                            continue
                        else:
                            print(f"Round result: {pretty_result(res)}", flush=True)
                            if res == RESULT_WIN:
                                wins += 1
                            elif res == RESULT_LOSS:
                                losses += 1
                            else:
                                ties += 1
                            break
                    break
                else:
                    print("Type Hit or Stand.", flush=True)

            print(f"Stats: W={wins} L={losses} T={ties}", flush=True)

    finally:
        try:
            conn.close()
        except Exception:
            pass
        print("Disconnected.", flush=True)


if __name__ == "__main__":
    main()
