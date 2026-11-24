from collections import defaultdict
from fractions import Fraction

from analysis.time_account import build_consumption_account
from handoff.port_map import PortRef
from station.evidence import EVIDENCE_HORIZON, MAX_TRACKED_CONSUMPTION
from station.linear_system import solve_unique_system


MAX_QUOTA = MAX_TRACKED_CONSUMPTION


def _indexed_tables(evidences, wiring):
    joints = {}
    exceedances = {}
    for evidence in evidences:
        station = evidence.origin.station
        for entrance, table in evidence.consumption:
            source = PortRef(station, entrance)
            linked = []
            for arrival in table.counted:
                if arrival.probability == 0:
                    continue
                target = None
                if arrival.exit_name is not None:
                    target = wiring.target_for(PortRef(station, arrival.exit_name))
                linked.append((arrival.tick, target, arrival.count, arrival.probability))
            joints[source] = tuple(linked)
            levels = defaultdict(list)
            for event in table.exceedances:
                if event.probability == 0:
                    continue
                levels[event.level].append((event.tick, event.probability))
            exceedances[source] = {level: tuple(items) for level, items in levels.items()}
    return joints, exceedances


def _usable_entrances(joints, exceedances):
    reverse_instant = defaultdict(set)
    usable = set()
    for source, linked in joints.items():
        if any(target is None or delay > 0 or count > 0 for delay, target, count, _ in linked):
            usable.add(source)
        if exceedances.get(source):
            usable.add(source)
        for delay, target, count, _ in linked:
            if target is not None and delay == 0 and count == 0:
                reverse_instant[target].add(source)
    pending = list(usable)
    while pending:
        for source in reverse_instant[pending.pop()]:
            if source not in usable:
                usable.add(source)
                pending.append(source)
    return tuple(sorted(usable))


def _visit_inverse(usable, joints):
    index = {entrance: position for position, entrance in enumerate(usable)}
    size = len(usable)
    coefficients = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    for source, position in index.items():
        for delay, target, count, probability in joints[source]:
            if delay == 0 and count == 0 and target in index:
                coefficients[index[target]][position] -= probability
    identity = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    return solve_unique_system(coefficients, identity), index


def compute_consumption(evidences, wiring, start, horizon, quota):
    """Settle the shared-quota consumable account from qualified evidence and fixed wiring."""
    if type(horizon) is not int or not 0 <= horizon <= EVIDENCE_HORIZON:
        raise ValueError('invalid report horizon')
    if type(quota) is not int or not 0 <= quota <= MAX_QUOTA:
        raise ValueError('consumable quota must be an integer from 0 through 8')
    for evidence in evidences:
        if evidence.consumption is None:
            raise ValueError('station evidence is missing the fixed consumable declaration')
    joints, exceedances = _indexed_tables(evidences, wiring)
    if not isinstance(start, PortRef) or start not in joints:
        raise ValueError('start is not a public entrance of the selected evidence')
    usable = _usable_entrances(joints, exceedances)
    inverse, _ = _visit_inverse(usable, joints)
    size = len(usable)
    scheduled = [defaultdict(Fraction) for _ in range(horizon + 1)]
    scheduled[0][start, 0] = Fraction(1)
    completed = [defaultdict(Fraction) for _ in range(horizon + 1)]
    exceeded = [Fraction(0) for _ in range(horizon + 1)]
    for tick, bucket in enumerate(scheduled):
        for used in range(quota + 1):
            incoming = [bucket.get((entrance, used), Fraction(0)) for entrance in usable]
            if not any(incoming):
                continue
            # Visits include every immediate return. Only terminal, delayed, or
            # consuming events leave this system; a transfer never restores quota.
            visits = [
                sum((row[column] * incoming[column] for column in range(size)), Fraction(0))
                for row in inverse
            ]
            for entrance, mass in zip(usable, visits):
                if mass == 0:
                    continue
                budget = quota - used
                for delay, target, count, probability in joints[entrance]:
                    if count > budget:
                        continue
                    if target is not None and delay == 0 and count == 0:
                        continue
                    due = tick + delay
                    if due > horizon:
                        continue
                    total = used + count
                    if target is None:
                        completed[due][total] += mass * probability
                    else:
                        scheduled[due][target, total] += mass * probability
                for lag, probability in exceedances[entrance].get(budget + 1, ()):
                    due = tick + lag
                    if due > horizon:
                        continue
                    exceeded[due] += mass * probability
    first_by_tick = tuple(
        tuple(completed[tick].get(used, Fraction(0)) for used in range(quota + 1))
        for tick in range(horizon + 1)
    )
    return build_consumption_account(first_by_tick, tuple(exceeded))
