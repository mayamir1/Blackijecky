# cards.py
import random

# suit encoding: 0=Hearts,1=Diamonds,2=Clubs,3=Spades  (H,D,C,S)
# 0=Hearts, 1=Diamonds, 2=Clubs, 3=Spades  (H,D,C,S)
# IMPORTANT: The protocol sends/receives suit as a small integer (0..3) and both sides
# must agree on the same mapping, so this list order is part of the "wire format".
SUITS = ["Hearts", "Diamonds", "Clubs", "Spades"]

# Rank encoding:
# 1..13 where 1=A, 11=J, 12=Q, 13=K.
# (Same idea: ranks are sent as numbers in the protocol, so the mapping must be stable.)
RANKS = list(range(1, 14))  # 1..13 (A=1, J=11,Q=12,K=13)


def card_value(rank: int) -> int:
    # Blackjack-like value rules (as required by the assignment):
    # - Ace is ALWAYS 11 here (no "soft ace" logic that can switch to 1).
    # - Face cards (J/Q/K) are 10.
    # - Number cards are their number (2..10).
    if rank == 1:
        return 11
    if 2 <= rank <= 10:
        return rank
    return 10


def rank_to_str(rank: int) -> str:
    # Convert numeric rank encoding to printable form (A,J,Q,K or "2".."10").
    if rank == 1:
        return "A"
    if rank == 11:
        return "J"
    if rank == 12:
        return "Q"
    if rank == 13:
        return "K"
    return str(rank)


class Deck:
    def __init__(self):
        # Create a standard 52-card deck as (rank, suit) tuples:
        # - suit in 0..3, rank in 1..13.
        # Card representation matches what the protocol sends to the client.
        self.cards = [(rank, suit) for suit in range(4) for rank in RANKS]
        random.shuffle(self.cards)  # In-place shuffle; randomness comes from Python's RNG.

    def draw(self):
        # Draw "top" card by popping from the end of the shuffled list.
        # Raises if the deck is empty (shouldn't happen in normal gameplay if deck is managed).
        if not self.cards:
            raise RuntimeError("Deck is empty")
        return self.cards.pop()


class Hand:
    # Cards held by a player/dealer, stored as (rank, suit) tuples.
    def __init__(self):
        self.cards = []  # list of (rank, suit)

    def add(self, card):
        # Add a drawn card tuple (rank, suit) to the hand.
        self.cards.append(card)

    def total(self) -> int:
        # Sum card values using card_value(); note that Ace is always 11 in this implementation.
        return sum(card_value(rank) for rank, _ in self.cards)

    def bust(self) -> bool:
        # "Bust" means total strictly greater than 21.
        return self.total() > 21

    def __str__(self):
        # Human-readable representation used for prints/logs, e.g. "A of Hearts, 10 of Spades".
        return ", ".join(f"{rank_to_str(r)} of {SUITS[s]}" for r, s in self.cards)
