import json
from contextlib import ExitStack, closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.scenarios import sign
from examples.scenarios import TRIAL_ID, positive_chain, register_example, register_station, return_loop
from handoff.center_store import CenterIntakeStore
from handoff.manifest import fix_manifest
from reports.comparison import compare_reports
from reports.history import get_report
from reports.ledger import ReportLedger
from routes.source_store import SourceStore


def _check_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f'expected {expected!r}, got {actual!r}')


def _account(report):
    account = report.values.account
    return {'first': [str(value) for value in account.first_by_tick], 'remaining': str(account.remaining)}


def _describe_report(case_id, inputs, expected, report, archived, oracle):
    actual = _account(report)
    _check_equal(actual, expected)
    _check_equal(archived, report)
    downstream_expected = {'report_id': report.report_id, 'intake_ids': list(report.values.receipt_ids)}
    downstream_actual = {'report_id': archived.receipt.report_id, 'intake_ids': list(archived.receipt.receipt_ids)}
    _check_equal(downstream_actual, downstream_expected)
    _scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
              ['analysis/completion.py', 'reports/publish.py', 'reports/history.py'], oracle)


def _scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    marker = dict(case_id=case_id, input=inputs, expected=expected, actual=actual,
                  downstream_expected=downstream_expected, downstream_actual=downstream_actual,
                  code_paths=code_paths, oracle=oracle)
    print('POINTWISE_SCENARIO ' + json.dumps(marker, ensure_ascii=False, sort_keys=True))


def main():
    with TemporaryDirectory(prefix='retest-demo-') as directory:
        root = Path(directory)
        left_path, right_path, center_path = (root / name for name in ('a.sqlite', 'b.sqlite', 'center.sqlite'))
        left_off, right_off = root / 'a.offline', root / 'b.offline'
        chain, original, corrected = positive_chain(), return_loop(), return_loop(retry_delay=1)
        with closing(CenterIntakeStore(center_path, TRIAL_ID)) as center:
            center.initialize()
            ReportLedger(center.connection).initialize()
            with ExitStack() as sources:
                left = sources.enter_context(closing(SourceStore(left_path)))
                right = sources.enter_context(closing(SourceStore(right_path)))
                left.initialize()
                right.initialize()
                chain_manifest = register_example(center, left, right, chain)
                old_manifest = register_example(center, left, right, original)
            left_path.rename(left_off)
            right_path.rename(right_off)
            positive_report = sign(center, chain_manifest.manifest_id, chain.start, 3)
            old_report = sign(center, old_manifest.manifest_id, original.start, 1)

            left_off.rename(left_path)
            with closing(SourceStore(left_path)) as left:
                left.initialize()
                new_receipt = register_station(center, left, 'A', corrected.left)
            left_path.rename(left_off)
            new_manifest = fix_manifest(center, (new_receipt, old_manifest.receipt_ids[1]), corrected.connections)
            new_report = sign(center, new_manifest.manifest_id, corrected.start, 1)
            extended_report = sign(center, new_manifest.manifest_id, corrected.start, 2)
            _check_equal(extended_report.values.account.first_by_tick,
                         (Fraction(0), Fraction(1, 2), Fraction(1, 8)))

        with closing(CenterIntakeStore(center_path, TRIAL_ID)) as center:
            center.initialize()
            ledger = ReportLedger(center.connection)
            ledger.initialize()
            _describe_report('v5', {'lag_a': 1, 'lag_b': 2, 'horizon': 3},
                             {'first': ['0', '0', '0', '1'], 'remaining': '0'},
                             positive_report, get_report(ledger, positive_report.report_id),
                             'The two deterministic lags add to three ticks.')
            old = get_report(ledger, old_report.report_id)
            _describe_report('v6', {'retry_delay': 0, 'direct': '1/2', 'retry': '1/4',
                                    'closed': '1/4', 'horizon': 1},
                             {'first': ['0', '2/3'], 'remaining': '1/3'}, old_report, old,
                             'Sum the exact geometric series with initial term 1/2 and ratio 1/4.')
            new = get_report(ledger, new_report.report_id)
            difference = compare_reports(ledger, old.report_id, new.report_id)
            _check_equal(new, new_report)
            _check_equal(old.values.origins, old_manifest.origins)
            _check_equal(new.values.origins, new_manifest.origins)
            _check_equal(difference.first_origins, old_manifest.origins)
            _check_equal(difference.second_origins, new_manifest.origins)
            expected = {'first': ['0', '1/2'], 'remaining': '1/2'}
            actual = _account(new)
            _check_equal(actual, expected)
            delta = [str(value) for value in difference.delta_by_tick]
            _check_equal(delta, ['0', '-1/6'])
            _scenario('v7', {'old_retry_delay': 0, 'new_retry_delay': 1, 'horizon': 1},
                      expected, actual, ['0', '-1/6'], delta,
                      ['station/freezing.py', 'analysis/completion.py', 'reports/comparison.py'],
                      'The delayed retry misses the first deadline. Subtract 2/3 from 1/2 at tick one.')


if __name__ == '__main__':
    main()
