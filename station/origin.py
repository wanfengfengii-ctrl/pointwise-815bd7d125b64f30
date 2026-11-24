from dataclasses import dataclass


@dataclass(frozen=True)
class StationOrigin:
    station: str
    revision_id: int


def make_origin(station, revision_id):
    if not isinstance(station, str) or not station.strip():
        raise ValueError('station must be a nonempty string')
    if type(revision_id) is not int or not 0 < revision_id < 2**63:
        raise ValueError('invalid revision number')
    return StationOrigin(station, revision_id)
