from collections import defaultdict
from fractions import Fraction

from analysis.time_account import build_completion_account
from handoff.port_map import PortRef
from station.evidence import EVIDENCE_HORIZON
from station.linear_system import solve_unique_system


def _indexed_events(evidences, wiring):
    events = {}
    for evidence in evidences:
        station = evidence.origin.station
        for entrance, arrivals in evidence.entry_arrivals:
            source = PortRef(station, entrance)
            linked = []
            for arrival in arrivals:
                if arrival.probability == 0:
                    continue
                target = None
                if arrival.exit_name is not None:
                    target = wiring.target_for(PortRef(station, arrival.exit_name))
                linked.append((arrival.tick, target, arrival.probability))
            events[source] = tuple(linked)
    return events


def _usable_entrances(events):
    reverse_instant = defaultdict(set)
    usable = set()
    for source, arrivals in events.items():
        for delay, target, _ in arrivals:
            if target is None or delay > 0:
                usable.add(source)
            else:
                reverse_instant[target].add(source)
    pending = list(usable)
    while pending:
        for source in reverse_instant[pending.pop()]:
            if source not in usable:
                usable.add(source)
                pending.append(source)
    return tuple(sorted(usable))


def _visit_equations(usable, events):
    index = {entrance: position for position, entrance in enumerate(usable)}
    size = len(usable)
    coefficients = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    for source, position in index.items():
        for delay, target, probability in events[source]:
            if delay == 0 and target in index:
                coefficients[index[target]][position] -= probability
    return coefficients


def compute_completion(evidences, wiring, start, horizon):
    """Settle the deadline account from qualified evidence and fixed wiring."""
    if type(horizon) is not int or not 0 <= horizon <= EVIDENCE_HORIZON:
        raise ValueError('invalid report horizon')
    events = _indexed_events(evidences, wiring)
    if not isinstance(start, PortRef) or start not in events:
        raise ValueError('start is not a public entrance of the selected evidence')
    usable = _usable_entrances(events)
    coefficients = _visit_equations(usable, events)
    scheduled = [defaultdict(Fraction) for _ in range(horizon + 1)]
    scheduled[0][start] = Fraction(1)
    completed = [Fraction(0) for _ in scheduled]
    for tick, bucket in enumerate(scheduled):
        incoming = [(bucket.get(entrance, Fraction(0)),) for entrance in usable]
        if not any(row[0] for row in incoming):
            continue
        # Visits include every immediate return. Only terminal and delayed events leave this system.
        visits = solve_unique_system(coefficients, incoming)
        for entrance, (mass,) in zip(usable, visits):
            if mass == 0:
                continue
            for delay, target, probability in events[entrance]:
                due = tick + delay
                if due > horizon:
                    continue
                if target is None:
                    completed[due] += mass * probability
                elif delay:
                    scheduled[due][target] += mass * probability
    return build_completion_account(completed)
