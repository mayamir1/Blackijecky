# cards.py
import random

# suit encoding: 0=Hearts,1=Diamonds,2=Clubs,3=Spades  (H,D,C,S)
SUITS = ["Hearts", "Diamonds", "Clubs", "Spades"]
RANKS = list(range(1, 14))  # 1..13 (A=1, J=11,Q=12,K=13)


def card_value(rank: int) -> int:
    # Per assignment: A=11 always, J/Q/K=10, 2..10 numeric
    if rank == 1:
        return 11
    if 2 <= rank <= 10:
        return rank
    return 10


def rank_to_str(rank: int) -> str:
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
        self.cards = [(rank, suit) for suit in range(4) for rank in RANKS]
        random.shuffle(self.cards)

    def draw(self):
        if not self.cards:
            raise RuntimeError("Deck is empty")
        return self.cards.pop()


class Hand:
    def __init__(self):
        self.cards = []  # list of (rank, suit)

    def add(self, card):
        self.cards.append(card)

    def total(self) -> int:
        return sum(card_value(rank) for rank, _ in self.cards)

    def bust(self) -> bool:
        return self.total() > 21

    def __str__(self):
        return ", ".join(f"{rank_to_str(r)} of {SUITS[s]}" for r, s in self.cards)
