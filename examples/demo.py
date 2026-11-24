import json
from contextlib import ExitStack, closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.scenarios import sign, sign_consumption
from examples.scenarios import (TRIAL_ID, positive_chain, register_declared_example,
                                register_example, register_station, return_loop)
from handoff.center_store import CenterIntakeStore
from handoff.manifest import fix_manifest
from reports.comparison import compare_reports
from reports.history import get_consumption_report, get_report
from reports.ledger import ReportLedger
from routes.source_store import SourceStore


def _check_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f'expected {expected!r}, got {actual!r}')


def _account(report):
    account = report.values.account
    return {'first': [str(value) for value in account.first_by_tick], 'remaining': str(account.remaining)}


def _consumption_account(report):
    account = report.values.account
    return {
        'first': [[str(value) for value in row] for row in account.first_by_tick],
        'exceeded': [str(value) for value in account.exceeded_by_tick],
        'remaining': str(account.remaining),
    }


def _describe_report(case_id, inputs, expected, report, archived, oracle):
    actual = _account(report)
    _check_equal(actual, expected)
    _check_equal(archived, report)
    downstream_expected = {'report_id': report.report_id, 'intake_ids': list(report.values.receipt_ids)}
    downstream_actual = {'report_id': archived.receipt.report_id, 'intake_ids': list(archived.receipt.receipt_ids)}
    _check_equal(downstream_actual, downstream_expected)
    _scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
              ['analysis/completion.py', 'reports/publish.py', 'reports/history.py'], oracle)


def _describe_consumption(case_id, inputs, expected, report, archived, oracle):
    actual = _consumption_account(report)
    _check_equal(actual, expected)
    _check_equal(archived, report)
    downstream_expected = {'report_id': report.report_id, 'intake_ids': list(report.values.receipt_ids)}
    downstream_actual = {'report_id': archived.receipt.report_id, 'intake_ids': list(archived.receipt.receipt_ids)}
    _check_equal(downstream_actual, downstream_expected)
    _scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
              ['station/consumption.py', 'analysis/consumption.py', 'reports/publish.py',
               'reports/history.py'], oracle)


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
                plain_manifest = register_declared_example(center, left, right, chain)
                declared_manifest = register_declared_example(
                    center, left, right, chain, consuming_left=('a-send',), consuming_right=('b-check',))
                loop_manifest = register_declared_example(
                    center, left, right, original, consuming_left=('a-retry',))
            left_path.rename(left_off)
            right_path.rename(right_off)
            positive_report = sign(center, chain_manifest.manifest_id, chain.start, 3)
            old_report = sign(center, old_manifest.manifest_id, original.start, 1)

            plain_completion = sign(center, plain_manifest.manifest_id, chain.start, 3)
            declared_completion = sign(center, declared_manifest.manifest_id, chain.start, 3)
            _check_equal(_account(declared_completion), _account(plain_completion))
            plain_quota = sign_consumption(center, plain_manifest.manifest_id, chain.start, 3, 0)
            declared_quota0 = sign_consumption(center, declared_manifest.manifest_id, chain.start, 3, 0)
            declared_quota1 = sign_consumption(center, declared_manifest.manifest_id, chain.start, 3, 1)
            loop_completion = sign(center, loop_manifest.manifest_id, original.start, 1)
            loop_quota1 = sign_consumption(center, loop_manifest.manifest_id, original.start, 1, 1)
            refused_error = None
            try:
                sign_consumption(center, old_manifest.manifest_id, original.start, 1, 1)
            except ValueError as error:
                refused_error = error
            if refused_error is None:
                raise AssertionError('expected the undeclared evidence to be refused')

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

            _check_equal(_account(plain_completion), {'first': ['0', '0', '0', '1'], 'remaining': '0'})
            _describe_consumption(
                'v8', {'lag_a': 1, 'lag_b': 2, 'horizon': 3, 'quota': 0, 'consuming': []},
                {'first': [['0'], ['0'], ['0'], ['1']], 'exceeded': ['0', '0', '0', '0'],
                 'remaining': '0'},
                plain_quota, get_consumption_report(ledger, plain_quota.report_id),
                'No row consumes, so the zero quota never binds and the chain completes at tick three.')
            _describe_consumption(
                'v9', {'lag_a': 1, 'lag_b': 2, 'horizon': 3, 'quota': 0,
                       'consuming': ['a-send', 'b-check']},
                {'first': [['0'], ['0'], ['0'], ['0']], 'exceeded': ['0', '1', '0', '0'],
                 'remaining': '0'},
                declared_quota0, get_consumption_report(ledger, declared_quota0.report_id),
                'Same completion rate as v8, but the first declared row spends a sample at tick '
                'one, past the zero quota.')
            _describe_consumption(
                'v10', {'lag_a': 1, 'lag_b': 2, 'horizon': 3, 'quota': 1,
                        'consuming': ['a-send', 'b-check']},
                {'first': [['0', '0'], ['0', '0'], ['0', '0'], ['0', '0']],
                 'exceeded': ['0', '0', '0', '1'], 'remaining': '0'},
                declared_quota1, get_consumption_report(ledger, declared_quota1.report_id),
                'The second sample completes at tick three together with the inspection; the '
                'overrun is settled before the same-tick completion.')
            _check_equal(_account(loop_completion), {'first': ['0', '2/3'], 'remaining': '1/3'})
            _describe_consumption(
                'v11', {'retry_delay': 0, 'direct': '1/2', 'retry': '1/4', 'closed': '1/4',
                        'horizon': 1, 'quota': 1, 'consuming': ['a-retry']},
                {'first': [['0', '0'], ['1/2', '1/8']], 'exceeded': ['1/16', '0'],
                 'remaining': '5/16'},
                loop_quota1, get_consumption_report(ledger, loop_quota1.report_id),
                'Each zero-delay return spends one more sample: completions use 0 or 1 of the '
                'quota, a second retry overruns at tick zero, and the closed branch plus a '
                'stranded retry leave 5/16 unsettled.')
            expected_refusal = {'error': 'ValueError',
                                'completion': {'first': ['0', '2/3'], 'remaining': '1/3'}}
            actual_refusal = {'error': type(refused_error).__name__, 'completion': _account(old)}
            _check_equal(actual_refusal, expected_refusal)
            _scenario('v12', {'horizon': 1, 'quota': 1, 'declaration': 'missing'},
                      expected_refusal, actual_refusal,
                      {'report_id': old_report.report_id, 'intake_ids': list(old_report.values.receipt_ids)},
                      {'report_id': old.report_id, 'intake_ids': list(old.receipt.receipt_ids)},
                      ['analysis/scenarios.py', 'analysis/consumption.py'],
                      'The undeclared station evidence still signs the completion account, but '
                      'carries no fixed consumable declaration.')


if __name__ == '__main__':
    main()
