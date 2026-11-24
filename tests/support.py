import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.scenarios import TRIAL_ID, register_example
from handoff.center_store import CenterIntakeStore
from reports.ledger import ReportLedger
from routes.source_store import SourceStore


class CenterCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='retest-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.left_path = self.root / 'a.sqlite'
        self.right_path = self.root / 'b.sqlite'
        self.center_path = self.root / 'center.sqlite'
        self.open_sources()
        self.open_center()

    def open_sources(self):
        self.left = SourceStore(self.left_path)
        self.addCleanup(self.left.close)
        self.right = SourceStore(self.right_path)
        self.addCleanup(self.right.close)
        self.left.initialize()
        self.right.initialize()

    def open_center(self, trial_id=TRIAL_ID):
        self.center = CenterIntakeStore(self.center_path, trial_id)
        self.addCleanup(self.center.close)
        self.center.initialize()
        self.ledger = ReportLedger(self.center.connection)
        self.ledger.initialize()

    def disable_sources(self):
        self.left.close()
        self.right.close()
        for path in (self.left_path, self.right_path):
            path.rename(path.with_suffix('.offline'))

    def restore_sources(self):
        for path in (self.left_path, self.right_path):
            path.with_suffix('.offline').rename(path)
        self.open_sources()

    def register(self, example):
        return register_example(self.center, self.left, self.right, example)

    def intake_count(self):
        return self.center.connection.execute('SELECT COUNT(*) FROM evidence_receipts').fetchone()[0]

    def manifest_count(self):
        return self.center.connection.execute('SELECT COUNT(*) FROM fixed_manifests').fetchone()[0]

    def publication_counts(self):
        connection = self.center.connection
        return (
            connection.execute('SELECT COUNT(*) FROM completion_reports').fetchone()[0],
            connection.execute('SELECT COUNT(*) FROM first_receipts').fetchone()[0],
        )
