from dataclasses import dataclass
from fractions import Fraction

from reports.history import get_report
from station.origin import StationOrigin


@dataclass(frozen=True)
class ReportComparison:
    report_ids: tuple[int, int]
    first_origins: tuple[StationOrigin, StationOrigin]
    second_origins: tuple[StationOrigin, StationOrigin]
    delta_by_tick: tuple[Fraction, ...]


def compare_reports(ledger, first_id, second_id):
    first = get_report(ledger, first_id).values
    second = get_report(ledger, second_id).values
    if (first.trial_id, first.start, first.horizon) != (second.trial_id, second.start, second.horizon):
        raise ValueError('reports must share a trial, start entrance, and horizon')
    delta = tuple(after - before for before, after in
                  zip(first.account.first_by_tick, second.account.first_by_tick, strict=True))
    return ReportComparison((first_id, second_id), first.origins, second.origins, delta)
