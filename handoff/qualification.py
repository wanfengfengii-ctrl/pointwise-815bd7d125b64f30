from fractions import Fraction

from station.evidence import EVIDENCE_HORIZON, FirstArrival, StationEvidence
from station.origin import StationOrigin, make_origin


def _port_set(ports):
    if not isinstance(ports, tuple) or any(not isinstance(name, str) or not name.strip() for name in ports):
        raise ValueError('invalid public port list')
    names = set(ports)
    if len(names) != len(ports):
        raise ValueError('duplicate public port name')
    return names


def qualify_evidence(evidence, expected_station, expected_revision):
    expected = make_origin(expected_station, expected_revision)
    if not isinstance(evidence, StationEvidence) or not isinstance(evidence.origin, StationOrigin):
        raise ValueError('invalid station evidence')
    actual = make_origin(evidence.origin.station, evidence.origin.revision_id)
    if actual != expected:
        raise ValueError('evidence station or revision differs from the expected identity')
    entrances = _port_set(evidence.entrances)
    exits = _port_set(evidence.exits)
    if len(entrances) > 12 or len(exits) > 12:
        raise ValueError('evidence exceeds station port limits')
    if not isinstance(evidence.entry_arrivals, tuple):
        raise ValueError('invalid evidence entrance table')
    seen_entrances = set()
    for entry in evidence.entry_arrivals:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError('invalid evidence entrance row')
        name, arrivals = entry
        if not isinstance(name, str) or name not in entrances or name in seen_entrances:
            raise ValueError('evidence must have one table for each public entrance')
        if not isinstance(arrivals, tuple):
            raise ValueError('invalid first-arrival table')
        seen_entrances.add(name)
        cells = set()
        total = Fraction(0)
        for arrival in arrivals:
            if not isinstance(arrival, FirstArrival):
                raise ValueError('invalid first-arrival record')
            if type(arrival.tick) is not int or not 0 <= arrival.tick <= EVIDENCE_HORIZON:
                raise ValueError('first arrival is outside the evidence horizon')
            target = arrival.exit_name
            if target is not None and (not isinstance(target, str) or target not in exits):
                raise ValueError('first arrival names an unknown exit')
            cell = (arrival.tick, target)
            if cell in cells:
                raise ValueError('duplicate first-arrival cell')
            cells.add(cell)
            if not isinstance(arrival.probability, Fraction) or arrival.probability < 0:
                raise ValueError('first arrival requires a nonnegative Fraction')
            total += arrival.probability
        if total > 1:
            raise ValueError(f'first-arrival mass exceeds one for entrance {name}')
    if seen_entrances != entrances:
        raise ValueError('missing evidence table for a public entrance')
