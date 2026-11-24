from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class TransitionRow:
    row_id: str
    source: str
    target: str
    delay: int
    probability: Fraction | int | str


def parse_transition_rows(rows):
    parsed = []
    seen = set()
    for row in rows:
        if isinstance(row, Mapping):
            try:
                row = TransitionRow(**row)
            except TypeError as error:
                raise ValueError('invalid transition fields') from error
        if not isinstance(row, TransitionRow):
            raise ValueError('each transition must be a TransitionRow or mapping')
        for text in (row.row_id, row.source, row.target):
            if not isinstance(text, str) or not text.strip():
                raise ValueError('transition IDs must be nonempty strings')
        if row.row_id in seen:
            raise ValueError(f'duplicate original row: {row.row_id}')
        seen.add(row.row_id)
        if type(row.delay) is not int or not 0 <= row.delay <= 3:
            raise ValueError(f'invalid delay on row {row.row_id}')
        value = row.probability
        if type(value) not in (Fraction, int, str):
            raise ValueError(f'expected exact probability on row {row.row_id}')
        try:
            probability = Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f'invalid probability on row {row.row_id}') from error
        if probability < 0:
            raise ValueError(f'negative probability on row {row.row_id}')
        parsed.append(TransitionRow(row.row_id, row.source, row.target, row.delay, probability))
    return tuple(parsed)


def outgoing_by_state(rows):
    outgoing = {}
    for row in rows:
        outgoing.setdefault(row.source, []).append(row)
    return {source: tuple(transitions) for source, transitions in outgoing.items()}
