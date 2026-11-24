from fractions import Fraction

from examples.scenarios import positive_chain
from handoff.manifest import fix_manifest
from handoff.receiving import receive
from routes.revisions import load_revision, save_revision
from routes.states import RouteState
from routes.transitions import TransitionRow
from station.evidence import FirstArrival
from station.freezing import freeze
from tests.support import CenterCase


class BoundaryTests(CenterCase):
    def test_station_closed_loop(self):
        states = (RouteState('hold-1', entry='hold'), RouteState('hold-2'), RouteState('done', 'complete'))
        rows = (TransitionRow('one-two', 'hold-1', 'hold-2', 0, 1),
                TransitionRow('two-one', 'hold-2', 'hold-1', 0, 1))
        revision = save_revision(self.left, 'A', states, rows)
        evidence = freeze(self.left, 'A', revision)
        self.assertEqual(evidence.entrances, ('hold',))
        self.assertEqual(evidence.arrivals_for('hold'), ())
        self.assertEqual(evidence.remaining_at('hold', 12), Fraction(1))
        self.assertEqual(evidence.remaining_at('hold', 0), Fraction(1))
        receive(self.center, evidence, 'A', revision)
        self.assertEqual(self.intake_count(), 1)

    def test_station_loop_with_immediate_and_delayed_arrivals(self):
        states = (RouteState('a', entry='a'), RouteState('blocked'), RouteState('step'),
                  RouteState('finish', 'complete', entry='at-finish'))
        rows = (
            TransitionRow('retry', 'a', 'a', 0, '1/2'),
            TransitionRow('block', 'a', 'blocked', 0, '1/4'),
            TransitionRow('one-measurement', 'a', 'finish', 0, '1/16'),
            TransitionRow('parallel-measurement', 'a', 'finish', 0, '1/16'),
            TransitionRow('delayed', 'a', 'step', 2, '1/8'),
            TransitionRow('blocked-self', 'blocked', 'blocked', 0, 1),
            TransitionRow('step-complete', 'step', 'finish', 1, 1),
        )
        first = save_revision(self.left, 'A', states, rows)
        reversed_id = save_revision(self.left, 'A', reversed(states), reversed(rows))
        expected = (FirstArrival(0, None, Fraction(1, 4)), FirstArrival(3, None, Fraction(1, 4)))
        for revision in (first, reversed_id):
            evidence = freeze(self.left, 'A', revision)
            self.assertEqual(evidence.arrivals_for('a'), expected)
            self.assertEqual(evidence.arrivals_for('at-finish'), (FirstArrival(0, None, Fraction(1)),))
            self.assertEqual(evidence.remaining_at('a', 2), Fraction(3, 4))
            self.assertEqual(evidence.remaining_at('a', 3), Fraction(1, 2))
        saved = load_revision(self.left, 'A', first)
        self.assertEqual(tuple(row.row_id for row in saved.rows), tuple(row.row_id for row in rows))
        self.assertEqual(saved.rows[2].probability, Fraction(1, 16))
        self.assertEqual(saved.rows[3].probability, Fraction(1, 16))

    def test_manifest_rejects_duplicate_or_missing_wires(self):
        example = positive_chain()
        manifest = self.register(example)
        for wiring in ((), example.connections * 2):
            with self.subTest(wiring=wiring), self.assertRaises(ValueError):
                fix_manifest(self.center, manifest.receipt_ids, wiring)
        self.assertEqual(self.manifest_count(), 1)
