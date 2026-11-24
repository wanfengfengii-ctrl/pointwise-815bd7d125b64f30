import json
from dataclasses import dataclass
from fractions import Fraction

from analysis.time_account import CompletionAccount
from handoff.port_map import PortRef
from station.origin import StationOrigin, make_origin


@dataclass(frozen=True)
class ReportValues:
    trial_id: str
    manifest_id: int
    start: PortRef
    horizon: int
    receipt_ids: tuple[int, int]
    origins: tuple[StationOrigin, StationOrigin]
    account: CompletionAccount


def build_report_values(manifest, start, horizon, account):
    if len(account.first_by_tick) != horizon + 1:
        raise ValueError('completion account does not cover the requested horizon')
    return ReportValues(manifest.trial_id, manifest.manifest_id, start, horizon,
                        manifest.receipt_ids, manifest.origins, account)


def _rational_pair(value):
    return [value.numerator, value.denominator]


def encode_report_values(values):
    payload = {
        'trial': values.trial_id,
        'manifest': values.manifest_id,
        'start': [values.start.station, values.start.name],
        'horizon': values.horizon,
        'receipts': list(values.receipt_ids),
        'origins': [[origin.station, origin.revision_id] for origin in values.origins],
        'first': [_rational_pair(value) for value in values.account.first_by_tick],
        'remaining': _rational_pair(values.account.remaining),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def decode_report_values(text):
    payload = json.loads(text)
    account = CompletionAccount(
        tuple(Fraction(*value) for value in payload['first']),
        Fraction(*payload['remaining']),
    )
    return ReportValues(
        payload['trial'], payload['manifest'], PortRef(*payload['start']), payload['horizon'],
        tuple(payload['receipts']), tuple(make_origin(*origin) for origin in payload['origins']), account,
    )
