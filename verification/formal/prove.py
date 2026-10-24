#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Generate and evaluate finite synchronous specification queries using Z3.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import pathlib
import shutil
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
SMT_DIR = ROOT / 'verification' / 'formal' / 'smt2'
REPORT = ROOT / 'verification' / 'reports' / 'formal_results.json'


def bv(v: int, width: int) -> str:
    return f'(_ bv{v} {width})'


def ext(hi: int, lo: int, source: str='image') -> str:
    return f'((_ extract {hi} {lo}) {source})'


def AND(*xs: str) -> str:
    return f'(and {" ".join(xs)})'


def OR(*xs: str) -> str:
    return f'(or {" ".join(xs)})'


def NOT(x: str) -> str:
    return f'(not {x})'


def eq(x: str, y: str) -> str:
    return f'(= {x} {y})'


def crc_rtl(prefix: str, img: str) -> tuple[list[str], str]:
    """Reference encoding of RTL's MSB-first 56-round recurrence."""
    terms=[f'(define-fun {prefix}0 () (_ BitVec 8) {bv(0,8)})']
    for i, b in enumerate(range(63,7,-1)):
        old=f'{prefix}{i}'
        feedback=f'(xor (= {ext(7,7,old)} #b1) (= {ext(b,b,img)} #b1))'
        expression=f'(bvxor (bvshl {old} {bv(1,8)}) (ite {feedback} {bv(7,8)} {bv(0,8)}))'
        terms.append(f'(define-fun {prefix}{i+1} () (_ BitVec 8) {expression})')
    return terms, f'{prefix}56'


def crc_bytewise(prefix: str, img: str) -> tuple[list[str],str]:
    """Independently encode missionc.py's 7-byte XOR-then-8-shifts CRC."""
    terms=[f'(define-fun {prefix}0 () (_ BitVec 8) {bv(0,8)})']
    n=0
    for hi in range(63, 7, -8):
        x=f'(bvxor {prefix}{n} {ext(hi,hi-7,img)})'
        n+=1
        terms.append(f'(define-fun {prefix}{n} () (_ BitVec 8) {x})')
        for _ in range(8):
            x=f'(bvxor (bvshl {prefix}{n} {bv(1,8)}) (ite (= {ext(7,7,prefix+str(n))} #b1) {bv(7,8)} {bv(0,8)}))'
            n+=1
            terms.append(f'(define-fun {prefix}{n} () (_ BitVec 8) {x})')
    return terms, f'{prefix}{n}'


def mission_fields(img: str) -> str:
    ver=ext(63,60,img);task=ext(59,56,img);sens=ext(55,52,img)
    threshold=ext(51,46,img);sample=ext(45,40,img);period=ext(39,34,img)
    maxrep=ext(33,28,img);flags=ext(15,8,img)
    return AND(
        eq(ver,bv(1,4)),OR(AND(eq(task,bv(1,4)),NOT(eq(threshold,bv(0,6)))),
                             AND(eq(task,bv(2,4)),eq(threshold,bv(0,6)))),
        eq(sens,bv(1,4)),NOT(eq(sample,bv(0,6))),NOT(eq(period,bv(0,6))),
        NOT(eq(maxrep,bv(0,6))),eq(flags,bv(0,8)))


def header() -> list[str]:
    return ['(set-logic QF_BV)', '(set-option :produce-models true)']


def crc_equiv() -> str:
    s=header()+['(declare-const image (_ BitVec 64))']
    aa,a=crc_rtl('r', 'image');bb,b=crc_bytewise('c','image')
    s+=aa+bb+[f'(assert (not (= {a} {b})))','(check-sat)']
    return '\n'.join(s)+'\n'


def format_equiv() -> str:
    s=header()+['(declare-const image (_ BitVec 64))']
    aa,a=crc_rtl('r','image');bb,b=crc_bytewise('c','image');s+=aa+bb
    s += [f'(define-fun rtl_ok () Bool {AND(mission_fields("image"), eq(a,ext(7,0,"image")))})',
          f'(define-fun compiler_ok () Bool {AND(mission_fields("image"), eq(b,ext(7,0,"image")))})',
          '(assert (xor rtl_ok compiler_ok))','(check-sat)']
    return '\n'.join(s)+'\n'


