from dataclasses import dataclass

from handoff.center_store import CenterIntakeStore
from handoff.qualification import qualify_evidence
from station.evidence import StationEvidence
from station.evidence_codec import decode_evidence, encode_evidence


@dataclass(frozen=True)
class ReceivedEvidence:
    receipt_id: int
    evidence: StationEvidence


def receive(center: CenterIntakeStore, evidence, expected_station, expected_revision):
    qualify_evidence(evidence, expected_station, expected_revision)
    if expected_station not in center.stations:
        raise ValueError('station is outside the center intake context')
    return center.insert_receipt(expected_station, expected_revision, encode_evidence(evidence))


def get_received_evidence(center: CenterIntakeStore, receipt_id):
    station, revision, payload = center.load_receipt(receipt_id)
    evidence = decode_evidence(payload)
    qualify_evidence(evidence, station, revision)
    return ReceivedEvidence(receipt_id, evidence)
