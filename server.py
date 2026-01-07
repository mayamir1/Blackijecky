# server.py
import socket
import threading
import time
# Import protocol constants and helper functions
from protocol import (
    UDP_OFFER_PORT,
    RESULT_LOSS,
    RESULT_NOT_OVER,
    RESULT_TIE,
    RESULT_WIN,
    pack_offer,
    pack_payload_server,
    unpack_payload_client,
    unpack_request,
)
# Import card game logic
from cards import Deck, Hand, SUITS, rank_to_str


def recv_exact(conn: socket.socket, n: int) -> bytes:
    # Receive exactly n bytes from the socket
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed by peer")
        data += chunk
    return data


def safe_print(*args):
    # Print immediately (no buffering)
    print(*args, flush=True)


class BlackjackServer:
    def __init__(self, server_name: str = "Blackijecky-Server", max_clients: int = 10):
        # Server name shown in UDP offer
        self.server_name = server_name
        # Event used to stop the server gracefully
        self._stop = threading.Event()

        # Semaphore to limit number of concurrent clients
        self.client_slots = threading.Semaphore(max_clients)

        # Create TCP socket
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to any available port
        self.tcp_sock.bind(("", 0))  # 0.0.0.0:any
        self.tcp_sock.listen(20)
        # Save the chosen TCP port
        self.tcp_port = self.tcp_sock.getsockname()[1]

        # Create UDP socket for broadcasting offers
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start(self):
        # Start server main loop
        safe_print(f"Server started, listening on TCP port {self.tcp_port}")
        # Start UDP offer thread
        threading.Thread(target=self._offer_loop, daemon=True).start()
        # Start TCP accept thread
        threading.Thread(target=self._accept_loop, daemon=True).start()
        # Keep server alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            # Stop server on Ctrl+C
            safe_print("Shutting down...")
            self._stop.set()
            try:
                self.tcp_sock.close()
            except Exception:
                pass
            try:
                self.udp_sock.close()
            except Exception:
                pass

    def _offer_loop(self):
        # Create UDP offer packet
        offer = pack_offer(self.tcp_port, self.server_name)

        # Broadcast addresses
        targets = [("255.255.255.255", UDP_OFFER_PORT)]
        # Try to add local subnet broadcast
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            if local_ip and local_ip.count(".") == 3:
                parts = local_ip.split(".")
                parts[-1] = "255"
                targets.append((".".join(parts), UDP_OFFER_PORT))
        except Exception:
            pass
        # Send offers repeatedly
        while not self._stop.is_set():
            for target in targets:
                try:
                    self.udp_sock.sendto(offer, target)
                except Exception:
                    pass
            time.sleep(1)

    def _accept_loop(self):
        # Accept incoming TCP clients
        while not self._stop.is_set():
            try:
                conn, addr = self.tcp_sock.accept()
            except OSError:
                break

            # Reject client if server is full
            if not self.client_slots.acquire(blocking=False):
                safe_print(f"Rejecting {addr}: server busy")
                try:
                    conn.close()
                except Exception:
                    pass
                continue
            # Handle client in a new thread
            threading.Thread(target=self._handle_client_wrap, args=(conn, addr), daemon=True).start()

    def _handle_client_wrap(self, conn: socket.socket, addr):
        # Wrapper to ensure semaphore is released
        try:
            self._handle_client(conn, addr)
        finally:
            self.client_slots.release()

    def _sanitize_team_name(self, name: str) -> str:
        # Remove non-printable characters
        name = "".join(ch if ch.isprintable() else "?" for ch in (name or ""))
        name = name.strip()
        if not name:
            name = "UnknownTeam"
        return name[:32]

    def _handle_client(self, conn: socket.socket, addr):
        safe_print(f"Client connected from {addr}")

        try:
            # Timeout for request phase
            conn.settimeout(20)
            # Read request packet
            req = recv_exact(conn, 38)
            num_rounds, team_name = unpack_request(req)
            team_name = self._sanitize_team_name(team_name)
            # Validate number of rounds
            if not (1 <= num_rounds <= 255):
                raise ValueError(f"Invalid rounds: {num_rounds}")

            # Ignore optional newline
            try:
                conn.settimeout(0.2)
                _ = conn.recv(1)
            except Exception:
                pass

            safe_print(f"Request from team '{team_name}' rounds={num_rounds}")

            wins = losses = ties = 0

            # Gameplay timeout
            conn.settimeout(300)
            # Play rounds
            for r in range(1, num_rounds + 1):
                safe_print(f"[{team_name}] Round {r}/{num_rounds} starting")
                result = self._play_round(conn, team_name)

                if result == RESULT_WIN:
                    wins += 1
                elif result == RESULT_LOSS:
                    losses += 1
                else:
                    ties += 1

                safe_print(f"[{team_name}] Stats: W={wins} L={losses} T={ties}")

        except (socket.timeout,) as e:
            safe_print(f"Client {addr} timeout: {e}")
        except (ConnectionError, ConnectionResetError, BrokenPipeError, OSError) as e:
            safe_print(f"Client {addr} disconnected unexpectedly: {e}")
        except Exception as e:
            safe_print(f"Client {addr} error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
            safe_print(f"Client {addr} disconnected")

    def _send_card(self, conn: socket.socket, result: int, card):
        # Send card and result to client
        rank, suit = card
        msg = pack_payload_server(result, rank, suit)
        conn.sendall(msg)

    def _read_decision(self, conn: socket.socket, team_name: str) -> str:
        # Read exactly 10 bytes decision packet
        decision_msg = recv_exact(conn, 10)
        try:
            decision = unpack_payload_client(decision_msg)
        except Exception:
            raise ValueError("Invalid decision payload from client")

        # Validate decision value
        if decision not in ("Hittt", "Stand"):
            raise ValueError(f"Invalid decision value from client: {decision}")

        safe_print(f"[{team_name}] Decision: {decision}")
        return decision

    def _play_round(self, conn: socket.socket, team_name: str) -> int:
        # Create deck and hands
        deck = Deck()
        player = Hand()
        dealer = Hand()

        # Initial card dealing
        p1 = deck.draw()
        p2 = deck.draw()
        d1 = deck.draw()
        d2 = deck.draw()  # hidden initially

        player.add(p1)
        player.add(p2)
        dealer.add(d1)
        dealer.add(d2)
        # Send initial cards
        self._send_card(conn, RESULT_NOT_OVER, p1)
        self._send_card(conn, RESULT_NOT_OVER, p2)
        self._send_card(conn, RESULT_NOT_OVER, d1)

        safe_print(f"[{team_name}] Player: {player} (total={player.total()})")
        safe_print(f"[{team_name}] Dealer shows: {rank_to_str(d1[0])} of {SUITS[d1[1]]}")

        # Player turn
        while True:
            decision = self._read_decision(conn, team_name)
            if decision == "Stand":
                break

            # Hit
            new_card = deck.draw()
            player.add(new_card)

            if player.bust():
                self._send_card(conn, RESULT_LOSS, new_card)
                safe_print(
                    f"[{team_name}] Player HIT -> {rank_to_str(new_card[0])} of {SUITS[new_card[1]]} "
                    f"BUST (total={player.total()})"
                )
                return RESULT_LOSS

            self._send_card(conn, RESULT_NOT_OVER, new_card)
            safe_print(
                f"[{team_name}] Player HIT -> {rank_to_str(new_card[0])} of {SUITS[new_card[1]]} "
                f"(total={player.total()})"
            )

        # Dealer reveals hidden card
        self._send_card(conn, RESULT_NOT_OVER, d2)
        safe_print(f"[{team_name}] Dealer reveals: {rank_to_str(d2[0])} of {SUITS[d2[1]]} (total={dealer.total()})")

        last_dealer_card = d2
        # Dealer draws until 17
        while dealer.total() < 17:
            c = deck.draw()
            dealer.add(c)
            last_dealer_card = c

            if dealer.bust():
                self._send_card(conn, RESULT_WIN, c)
                safe_print(f"[{team_name}] Dealer draws {rank_to_str(c[0])} of {SUITS[c[1]]} -> BUST (total={dealer.total()})")
                return RESULT_WIN

            self._send_card(conn, RESULT_NOT_OVER, c)
            safe_print(f"[{team_name}] Dealer draws {rank_to_str(c[0])} of {SUITS[c[1]]} (total={dealer.total()})")

        # Compare totals
        p_total = player.total()
        d_total = dealer.total()

        if p_total > d_total:
            final = RESULT_WIN
        elif d_total > p_total:
            final = RESULT_LOSS
        else:
            final = RESULT_TIE

        self._send_card(conn, final, last_dealer_card)
        safe_print(f"[{team_name}] Final: player={p_total} dealer={d_total} -> result={final}")
        return final


if __name__ == "__main__":
    # Start the Blackjack server
    BlackjackServer(server_name="Blackijecky", max_clients=10).start()
