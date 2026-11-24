from dataclasses import dataclass
from fractions import Fraction

from station.origin import StationOrigin


EVIDENCE_HORIZON = 12


@dataclass(frozen=True)
class FirstArrival:
    tick: int
    exit_name: str | None
    probability: Fraction


@dataclass(frozen=True)
class StationEvidence:
    origin: StationOrigin
    entrances: tuple[str, ...]
    exits: tuple[str, ...]
    entry_arrivals: tuple[tuple[str, tuple[FirstArrival, ...]], ...]

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