def single_bit_detection() -> str:
    s=header()+['(declare-const image (_ BitVec 64))','(declare-const pos (_ BitVec 6))',
        f'(define-fun changed () (_ BitVec 64) (bvxor image (bvshl {bv(1,64)} ((_ zero_extend 58) pos))))']
    aa,a=crc_rtl('original','image');bb,b=crc_rtl('modified','changed');s+=aa+bb
    s += [f'(assert {AND(mission_fields("image"),eq(a,ext(7,0,"image")))})',
          f'(assert {AND(mission_fields("changed"),eq(b,ext(7,0,"changed")))})',
          '(check-sat)']
    return '\n'.join(s)+'\n'


# Policy states mirror wcm_mission64_engine.v. Formal state abstractions
# deliberately hide timebase/sampling fields and treat 'due' as arbitrary;
# the timebase and sensor validity properties are NOT proven by this model.
S_LOAD,S_ACTIVE,S_REQUEST,S_INFLIGHT,S_PASSIVE,S_FAILED=[bv(i,3) for i in range(6)]

def state_machine(mutate: bool=False) -> list[str]:
    s=header()+[
       '(declare-const state (_ BitVec 3))','(declare-const state_next (_ BitVec 3))',
       '(declare-const reports (_ BitVec 6))','(declare-const reports_next (_ BitVec 6))',
       '(declare-const maximum (_ BitVec 6))',
       '(declare-const reset_ok Bool)','(declare-const verified Bool)',
       '(declare-const invalid Bool)','(declare-const abort Bool)',
       '(declare-const due Bool)','(declare-const accept Bool)',
       '(declare-const started Bool)','(declare-const full_frame_closed Bool)',
       '(declare-const quarantined Bool)','(declare-const phy_settled_this_frame Bool)',
       '(declare-const settle_pulse Bool)','(declare-const settle_after_quarantine Bool)',
       '(declare-const settled_ok Bool)','(declare-const dirty Bool)',
       '(declare-const world_break Bool)',
    ]
    commit=AND('started','full_frame_closed','quarantined','phy_settled_this_frame',
               'settle_pulse','settle_after_quarantine','settled_ok','reset_ok',
               NOT('dirty'),NOT('world_break'))
    # The mutation deliberately bypasses PHY settle on report increment, and
    # should be caught by the COMMIT-ONLY proof obligation.
    s += [f'(define-fun commit () Bool {commit})',
          f'(define-fun complete () Bool {"accept" if mutate else "commit"})']
    report_update=AND('reset_ok',NOT(OR('invalid','abort')),eq('state',S_INFLIGHT),'complete')
    s += [f'(define-fun count_step () Bool {report_update})',
          f'(define-fun inc () (_ BitVec 6) (bvadd reports {bv(1,6)}))']
    next_state=f'''(ite (not reset_ok) {S_LOAD}
      (ite (or invalid abort) {S_FAILED}
        (ite (and (= state {S_LOAD}) verified) {S_ACTIVE}
          (ite (and (= state {S_ACTIVE}) due) {S_REQUEST}
            (ite (and (= state {S_REQUEST}) accept) {S_INFLIGHT}
              (ite count_step (ite (bvuge inc maximum) {S_PASSIVE} {S_ACTIVE}) state))))))'''
    s += [f'(assert (= state_next {next_state}))',
          f'(assert (= reports_next (ite (not reset_ok) {bv(0,6)} (ite count_step inc reports))))',
          f'(define-fun inv () Bool {AND(
              OR(*[eq("state",bv(i,3)) for i in range(6)]),
              NOT(eq("maximum",bv(0,6))),
              "(bvule reports maximum)",
              OR(NOT(OR(eq("state",S_ACTIVE),eq("state",S_REQUEST),eq("state",S_INFLIGHT))),"(bvult reports maximum)"),
              OR(NOT(eq("state",S_LOAD)),eq("reports",bv(0,6))),
              OR(NOT(eq("state",S_PASSIVE)),eq("reports","maximum")),
          )})',
          f'(define-fun inv_next () Bool {AND(
              OR(*[eq("state_next",bv(i,3)) for i in range(6)]),
              NOT(eq("maximum",bv(0,6))),
              "(bvule reports_next maximum)",
              OR(NOT(OR(eq("state_next",S_ACTIVE),eq("state_next",S_REQUEST),eq("state_next",S_INFLIGHT))),"(bvult reports_next maximum)"),
              OR(NOT(eq("state_next",S_LOAD)),eq("reports_next",bv(0,6))),
              OR(NOT(eq("state_next",S_PASSIVE)),eq("reports_next","maximum")),
          )})',
          f'(define-fun request () Bool {AND("reset_ok","verified",NOT("invalid"),eq("state",S_REQUEST))})',
          ]
    return s


