from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class PortRef:
    station: str
    name: str

    def __post_init__(self):
        for value in (self.station, self.name):
            if not isinstance(value, str) or not value.strip():
                raise ValueError('port reference needs a station and a port name')


@dataclass(frozen=True)
class PortMap:
    connections: tuple[tuple[PortRef, PortRef], ...]

    def target_for(self, source):
        for exit_port, entrance in self.connections:
            if exit_port == source:
                return entrance
        raise LookupError(f'no wiring for exit {source}')


def build_port_map(evidences, connections):
    exits = {PortRef(evidence.origin.station, name) for evidence in evidences for name in evidence.exits}
    entrances = {PortRef(evidence.origin.station, name) for evidence in evidences for name in evidence.entrances}
    pairs = connections.items() if isinstance(connections, Mapping) else connections
    try:
        pairs = tuple(pairs)
    except TypeError as error:
        raise ValueError('connections must contain exit and entrance pairs') from error
    wired = {}
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError('each connection needs an exit and an entrance')
        source, target = pair
        if not isinstance(source, PortRef) or source not in exits:
            raise ValueError(f'unknown exit on wiring: {source}')
        if not isinstance(target, PortRef) or target not in entrances:
            raise ValueError(f'unknown entrance on wiring: {target}')
        if source.station == target.station:
            raise ValueError('an exit must connect to the other station')
        if source in wired:
            raise ValueError(f'exit wired more than once: {source}')
        wired[source] = target
    if set(wired) != exits:
        raise ValueError('each declared exit must be wired')
    return PortMap(tuple(sorted(wired.items())))
