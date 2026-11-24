import json
from fractions import Fraction

from station.evidence import (CountedArrival, EntranceConsumption, FirstArrival, FirstExceedance,
                              StationEvidence)
from station.origin import make_origin


def _encode_event(event):
    return [event.tick, event.exit_name, event.probability.numerator, event.probability.denominator]


def encode_evidence(evidence):
    payload = {
        'version': 1,
        'station': evidence.origin.station,
        'revision': evidence.origin.revision_id,
        'entrances': list(evidence.entrances),
        'exits': list(evidence.exits),
        'arrivals': [
            [name, [_encode_event(event) for event in events]]
            for name, events in evidence.entry_arrivals
        ],
    }
    if evidence.consumption is not None:
        payload['version'] = 2
        payload['consuming'] = list(evidence.consuming_rows)
        payload['consumption'] = [
            [name, [
                [[event.tick, event.exit_name, event.count,
                  event.probability.numerator, event.probability.denominator]
                 for event in table.counted],
                [[event.level, event.tick, event.probability.numerator, event.probability.denominator]
                 for event in table.exceedances],
            ]]
            for name, table in evidence.consumption
        ]
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def _decode_names(value):
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise ValueError('invalid public port list')
    return tuple(value)


def _decode_event(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('invalid first-arrival row')
    tick, target, numerator, denominator = value
    if type(tick) is not int or (target is not None and not isinstance(target, str)):
        raise ValueError('invalid first-arrival coordinates')
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('invalid first-arrival fraction')
    return FirstArrival(tick, target, Fraction(numerator, denominator))


def _decode_counted(value):
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError('invalid counted arrival row')
    tick, target, count, numerator, denominator = value
    if type(tick) is not int or (target is not None and not isinstance(target, str)):
        raise ValueError('invalid counted arrival coordinates')
    if type(count) is not int:
        raise ValueError('invalid counted arrival count')
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('invalid counted arrival fraction')
    return CountedArrival(tick, target, count, Fraction(numerator, denominator))


def _decode_exceedance(value):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError('invalid first-exceedance row')
    level, tick, numerator, denominator = value
    if type(level) is not int or type(tick) is not int:
        raise ValueError('invalid first-exceedance coordinates')
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('invalid first-exceedance fraction')
    return FirstExceedance(level, tick, Fraction(numerator, denominator))


def _decode_arrivals(value):
    if not isinstance(value, list):
        raise ValueError('invalid entrance evidence list')
    arrivals = []
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError('invalid entrance evidence row')
        name, events = entry
        if not isinstance(name, str) or not isinstance(events, list):
            raise ValueError('invalid entrance evidence fields')
        arrivals.append((name, tuple(_decode_event(event) for event in events)))
    return tuple(arrivals)


def _decode_consuming(value):
    if not isinstance(value, list) or any(not isinstance(row_id, str) for row_id in value):
        raise ValueError('invalid consumable declaration')
    return tuple(value)


def _decode_consumption(value):
    if not isinstance(value, list):
        raise ValueError('invalid consumable evidence list')
    consumption = []
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError('invalid consumable entrance row')
        name, tables = entry
        if not isinstance(name, str) or not isinstance(tables, list) or len(tables) != 2:
            raise ValueError('invalid consumable entrance fields')
        counted, exceedances = tables
        if not isinstance(counted, list) or not isinstance(exceedances, list):
            raise ValueError('invalid consumable entrance tables')
        consumption.append((name, EntranceConsumption(
            tuple(_decode_counted(event) for event in counted),
            tuple(_decode_exceedance(event) for event in exceedances),
        )))
    return tuple(consumption)


def decode_evidence(text):
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError('invalid evidence envelope')
    version = payload.get('version')
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported evidence version')
    fields = {'version', 'station', 'revision', 'entrances', 'exits', 'arrivals'}
    if version == 2:
        fields |= {'consuming', 'consumption'}
    if set(payload) != fields:
        raise ValueError('invalid evidence envelope')
    consuming_rows = None
    consumption = None
    if version == 2:
        consuming_rows = _decode_consuming(payload['consuming'])
        consumption = _decode_consumption(payload['consumption'])
    return StationEvidence(
        make_origin(payload['station'], payload['revision']),
        _decode_names(payload['entrances']),
        _decode_names(payload['exits']),
        _decode_arrivals(payload['arrivals']),
        consuming_rows,
        consumption,
    )
