from reports.ledger import ReportLedger


def get_report(ledger: ReportLedger, report_id):
    pair = ledger.read_pair(report_id)
    if pair is None:
        raise LookupError(f'unknown signed report: {report_id}')
    return pair
