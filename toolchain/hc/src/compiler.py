# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Validate fixed-profile hardware contracts and generate specialized Verilog.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
import tomllib
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARD_REQUIREMENTS = (
    'independent_time_watchdog', 'qualified_witness_liveness',
    'capture_after_cutover', 'qualified_settlement',
    'qualified_energy_sampling', 'qualified_local_policy_authorization',
    'supply_brownout_interlock',
)
PORTS = [
    'clk','rst_n','power_good','hard_fault','timing_alive',
    'tx_deadline_ok','aero_deadline_ok','world_break',
    'observation_dirty_latched','observation_dirty_ack','capture_w0',
    'capture_w1','capture_after_cutover','w0_live','w1_live',
    'energy_sample','energy_after_settlement','tx_energy_ok',
    'aero_energy_ok','req_tx','req_aero','local_mission_authorized','tx_frame',
    'symbol_done_tick','aero_done_pulse','aero_done_auth',
    'settle_pulse','settle_after_quarantine','settled_ok',
    'optical_reflect','tx_active','aero_start','tx_start',
    'actuator_authority','quarantined','state_debug',
]

class SpecificationError(ValueError):
    pass

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def require_keys(obj, required, optional=(), label='object'):
    if not isinstance(obj, dict):
        raise SpecificationError(f'{label} must be a table')
    missing = set(required) - set(obj)
    extra = set(obj) - set(required) - set(optional)
    if missing or extra:
        raise SpecificationError(f'{label} invalid keys: missing={sorted(missing)}, unknown={sorted(extra)}')

def integer(v, label, low, high):
    if type(v) is not int or not low <= v <= high:
        raise SpecificationError(f'{label}: expected integer in [{low}, {high}]')
    return v

