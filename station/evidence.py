from dataclasses import dataclass
from fractions import Fraction

from station.origin import StationOrigin


EVIDENCE_HORIZON = 12
MAX_TRACKED_CONSUMPTION = 8
OVERFLOW_LEVEL = 9


@dataclass(frozen=True)
class FirstArrival:
    tick: int
    exit_name: str | None
    probability: Fraction


@dataclass(frozen=True)
class CountedArrival:
    tick: int
    exit_name: str | None
    count: int
    probability: Fraction


@dataclass(frozen=True)
class FirstExceedance:
    level: int
    tick: int
    probability: Fraction


@dataclass(frozen=True)
class EntranceConsumption:
    counted: tuple[CountedArrival, ...]
    exceedances: tuple[FirstExceedance, ...]


@dataclass(frozen=True)
class StationEvidence:
    origin: StationOrigin
    entrances: tuple[str, ...]
    exits: tuple[str, ...]
    entry_arrivals: tuple[tuple[str, tuple[FirstArrival, ...]], ...]
    consuming_rows: tuple[str, ...] | None = None
    consumption: tuple[tuple[str, EntranceConsumption], ...] | None = None

    def arrivals_for(self, entrance):
        for name, arrivals in self.entry_arrivals:
            if name == entrance:
                return arrivals
        raise LookupError(f'unknown evidence entrance: {entrance}')

    def remaining_at(self, entrance, horizon=EVIDENCE_HORIZON):
        if type(horizon) is not int or not 0 <= horizon <= EVIDENCE_HORIZON:
            raise ValueError('invalid station evidence horizon')
        arrived = sum(
            (event.probability for event in self.arrivals_for(entrance) if event.tick <= horizon),
            Fraction(0),
        )
        return 1 - arrived

    def consumption_for(self, entrance):
        if self.consumption is None:
            raise ValueError('station evidence is missing the fixed consumable declaration')
        for name, table in self.consumption:
            if name == entrance:
                return table
        raise LookupError(f'unknown evidence entrance: {entrance}')
