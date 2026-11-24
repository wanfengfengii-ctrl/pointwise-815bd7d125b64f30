from dataclasses import dataclass

from handoff.center_store import CenterIntakeStore
from handoff.port_map import PortMap, PortRef, build_port_map
from handoff.receiving import get_received_evidence
from station.origin import StationOrigin, make_origin


@dataclass(frozen=True)
class FixedManifest:
    manifest_id: int
    trial_id: str
    receipt_ids: tuple[int, int]
    origins: tuple[StationOrigin, StationOrigin]
    wiring: PortMap


def fix_manifest(center: CenterIntakeStore, receipt_ids, connections):
    if not isinstance(receipt_ids, (tuple, list)) or len(receipt_ids) != 2:
        raise ValueError('a manifest needs two ordered intake receipt numbers')
    receipt_ids = tuple(receipt_ids)
    evidences = tuple(get_received_evidence(center, receipt_id).evidence for receipt_id in receipt_ids)
    origins = tuple(evidence.origin for evidence in evidences)
    if tuple(origin.station for origin in origins) != center.stations:
        raise ValueError('intake receipts must match the two ordered station slots')
    wiring = build_port_map(evidences, connections)
    rows = [(source.station, source.name, target.station, target.name)
            for source, target in wiring.connections]
    manifest_id = center.insert_manifest(receipt_ids, rows)
    return FixedManifest(manifest_id, center.trial_id, receipt_ids, origins, wiring)


def get_manifest(center: CenterIntakeStore, manifest_id):
    trial_id, receipt_ids, origin_rows, wiring_rows = center.load_manifest(manifest_id)
    wiring = PortMap(tuple((PortRef(a, exit_name), PortRef(b, entry_name))
                           for a, exit_name, b, entry_name in wiring_rows))
    origins = tuple(make_origin(station, revision) for station, revision in origin_rows)
    return FixedManifest(manifest_id, trial_id, receipt_ids, origins, wiring)
