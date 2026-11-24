from dataclasses import dataclass

from analysis.completion import compute_completion
from analysis.report_values import build_report_values
from handoff.manifest import FixedManifest, get_manifest
from handoff.port_map import PortRef
from handoff.receiving import get_received_evidence
from reports.ledger import ReportLedger
from reports.publish import publish_report
from station.evidence import EVIDENCE_HORIZON, StationEvidence


@dataclass(frozen=True)
class ReportRequest:
    manifest: FixedManifest
    start: PortRef
    horizon: int
    evidences: tuple[StationEvidence, StationEvidence]


def resolve_request(center, manifest_id, start, horizon):
    if type(horizon) is not int or not 0 <= horizon <= EVIDENCE_HORIZON:
        raise ValueError('report horizon must be an integer from 0 through 12')
    if not isinstance(start, PortRef):
        raise ValueError('report start must be a station-scoped port reference')
    manifest = get_manifest(center, manifest_id)
    evidences = tuple(get_received_evidence(center, receipt_id).evidence
                      for receipt_id in manifest.receipt_ids)
    ports = {PortRef(evidence.origin.station, name) for evidence in evidences for name in evidence.entrances}
    if start not in ports:
        raise ValueError('report start is not a public entrance of the selected evidence')
    return ReportRequest(manifest, start, horizon, evidences)


def sign(center, manifest_id, start, horizon):
    request = resolve_request(center, manifest_id, start, horizon)
    account = compute_completion(request.evidences, request.manifest.wiring, request.start, request.horizon)
    values = build_report_values(request.manifest, request.start, request.horizon, account)
    return publish_report(ReportLedger(center.connection), values)
