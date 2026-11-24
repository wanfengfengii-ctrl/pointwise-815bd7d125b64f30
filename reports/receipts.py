from dataclasses import dataclass

from station.origin import StationOrigin


@dataclass(frozen=True)
class FirstReceipt:
    report_id: int
    receipt_ids: tuple[int, int]
    origins: tuple[StationOrigin, StationOrigin]


def build_first_receipt(report_id, values):
    if type(report_id) is not int or report_id <= 0:
        raise ValueError('invalid report number for first receipt')
    return FirstReceipt(report_id, values.receipt_ids, values.origins)
