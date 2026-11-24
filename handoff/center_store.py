import json
import sqlite3


def _check_id(value, label):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError(f'invalid {label} number')


class CenterIntakeStore:
    def __init__(self, path, trial_id, stations=('A', 'B')):
        if not isinstance(trial_id, str) or not trial_id.strip():
            raise ValueError('trial ID must be a nonempty string')
        if not isinstance(stations, (tuple, list)) or len(stations) != 2:
            raise ValueError('provide two ordered stations')
        if any(not isinstance(station, str) or not station.strip() for station in stations):
            raise ValueError('station must be a nonempty string')
        if stations[0] == stations[1]:
            raise ValueError('the two station slots must be distinct')
        self.trial_id = trial_id
        self.stations = tuple(stations)
        self.connection = sqlite3.connect(path, isolation_level=None)
        self.connection.execute('PRAGMA foreign_keys = ON')

    def close(self):
        self.connection.close()

    def _require_autocommit(self):
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('finish the active center transaction first')

    def initialize(self):
        self._require_autocommit()
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS evidence_receipts (
                id INTEGER PRIMARY KEY,
                station TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fixed_manifests (
                id INTEGER PRIMARY KEY,
                trial_id TEXT NOT NULL,
                left_receipt INTEGER NOT NULL REFERENCES evidence_receipts(id),
                right_receipt INTEGER NOT NULL REFERENCES evidence_receipts(id),
                wiring TEXT NOT NULL,
                CHECK (left_receipt <> right_receipt)
            );
        ''')

    def insert_receipt(self, station, revision_id, payload):
        self._require_autocommit()
        cursor = self.connection.execute(
            'INSERT INTO evidence_receipts (station, revision, payload) VALUES (?, ?, ?)',
            (station, revision_id, payload),
        )
        return cursor.lastrowid

    def load_receipt(self, receipt_id):
        _check_id(receipt_id, 'intake receipt')
        row = self.connection.execute(
            'SELECT station, revision, payload FROM evidence_receipts WHERE id = ?', (receipt_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f'unknown intake receipt: {receipt_id}')
        return row

    def insert_manifest(self, receipt_ids, wiring):
        self._require_autocommit()
        left, right = receipt_ids
        cursor = self.connection.execute(
            'INSERT INTO fixed_manifests (trial_id, left_receipt, right_receipt, wiring) VALUES (?, ?, ?, ?)',
            (self.trial_id, left, right, json.dumps(wiring, ensure_ascii=False)),
        )
        return cursor.lastrowid

    def load_manifest(self, manifest_id):
        _check_id(manifest_id, 'manifest')
        row = self.connection.execute(
            '''SELECT m.trial_id, m.left_receipt, m.right_receipt, m.wiring,
                      a.station, a.revision, b.station, b.revision
               FROM fixed_manifests AS m
               JOIN evidence_receipts AS a ON a.id = m.left_receipt
               JOIN evidence_receipts AS b ON b.id = m.right_receipt
               WHERE m.id = ?''',
            (manifest_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f'unknown manifest: {manifest_id}')
        trial_id, left, right, wiring, left_station, left_revision, right_station, right_revision = row
        return trial_id, (left, right), ((left_station, left_revision), (right_station, right_revision)), json.loads(wiring)
