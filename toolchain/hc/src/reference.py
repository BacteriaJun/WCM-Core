# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Independent host-side event-step model of the fixed control logic."""
from __future__ import annotations
from dataclasses import dataclass
from enum import IntEnum

class S(IntEnum):
    QUARANTINE=0; REBIND=1; READY=2; TX=3; AERO=4

DEFAULT={
    'rst_n':True,'power_good':True,'hard_fault':False,'timing_alive':True,
    'world_break':False,'observation_dirty_latched':False,'w0_live':True,'w1_live':True,'local_mission_authorized':True,
    'tx_deadline_ok':True,'aero_deadline_ok':True,'capture_w0':False,
    'capture_w1':False,'capture_after_cutover':True,'energy_sample':False,
    'energy_after_settlement':True,'tx_energy_ok':True,'aero_energy_ok':True,
    'req_tx':False,'req_aero':False,'symbol_done_tick':False,
    'aero_done_pulse':False,'aero_done_auth':False,'settle_pulse':False,
    'settle_after_quarantine':True,'settled_ok':True,'tx_frame':0xAD,
}

@dataclass(frozen=True)
class Cell:
    state: S=S.QUARANTINE
    w0: bool=False
    w1: bool=False
    armed: bool=False
    frame: int=0
    bits_done: int=0
    tx_start: bool=False
    aero_start: bool=False

def async_ok(x):
    return (x['rst_n'] and x['power_good'] and not x['hard_fault']
            and x['timing_alive'] and not x['world_break']
            and x['w0_live'] and x['w1_live'] and x['local_mission_authorized']
            and not x['observation_dirty_latched'])

def outputs(c, values=None, bits=8):
    x={**DEFAULT,**(values or {})}
    enable=async_ok(x)
    good=enable and c.w0 and c.w1 and not x['capture_w0'] and not x['capture_w1']
    opt=good and c.state==S.TX and x['tx_deadline_ok'] and bool(c.frame & (1<<(bits-1)))
    return dict(
        optical_reflect=opt,
        tx_active=enable and c.state==S.TX and x['tx_deadline_ok'],
        tx_start=good and c.state==S.TX and x['tx_deadline_ok'] and c.tx_start,
        aero_start=good and c.state==S.AERO and x['aero_deadline_ok'] and c.aero_start,
        quarantined=c.state==S.QUARANTINE,
        authorized=good and ((c.state==S.TX and x['tx_deadline_ok'])
                             or (c.state==S.AERO and x['aero_deadline_ok'])),
    )

def step(c:Cell, values=None, bits=8):
    x={**DEFAULT,**(values or {})}; mask=(1<<bits)-1
    if not async_ok(x): return Cell() # conservative async physical quarantine
    s=c.state; w0=c.w0;w1=c.w1;armed=c.armed
    frame=c.frame;done=c.bits_done;tx_start=False;aero_start=False
    if s==S.QUARANTINE:
        if x['settle_pulse'] and x['settle_after_quarantine'] and x['settled_ok']:
            s=S.REBIND;w0=w1=armed=False
    elif s==S.REBIND:
        if not x['w0_live']: w0=False
        if not x['w1_live']: w1=False
        if x['capture_w0'] and x['capture_after_cutover'] and x['w0_live']:w0=True
        if x['capture_w1'] and x['capture_after_cutover'] and x['w1_live']:w1=True
        if x['energy_sample'] and x['energy_after_settlement']:armed=True
        if (c.w0 and c.w1 and x['w0_live'] and x['w1_live'] and c.armed
                and not x['capture_w0'] and not x['capture_w1']):s=S.READY
    elif s==S.READY:
        if x['capture_w0'] or x['capture_w1']:
            if x['capture_after_cutover']:
                if x['capture_w0']:w0=True
                if x['capture_w1']:w1=True
            s=S.REBIND
        elif (x['req_tx'] and not x['req_aero'] and c.w0 and c.w1 and c.armed
                and x['tx_energy_ok'] and x['tx_deadline_ok']):
            s=S.TX;frame=x['tx_frame']&mask;done=0;armed=False;tx_start=True
        elif (x['req_aero'] and not x['req_tx'] and c.w0 and c.w1 and c.armed
                and x['aero_energy_ok'] and x['aero_deadline_ok']):
            s=S.AERO;armed=False;aero_start=True
    elif s==S.TX:
        if not x['tx_deadline_ok'] or x['capture_w0'] or x['capture_w1']:
            s=S.QUARANTINE;w0=w1=armed=False
        elif x['symbol_done_tick']:
            if done==bits-1:
                s=S.QUARANTINE;w0=w1=armed=False;frame=0
            else:
                done+=1;frame=(frame<<1)&mask
    elif s==S.AERO:
        if not x['aero_deadline_ok'] or x['capture_w0'] or x['capture_w1']:
            s=S.QUARANTINE;w0=w1=armed=False
        elif x['aero_done_pulse'] and x['aero_done_auth']:
            s=S.REBIND;w0=w1=armed=False
    else:
        return Cell()
    return Cell(s,w0,w1,armed,frame,done,tx_start,aero_start)

EVENTS={
    'noop':{},'settle':{'settle_pulse':True},
    'capture':{'capture_w0':True,'capture_w1':True,'energy_sample':True},
    'stale_capture':{'capture_w0':True,'capture_w1':True,'capture_after_cutover':False},
    'stale_energy':{'energy_sample':True,'energy_after_settlement':False},
    'tx':{'req_tx':True},'aero':{'req_aero':True},'both':{'req_tx':True,'req_aero':True},
    'low_energy':{'req_tx':True,'tx_energy_ok':False},
    'symbol':{'symbol_done_tick':True},
    'done':{'aero_done_pulse':True,'aero_done_auth':True},
    'false_done':{'aero_done_pulse':True,'aero_done_auth':False},
    'break':{'world_break':True}, 'brownout':{'power_good':False},
    'timeout':{'tx_deadline_ok':False,'aero_deadline_ok':False},
    'lost_witness':{'w0_live':False},'revoke':{'local_mission_authorized':False},
    'dirty':{'observation_dirty_latched':True},
}