def validate(data):
    require_keys(data, ('schema','name','frame_bits','witness','geometry','power','optical','aerodynamics','transactions','trust_boundary'),label='spec')
    if data['schema'] != 1 or type(data['schema']) is not int:
        raise SpecificationError('schema 1 required')
    name = data['name']
    if type(name) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,31}', name):
        raise SpecificationError('name must be lowercase Verilog identifier up to 32 characters')
    bits = integer(data['frame_bits'],'frame_bits',2,32)
    ws = data['witness']
    if not isinstance(ws,list) or len(ws)!=2:
        raise SpecificationError('P1 requires exactly 2 witness declarations')
    for i,w in enumerate(ws):
        require_keys(w, ('name','max_age_us'),label=f'witness[{i}]')
        if type(w['name']) is not str or not re.fullmatch('[a-z][a-z0-9_]{0,31}',w['name']):
            raise SpecificationError('invalid witness name')
        integer(w['max_age_us'],f'witness[{i}].max_age_us',1,2**31-1)
    if ws[0]['name']==ws[1]['name']:
        raise SpecificationError('witness identifiers must be unique')
    geom=data['geometry']; require_keys(geom,('max_span_um','capacitor_area_fraction_ppm'),label='geometry')
    span=integer(geom['max_span_um'],'max_span_um',1,1000)
    fraction=integer(geom['capacitor_area_fraction_ppm'],'capacitor_area_fraction_ppm',1,1000000)
    power=data['power']; require_keys(power,('capacitance_nF','v_high_mV','v_cutoff_mV','efficiency_ppm','reserve_nJ'),label='power')
    c=integer(power['capacitance_nF'],'capacitance_nF',1,10**10)
    hi=integer(power['v_high_mV'],'v_high_mV',1,100000)
    lo=integer(power['v_cutoff_mV'],'v_cutoff_mV',1,99999)
    eta=integer(power['efficiency_ppm'],'efficiency_ppm',1,1000000)
    reserve=integer(power['reserve_nJ'],'reserve_nJ',0,10**12)
    if hi <= lo: raise SpecificationError('v_high must exceed v_cutoff')
    available=Fraction(c*(hi**2-lo**2)*eta,2*10**12)
    optical=data['optical']; require_keys(optical,('symbol_period_us','effect_latency_us','startup_energy_nJ','per_symbol_energy_nJ'),label='optical')
    for key in ('symbol_period_us','effect_latency_us','startup_energy_nJ','per_symbol_energy_nJ'):
        integer(optical[key], 'optical.'+key, 0 if 'energy' in key else 1, 2**31-1)
    aero=data['aerodynamics']; require_keys(aero,('effect_latency_us','actuation_energy_nJ'),label='aerodynamics')
    integer(aero['effect_latency_us'],'aerodynamics.effect_latency_us',1,2**31-1)
    integer(aero['actuation_energy_nJ'],'aerodynamics.actuation_energy_nJ',1,2**31-1)
    txs=data['transactions']; require_keys(txs,('tx','aero'),label='transactions')
    if not isinstance(data['trust_boundary'],dict): raise SpecificationError('trust_boundary must be a table')
    require_keys(data['trust_boundary'],HARD_REQUIREMENTS,label='trust_boundary')
    for requirement in HARD_REQUIREMENTS:
        if data['trust_boundary'][requirement] is not True:
            raise SpecificationError('required externally-qualified hardware contract: '+requirement)
    if all(not txs[t].get('enabled',False) for t in ('tx','aero')):
        raise SpecificationError('at least one transaction type must be enabled')
    limits={}
    for t in ('tx','aero'):
        x=txs[t];require_keys(x,('enabled','worst_case_nJ','deadline_us'),label=t)
        if type(x['enabled']) is not bool: raise SpecificationError(t+'.enabled must be bool')
        cost=integer(x['worst_case_nJ'],t+'.worst_case_nJ',1,10**12)
        deadline=integer(x['deadline_us'],t+'.deadline_us',1,2**31-1)
        if x['enabled'] and t=='tx' and (cost < optical['startup_energy_nJ'] + bits*optical['per_symbol_energy_nJ']):
            raise SpecificationError('tx energy budget below declared physical symbol cost')
        if x['enabled'] and t=='aero' and cost < aero['actuation_energy_nJ']:
            raise SpecificationError('aero energy budget below declared physical actuation cost')
        if x['enabled'] and t=='tx' and deadline < bits*optical['symbol_period_us'] + optical['effect_latency_us']:
            raise SpecificationError('optical frame cannot finish before specified deadline')
        if x['enabled'] and t=='aero' and deadline < aero['effect_latency_us']:
            raise SpecificationError('aerodynamic effect cannot finish before specified deadline')
        if x['enabled'] and cost+reserve > available:
            raise SpecificationError(f'{t}: energy budget infeasible; need {cost+reserve} nJ, calculated conservative capacity {float(available):.3f} nJ')
        if x['enabled'] and deadline > min(w['max_age_us'] for w in ws):
            raise SpecificationError(f'{t}: deadline exceeds shortest witness age; conservative no-hidden-renewal P1 rule')
        limits[t]={'enabled':x['enabled'],'worst_case_nJ':cost,'deadline_us':deadline}
    return available, limits

def render_ports(bits):
    lines=[]
    outputs = {'optical_reflect','tx_active','aero_start','tx_start','actuator_authority','quarantined','state_debug','observation_dirty_ack'}
    for p in PORTS:
        d='output wire' if p in outputs else 'input  wire'
        wd=f'[{bits-1}:0]' if p=='tx_frame' else ('[2:0]' if p=='state_debug' else '')
        lines.append(f'    {d} {wd:>7} {p}')
    return ',\n'.join(lines)

