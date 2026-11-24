from collections import defaultdict
from fractions import Fraction

from routes.states import public_ports
from station.evidence import (EVIDENCE_HORIZON, MAX_TRACKED_CONSUMPTION, CountedArrival,
                              EntranceConsumption, FirstExceedance)
from station.linear_system import solve_unique_system


def _annotated_outgoing(rows, consuming):
    outgoing = {}
    for row in rows:
        if not row.probability:
            continue
        consume = row.row_id in consuming
        outgoing.setdefault(row.source, []).append((row.target, row.delay, row.probability, consume))
    return {source: tuple(items) for source, items in outgoing.items()}


def _advancing_states(outgoing, terminal_targets):
    # A state advances when a resolving row (terminal, delayed, or consuming) is reachable
    # through immediate rows (zero delay, no consumption, work target).
    predecessors = {state: set() for state in outgoing}
    advancing = set()
    for source, rows in outgoing.items():
        for target, delay, _, consume in rows:
            if target in terminal_targets or delay > 0 or consume:
                advancing.add(source)
            else:
                predecessors[target].add(source)
    pending = list(advancing)
    while pending:
        for predecessor in predecessors[pending.pop()]:
            if predecessor not in advancing:
                advancing.add(predecessor)
                pending.append(predecessor)
    return tuple(sorted(advancing))


def _immediate_inverse(advancing, outgoing):
    positions = {state: position for position, state in enumerate(advancing)}
    size = len(advancing)
    coefficients = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    for source, position in positions.items():
        for target, delay, probability, consume in outgoing[source]:
            if delay == 0 and not consume and target in positions:
                coefficients[positions[target]][position] -= probability
    identity = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    return solve_unique_system(coefficients, identity), positions


def _entrance_tables(entrance_state, outgoing, terminal_targets, inverse, positions):
    joints = defaultdict(Fraction)
    exceedances = defaultdict(Fraction)
    if entrance_state in terminal_targets:
        joints[(0, terminal_targets[entrance_state], 0)] = Fraction(1)
        return joints, exceedances
    if entrance_state not in positions:
        return joints, exceedances
    size = len(positions)
    scheduled = [defaultdict(Fraction) for _ in range(EVIDENCE_HORIZON + 1)]
    scheduled[0][entrance_state, 0] = Fraction(1)
    for tick, bucket in enumerate(scheduled):
        for count in range(MAX_TRACKED_CONSUMPTION + 1):
            incoming = [bucket.get((state, count), Fraction(0)) for state in positions]
            if not any(incoming):
                continue
            visits = [
                sum((row[column] * incoming[column] for column in range(size)), Fraction(0))
                for row in inverse
            ]
            for state, mass in zip(positions, visits):
                if not mass:
                    continue
                for target, delay, probability, consume in outgoing[state]:
                    if delay == 0 and not consume and target not in terminal_targets:
                        continue
                    due = tick + delay
                    if due > EVIDENCE_HORIZON:
                        continue
                    total = count + int(consume)
                    if consume:
                        exceedances[total, due] += mass * probability
                    if target in terminal_targets:
                        if total <= MAX_TRACKED_CONSUMPTION:
                            joints[due, terminal_targets[target], total] += mass * probability
                    elif total <= MAX_TRACKED_CONSUMPTION:
                        scheduled[due][target, total] += mass * probability
    return joints, exceedances


def _joint_sort_key(item):
    (tick, exit_name, count), _ = item
    return (tick, exit_name is not None, exit_name, count)


def compute_consumption_evidence(states, rows, consuming):
    """Return per-entrance consumable tables for a validated route and declaration.

    Counted arrivals keep exact sample counts 0 through 8. The first passage to each
    level 1 through 9 is recorded as an exceedance; level 9 always exceeds any quota.
    """
    entrances, _ = public_ports(states)
    terminal_targets = {state.state_id: state.exit for state in states if state.kind != 'work'}
    outgoing = _annotated_outgoing(rows, consuming)
    advancing = _advancing_states(outgoing, terminal_targets)
    inverse, positions = _immediate_inverse(advancing, outgoing)
    tables = {}
    for name, state in sorted(entrances.items()):
        joints, exceedances = _entrance_tables(state, outgoing, terminal_targets, inverse, positions)
        counted = tuple(
            CountedArrival(tick, exit_name, count, probability)
            for (tick, exit_name, count), probability in sorted(joints.items(), key=_joint_sort_key)
        )
        first_exceedance = tuple(
            FirstExceedance(level, tick, probability)
            for (level, tick), probability in sorted(exceedances.items())
        )
        tables[name] = EntranceConsumption(counted, first_exceedance)
    return tables