def policy_obligations() -> dict[str,str]:
    base=state_machine()
    pre='(assert inv)'
    checks={
      'POLICY_INIT':'',
      'POLICY_INDUCTIVE': '(assert (not inv_next))',
      'NO_INVALID_REQUEST':'(assert request)(assert (or (not reset_ok) invalid (not verified)))',
      'REPORT_ONLY_AFTER_COMMIT':'(assert (not (= reports_next reports)))(assert reset_ok)(assert (not commit))',
      'REPORT_NOT_IN_NONINFLIGHT':'(assert (not (= reports_next reports)))(assert (not (= state '+S_INFLIGHT+')))(assert reset_ok)',
      'REPORT_NEVER_EXCEEDS_MAX':'(assert (bvugt reports_next maximum))',
      'ABORT_NEVER_INCREMENTS':'(assert abort)(assert reset_ok)(assert (not (= reports_next reports)))',
      'FAILURE_STICKY':'(assert (= state '+S_FAILED+'))(assert reset_ok)(assert (not (= state_next '+S_FAILED+')))',
      'PASSIVE_STICKY_UNLESS_FAULT':'(assert (= state '+S_PASSIVE+'))(assert reset_ok)(assert (not abort))(assert (not invalid))(assert (not (= state_next '+S_PASSIVE+')))',
      'PASSIVE_FAULT_TRANSITIONS_TO_FAILED':'(assert (= state '+S_PASSIVE+'))(assert reset_ok)(assert (or abort invalid))(assert (not (= state_next '+S_FAILED+')))',
      'RESET_CLEARS_STATE':'(assert (not reset_ok))(assert (or (not (= state_next '+S_LOAD+')) (not (= reports_next '+bv(0,6)+'))))',
      'BAD_MISSION_NO_REQUEST':'(assert invalid)(assert request)',
      'NO_COUNT_ON_QUARANTINE_ALONE':'(assert quarantined)(assert (not phy_settled_this_frame))(assert reset_ok)(assert (not (= reports_next reports)))',
      'NO_COUNT_ON_DIRTY_EVIDENCE':'(assert dirty)(assert reset_ok)(assert (not (= reports_next reports)))',
      'NO_COUNT_ON_WORLD_BREAK':'(assert world_break)(assert reset_ok)(assert (not (= reports_next reports)))',
    }
    # POLICY_INIT checks that the *initial* state satisfies invariant; direct negated-init
    # conjunct query is not an inductive step.
    checks['POLICY_INIT']='(assert (= state '+S_LOAD+'))(assert (= reports '+bv(0,6)+'))(assert (not (= maximum '+bv(0,6)+')))(assert (not inv))'
    return {name:'\n'.join(base+[pre if name!='POLICY_INIT' else '; no inv premise']+[body,'(check-sat)'])+'\n' for name,body in checks.items()}


