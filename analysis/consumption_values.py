import json
from dataclasses import dataclass
from fractions import Fraction

from analysis.time_account import ConsumptionAccount
from handoff.port_map import PortRef
from station.origin import StationOrigin, make_origin


@dataclass(frozen=True)
class ConsumptionReportValues:
    trial_id: str
    manifest_id: int
    start: PortRef
    horizon: int
    quota: int
    receipt_ids: tuple[int, int]
    origins: tuple[StationOrigin, StationOrigin]
    account: ConsumptionAccount


def build_consumption_values(manifest, start, horizon, quota, account):
    if len(account.first_by_tick) != horizon + 1 or len(account.exceeded_by_tick) != horizon + 1:
        raise ValueError('consumption account does not cover the requested horizon')
    if any(len(row) != quota + 1 for row in account.first_by_tick):
        raise ValueError('consumption account does not cover the requested quota')
    return ConsumptionReportValues(manifest.trial_id, manifest.manifest_id, start, horizon, quota,
                                   manifest.receipt_ids, manifest.origins, account)


def _rational_pair(value):
    return [value.numerator, value.denominator]


def encode_consumption_values(values):
    payload = {
        'trial': values.trial_id,
        'manifest': values.manifest_id,
        'start': [values.start.station, values.start.name],
        'horizon': values.horizon,
        'quota': values.quota,
        'receipts': list(values.receipt_ids),
        'origins': [[origin.station, origin.revision_id] for origin in values.origins],
        'first': [[_rational_pair(value) for value in row] for row in values.account.first_by_tick],
        'exceeded': [_rational_pair(value) for value in values.account.exceeded_by_tick],
        'remaining': _rational_pair(values.account.remaining),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))


def decode_consumption_values(text):
    payload = json.loads(text)
    account = ConsumptionAccount(
        tuple(tuple(Fraction(*value) for value in row) for row in payload['first']),
        tuple(Fraction(*value) for value in payload['exceeded']),
        Fraction(*payload['remaining']),
    )
    return ConsumptionReportValues(
        payload['trial'], payload['manifest'], PortRef(*payload['start']), payload['horizon'],
        payload['quota'], tuple(payload['receipts']),
        tuple(make_origin(*origin) for origin in payload['origins']), account,
    )
