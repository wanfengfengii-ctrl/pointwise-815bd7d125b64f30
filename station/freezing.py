from routes.revisions import load_revision
from routes.states import public_ports
from station.evidence import StationEvidence
from station.first_exit import compute_first_arrivals
from station.origin import make_origin


def freeze(source, station, revision_id):
    revision = load_revision(source, station, revision_id)
    entrances, exits = public_ports(revision.states)
    arrivals = compute_first_arrivals(revision.states, revision.rows)
    return StationEvidence(
        make_origin(revision.station, revision.revision_id),
        tuple(sorted(entrances)),
        tuple(sorted(exits)),
        tuple((name, arrivals[name]) for name in sorted(entrances)),
    )
