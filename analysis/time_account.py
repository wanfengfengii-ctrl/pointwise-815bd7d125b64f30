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


@dataclass(frozen=True)
class ConsumptionAccount:
    first_by_tick: tuple[tuple[Fraction, ...], ...]
    exceeded_by_tick: tuple[Fraction, ...]
    remaining: Fraction

    @property
    def within_quota_by_tick(self):
        return tuple(sum(row, Fraction(0)) for row in self.first_by_tick)

    @property
    def cumulative(self):
        return tuple(accumulate(self.within_quota_by_tick))

    @property
    def completed(self):
        return sum(self.within_quota_by_tick, Fraction(0))

    @property
    def exceeded(self):
        return sum(self.exceeded_by_tick, Fraction(0))


def build_consumption_account(first_by_tick, exceeded_by_tick):
    first = tuple(tuple(row) for row in first_by_tick)
    exceeded = tuple(exceeded_by_tick)
    if not first or len(first) != len(exceeded):
        raise ValueError('expected matching nonempty consumption sequences')
    width = len(first[0])
    if width == 0 or any(len(row) != width for row in first):
        raise ValueError('expected a rectangular per-tick consumption table')
    values = [value for row in first for value in row] + list(exceeded)
    if any(not isinstance(value, Fraction) or value < 0 for value in values):
        raise ValueError('expected exact nonnegative consumption probabilities')
    settled = sum(values, Fraction(0))
    if settled > 1:
        raise ValueError('consumption account mass exceeds one')
    return ConsumptionAccount(first, exceeded, 1 - settled)
