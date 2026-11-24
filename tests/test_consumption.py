import sqlite3
from fractions import Fraction

from analysis.scenarios import sign, sign_consumption
from examples.scenarios import (positive_chain, register_declared_example, register_example,
                                register_station, return_loop)
from handoff.manifest import fix_manifest
from handoff.port_map import PortRef
from handoff.receiving import get_received_evidence, receive
from reports.history import get_consumption_report, get_report
from routes.revisions import save_revision
from routes.states import RouteState
from routes.transitions import TransitionRow
from station.evidence import CountedArrival, FirstArrival, FirstExceedance
from station.evidence_codec import decode_evidence, encode_evidence
from station.freezing import freeze
from tests.support import CenterCase


def consuming_chain(steps):
    states = [RouteState(f'step-{index}', entry='a') if index == 0 else RouteState(f'step-{index}')
              for index in range(steps)]
    states.append(RouteState('finish-a', 'complete'))
    rows = tuple(
        TransitionRow(f'spend-{index}', f'step-{index}',
                      f'step-{index + 1}' if index + 1 < steps else 'finish-a', 1, 1)
        for index in range(steps)
    )
    return states, rows


def trivial_right():
    states = (RouteState('start-b', entry='b'), RouteState('finish-b', 'complete'))
    rows = (TransitionRow('b-check', 'start-b', 'finish-b', 0, 1),)
    return states, rows


