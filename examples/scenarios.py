from dataclasses import dataclass

from handoff.manifest import fix_manifest
from handoff.port_map import PortRef
from handoff.receiving import receive
from routes.revisions import save_revision
from routes.states import RouteState
from routes.transitions import TransitionRow
from station.freezing import freeze


TRIAL_ID = 'retest-line-1'


@dataclass(frozen=True)
class RouteInput:
    states: tuple[RouteState, ...]
    rows: tuple[TransitionRow, ...]


@dataclass(frozen=True)
class TrialExample:
    left: RouteInput
    right: RouteInput
    connections: tuple[tuple[PortRef, PortRef], ...]
    start: PortRef


def positive_chain(exit_delay=1, completion_delay=2):
    left = RouteInput(
        (RouteState('start-a', entry='a'), RouteState('send', 'exit', exit='out')),
        (TransitionRow('a-send', 'start-a', 'send', exit_delay, 1),),
    )
    right = RouteInput(
        (RouteState('start-b', entry='b'), RouteState('finish-b', 'complete')),
        (TransitionRow('b-check', 'start-b', 'finish-b', completion_delay, 1),),
    )
    return TrialExample(left, right, ((PortRef('A', 'out'), PortRef('B', 'b')),), PortRef('A', 'a'))


def return_loop(retry_delay=0):
    left = RouteInput(
        (RouteState('start-a', entry='a'), RouteState('start-d', entry='d'),
         RouteState('retry', 'exit', exit='to-b'), RouteState('hold', 'exit', exit='to-c'),
         RouteState('send-back', 'exit', exit='back-to-c'), RouteState('finish-a', 'complete')),
        (TransitionRow('a-completes', 'start-a', 'finish-a', 1, '1/2'),
         TransitionRow('a-retry', 'start-a', 'retry', retry_delay, '1/4'),
         TransitionRow('a-hold', 'start-a', 'hold', 0, '1/4'),
         TransitionRow('d-return', 'start-d', 'send-back', 0, 1)),
    )
    right = RouteInput(
        (RouteState('start-b', entry='b'), RouteState('start-c', entry='c'),
         RouteState('return-b', 'exit', exit='to-a'), RouteState('return-c', 'exit', exit='to-d')),
        (TransitionRow('b-returns', 'start-b', 'return-b', 0, 1),
         TransitionRow('c-returns', 'start-c', 'return-c', 0, 1)),
    )
    wiring = (
        (PortRef('A', 'to-b'), PortRef('B', 'b')),
        (PortRef('A', 'to-c'), PortRef('B', 'c')),
        (PortRef('A', 'back-to-c'), PortRef('B', 'c')),
        (PortRef('B', 'to-a'), PortRef('A', 'a')),
        (PortRef('B', 'to-d'), PortRef('A', 'd')),
    )
    return TrialExample(left, right, wiring, PortRef('A', 'a'))


def register_station(center, source, station, route):
    revision = save_revision(source, station, route.states, route.rows)
    evidence = freeze(source, station, revision)
    return receive(center, evidence, station, revision)


def register_example(center, left_source, right_source, example):
    left = register_station(center, left_source, 'A', example.left)
    right = register_station(center, right_source, 'B', example.right)
    return fix_manifest(center, (left, right), example.connections)
