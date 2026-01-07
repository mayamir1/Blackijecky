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


def safe_send(conn: socket.socket, data: bytes) -> bool:
    try:
        conn.sendall(data)
        return True
    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
        print("Connection lost while sending.", flush=True)
        return False


def recv_exact(conn: socket.socket, n: int, timeout_sec: float = 20.0) -> bytes:
    """
    Receive exactly n bytes or raise.
    timeout_sec is applied only while waiting for server data (protects against 'server silent').
    """
    old_timeout = conn.gettimeout()
    conn.settimeout(timeout_sec)
    try:
        data = b""
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed by peer")
            data += chunk
        return data
    finally:
        conn.settimeout(old_timeout)


def pretty_result(r: int) -> str:
    if r == RESULT_WIN:
        return "WIN"
    if r == RESULT_LOSS:
        return "LOSS"
    if r == RESULT_TIE:
        return "TIE"
    return "NOT_OVER"


def recv_server_payload(conn: socket.socket):
    raw = recv_exact(conn, 9, timeout_sec=20.0)
    try:
        return unpack_payload_server(raw)  # validates cookie/type/structure inside protocol.py
    except Exception as e:
        raise ValueError(f"Bad server payload: {e}")


def listen_for_offer(timeout_sec: int = 15):
    """
    Connect to the first VALID offer received (like the assignment example).
    Close the UDP socket afterwards -> ignores all further offers while connected/playing.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", UDP_OFFER_PORT))
        s.settimeout(timeout_sec)

        print(f"Client listening for offers on UDP {UDP_OFFER_PORT} (timeout {timeout_sec}s)...", flush=True)

        while True:
            try:
                data, addr = s.recvfrom(2048)
            except socket.timeout:
                return None

            try:
                tcp_port, server_name = unpack_offer(data)
                server_ip = addr[0]
                print(f"Received offer from {server_ip} (server='{server_name}', tcp_port={tcp_port})", flush=True)
                return server_ip, tcp_port, server_name
            except Exception:
                # ignore corrupted / unrelated packets and keep waiting until timeout
                continue
    finally:
        s.close()


def run_session(conn: socket.socket, rounds: int):
    wins = losses = ties = 0

    for r in range(1, rounds + 1):
        print(f"\n=== Round {r}/{rounds} ===", flush=True)

        # Initial deal
        p1 = recv_server_payload(conn)
        p2 = recv_server_payload(conn)
        d1 = recv_server_payload(conn)

        def show_card(tag, payload):
            res, rank, suit = payload
            print(f"{tag}: {rank_to_str(rank)} of {SUITS[suit]}  (msg_result={pretty_result(res)})", flush=True)

        show_card("You", p1)
        show_card("You", p2)
        show_card("Dealer shows", d1)

        # Player turn
        while True:
            choice = input("Hit or Stand? ").strip().lower()

            if choice in ("hit", "h"):
                if not safe_send(conn, pack_payload_client("Hittt")):
                    raise ConnectionError("Lost connection while sending HIT")

                res, rank, suit = recv_server_payload(conn)
                print(f"You drew: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)

                if res == RESULT_LOSS:
                    print("You busted. Dealer wins this round.", flush=True)
                    losses += 1
                    break

            elif choice in ("stand", "s"):
                if not safe_send(conn, pack_payload_client("Stand")):
                    raise ConnectionError("Lost connection while sending STAND")

                # Dealer reveals hidden card
                res, rank, suit = recv_server_payload(conn)
                print(f"Dealer reveals: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)

                # Dealer draws until final result
                while True:
                    res, rank, suit = recv_server_payload(conn)
                    if res == RESULT_NOT_OVER:
                        print(f"Dealer draws: {rank_to_str(rank)} of {SUITS[suit]}", flush=True)
                        continue

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

    played = wins + losses + ties
    win_rate = (wins / played) if played else 0.0
    print("\n=== Session finished ===", flush=True)
    print(f"Final stats: W={wins} L={losses} T={ties}", flush=True)
    print(f"Finished playing {played} rounds, win rate: {win_rate:.2f}", flush=True)


def main():
    team = input("Enter your team name (Enter for default): ").strip() or "BlackijeckyTeam"

    while True:
        # rounds validation
        while True:
            try:
                rounds = int(input("Number of rounds (1-255): ").strip())
                if 1 <= rounds <= 255:
                    break
            except Exception:
                pass
            print("Please enter a number between 1 and 255.")

        offer = listen_for_offer(timeout_sec=15)
        if offer is None:
            ans = input("No offers received. Retry? (y/n): ").strip().lower()
            if ans != "y":
                print("Goodbye.")
                return
            time.sleep(2)
            continue

        server_ip, tcp_port, server_name = offer

        # Connect TCP
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(10)
        print(f"Connecting to {server_ip}:{tcp_port} (server='{server_name}') ...", flush=True)

        try:
            conn.connect((server_ip, tcp_port))
        except Exception as e:
            print(f"Failed to connect: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            continue

        # Send request (newline optional; server tolerates it)
        req = pack_request(rounds, team)
        if not safe_send(conn, req + b"\n"):
            try:
                conn.close()
            except Exception:
                pass
            continue

        # gameplay: no strict timeout for user input, but recv_exact has its own network timeout
        conn.settimeout(None)

        try:
            run_session(conn, rounds)
        except (ConnectionError, OSError, ValueError, socket.timeout) as e:
            print(f"Protocol/network error: {e}", flush=True)
        finally:
            try:
                conn.close()
            except Exception:
                pass
            print("Session ended.", flush=True)

        again = input("Play another session? (y/n): ").strip().lower()
        if again != "y":
            print("Goodbye.")
            return


if __name__ == "__main__":
    main()