class ConsumptionDeclarationTests(CenterCase):
    def test_declaration_frozen_with_evidence(self):
        route = return_loop().left
        revision = save_revision(self.left, 'A', route.states, route.rows)
        evidence = freeze(self.left, 'A', revision, consuming=('a-retry',))
        self.assertEqual(evidence.consuming_rows, ('a-retry',))
        table = evidence.consumption_for('a')
        self.assertIn(CountedArrival(0, 'to-b', 1, Fraction(1, 4)), table.counted)
        self.assertIn(CountedArrival(1, None, 0, Fraction(1, 2)), table.counted)
        self.assertIn(CountedArrival(0, 'to-c', 0, Fraction(1, 4)), table.counted)
        self.assertEqual(table.exceedances, (FirstExceedance(1, 0, Fraction(1, 4)),))
        self.assertIn(FirstArrival(1, None, Fraction(1, 2)), evidence.arrivals_for('a'))
        self.assertEqual(decode_evidence(encode_evidence(evidence)), evidence)

    def test_declaration_rejects_unknown_or_wrong_revision_rows(self):
        first = save_revision(self.left, 'A', positive_chain().left.states, positive_chain().left.rows)
        loop = return_loop().left
        second = save_revision(self.left, 'A', loop.states, loop.rows)
        with self.assertRaisesRegex(ValueError, 'unknown original transition row'):
            freeze(self.left, 'A', second, consuming=('a-send',))
        with self.assertRaisesRegex(ValueError, 'unknown original transition row'):
            freeze(self.left, 'A', first, consuming=('a-send', 'missing'))
        with self.assertRaisesRegex(ValueError, 'duplicate consumable row'):
            freeze(self.left, 'A', first, consuming=('a-send', 'a-send'))
        for bad in ('a-send', 7, b'a-send'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                freeze(self.left, 'A', first, consuming=bad)
        undeclared = freeze(self.left, 'A', first)
        self.assertIsNone(undeclared.consuming_rows)
        self.assertIsNone(undeclared.consumption)
        evidence = freeze(self.left, 'A', first, consuming=('a-send',))
        self.assertEqual(evidence.consuming_rows, ('a-send',))

    def test_parallel_rows_marked_separately(self):
        states = (RouteState('a', entry='a'), RouteState('finish', 'complete'))
        rows = (TransitionRow('one-measurement', 'a', 'finish', 0, '1/2'),
                TransitionRow('parallel-measurement', 'a', 'finish', 0, '1/2'))
        revision = save_revision(self.left, 'A', states, rows)
        evidence = freeze(self.left, 'A', revision, consuming=('one-measurement',))
        table = evidence.consumption_for('a')
        self.assertEqual(set(table.counted),
                         {CountedArrival(0, None, 0, Fraction(1, 2)),
                          CountedArrival(0, None, 1, Fraction(1, 2))})
        self.assertEqual(table.exceedances, (FirstExceedance(1, 0, Fraction(1, 2)),))
        self.assertEqual(evidence.arrivals_for('a'), (FirstArrival(0, None, Fraction(1)),))
        both = freeze(self.left, 'A', revision, consuming=('one-measurement', 'parallel-measurement'))
        self.assertEqual(set(both.consumption_for('a').counted),
                         {CountedArrival(0, None, 1, Fraction(1))})

    def test_empty_declaration_keeps_completion_account(self):
        example = positive_chain()
        manifest = register_declared_example(self.center, self.left, self.right, example)
        evidence = get_received_evidence(self.center, manifest.receipt_ids[0]).evidence
        self.assertEqual(evidence.consuming_rows, ())
        self.assertIsNotNone(evidence.consumption)
        self.disable_sources()
        report = sign_consumption(self.center, manifest.manifest_id, example.start, 3, 0)
        self.assertEqual(report.values.account.first_by_tick,
                         ((Fraction(0),),) * 3 + ((Fraction(1),),))
        self.assertEqual(report.values.account.exceeded_by_tick, (Fraction(0),) * 4)
        self.assertEqual(report.values.account.remaining, Fraction(0))

    def test_old_evidence_missing_declaration(self):
        example = return_loop()
        manifest = register_example(self.center, self.left, self.right, example)
        evidence = get_received_evidence(self.center, manifest.receipt_ids[0]).evidence
        self.assertIsNone(evidence.consumption)
        self.assertIsNone(evidence.consuming_rows)
        self.disable_sources()
        completion = sign(self.center, manifest.manifest_id, example.start, 1)
        self.assertEqual(completion.values.account.first_by_tick, (Fraction(0), Fraction(2, 3)))
        with self.assertRaisesRegex(ValueError, 'missing the fixed consumable declaration'):
            sign_consumption(self.center, manifest.manifest_id, example.start, 1, 1)
        self.assertEqual(self.consumption_counts(), (0, 0))

    def consumption_counts(self):
        connection = self.center.connection
        return (
            connection.execute('SELECT COUNT(*) FROM consumption_reports').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM consumption_receipts').fetchone()[0],
        )


class ConsumptionReportTests(CenterCase):
    def consumption_counts(self):
        connection = self.center.connection
        return (
            connection.execute('SELECT COUNT(*) FROM consumption_reports').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM consumption_receipts').fetchone()[0],
        )

    def test_same_completion_rate_different_quota_outcome(self):
        example = positive_chain()
        plain = register_declared_example(self.center, self.left, self.right, example)
        declared = register_declared_example(self.center, self.left, self.right, example,
                                             consuming_left=('a-send',), consuming_right=('b-check',))
        self.disable_sources()
        for manifest in (plain, declared):
            completion = sign(self.center, manifest.manifest_id, example.start, 3)
            self.assertEqual(completion.values.account.first_by_tick, tuple(map(Fraction, (0, 0, 0, 1))))
            self.assertEqual(completion.values.account.remaining, Fraction(0))
        untouched = sign_consumption(self.center, plain.manifest_id, example.start, 3, 0)
        self.assertEqual(untouched.values.account.first_by_tick[3], (Fraction(1),))
        self.assertEqual(untouched.values.account.exceeded, Fraction(0))
        refused = sign_consumption(self.center, declared.manifest_id, example.start, 3, 0)
        self.assertEqual(refused.values.account.exceeded_by_tick, tuple(map(Fraction, (0, 1, 0, 0))))
        self.assertEqual(refused.values.account.completed, Fraction(0))
        self.assertEqual(refused.values.account.remaining, Fraction(0))

    def test_overrun_settles_before_same_tick_completion(self):
        example = positive_chain()
        declared = register_declared_example(self.center, self.left, self.right, example,
                                             consuming_left=('a-send',), consuming_right=('b-check',))
        self.disable_sources()
        report = sign_consumption(self.center, declared.manifest_id, example.start, 3, 1)
        self.assertEqual(report.values.account.exceeded_by_tick, tuple(map(Fraction, (0, 0, 0, 1))))
        self.assertEqual(report.values.account.completed, Fraction(0))
        self.assertEqual(report.values.account.remaining, Fraction(0))
        enough = sign_consumption(self.center, declared.manifest_id, example.start, 3, 2)
        self.assertEqual(enough.values.account.first_by_tick[3], (Fraction(0), Fraction(0), Fraction(1)))
        self.assertEqual(enough.values.account.exceeded, Fraction(0))

    def test_zero_delay_return_consumes_repeatedly(self):
        example = return_loop()
        manifest = register_declared_example(self.center, self.left, self.right, example,
                                             consuming_left=('a-retry',))
        self.disable_sources()
        completion = sign(self.center, manifest.manifest_id, example.start, 1)
        self.assertEqual(completion.values.account.first_by_tick, (Fraction(0), Fraction(2, 3)))
        report = sign_consumption(self.center, manifest.manifest_id, example.start, 1, 1)
        account = report.values.account
        self.assertEqual(account.first_by_tick,
                         ((Fraction(0), Fraction(0)), (Fraction(1, 2), Fraction(1, 8))))
        self.assertEqual(account.exceeded_by_tick, (Fraction(1, 16), Fraction(0)))
        self.assertEqual(account.remaining, Fraction(5, 16))
        self.assertEqual(account.within_quota_by_tick, (Fraction(0), Fraction(5, 8)))
        self.assertEqual(account.cumulative, (Fraction(0), Fraction(5, 8)))
        self.assertEqual(account.completed, Fraction(5, 8))
        self.assertEqual(account.exceeded, Fraction(1, 16))
        tighter = sign_consumption(self.center, manifest.manifest_id, example.start, 1, 0)
        self.assertEqual(tighter.values.account.first_by_tick, ((Fraction(0),), (Fraction(1, 2),)))
        self.assertEqual(tighter.values.account.exceeded_by_tick, (Fraction(1, 4), Fraction(0)))
        self.assertEqual(tighter.values.account.remaining, Fraction(1, 4))
        wider = sign_consumption(self.center, manifest.manifest_id, example.start, 1, 2)
        self.assertEqual(wider.values.account.first_by_tick[1],
                         (Fraction(1, 2), Fraction(1, 8), Fraction(1, 32)))
        self.assertEqual(wider.values.account.exceeded_by_tick, (Fraction(1, 64), Fraction(0)))
        self.assertEqual(wider.values.account.remaining, Fraction(21, 64))

    def test_zero_delay_self_loop_spends_at_tick_zero(self):
        states = (RouteState('work-a', entry='a'), RouteState('finish-a', 'complete'))
        rows = (TransitionRow('spin', 'work-a', 'work-a', 0, '1/2'),
                TransitionRow('stop', 'work-a', 'finish-a', 0, '1/2'))
        revision = save_revision(self.left, 'A', states, rows)
        evidence = freeze(self.left, 'A', revision, consuming=('spin',))
        table = evidence.consumption_for('a')
        self.assertEqual(table.counted,
                         tuple(CountedArrival(0, None, count, Fraction(1, 2) ** (count + 1))
                               for count in range(9)))
        self.assertEqual(table.exceedances,
                         tuple(FirstExceedance(level, 0, Fraction(1, 2) ** level)
                               for level in range(1, 10)))
        right_states, right_rows = trivial_right()
        right_revision = save_revision(self.right, 'B', right_states, right_rows)
        right_receipt = receive(self.center, freeze(self.right, 'B', right_revision, consuming=()),
                                'B', right_revision)
        left_receipt = receive(self.center, evidence, 'A', revision)
        manifest = fix_manifest(self.center, (left_receipt, right_receipt), ())
        self.disable_sources()
        report = sign_consumption(self.center, manifest.manifest_id, PortRef('A', 'a'), 0, 1)
        self.assertEqual(report.values.account.first_by_tick, ((Fraction(1, 2), Fraction(1, 4)),))
        self.assertEqual(report.values.account.exceeded_by_tick, (Fraction(1, 4),))
        self.assertEqual(report.values.account.remaining, Fraction(0))

    def test_closed_zero_delay_loop_stays_or_drains(self):
        states = (RouteState('work-a', entry='a'),)
        rows = (TransitionRow('loop', 'work-a', 'work-a', 0, 1),)
        revision = save_revision(self.left, 'A', states, rows)
        right_states, right_rows = trivial_right()
        right_revision = save_revision(self.right, 'B', right_states, right_rows)
        right_receipt = receive(self.center, freeze(self.right, 'B', right_revision, consuming=()),
                                'B', right_revision)
        idle = receive(self.center, freeze(self.left, 'A', revision, consuming=()), 'A', revision)
        idle_manifest = fix_manifest(self.center, (idle, right_receipt), ())
        draining = receive(self.center, freeze(self.left, 'A', revision, consuming=('loop',)),
                           'A', revision)
        draining_manifest = fix_manifest(self.center, (draining, right_receipt), ())
        self.disable_sources()
        parked = sign_consumption(self.center, idle_manifest.manifest_id, PortRef('A', 'a'), 0, 0)
        self.assertEqual(parked.values.account.first_by_tick, ((Fraction(0),),))
        self.assertEqual(parked.values.account.exceeded_by_tick, (Fraction(0),))
        self.assertEqual(parked.values.account.remaining, Fraction(1))
        drained = sign_consumption(self.center, draining_manifest.manifest_id, PortRef('A', 'a'), 12, 8)
        self.assertEqual(drained.values.account.exceeded_by_tick,
                         (Fraction(1),) + (Fraction(0),) * 12)
        self.assertEqual(drained.values.account.remaining, Fraction(0))

    def test_overflow_level_nine(self):
        states, rows = consuming_chain(9)
        revision = save_revision(self.left, 'A', states, rows)
        right_states, right_rows = trivial_right()
        right_revision = save_revision(self.right, 'B', right_states, right_rows)
        right_receipt = receive(self.center, freeze(self.right, 'B', right_revision, consuming=()),
                                'B', right_revision)
        declared = tuple(row.row_id for row in rows)
        left_receipt = receive(self.center, freeze(self.left, 'A', revision, consuming=declared),
                               'A', revision)
        manifest = fix_manifest(self.center, (left_receipt, right_receipt), ())
        self.disable_sources()
        exact = sign_consumption(self.center, manifest.manifest_id, PortRef('A', 'a'), 9, 8)
        self.assertEqual(exact.values.account.exceeded_by_tick, (Fraction(0),) * 9 + (Fraction(1),))
        self.assertEqual(exact.values.account.completed, Fraction(0))
        self.assertEqual(exact.values.account.remaining, Fraction(0))
        early = sign_consumption(self.center, manifest.manifest_id, PortRef('A', 'a'), 8, 8)
        self.assertEqual(early.values.account.exceeded, Fraction(0))
        self.assertEqual(early.values.account.remaining, Fraction(1))

    def test_full_quota_completes_at_deadline(self):
        states, rows = consuming_chain(8)
        revision = save_revision(self.left, 'A', states, rows)
        right_states, right_rows = trivial_right()
        right_revision = save_revision(self.right, 'B', right_states, right_rows)
        right_receipt = receive(self.center, freeze(self.right, 'B', right_revision, consuming=()),
                                'B', right_revision)
        declared = tuple(row.row_id for row in rows)
        left_receipt = receive(self.center, freeze(self.left, 'A', revision, consuming=declared),
                               'A', revision)
        manifest = fix_manifest(self.center, (left_receipt, right_receipt), ())
        self.disable_sources()
        report = sign_consumption(self.center, manifest.manifest_id, PortRef('A', 'a'), 8, 8)
        self.assertEqual(report.values.account.first_by_tick[8],
                         (Fraction(0),) * 8 + (Fraction(1),))
        self.assertEqual(report.values.account.remaining, Fraction(0))
        short = sign_consumption(self.center, manifest.manifest_id, PortRef('A', 'a'), 8, 7)
        self.assertEqual(short.values.account.exceeded_by_tick, (Fraction(0),) * 8 + (Fraction(1),))
        self.assertEqual(short.values.account.remaining, Fraction(0))

    def test_invalid_consumption_request(self):
        example = positive_chain()
        manifest = register_declared_example(self.center, self.left, self.right, example)
        self.disable_sources()
        for quota in (-1, 9, True, '1', 1.5):
            with self.subTest(quota=quota), self.assertRaises(ValueError):
                sign_consumption(self.center, manifest.manifest_id, example.start, 3, quota)
        for horizon in (13, -1, True):
            with self.subTest(horizon=horizon), self.assertRaises(ValueError):
                sign_consumption(self.center, manifest.manifest_id, example.start, horizon, 0)
        with self.assertRaises(ValueError):
            sign_consumption(self.center, manifest.manifest_id, PortRef('B', 'a'), 3, 0)
        with self.assertRaises(LookupError):
            sign_consumption(self.center, manifest.manifest_id + 1, example.start, 3, 0)
        self.assertEqual(self.consumption_counts(), (0, 0))

    def test_consumption_report_survives_reopen(self):
        example = return_loop()
        manifest = register_declared_example(self.center, self.left, self.right, example,
                                             consuming_left=('a-retry',))
        self.disable_sources()
        report = sign_consumption(self.center, manifest.manifest_id, example.start, 1, 1)
        self.assertEqual(self.consumption_counts(), (1, 1))
        self.center.close()
        self.open_center()
        archived = get_consumption_report(self.ledger, report.report_id)
        self.assertEqual(archived, report)
        self.assertEqual(archived.values.quota, 1)
        self.assertEqual(archived.values.manifest_id, manifest.manifest_id)
        self.assertEqual(archived.receipt.origins, manifest.origins)
        self.assertEqual(archived.receipt.receipt_ids, manifest.receipt_ids)
        with self.assertRaises(LookupError):
            get_consumption_report(self.ledger, report.report_id + 1)
        with self.assertRaises(LookupError):
            get_report(self.ledger, report.report_id)

    def test_consumption_publish_rollback(self):
        example = positive_chain()
        manifest = register_declared_example(self.center, self.left, self.right, example,
                                             consuming_left=('a-send',))
        self.disable_sources()
        old = sign_consumption(self.center, manifest.manifest_id, example.start, 3, 1)
        self.assertEqual(self.consumption_counts(), (1, 1))
        self.center.connection.executescript('''
            CREATE TABLE release_permits (id INTEGER PRIMARY KEY);
            CREATE TABLE release_checks (
                permit INTEGER NOT NULL REFERENCES release_permits(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER require_consumption_permit AFTER INSERT ON consumption_receipts
            BEGIN
                INSERT INTO release_checks (permit) VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            sign_consumption(self.center, manifest.manifest_id, example.start, 3, 1)
        self.assertFalse(self.center.connection.in_transaction)
        self.assertEqual(self.consumption_counts(), (1, 1))
        self.center.close()
        self.open_center()
        self.assertEqual(self.consumption_counts(), (1, 1))
        self.assertEqual(get_consumption_report(self.ledger, old.report_id), old)
        self.center.connection.execute('INSERT INTO release_permits (id) VALUES (1)')
        recovered = sign_consumption(self.center, manifest.manifest_id, example.start, 3, 1)
        self.assertEqual(get_consumption_report(self.ledger, recovered.report_id), recovered)
        self.assertEqual(self.consumption_counts(), (2, 2))
