from fractions import Fraction

from routes.states import index_states, public_ports
from routes.transitions import outgoing_by_state, parse_transition_rows


def validate_revision(station, states, rows):
    if not isinstance(station, str) or not station.strip():
        raise ValueError('station must be a nonempty string')
    try:
        states = tuple(states)
        rows = tuple(rows)
    except TypeError as error:
        raise ValueError('states and transitions must be iterable') from error
    if not 1 <= len(states) <= 12:
        raise ValueError('a route must have 1 to 12 states')
    index = index_states(states)
    public_ports(states)
    parsed = parse_transition_rows(rows)
    for row in parsed:
        if row.source not in index or row.target not in index:
            raise ValueError(f'unknown state on row {row.row_id}')
        if index[row.source].kind != 'work':
            raise ValueError(f'terminal state has an outgoing row: {row.source}')
    outgoing = outgoing_by_state(parsed)
    for state in states:
        if state.kind == 'work':
            total = sum((row.probability for row in outgoing.get(state.state_id, ())), Fraction(0))
            if total != 1:
                raise ValueError(f'outgoing probability at {state.state_id} is {total}; expected 1')
    return states, parsed
