from routes.revisions import load_revision
from routes.states import public_ports
from station.consumption import compute_consumption_evidence
from station.evidence import StationEvidence
from station.first_exit import compute_first_arrivals
from station.origin import make_origin


def _validate_consuming(revision, consuming):
    if isinstance(consuming, (str, bytes)):
        raise ValueError('consumable declaration must be a collection of original row IDs')
    try:
        declared = tuple(consuming)
    except TypeError as error:
        raise ValueError('consumable declaration must be a collection of original row IDs') from error
    known = {row.row_id for row in revision.rows}
    seen = set()
    for row_id in declared:
        if not isinstance(row_id, str) or not row_id.strip():
            raise ValueError('consumable row IDs must be nonempty strings')
        if row_id in seen:
            raise ValueError(f'duplicate consumable row declaration: {row_id}')
        if row_id not in known:
            raise ValueError(f'unknown original transition row: {row_id}')
        seen.add(row_id)
    return tuple(sorted(seen))


def freeze(source, station, revision_id, consuming=None):
    revision = load_revision(source, station, revision_id)
    entrances, exits = public_ports(revision.states)
    arrivals = compute_first_arrivals(revision.states, revision.rows)
    if consuming is None:
        consuming_rows, consumption = None, None
    else:
        consuming_rows = _validate_consuming(revision, consuming)
        tables = compute_consumption_evidence(revision.states, revision.rows, frozenset(consuming_rows))
        consumption = tuple((name, tables[name]) for name in sorted(entrances))
    return StationEvidence(
        make_origin(revision.station, revision.revision_id),
        tuple(sorted(entrances)),
        tuple(sorted(exits)),
        tuple((name, arrivals[name]) for name in sorted(entrances)),
        consuming_rows,
        consumption,
    )
