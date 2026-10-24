# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Generate reference-model stimulus and assertions for execution with Icarus Verilog.
"""
from __future__ import annotations
import argparse
import random
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.reference import Cell, S, DEFAULT, EVENTS, outputs, step
from src.compiler import PORTS

def render(seed=20261023, rounds=12, per_round=48):
    rng=random.Random(seed)
    t=['`timescale 1ns/1ps','module tb_trace_wcm_reference_core;',
       'reg clk = 0; always #5 clk = ~clk;']
    outs=set(('optical_reflect','tx_active','aero_start','tx_start','actuator_authority','quarantined','state_debug','observation_dirty_ack'))
    for p in PORTS:
        if p=='clk':continue
        if p in outs:
            w='[2:0] ' if p=='state_debug' else ''
            t.append(f'wire {w}{p};')
        else:
            w='[7:0] ' if p=='tx_frame' else ''
            t.append(f'reg {w}{p} = '+('8\'hAD' if p=='tx_frame' else "1'b"+('1' if DEFAULT.get(p,False) else '0'))+';')
    t.append('wcm_reference_core dut (.*);')
    t.append('initial begin')
    t.append("  rst_n = 0; @(posedge clk); #1;")
    t.append('  if (state_debug !== 3\'d0) $fatal(1,"reset not quarantine");')
    count=0
    for round_index in range(rounds):
        if round_index:
            t.append('  @(negedge clk); rst_n = 0; @(posedge clk); #1;')
            t.append('  if (state_debug !== 3\'d0) $fatal(1,"reset not quarantine");')
        c=Cell()
        forced=[
            {'settle_pulse':True},
            {'capture_w0':True,'capture_w1':True,'energy_sample':True},
            {},
            {'req_tx':True,'tx_frame':0xAD},
            *([{'symbol_done_tick':True}]*8),
            {'settle_pulse':True},
            {'capture_w0':True,'capture_w1':True,'energy_sample':True},
            {},
            {'req_aero':True},
            {'aero_done_pulse':True,'aero_done_auth':True},
        ]
        choices=list(EVENTS.values())
        trace=forced+[dict(rng.choice(choices)) for _ in range(per_round)]
        for e in trace:
            x={**DEFAULT,**e};x['rst_n']=True
            c=step(c,e)
            expected=outputs(c,e)
            t.append('  @(negedge clk);')
            for p in PORTS:
                if p in outs or p=='clk':continue
                v=x[p]
                vv=f"8'd{int(v)}" if p=='tx_frame' else f"1'b{int(v)}"
                t.append(f'    {p} = {vv};')
            t.append('  @(posedge clk); #1;')
            t.append(f'  if (state_debug !== 3\'d{int(c.state)}) $fatal(1,"state mismatch at cycle {count}");')
            mapping={'optical_reflect':'optical_reflect','tx_active':'tx_active','tx_start':'tx_start','aero_start':'aero_start','quarantined':'quarantined','actuator_authority':'authorized'}
            for verilog,model_key in mapping.items():
                t.append(f'  if ({verilog} !== 1\'b{int(expected[model_key])}) $fatal(1,"{verilog} mismatch at cycle {count}");')
            ack = c.state == S.QUARANTINE and x['rst_n'] and x['power_good'] and not x['hard_fault'] and x['timing_alive']
            t.append(f'  if (observation_dirty_ack !== 1\'b{int(ack)}) $fatal(1,"dirty_ack mismatch at cycle {count}");')
            count+=1
    t.append(f'  $display("PASS reference-vs-RTL trace: {count} stimulus cycles");')
    t.append('  $finish;')
    t.append('end')
    t.append('endmodule')
    return '\n'.join(t)+'\n',count

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--out',default=str(ROOT/'build/tb_trace_wcm_reference_core.v'));a.add_argument('--rounds',type=int,default=12);a.add_argument('--per-round',type=int,default=48)
    args=a.parse_args()
    src,n=render(rounds=args.rounds,per_round=args.per_round)
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(src)
    print(f'generated clock-accurate test vectors (not executed): {n} cycles -> {dest}')