def generate(data, source_path, outdir):
    capacity,tx=validate(data)
    outdir=Path(outdir)
    outdir.mkdir(parents=True,exist_ok=True)
    bits=data['frame_bits']; name=data['name']; top='wcm_'+name
    core_src=(ROOT/'rtl/core_template.v').read_text()
    # Specialize the fixed-function reference state machine; strengthen
    # asynchronous invalidation to avoid glitch-resurrection of stale authority.
    core_src=core_src.replace('module wcm_film_p1 #(', 'module wcm_hc_fixed_core #(')
    needle='wire reset_domain_ok = rst_n && power_good && !hard_fault && timing_alive;'
    replacement=('wire reset_domain_ok = rst_n && power_good && !hard_fault &&\n'
       '                           timing_alive && !world_break &&\n'
       '                           w0_live && w1_live && local_mission_authorized &&\n'
       '                           !observation_dirty_latched;')
    if core_src.count(needle)!=1: raise RuntimeError('review upstream template; reset interface changed')
    core_src=core_src.replace(needle,replacement)
    # If one function is disallowed by spec, hardwire it to disabled at the wrapper.
    disabled={'tx':not tx['tx']['enabled'],'aero':not tx['aero']['enabled']}
    connections=[]
    for p in PORTS:
        expr=p
        if p in ('req_tx','tx_energy_ok') and disabled['tx']: expr="1'b0"
        if p in ('req_aero','aero_energy_ok') and disabled['aero']: expr="1'b0"
        connections.append(f'        .{p}({expr})')
    wrapper=f'''// Generated by WCM-HC P2; contract SHA-256 {sha(source_path.read_bytes())}.
// Inputs follow the timing, evidence and settlement frontend requirements
// in spec/WCM-SYSTEM-CONTRACT.md.
module {top} (\n{render_ports(bits)}\n);
    wcm_hc_fixed_core #(.FRAME_BITS({bits})) core_instance (\n{',\n'.join(connections)}\n    );
endmodule
'''
    output=(outdir/(top+'.v'))
    output.write_text(core_src+'\n'+wrapper)
    tb=(ROOT/'tb/tb_template.v').read_text()
    tb=tb.replace('tb_wcm_film_p1',f'tb_{top}').replace('wcm_film_p1 #(.FRAME_BITS(8)) dut (.*);',f'{top} dut (.*);')
    if bits!=8:
        # This bench is currently only qualified for the 8-bit demo; do not silently issue invalid tests.
        tb='// No automatically adapted symbol testbench for frame_bits != 8.\n'
    if disabled['tx'] or disabled['aero']:
        tb='// Reference testbench disabled when a transaction class is absent.\n'
    (outdir/(f'tb_{top}.v')).write_text(tb)
    count_bits=(bits+1).bit_length() - 1
    if (1<<count_bits)<bits+1: count_bits+=1
    registers=3+2+1+bits+count_bits+2
    manifest={
        'stage':'P2-research-prototype','schema':1,'top':top,
        'spec_sha256':sha(source_path.read_bytes()),'rtl_sha256':sha(output.read_bytes()),
        'source_baseline':'toolchain/hc/rtl/core_template.v (specialized async invalidation)',
        'frame_bits':bits,'witness_names':[w['name'] for w in data['witness']],
        'stated_witness_max_age_us':[w['max_age_us'] for w in data['witness']],
        'calculated_ideal_conservative_available_energy_nJ':float(capacity),
        'energy_model':'reference C*(Vhi^2-Vlo^2)/2 estimate using declared efficiency',
        'geometry_outer_span_um':data['geometry']['max_span_um'],
        'capacitor_reserved_area_mm2':data['geometry']['max_span_um']**2/1000000*data['geometry']['capacitor_area_fraction_ppm']/1000000,
        'required_capacitance_density_nF_per_mm2':data['power']['capacitance_nF']/(data['geometry']['max_span_um']**2/1000000*data['geometry']['capacitor_area_fraction_ppm']/1000000),
        'capacitance_density_qualification':'pending target-process selection and validation',
        'transactions':tx,
        'optical_declared_min_duration_us':bits*data['optical']['symbol_period_us']+data['optical']['effect_latency_us'],
        'optical_declared_min_energy_nJ':data['optical']['startup_energy_nJ']+bits*data['optical']['per_symbol_energy_nJ'],
        'aero_declared_min_duration_us':data['aerodynamics']['effect_latency_us'],
        'declared_sequential_bits_without_frontend_or_driver':registers,
        'electrical_or_clock_domain_qualification':'pending target validation',
        'external_contracts':'frontend requirements for target integration',
        'dirty_latched_protocol':'sticky async event held until QUARANTINE acknowledgment; target defines capture pulse width',
        'rtl_simulation':'run separately with an HDL simulator',
        'technology_mapping':'run separately with the selected target technology library',
    }
    (outdir/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return manifest

def main():
    p=argparse.ArgumentParser(description='WCM-HC P1 control-spec -> specialized RTL')
    p.add_argument('spec',type=Path);p.add_argument('--out',type=Path,default=ROOT/'build')
    a=p.parse_args()
    try:
        with a.spec.open('rb') as f: data=tomllib.load(f)
        print(json.dumps(generate(data,a.spec,a.out),indent=2))
    except (SpecificationError, ValueError) as e:
        print('WCM-HC: REJECT: '+str(e),file=sys.stderr)
        raise SystemExit(2)
if __name__=='__main__': main()
