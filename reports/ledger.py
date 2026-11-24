import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from analysis.report_values import ReportValues, decode_report_values, encode_report_values
from reports.receipts import FirstReceipt
from station.origin import make_origin


@dataclass(frozen=True)
class SignedReport:
    report_id: int
    values: ReportValues
    receipt: FirstReceipt


class ReportLedger:
    def __init__(self, connection):
        self.connection = connection

    def initialize(self):
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('finish the active transaction before ledger initialization')
        self.connection.execute('PRAGMA foreign_keys = ON')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS completion_reports (
                id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS first_receipts (
                report_id INTEGER PRIMARY KEY REFERENCES completion_reports(id),
                payload TEXT NOT NULL
            );
        ''')

    @contextmanager
    def transaction(self):
        if self.connection.in_transaction:
            raise sqlite3.ProgrammingError('publishing requires its own ledger transaction')
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.connection.commit()
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def insert_report(self, values):
        if not self.connection.in_transaction:
            raise sqlite3.ProgrammingError('start a ledger transaction before publishing')
        cursor = self.connection.execute(
            'INSERT INTO completion_reports (payload) VALUES (?)', (encode_report_values(values),)
        )
        return cursor.lastrowid

    def insert_receipt(self, receipt):
        if not self.connection.in_transaction:
            raise sqlite3.ProgrammingError('start a ledger transaction before publishing')
        payload = {
            'receipts': list(receipt.receipt_ids),
            'origins': [[origin.station, origin.revision_id] for origin in receipt.origins],
        }
        self.connection.execute(
            'INSERT INTO first_receipts (report_id, payload) VALUES (?, ?)',
            (receipt.report_id, json.dumps(payload, ensure_ascii=False, separators=(',', ':'))),
        )

    def read_pair(self, report_id):
        if type(report_id) is not int or not 0 < report_id < 2**63:
            raise ValueError('invalid report number')
        row = self.connection.execute(
            '''SELECT report.payload, receipt.payload
               FROM completion_reports AS report
               JOIN first_receipts AS receipt ON receipt.report_id = report.id
               WHERE report.id = ?''',
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        values_text, receipt_text = row
        stored_receipt = json.loads(receipt_text)
        receipt = FirstReceipt(report_id, tuple(stored_receipt['receipts']),
                               tuple(make_origin(*origin) for origin in stored_receipt['origins']))
        return SignedReport(report_id, decode_report_values(values_text), receipt)
