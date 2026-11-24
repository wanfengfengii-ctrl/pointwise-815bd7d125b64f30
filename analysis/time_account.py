from dataclasses import dataclass
from fractions import Fraction
from itertools import accumulate


@dataclass(frozen=True)
class CompletionAccount:
    first_by_tick: tuple[Fraction, ...]
    remaining: Fraction

    @property
    def cumulative(self):
        return tuple(accumulate(self.first_by_tick))


def build_completion_account(first_by_tick):
    values = tuple(first_by_tick)
    if not values or any(not isinstance(value, Fraction) or value < 0 for value in values):
        raise ValueError('expected a nonempty exact nonnegative completion sequence')
    completed = sum(values, Fraction(0))
    if completed > 1:
        raise ValueError('completion mass exceeds one')
    return CompletionAccount(values, 1 - completed)