def loader_obligations() -> dict[str,str]:
    """One-step induction for the exact serial-loader state recurrence.

    candidate_ok is unconstrained: these obligations do NOT prove physical NVM
    sampling or CRC function. CRC equivalence is proved independently above.
    """
    base=header()+[
      '(declare-const count (_ BitVec 6))','(declare-const count_next (_ BitVec 6))',
      '(declare-const valid BitVec)', # placeholder, replaced below
      '(declare-const verified Bool)','(declare-const verified_next Bool)',
      '(declare-const invalid Bool)','(declare-const invalid_next Bool)',
      '(declare-const reset_ok Bool)','(declare-const bit_valid Bool)',
      '(declare-const candidate_ok Bool)',
    ]
    base=[line for line in base if '(declare-const valid BitVec)' not in line]
    final=eq('count',bv(63,6))
    base.extend([
      f'(define-fun last_bit () Bool {final})',
      f'(define-fun incoming () Bool {AND("reset_ok","bit_valid",NOT("invalid"))})',
      f'(assert (= count_next (ite (not reset_ok) {bv(0,6)} (ite (and incoming (not verified) (not last_bit)) (bvadd count {bv(1,6)}) count))))',
      f'(assert (= verified_next (ite (not reset_ok) false (ite (and incoming verified) false (ite (and incoming last_bit) candidate_ok verified)))))',
      f'(assert (= invalid_next (ite (not reset_ok) false (ite (and incoming verified) true (ite (and incoming last_bit) (not candidate_ok) invalid)))))',
      f'(define-fun inv () Bool {AND(
          OR(NOT("verified"),final), OR(NOT("invalid"),final),
          NOT(AND("verified","invalid")))})',
      f'(define-fun inv_next () Bool {AND(
          OR(NOT("verified_next"),eq("count_next",bv(63,6))),
          OR(NOT("invalid_next"),eq("count_next",bv(63,6))),
          NOT(AND("verified_next","invalid_next")))})',
    ])
    cases={
      'LOADER_INIT':'(assert (= count '+bv(0,6)+'))(assert (not verified))(assert (not invalid))(assert (not inv))',
      'LOADER_INDUCTIVE':'(assert (not inv_next))',
      'LOADER_NO_VERIFY_BEFORE_64_BITS':'(assert verified_next)(assert (not (= count_next '+bv(63,6)+')))',
      'LOADER_NO_COUNT_WRAP':'(assert (= count '+bv(63,6)+'))(assert (not (= count_next '+bv(63,6)+')))(assert reset_ok)',
      'LOADER_BIT_ABSENCE_HOLDS':'(assert reset_ok)(assert (not bit_valid))(assert (or (not (= count_next count)) (not (= verified_next verified)) (not (= invalid_next invalid))))',
      'LOADER_BAD_STICKY':'(assert invalid)(assert reset_ok)(assert (not invalid_next))',
      'LOADER_EXTRA_BIT_INVALIDATES':'(assert reset_ok)(assert verified)(assert bit_valid)(assert (or verified_next (not invalid_next)))',
      'LOADER_CRC_FAIL_NEVER_ENABLES':'(assert reset_ok)(assert bit_valid)(assert (not verified))(assert last_bit)(assert (not candidate_ok))(assert verified_next)',
      'LOADER_RESET_CLEARS':'(assert (not reset_ok))(assert (or (not (= count_next '+bv(0,6)+')) verified_next invalid_next))',
    }
    return {name:'\n'.join(base+(['(assert inv)'] if name!='LOADER_INIT' else [])+[body,'(check-sat)'])+'\n' for name,body in cases.items()}



def timer_obligations() -> dict[str,str]:
    # Synchronous timebase fail-closed specification obligations.

    # Matches the intended priority in wcm_mission64_engine.v but does not
    # establish an extracted RTL equivalence relation. All 16-bit elapsed values
    # and all combinations of handshake/fault booleans are universally checked.
    base=header()+[
        '(declare-const state (_ BitVec 3))',
        '(declare-const state_next (_ BitVec 3))',
        '(declare-const elapsed (_ BitVec 16))',
        '(declare-const elapsed_next (_ BitVec 16))',
        '(declare-const reports (_ BitVec 6))',
        '(declare-const reports_next (_ BitVec 6))',
        '(declare-const tick Bool)',
        '(declare-const due Bool)',
        '(declare-const accept Bool)',
        '(declare-const complete Bool)',
        '(declare-const abort Bool)',
        '(declare-const reset_ok Bool)',
    ]
    active=OR(eq('state',S_ACTIVE),eq('state',S_REQUEST),eq('state',S_INFLIGHT))
    overflow=AND('tick',eq('elapsed',bv(65535,16)))
    transition=f'''(ite (not reset_ok) {S_LOAD}
      (ite abort {S_FAILED}
        (ite (and {active} {overflow}) {S_FAILED}
          (ite (and (= state {S_ACTIVE}) due) {S_REQUEST}
            (ite (and (= state {S_REQUEST}) accept) {S_INFLIGHT}
              (ite (and (= state {S_INFLIGHT}) complete) {S_ACTIVE} state))))))'''
    base.extend([
        f'(define-fun overflow () Bool {overflow})',
        f'(define-fun active () Bool {active})',
        f'(assert (= state_next {transition}))',
        f'(assert (= elapsed_next (ite (not reset_ok) {bv(0,16)} (ite (and active tick (not overflow)) (bvadd elapsed {bv(1,16)}) elapsed))))',
        f'(assert (= reports_next (ite (not reset_ok) {bv(0,6)} (ite (and active (not abort) (not overflow) (= state {S_INFLIGHT}) complete) (bvadd reports {bv(1,6)}) reports))))',
    ])
    tests={
        'TIME_OVERFLOW_TO_FAILED':'(assert reset_ok)(assert (not abort))(assert active)(assert overflow)(assert (not (= state_next '+S_FAILED+')))',
        'TIME_NO_WRAP_AT_LIMIT':'(assert reset_ok)(assert active)(assert overflow)(assert (not (= elapsed_next elapsed)))',
        'TIME_OVERFLOW_NO_REPORT':'(assert reset_ok)(assert active)(assert overflow)(assert (not (= reports_next reports)))',
        'TIME_RESET_ZERO':'(assert (not reset_ok))(assert (or (not (= elapsed_next '+bv(0,16)+')) (not (= reports_next '+bv(0,6)+'))))',
    }
    return {n:'\n'.join(base+[b,'(check-sat)'])+'\n' for n,b in tests.items()}

