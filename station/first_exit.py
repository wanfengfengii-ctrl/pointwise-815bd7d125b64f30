from fractions import Fraction

from routes.states import public_ports
from routes.transitions import outgoing_by_state
from station.evidence import EVIDENCE_HORIZON, FirstArrival
from station.linear_system import solve_unique_system


def _advancing_states(outgoing, terminal_targets):
    predecessors = {state: set() for state in outgoing}
    advancing = set()
    for source, rows in outgoing.items():
        for row in rows:
            if row.target in terminal_targets or row.delay > 0:
                advancing.add(source)
            else:
                predecessors[row.target].add(source)
    pending = list(advancing)
    while pending:
        for predecessor in predecessors[pending.pop()]:
            if predecessor not in advancing:
                advancing.add(predecessor)
                pending.append(predecessor)
    return tuple(sorted(advancing))


def _immediate_equations(positions, outgoing):
    size = len(positions)
    coefficients = [[Fraction(int(i == j)) for j in range(size)] for i in range(size)]
    for source, i in positions.items():
        for row in outgoing[source]:
            if row.delay == 0 and row.target in positions:
                coefficients[i][positions[row.target]] -= row.probability
    return coefficients


def compute_first_arrivals(states, rows):
    """Return first terminal arrivals from each public entrance in a validated route."""
    entrances, exits = public_ports(states)
    terminal_targets = {state.state_id: state.exit for state in states if state.kind != 'work'}
    targets = ((None,) if None in terminal_targets.values() else ()) + tuple(sorted(exits))
    columns = {target: column for column, target in enumerate(targets)}
    outgoing = outgoing_by_state(row for row in rows if row.probability)
    active = _advancing_states(outgoing, terminal_targets)
    positions = {state: i for i, state in enumerate(active)}
    coefficients = _immediate_equations(positions, outgoing)

    # A row holds first-arrival probabilities starting from one state at the current exact lag.
    # States outside the system have no terminal or delayed event reachable by immediate edges.
    solved = []
    for tick in range(EVIDENCE_HORIZON + 1):
        rhs = [[Fraction(0) for _ in targets] for _ in active]
        for source, position in positions.items():
            for row in outgoing[source]:
                if row.target in terminal_targets:
                    if row.delay == tick:
                        rhs[position][columns[terminal_targets[row.target]]] += row.probability
                elif 0 < row.delay <= tick and row.target in positions:
                    previous = solved[tick - row.delay][positions[row.target]]
                    for column, probability in enumerate(previous):
                        rhs[position][column] += row.probability * probability
        solved.append(solve_unique_system(coefficients, rhs))

    result = {}
    for name, state in sorted(entrances.items()):
        if state in terminal_targets:
            result[name] = (FirstArrival(0, terminal_targets[state], Fraction(1)),)
        elif state in positions:
            position = positions[state]
            result[name] = tuple(
                FirstArrival(tick, target, probability)
                for tick, table in enumerate(solved)
                for target, probability in zip(targets, table[position])
                if probability
            )
        else:
            result[name] = ()
    return result
