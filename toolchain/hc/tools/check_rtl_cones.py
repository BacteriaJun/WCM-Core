# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Check emitted Verilog combinational assignments using Boolean SAT queries.
"""
from __future__ import annotations
import re
from pathlib import Path
from sympy import Symbol, And, Not, satisfiable, sympify

NAMES = ('reset_domain_ok','hard_enable','live_evidence','evidence_output_ok',
         'actuator_authority','optical_reflect','tx_start','aero_start')
OUTPUTS = ('actuator_authority','optical_reflect','tx_start','aero_start')
FAULTS = ('observation_dirty_latched','world_break','hard_fault',
          'power_good','timing_alive','rst_n','w0_live','w1_live',
          'local_mission_authorized','capture_w0','capture_w1')

def extract(source):
    source = re.sub(r'//[^\n]*', '', source)
    result={}
    for name in NAMES:
        pat=r'\b(?:wire|assign)\s+'+name+r'\s*=\s*(.*?);'
        matches=re.findall(pat,source,re.S)
        if len(matches)!=1:
            raise AssertionError(f'{name}: need unique assignment, found {len(matches)}')
        result[name]=matches[0].strip()
    return result

def to_sympy(name, rhs, memo):
    if name in memo: return memo[name]
    expr=rhs[name]
    expr=re.sub(r'state\s*==\s*S_TX', 'STATE_TX',expr)
    expr=re.sub(r'state\s*==\s*S_AERO', 'STATE_AERO',expr)
    expr=expr.replace('frame_shift[FRAME_BITS-1]','FRAME_BIT')
    # Inline cones recursively, parenthesizing every substitution.
    for dependency in NAMES:
        if dependency!=name and re.search(r'\b'+dependency+r'\b',expr):
            expr=re.sub(r'\b'+dependency+r'\b',
                        '('+str(to_sympy(dependency,rhs,memo))+')',expr)
    expr=expr.replace('&&',' & ').replace('||',' | ')
    expr=re.sub(r'!(?!=)', '~',expr)
    if re.search(r'[^a-zA-Z0-9_\s~&|()]',expr):
        raise ValueError(f'unhandled RTL expression for {name}: {expr}')
    symbols={x:Symbol(x) for x in set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*',expr))}
    result=sympify(expr,locals=symbols,evaluate=False)
    memo[name]=result
    return result

def verify(path):
    rhs=extract(Path(path).read_text())
    m={};s={k:to_sympy(k,rhs,m) for k in OUTPUTS}
    checks=0
    for out,cone in s.items():
        for bad in FAULTS:
            v=Symbol(bad)
            forbidden=Not(v) if bad in ('power_good','timing_alive','rst_n','w0_live','w1_live','local_mission_authorized') else v
            if satisfiable(And(cone,forbidden)) is not False:
                raise AssertionError(f'{out} can assert under forbidden condition: {bad}')
            checks+=1
        for flag in ('w0_seen','w1_seen'):
            if satisfiable(And(cone,Not(Symbol(flag)))) is not False:
                raise AssertionError(f'{out} asserts without {flag}')
            checks+=1
    # Same state value cannot be TX and AERO simultaneously.
    if satisfiable(And(s['tx_start'],s['aero_start'],
                       Not(And(Symbol('STATE_TX'),Symbol('STATE_AERO'))))) is not False:
        raise AssertionError('both start strobes possible under mutually exclusive state')
    checks+=1
    print(f'PASS emitted RTL combinational-cone SAT: {checks} forbidden-output queries')
    return checks

if __name__=='__main__':
    import sys
    verify(sys.argv[1] if len(sys.argv)>1 else 'build/wcm_reference_core.v')