def mutation_query() -> str:
    return '\n'.join(state_machine(mutate=True)+['(assert inv)',
            '(assert (not (= reports_next reports)))','(assert reset_ok)',
            '(assert (not commit))','(check-sat)'])+'\n'


def load_z3():
    names=['libz3.so.4','libz3.so','libz3.dylib','libz3.dll']
    for name in names:
        try:
            z=ctypes.CDLL(name)
            z.Z3_mk_config.restype=ctypes.c_void_p
            z.Z3_mk_context.argtypes=[ctypes.c_void_p];z.Z3_mk_context.restype=ctypes.c_void_p
            z.Z3_eval_smtlib2_string.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            z.Z3_eval_smtlib2_string.restype=ctypes.c_char_p
            z.Z3_del_context.argtypes=[ctypes.c_void_p]
            z.Z3_del_config.argtypes=[ctypes.c_void_p]
            return z
        except OSError:pass
    raise RuntimeError('Z3 solver not installed (need z3 CLI or libz3 shared library)')


def solve(code: str) -> tuple[str,str]:
    if shutil.which('z3'):
        p=subprocess.run(['z3','-in','-smt2'],input=code,text=True,
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        if p.returncode:return 'error',p.stdout+'\n'+p.stderr
        out=p.stdout
    else:
        z=load_z3();cfg=z.Z3_mk_config();ctx=z.Z3_mk_context(cfg)
        try:out=z.Z3_eval_smtlib2_string(ctx,code.encode()).decode()
        finally:z.Z3_del_context(ctx);z.Z3_del_config(cfg)
    line=out.splitlines()[0].strip() if out.splitlines() else 'error'
    return (line if line in ('sat','unsat','unknown') else 'error'),out


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=pathlib.Path,default=REPORT)
    args=p.parse_args()
    SMT_DIR.mkdir(parents=True,exist_ok=True);args.report.parent.mkdir(parents=True,exist_ok=True)
    obligations={
       'CRC_RTL_BYTEWISE_EQUIV':crc_equiv(),
       'MISSION64_ACCEPTANCE_EQUIV':format_equiv(),
       'MISSION64_ANY_SINGLE_BIT_DETECTED':single_bit_detection(),
       **policy_obligations(),
       **loader_obligations(),
       **timer_obligations(),
       'MUTATION_MISSING_SETTLEMENT_IS_DETECTED':mutation_query(),
    }
    results=[];passed=True
    for name,src in obligations.items():
        filename=SMT_DIR/(name+'.smt2');filename.write_text(src,encoding='utf-8')
        start=time.monotonic();result,out=solve(src);elapsed=round(time.monotonic()-start,3)
        expected='sat' if name.startswith('MUTATION_') else 'unsat'
        ok=result==expected and '(error ' not in out
        if result=='sat':
            # A model is requested *only* for satisfiable queries. libZ3 can
            # terminate a process when get-model follows UNSAT.
            _status, details = solve(src.replace('(check-sat)', '(check-sat)\n(get-model)'))
            if _status=='sat' and '(error ' not in details:out=details
        passed=passed and ok
        results.append({'name':name,'solver_result':result,'expected':expected,
            'pass':ok,'duration_s':elapsed,'query_sha256':hashlib.sha256(src.encode()).hexdigest(),
            'model_excerpt':out[:2200] if result=='sat' else None})
        print(f'{"PASS" if ok else "FAIL"} {name}: {result} (expected {expected}, {elapsed}s)',flush=True)
    report={'release':'v1.0.0','kind':'finite-SMT-specification-proof',
        'important_limit':'Symbolic proofs cover specified Mission-64 predicates and synchronous abstract policy transition only; no RTL sequential equivalence or physical hardware qualification',
        'solver': 'Z3', 'passed':passed,'obligations':results}
    args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'REPORT={args.report}; SUMMARY {sum(x["pass"] for x in results)}/{len(results)}')
    return 0 if passed else 1

if __name__=='__main__':raise SystemExit(main())
