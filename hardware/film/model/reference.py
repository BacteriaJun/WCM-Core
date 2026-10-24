# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Event-step Film control model with externally qualified frontend inputs.
"""
from dataclasses import dataclass, replace
from typing import NamedTuple

Q, REBIND, READY, TX, AERO = range(5)
FRAME = 0xAD
BITS = 8

@dataclass(frozen=True)
class State:
    mode: int = Q
    w0: bool = False
    w1: bool = False
    credit: bool = False
    data: int = 0
    bits_done: int = 0

class Event(NamedTuple):
    name: str
    power: bool = True
    fault: bool = False
    break_event: bool = False
    timing_alive: bool = True
    tx_deadline_ok: bool = True
    aero_deadline_ok: bool = True
    cap0: bool = False
    cap1: bool = False
    capture_after_cutover: bool = True
    w0_live: bool = True
    w1_live: bool = True
    energy_sample: bool = False
    energy_after_settle: bool = True
    tx_energy_ok: bool = True
    aero_energy_ok: bool = True
    req_tx: bool = False
    req_aero: bool = False
    authorized: bool = True
    symbol_done: bool = False
    aero_done: bool = False
    aero_done_auth: bool = True
    settle: bool = False
    settle_after_entry: bool = True
    settled_ok: bool = True
    reset: bool = False


def outputs(s: State, e: Event):
    # outputs electrically masked BEFORE next state-machine clock edge
    safe = e.power and not e.fault and not e.break_event and not e.reset and e.timing_alive
    live = s.w0 and s.w1 and e.w0_live and e.w1_live and e.authorized and not e.cap0 and not e.cap1
    return dict(optical=bool(safe and live and e.tx_deadline_ok and s.mode == TX and (s.data & 0x80)),
                authority=bool(safe and live and ((s.mode == TX and e.tx_deadline_ok) or (s.mode == AERO and e.aero_deadline_ok))))


def step(s: State, e: Event):
    """Returns successor, tx_start, aero_start. Events represent synchronized edges."""
    if e.reset or not e.power or e.fault or not e.timing_alive:
        return State(), False, False
    if e.break_event:
        next_mode = Q if s.mode in (Q, TX, AERO) else REBIND
        return State(mode=next_mode), False, False
    if s.mode == Q:
        return (State(mode=REBIND) if (e.settle and e.settle_after_entry and e.settled_ok)
                else s), False, False
    if s.mode == REBIND:
        s2 = replace(s, w0=e.w0_live and (s.w0 or (e.cap0 and e.capture_after_cutover)),
                     w1=e.w1_live and (s.w1 or (e.cap1 and e.capture_after_cutover)),
                     credit=(s.credit or (e.energy_sample and e.energy_after_settle)))
        if (s.w0 and s.w1 and s.credit and e.w0_live and e.w1_live
                and not e.cap0 and not e.cap1):
            s2 = replace(s2, mode=READY)
        return s2, False, False
    if s.mode == READY:
        if not (e.w0_live and e.w1_live):
            return replace(s, mode=REBIND, w0=s.w0 and e.w0_live,
                           w1=s.w1 and e.w1_live), False, False
        if e.cap0 or e.cap1:
            return replace(s, mode=REBIND,
                           w0=s.w0 or (e.cap0 and e.capture_after_cutover),
                           w1=s.w1 or (e.cap1 and e.capture_after_cutover)), False, False
        auth = s.w0 and s.w1 and s.credit and e.authorized
        if e.req_tx and not e.req_aero and auth and e.tx_energy_ok and e.tx_deadline_ok:
            return replace(s, mode=TX, credit=False, data=FRAME, bits_done=0), True, False
        if e.req_aero and not e.req_tx and auth and e.aero_energy_ok and e.aero_deadline_ok:
            return replace(s, mode=AERO, credit=False), False, True
        return s, False, False
    if s.mode == TX:
        if (not s.w0 or not s.w1 or not e.w0_live or not e.w1_live
                or e.cap0 or e.cap1 or not e.authorized or not e.tx_deadline_ok):
            return State(), False, False
        if e.symbol_done:
            if s.bits_done == BITS-1:
                return State(), False, False
            return replace(s, data=(s.data << 1) & 255, bits_done=s.bits_done+1), False, False
        return s, False, False
    if s.mode == AERO:
        if (not s.w0 or not s.w1 or not e.w0_live or not e.w1_live
                or e.cap0 or e.cap1 or not e.authorized or not e.aero_deadline_ok):
            return State(), False, False
        if e.aero_done and e.aero_done_auth:
            return State(mode=REBIND), False, False
        return s, False, False
    return State(), False, False
