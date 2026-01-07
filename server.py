# server.py
import socket
import threading
import time

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
from cards import Deck, Hand, SUITS, rank_to_str


def recv_exact(conn: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def safe_print(*args):
    print(*args, flush=True)


class BlackjackServer:
    def __init__(self, server_name: str = "Blackijecky-Server"):
        self.server_name = server_name
        self._stop = threading.Event()

        # TCP socket: bind to any free port (no fixed port required)
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_sock.bind(("", 0))
        self.tcp_sock.listen(20)
        self.tcp_port = self.tcp_sock.getsockname()[1]

        # UDP socket for broadcasting offers
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start(self):
        safe_print(f"Server started, listening on TCP port {self.tcp_port}")

        t1 = threading.Thread(target=self._offer_loop, daemon=True)
        t2 = threading.Thread(target=self._accept_loop, daemon=True)
        t1.start()
        t2.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
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
        offer = pack_offer(self.tcp_port, self.server_name)
        while not self._stop.is_set():
            try:
                # broadcast
                self.udp_sock.sendto(offer, ("255.255.255.255", UDP_OFFER_PORT))
            except Exception:
                pass
            time.sleep(1)

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self.tcp_sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()

    def _handle_client(self, conn: socket.socket, addr):
        conn.settimeout(20)
        safe_print(f"Client connected from {addr}")

        try:
            # Request is 38 bytes. Some clients might also send '\n' after it.
            req = recv_exact(conn, 38)
            num_rounds, team_name = unpack_request(req)

            # swallow optional newline if exists (non-blocking-ish)
            try:
                conn.settimeout(0.2)
                extra = conn.recv(1)
                _ = extra  # ignore
            except Exception:
                pass
            finally:
                conn.settimeout(20)

            safe_print(f"Request from team '{team_name}' rounds={num_rounds}")

            wins = losses = ties = 0

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

        except Exception as e:
            safe_print(f"Client {addr} error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
            safe_print(f"Client {addr} disconnected")

    def _send_card(self, conn: socket.socket, result: int, card):
        rank, suit = card
        msg = pack_payload_server(result, rank, suit)
        conn.sendall(msg)

    def _play_round(self, conn: socket.socket, team_name: str) -> int:
        deck = Deck()
        player = Hand()
        dealer = Hand()

        # Initial deal:
        # We send payloads for: player card1, player card2, dealer upcard
        p1 = deck.draw()
        p2 = deck.draw()
        d1 = deck.draw()
        d2 = deck.draw()  # hidden initially

        player.add(p1)
        player.add(p2)
        dealer.add(d1)
        dealer.add(d2)

        self._send_card(conn, RESULT_NOT_OVER, p1)
        self._send_card(conn, RESULT_NOT_OVER, p2)
        self._send_card(conn, RESULT_NOT_OVER, d1)

        safe_print(f"[{team_name}] Player: {player} (total={player.total()})")
        safe_print(f"[{team_name}] Dealer shows: {rank_to_str(d1[0])} of {SUITS[d1[1]]}")

        # Player turn
        while True:
            # read decision payload (10 bytes)
            decision_msg = recv_exact(conn, 10)
            decision = unpack_payload_client(decision_msg)
            safe_print(f"[{team_name}] Decision: {decision}")

            if decision == "Stand":
                break

            # Hit
            new_card = deck.draw()
            player.add(new_card)

            # if bust -> send the busting card with LOSS
            if player.bust():
                self._send_card(conn, RESULT_LOSS, new_card)
                safe_print(f"[{team_name}] Player HIT -> {rank_to_str(new_card[0])} of {SUITS[new_card[1]]} BUST (total={player.total()})")
                return RESULT_LOSS

            # else round not over -> send card with NOT_OVER
            self._send_card(conn, RESULT_NOT_OVER, new_card)
            safe_print(f"[{team_name}] Player HIT -> {rank_to_str(new_card[0])} of {SUITS[new_card[1]]} (total={player.total()})")

        # Dealer turn (player didn't bust)
        # Reveal hidden dealer card
        self._send_card(conn, RESULT_NOT_OVER, d2)
        safe_print(f"[{team_name}] Dealer reveals: {rank_to_str(d2[0])} of {SUITS[d2[1]]} (total={dealer.total()})")

        last_dealer_card = d2

        while dealer.total() < 17:
            c = deck.draw()
            dealer.add(c)
            last_dealer_card = c

            if dealer.bust():
                self._send_card(conn, RESULT_WIN, c)  # dealer bust card => client wins
                safe_print(f"[{team_name}] Dealer draws {rank_to_str(c[0])} of {SUITS[c[1]]} -> BUST (total={dealer.total()})")
                return RESULT_WIN

            self._send_card(conn, RESULT_NOT_OVER, c)
            safe_print(f"[{team_name}] Dealer draws {rank_to_str(c[0])} of {SUITS[c[1]]} (total={dealer.total()})")

        # Decide winner (dealer stands)
        p_total = player.total()
        d_total = dealer.total()

        if p_total > d_total:
            final = RESULT_WIN
        elif d_total > p_total:
            final = RESULT_LOSS
        else:
            final = RESULT_TIE

        # Send final result as a payload (reusing last dealer card)
        self._send_card(conn, final, last_dealer_card)
        safe_print(f"[{team_name}] Final: player={p_total} dealer={d_total} -> result={final}")
        return final


if __name__ == "__main__":
    BlackjackServer(server_name="Blackijecky").start()
