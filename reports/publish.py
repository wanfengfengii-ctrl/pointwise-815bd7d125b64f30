from reports.ledger import ReportLedger, SignedReport
from reports.receipts import build_first_receipt


def publish_report(ledger: ReportLedger, values):
    with ledger.transaction():
        report_id = ledger.insert_report(values)
        receipt = build_first_receipt(report_id, values)
        ledger.insert_receipt(receipt)
    return SignedReport(report_id, values, receipt)
