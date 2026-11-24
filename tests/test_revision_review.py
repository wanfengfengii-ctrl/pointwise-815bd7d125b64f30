from fractions import Fraction

from analysis.scenarios import sign
from examples.scenarios import positive_chain, register_station, return_loop
from handoff.manifest import fix_manifest
from handoff.receiving import get_received_evidence
from reports.comparison import compare_reports
from reports.history import get_report
from routes.revisions import load_revision
from station.evidence import FirstArrival
from tests.support import CenterCase


class RevisionReviewTests(CenterCase):
    def _reports_before_and_after(self):
        original = return_loop()
        old_manifest = self.register(original)
        self.disable_sources()
        old = sign(self.center, old_manifest.manifest_id, original.start, 1)
        self.restore_sources()
        corrected = return_loop(retry_delay=1)
        new_receipt = register_station(self.center, self.left, 'A', corrected.left)
        new_manifest = fix_manifest(self.center, (new_receipt, old_manifest.receipt_ids[1]), corrected.connections)
        self.disable_sources()
        new = sign(self.center, new_manifest.manifest_id, corrected.start, 1)
        return old, new, old_manifest, new_manifest

    def test_old_and_corrected_report(self):
        old, new, old_manifest, new_manifest = self._reports_before_and_after()
        self.assertEqual(old.values.account.first_by_tick, (Fraction(0), Fraction(2, 3)))
        self.assertEqual(new.values.account.first_by_tick, (Fraction(0), Fraction(1, 2)))
        self.assertEqual(new.values.account.remaining, Fraction(1, 2))
        self.assertEqual(old.receipt.origins, old_manifest.origins)
        self.assertEqual(new.receipt.origins, new_manifest.origins)
        self.assertNotEqual(old.receipt.receipt_ids[0], new.receipt.receipt_ids[0])
        self.assertEqual(old.receipt.receipt_ids[1], new.receipt.receipt_ids[1])
        self.center.close()
        self.open_center()
        self.assertEqual(get_report(self.ledger, old.report_id), old)
        self.assertEqual(get_report(self.ledger, new.report_id), new)
        diff = compare_reports(self.ledger, old.report_id, new.report_id)
        self.assertEqual(diff.delta_by_tick, (Fraction(0), Fraction(-1, 6)))
        self.assertEqual(diff.report_ids, (old.report_id, new.report_id))
        self.assertEqual(diff.first_origins, old_manifest.origins)
        self.assertEqual(diff.second_origins, new_manifest.origins)

    def test_corrected_horizon_two(self):
        old, new, old_manifest, new_manifest = self._reports_before_and_after()
        extended = sign(self.center, new_manifest.manifest_id, new.values.start, 2)
        self.assertEqual(extended.values.account.first_by_tick, (Fraction(0), Fraction(1, 2), Fraction(1, 8)))
        self.assertEqual(extended.values.account.remaining, Fraction(3, 8))
        left_old = get_received_evidence(self.center, old_manifest.receipt_ids[0]).evidence
        left_new = get_received_evidence(self.center, new_manifest.receipt_ids[0]).evidence
        self.assertIn(FirstArrival(0, 'to-b', Fraction(1, 4)), left_old.arrivals_for('a'))
        self.assertIn(FirstArrival(1, 'to-b', Fraction(1, 4)), left_new.arrivals_for('a'))
        self.assertEqual(get_report(self.ledger, old.report_id), old)

    def test_reopen_initialization(self):
        old, new, old_manifest, new_manifest = self._reports_before_and_after()
        self.restore_sources()
        self.left.initialize()
        self.right.initialize()
        old_route = load_revision(self.left, 'A', old_manifest.origins[0].revision_id)
        changed = load_revision(self.left, 'A', new_manifest.origins[0].revision_id)
        self.assertEqual({row.row_id: row.delay for row in old_route.rows}['a-retry'], 0)
        self.assertEqual({row.row_id: row.delay for row in changed.rows}['a-retry'], 1)
        self.assertEqual(self.left.connection.execute('SELECT COUNT(*) FROM route_revisions').fetchone(), (2,))
        self.disable_sources()
        self.center.close()
        self.open_center()
        self.center.initialize()
        self.ledger.initialize()
        self.assertEqual(self.publication_counts(), (2, 2))
        self.assertEqual(self.intake_count(), 3)
        self.assertEqual(self.manifest_count(), 2)
        self.assertEqual(get_report(self.ledger, old.report_id), old)
        self.assertEqual(get_report(self.ledger, new.report_id), new)

    def test_incompatible_scope(self):
        old, new, _, new_manifest = self._reports_before_and_after()
        extended = sign(self.center, new_manifest.manifest_id, new.values.start, 2)
        with self.assertRaises(ValueError):
            compare_reports(self.ledger, old.report_id, extended.report_id)
        with self.assertRaises(LookupError):
            compare_reports(self.ledger, new.report_id, extended.report_id + 1)

    def test_manifest_keeps_trial_context_on_reopen(self):
        example = positive_chain()
        manifest = self.register(example)
        self.disable_sources()
        old = sign(self.center, manifest.manifest_id, example.start, 3)
        self.center.close()
        self.open_center(trial_id='another-trial')
        repeated = sign(self.center, manifest.manifest_id, example.start, 3)
        other_manifest = fix_manifest(self.center, manifest.receipt_ids, example.connections)
        other = sign(self.center, other_manifest.manifest_id, example.start, 3)
        self.assertEqual(repeated.values.trial_id, old.values.trial_id)
        self.assertEqual(other.values.trial_id, 'another-trial')
        with self.assertRaises(ValueError):
            compare_reports(self.ledger, old.report_id, other.report_id)
