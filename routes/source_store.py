import sqlite3
from fractions import Fraction

from routes.states import RouteState
from routes.transitions import TransitionRow


class SourceStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA foreign_keys = ON')

    def close(self):
        self.connection.close()

    def initialize(self):
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('finish the active source transaction before initialization')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS route_revisions (
                id INTEGER PRIMARY KEY,
                station TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS route_states (
                revision INTEGER NOT NULL REFERENCES route_revisions(id),
                ordinal INTEGER NOT NULL,
                state_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                entry TEXT,
                exit_port TEXT,
                PRIMARY KEY (revision, state_id),
                UNIQUE (revision, ordinal)
            );
            CREATE TABLE IF NOT EXISTS route_transitions (
                revision INTEGER NOT NULL REFERENCES route_revisions(id),
                ordinal INTEGER NOT NULL,
                row_id TEXT NOT NULL,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                delay INTEGER NOT NULL,
                numerator TEXT NOT NULL,
                denominator TEXT NOT NULL,
                PRIMARY KEY (revision, row_id),
                UNIQUE (revision, ordinal),
                FOREIGN KEY (revision, source) REFERENCES route_states(revision, state_id),
                FOREIGN KEY (revision, target) REFERENCES route_states(revision, state_id)
            );
        ''')

    def insert_revision(self, station, states, rows):
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('finish the active source transaction before saving a revision')
        with self.connection:
            cursor = self.connection.execute('INSERT INTO route_revisions (station) VALUES (?)', (station,))
            revision = cursor.lastrowid
            self.connection.executemany(
                'INSERT INTO route_states VALUES (?, ?, ?, ?, ?, ?)',
                ((revision, ordinal, state.state_id, state.kind, state.entry, state.exit)
                 for ordinal, state in enumerate(states)),
            )
            self.connection.executemany(
                'INSERT INTO route_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                ((revision, ordinal, row.row_id, row.source, row.target, row.delay,
                  str(row.probability.numerator), str(row.probability.denominator))
                 for ordinal, row in enumerate(rows)),
            )
        return revision

    def load_revision(self, station, revision_id):
        if type(revision_id) is not int or not 0 < revision_id < 2**63:
            raise ValueError('invalid revision number')
        found = self.connection.execute(
            'SELECT id FROM route_revisions WHERE station = ? AND id = ?', (station, revision_id)
        ).fetchone()
        if found is None:
            raise LookupError(f'no revision {revision_id} for station {station}')
        states = self.connection.execute(
            'SELECT state_id, kind, entry, exit_port FROM route_states WHERE revision = ? ORDER BY ordinal',
            (revision_id,),
        )
        rows = self.connection.execute(
            '''SELECT row_id, source, target, delay, numerator, denominator
               FROM route_transitions WHERE revision = ? ORDER BY ordinal''',
            (revision_id,),
        )
        return (
            tuple(RouteState(*row) for row in states),
            tuple(TransitionRow(row_id, source, target, delay, Fraction(int(numerator), int(denominator)))
                  for row_id, source, target, delay, numerator, denominator in rows),
        )
