from fractions import Fraction

from station.evidence import (EVIDENCE_HORIZON, MAX_TRACKED_CONSUMPTION, OVERFLOW_LEVEL,
                              CountedArrival, EntranceConsumption, FirstArrival, FirstExceedance,
                              StationEvidence)
from station.origin import StationOrigin, make_origin


def _port_set(ports):
    if not isinstance(ports, tuple) or any(not isinstance(name, str) or not name.strip() for name in ports):
        raise ValueError('invalid public port list')
    names = set(ports)
    if len(names) != len(ports):
        raise ValueError('duplicate public port name')
    return names


def _check_probability(value, message):
    if not isinstance(value, Fraction) or value < 0:
        raise ValueError(message)


def _qualify_counted(counted, exits, name):
    if not isinstance(counted, tuple):
        raise ValueError('invalid counted arrival table')
    cells = set()
    total = Fraction(0)
    for arrival in counted:
        if not isinstance(arrival, CountedArrival):
            raise ValueError('invalid counted arrival record')
        if type(arrival.tick) is not int or not 0 <= arrival.tick <= EVIDENCE_HORIZON:
            raise ValueError('counted arrival is outside the evidence horizon')
        target = arrival.exit_name
        if target is not None and (not isinstance(target, str) or target not in exits):
            raise ValueError('counted arrival names an unknown exit')
        if type(arrival.count) is not int or not 0 <= arrival.count <= MAX_TRACKED_CONSUMPTION:
            raise ValueError('counted arrival is outside the tracked consumption range')
        cell = (arrival.tick, target, arrival.count)
        if cell in cells:
            raise ValueError('duplicate counted arrival cell')
        cells.add(cell)
        _check_probability(arrival.probability, 'counted arrival requires a nonnegative Fraction')
        total += arrival.probability
    if total > 1:
        raise ValueError(f'counted arrival mass exceeds one for entrance {name}')


def _qualify_exceedances(exceedances, name):
    if not isinstance(exceedances, tuple):
        raise ValueError('invalid first-exceedance table')
    cells = set()
    totals = {}
    for event in exceedances:
        if not isinstance(event, FirstExceedance):
            raise ValueError('invalid first-exceedance record')
        if type(event.level) is not int or not 1 <= event.level <= OVERFLOW_LEVEL:
            raise ValueError('first exceedance is outside the tracked consumption range')
        if type(event.tick) is not int or not 0 <= event.tick <= EVIDENCE_HORIZON:
            raise ValueError('first exceedance is outside the evidence horizon')
        cell = (event.level, event.tick)
        if cell in cells:
            raise ValueError('duplicate first-exceedance cell')
        cells.add(cell)
        _check_probability(event.probability, 'first exceedance requires a nonnegative Fraction')
        totals[event.level] = totals.get(event.level, Fraction(0)) + event.probability
    if any(total > 1 for total in totals.values()):
        raise ValueError(f'first-exceedance mass exceeds one for entrance {name}')


def _qualify_consumption(evidence, entrances, exits):
    rows = evidence.consuming_rows
    consumption = evidence.consumption
    if rows is None and consumption is None:
        return
    if not isinstance(rows, tuple) or not isinstance(consumption, tuple):
        raise ValueError('consumable declaration and tables must be fixed together')
    if any(not isinstance(row_id, str) or not row_id.strip() for row_id in rows):
        raise ValueError('invalid consumable row declaration')
    if len(set(rows)) != len(rows):
        raise ValueError('duplicate consumable row declaration')
    seen_entrances = set()
    for entry in consumption:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError('invalid consumable entrance row')
        name, table = entry
        if not isinstance(name, str) or name not in entrances or name in seen_entrances:
            raise ValueError('consumable evidence must have one table for each public entrance')
        if not isinstance(table, EntranceConsumption):
            raise ValueError('invalid consumable entrance table')
        seen_entrances.add(name)
        _qualify_counted(table.counted, exits, name)
        _qualify_exceedances(table.exceedances, name)
    if seen_entrances != entrances:
        raise ValueError('missing consumable evidence table for a public entrance')


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
    _qualify_consumption(evidence, entrances, exits)
