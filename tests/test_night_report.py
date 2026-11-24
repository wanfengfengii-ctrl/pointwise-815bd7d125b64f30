import sqlite3
from fractions import Fraction

from analysis.scenarios import sign
from examples.scenarios import positive_chain, return_loop
from handoff.port_map import PortRef
from reports.history import get_report
from tests.support import CenterCase


class NightReportTests(CenterCase):
    def test_completion_at_deadline(self):
        example = positive_chain()
        manifest = self.register(example)
        self.disable_sources()
        early = sign(self.center, manifest.manifest_id, example.start, 2)
        exact = sign(self.center, manifest.manifest_id, example.start, 3)
        self.assertEqual(early.values.account.first_by_tick, (Fraction(0),) * 3)
        self.assertEqual(early.values.account.remaining, Fraction(1))
        self.assertEqual(exact.values.account.first_by_tick, tuple(map(Fraction, (0, 0, 0, 1))))
        self.assertEqual(exact.values.account.cumulative, tuple(map(Fraction, (0, 0, 0, 1))))
        self.assertEqual(exact.values.account.remaining, Fraction(0))
        self.assertTrue(all(type(value) is Fraction for value in exact.values.account.first_by_tick))
        self.assertEqual(exact.receipt.origins, manifest.origins)
        self.assertEqual(exact.receipt.receipt_ids, manifest.receipt_ids)
        self.assertEqual(get_report(self.ledger, exact.report_id), exact)

    def test_same_tick_returns(self):
        example = return_loop()
        manifest = self.register(example)
        self.disable_sources()
        report = sign(self.center, manifest.manifest_id, example.start, 1)
        self.assertEqual(report.values.account.first_by_tick, (Fraction(0), Fraction(2, 3)),
                         'RETEST_FIRST_COMPLETION')
        self.assertEqual(report.values.account.remaining, Fraction(1, 3))
        self.assertEqual(report.values.account.cumulative, (Fraction(0), Fraction(2, 3)))
        self.assertEqual(report.values.origins, manifest.origins)
        self.assertEqual(report.receipt.origins, manifest.origins)
        self.assertEqual(get_report(self.ledger, report.report_id), report)
        self.assertFalse(self.left_path.exists())
        self.assertFalse(self.right_path.exists())

    def test_instant_completion(self):
        example = positive_chain(exit_delay=0, completion_delay=0)
        manifest = self.register(example)
        self.disable_sources()
        result = sign(self.center, manifest.manifest_id, example.start, 0)
        self.assertEqual(result.values.account.first_by_tick, (Fraction(1),))
        self.assertEqual(result.values.account.remaining, Fraction(0))

    def test_closed_start(self):
        manifest = self.register(return_loop())
        self.disable_sources()
        for horizon in (0, 12):
            with self.subTest(horizon=horizon):
                result = sign(self.center, manifest.manifest_id, PortRef('A', 'd'), horizon)
                self.assertEqual(result.values.account.first_by_tick, (Fraction(0),) * (horizon + 1))
                self.assertEqual(result.values.account.remaining, Fraction(1))

    def test_invalid_request(self):
        example = positive_chain()
        manifest = self.register(example)
        self.disable_sources()
        for start, horizon in ((PortRef('B', 'a'), 3), (example.start, 13),
                               (example.start, -1), (example.start, True)):
            with self.subTest(start=start, horizon=horizon), self.assertRaises(ValueError):
                sign(self.center, manifest.manifest_id, start, horizon)
        with self.assertRaises(LookupError):
            sign(self.center, manifest.manifest_id + 1, example.start, 3)
        self.assertEqual(self.publication_counts(), (0, 0))

    def test_publish_rollback(self):
        example = positive_chain()
        manifest = self.register(example)
        self.disable_sources()
        old = sign(self.center, manifest.manifest_id, example.start, 3)
        self.assertEqual(self.publication_counts(), (1, 1))
        self.center.connection.executescript('''
            CREATE TABLE release_permits (id INTEGER PRIMARY KEY);
            CREATE TABLE release_checks (
                permit INTEGER NOT NULL REFERENCES release_permits(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER require_release_permit AFTER INSERT ON first_receipts
            BEGIN
                INSERT INTO release_checks (permit) VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY'):
            sign(self.center, manifest.manifest_id, example.start, 3)
        self.assertFalse(self.center.connection.in_transaction)
        self.assertEqual(self.publication_counts(), (1, 1))
        self.center.close()
        self.open_center()
        self.assertEqual(self.publication_counts(), (1, 1))
        self.assertEqual(self.center.connection.execute('SELECT COUNT(*) FROM release_checks').fetchone(), (0,))
        self.assertEqual(get_report(self.ledger, old.report_id), old)
        with self.assertRaises(LookupError):
            get_report(self.ledger, old.report_id + 1)
        self.center.connection.execute('INSERT INTO release_permits (id) VALUES (1)')
        recovered = sign(self.center, manifest.manifest_id, example.start, 3)
        self.assertEqual(get_report(self.ledger, recovered.report_id), recovered)
        self.assertEqual(self.publication_counts(), (2, 2))
