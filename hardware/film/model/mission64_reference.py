# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Mission-64 behavioral oracle using synchronous events and modeled sensor values.
"""
from dataclasses import dataclass
from enum import IntEnum

class Mode(IntEnum):
    LOAD=0; ACTIVE=1; REQUEST=2; INFLIGHT=3; PASSIVE=4; FAILED=5

def crc_atm(data: bytes) -> int:
    register=0
    for value in data:
        for i in range(7,-1,-1):
            feedback=((register>>7)^((value>>i)&1))&1
            register=((register<<1)&255)^(7 if feedback else 0)
    return register

@dataclass
class FilmMission:
    image: bytes | None = None
    bad: bool = False
    mode: Mode = Mode.LOAD
    elapsed_ms: int = 0
    last_report_ms: int = 0
    phase: int = 0
    sampled: bool = False
    sensor_met: bool = False
    reports: int = 0

    @property
    def mission_valid(self):
        return self.image is not None and not self.bad

    @property
    def request(self):
        return self.mission_valid and self.mode == Mode.REQUEST

    def reset(self):
        self.__init__()

    def bit(self, value: int):
        if value not in (0,1): raise ValueError('bit required')
        if self.bad or self.image is not None:
            self.bad=True;self.image=None;self.mode=Mode.FAILED
            return
        # Model partial NVM shifts as a list to distinguish a truncated image.
        if not hasattr(self,'_bits'):self._bits=[]
        self._bits.append(value)
        if len(self._bits)==64:
            raw=bytes(int(''.join(str(b) for b in self._bits[k:k+8]),2)
                      for k in range(0,64,8))
            # No dependency on Python mission compiler: decode fields locally.
            word=int.from_bytes(raw,'big')
            ver=(word>>60)&15;task=(word>>56)&15;sen=(word>>52)&15
            threshold=(word>>46)&63;sample=(word>>40)&63
            period=(word>>34)&63;maxrep=(word>>28)&63
            flags=(word>>8)&255
            if (crc_atm(raw[:7])!=raw[7] or ver!=1 or sen!=1 or
                task not in (1,2) or (task==1 and not threshold) or
                (task==2 and threshold) or not sample or not period or
                not maxrep or flags!=0):
                self.bad=True;self.mode=Mode.FAILED
            else:self.image=raw

    def fields(self):
        if not self.mission_valid:raise ValueError('unverified image')
        w=int.from_bytes(self.image,'big')
        return {'task':(w>>56)&15,'threshold':(w>>46)&63,
                'sample_period':(w>>40)&63,'report_period':(w>>34)&63,
                'max_reports':(w>>28)&63,'seed':(w>>16)&4095}

    def edge(self, *,tick=False,sensor_valid=True,sensor_value=100,
             accept=False,complete=False,abort=False):
        if self.bad or abort:
            self.mode=Mode.FAILED;return
        if self.mode==Mode.LOAD:
            if self.mission_valid:self.mode=Mode.ACTIVE
            return
        if self.mode in (Mode.FAILED,Mode.PASSIVE):return
        f=self.fields()
        prev=self.mode
        # Verilog computes due with the state *before* the current clock edge.
        due=self.sampled and self.sensor_met and self.reports<f['max_reports'] and (
            (self.reports==0 and self.elapsed_ms>=(f['seed']&15)) or
            (self.reports!=0 and self.elapsed_ms>=self.last_report_ms and
             self.elapsed_ms-self.last_report_ms>=f['report_period']*10))
        if tick:
            if self.elapsed_ms>=65535:self.mode=Mode.FAILED;return
            self.elapsed_ms+=1
            if self.phase==f['sample_period']-1:
                self.phase=0
                self.sampled=sensor_valid
                self.sensor_met=sensor_valid and (
                    f['task']==2 or sensor_value>=f['threshold']*10)
            else:self.phase+=1
        if prev==Mode.ACTIVE and due:self.mode=Mode.REQUEST
        elif prev==Mode.REQUEST and accept:self.mode=Mode.INFLIGHT
        elif prev==Mode.INFLIGHT and complete:
            self.reports+=1
            # At a simultaneous tick, Verilog stores PRE-EDGE elapsed_ms.
            self.last_report_ms=self.elapsed_ms-(1 if tick else 0)
            self.sampled=False
            self.mode=Mode.PASSIVE if self.reports==f['max_reports'] else Mode.ACTIVE
