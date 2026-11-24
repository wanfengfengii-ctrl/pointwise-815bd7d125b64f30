from dataclasses import dataclass


@dataclass(frozen=True)
class RouteState:
    state_id: str
    kind: str = 'work'
    entry: str | None = None
    exit: str | None = None


def index_states(states):
    index = {}
    for state in states:
        if not isinstance(state, RouteState):
            raise ValueError('each state must be a RouteState')
        if not isinstance(state.state_id, str) or not state.state_id.strip():
            raise ValueError('state ID must be a nonempty string')
        if state.state_id in index:
            raise ValueError(f'duplicate state: {state.state_id}')
        if state.kind not in ('work', 'exit', 'complete'):
            raise ValueError(f'unknown state kind: {state.kind}')
        if state.kind == 'exit' and state.exit is None:
            raise ValueError(f'exit state needs a public name: {state.state_id}')
        if state.kind != 'exit' and state.exit is not None:
            raise ValueError(f'only an exit state can declare an exit: {state.state_id}')
        index[state.state_id] = state
    return index


def public_ports(states):
    entrances = {}
    exits = {}
    for state in states:
        for name, ports in ((state.entry, entrances), (state.exit, exits)):
            if name is None:
                continue
            if not isinstance(name, str) or not name.strip():
                raise ValueError('public port name must be a nonempty string')
            if name in ports:
                raise ValueError(f'duplicate public port: {name}')
            ports[name] = state.state_id
    return entrances, exits
