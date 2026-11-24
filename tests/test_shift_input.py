from dataclasses import replace
from fractions import Fraction

from examples.scenarios import positive_chain, register_station
from handoff.manifest import fix_manifest, get_manifest
from handoff.port_map import PortRef
from handoff.receiving import get_received_evidence, receive
from routes.revisions import save_revision
from station.evidence import FirstArrival
from station.evidence_codec import decode_evidence, encode_evidence
from station.freezing import freeze
from station.origin import StationOrigin
from tests.support import CenterCase


class ShiftInputTests(CenterCase):
    def test_positive_lag_handoff(self):
        example = positive_chain()
        manifest = self.register(example)
        left, right = (get_received_evidence(self.center, receipt).evidence for receipt in manifest.receipt_ids)
        self.assertEqual(left.arrivals_for('a'), (FirstArrival(1, 'out', Fraction(1)),))
        self.assertEqual(right.arrivals_for('b'), (FirstArrival(2, None, Fraction(1)),))
        self.assertEqual((left.origin, right.origin), (StationOrigin('A', 1), StationOrigin('B', 1)))
        self.assertEqual(manifest.origins, (left.origin, right.origin))
        self.assertEqual(manifest.wiring.target_for(PortRef('A', 'out')), PortRef('B', 'b'))
        self.assertEqual(get_manifest(self.center, manifest.manifest_id), manifest)
        self.assertEqual((self.intake_count(), self.manifest_count()), (2, 1))

    def test_zero_tick_first_exit(self):
        immediate = positive_chain(exit_delay=0).left
        delayed = positive_chain(exit_delay=1).left
        ids = [save_revision(self.left, 'A', route.states, route.rows) for route in (immediate, delayed)]
        first, second = (freeze(self.left, 'A', revision) for revision in ids)
        self.assertEqual(first.arrivals_for('a'), (FirstArrival(0, 'out', Fraction(1)),))
        self.assertEqual(second.arrivals_for('a'), (FirstArrival(1, 'out', Fraction(1)),))
        self.assertEqual(first.remaining_at('a', 0), Fraction(0))
        self.assertEqual(second.remaining_at('a', 0), Fraction(1))
        self.assertEqual(decode_evidence(encode_evidence(first)), first)

    def test_invalid_probability_sum(self):
        route = positive_chain().left
        old = save_revision(self.left, 'A', route.states, route.rows)
        incomplete = (replace(route.rows[0], probability='3/4'),)
        with self.assertRaisesRegex(ValueError, 'expected 1'):
            save_revision(self.left, 'A', route.states, incomplete)
        revisions = self.left.connection.execute('SELECT id FROM route_revisions').fetchall()
        self.assertEqual(revisions, [(old,)])
        self.assertEqual(freeze(self.left, 'A', old).arrivals_for('a'), (FirstArrival(1, 'out', Fraction(1)),))
        with self.assertRaises(LookupError):
            freeze(self.left, 'B', old)

    def test_wrong_revision_receipt(self):
        old_route = positive_chain().left
        new_route = positive_chain(exit_delay=0).left
        old = save_revision(self.left, 'A', old_route.states, old_route.rows)
        new = save_revision(self.left, 'A', new_route.states, new_route.rows)
        with self.assertRaises(ValueError):
            receive(self.center, freeze(self.left, 'A', old), 'A', new)
        self.assertEqual(self.intake_count(), 0)
        receipt = receive(self.center, freeze(self.left, 'A', new), 'A', new)
        self.assertEqual(get_received_evidence(self.center, receipt).evidence.origin, StationOrigin('A', new))

    def test_invalid_evidence_mass(self):
        route = positive_chain().left
        revision = save_revision(self.left, 'A', route.states, route.rows)
        original = freeze(self.left, 'A', revision)
        bad = replace(original, entry_arrivals=(('a', (FirstArrival(0, 'out', Fraction(1)),
                                                        FirstArrival(1, 'out', Fraction(1, 4)))),))
        with self.assertRaisesRegex(ValueError, 'mass exceeds one'):
            receive(self.center, bad, 'A', revision)
        self.assertEqual(self.intake_count(), 0)

    def test_unknown_manifest_port(self):
        example = positive_chain()
        left = register_station(self.center, self.left, 'A', example.left)
        right = register_station(self.center, self.right, 'B', example.right)
        wrong = ((PortRef('A', 'out'), PortRef('B', 'missing')),)
        with self.assertRaises(ValueError):
            fix_manifest(self.center, (left, right), wrong)
        self.assertEqual(self.manifest_count(), 0)
        self.assertEqual(self.publication_counts(), (0, 0))
        valid = fix_manifest(self.center, (left, right), example.connections)
        self.assertEqual(valid.receipt_ids, (left, right))

    def test_station_scoped_ports(self):
        example = positive_chain()
        left = register_station(self.center, self.left, 'A', example.left)
        right = register_station(self.center, self.right, 'B', example.right)
        wrong = ((PortRef('A', 'out'), PortRef('B', 'a')),)
        with self.assertRaisesRegex(ValueError, 'unknown entrance'):
            fix_manifest(self.center, (left, right), wrong)
        with self.assertRaises(ValueError):
            fix_manifest(self.center, (right, left), example.connections)
        self.assertEqual(self.manifest_count(), 0)
        self.assertEqual(self.publication_counts(), (0, 0))
