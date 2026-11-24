import json
from fractions import Fraction

from station.evidence import FirstArrival, StationEvidence
from station.origin import make_origin


def encode_evidence(evidence):
    payload = {
        'version': 1,
        'station': evidence.origin.station,
        'revision': evidence.origin.revision_id,
        'entrances': list(evidence.entrances),
        'exits': list(evidence.exits),
        'arrivals': [
            [name, [[event.tick, event.exit_name, event.probability.numerator, event.probability.denominator]
                    for event in events]]
            for name, events in evidence.entry_arrivals
        ],
    }
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


def decode_evidence(text):
    payload = json.loads(text)
    fields = {'version', 'station', 'revision', 'entrances', 'exits', 'arrivals'}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError('invalid evidence envelope')
    if type(payload['version']) is not int or payload['version'] != 1:
        raise ValueError('unsupported evidence version')
    if not isinstance(payload['arrivals'], list):
        raise ValueError('invalid entrance evidence list')
    arrivals = []
    for entry in payload['arrivals']:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError('invalid entrance evidence row')
        name, events = entry
        if not isinstance(name, str) or not isinstance(events, list):
            raise ValueError('invalid entrance evidence fields')
        arrivals.append((name, tuple(_decode_event(event) for event in events)))
    return StationEvidence(
        make_origin(payload['station'], payload['revision']),
        _decode_names(payload['entrances']),
        _decode_names(payload['exits']),
        tuple(arrivals),
    )
