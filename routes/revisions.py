from dataclasses import dataclass

from routes.source_store import SourceStore
from routes.states import RouteState
from routes.transitions import TransitionRow
from routes.validation import validate_revision


@dataclass(frozen=True)
class RouteRevision:
    station: str
    revision_id: int
    states: tuple[RouteState, ...]
    rows: tuple[TransitionRow, ...]


def save_revision(source: SourceStore, station, states, rows):
    states, rows = validate_revision(station, states, rows)
    return source.insert_revision(station, states, rows)


def load_revision(source: SourceStore, station, revision_id):
    if not isinstance(station, str) or not station.strip():
        raise ValueError('station must be a nonempty string')
    states, rows = source.load_revision(station, revision_id)
    return RouteRevision(station, revision_id, states, rows)
