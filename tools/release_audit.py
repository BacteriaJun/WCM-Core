#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Check release-source completeness and formal-evidence hashes."""
from pathlib import Path
import argparse
import json
import hashlib
import sys
ROOT=Path(__file__).resolve().parents[1]
REQUIRED=[
 'LICENSE','NOTICE','SECURITY.md','CONTRIBUTING.md','README.md',
 'spec/WCM-SYSTEM-CONTRACT.md','docs/MISSION_64_V1.md',
 'docs/FORMAL_VERIFICATION.md','docs/RELEASE_SCOPE.md',
 'devices/virtual-node/virtual_device.c','system/cell/wcm_cell_r4.c',
 'system/mission/wcm_mission64.c','system/optical/wcm_optical.c',
 'system/energy/wcm_power_model.c',
 'hardware/film/rtl/wcm_mission64_engine.v',
 'hardware/film/rtl/wcm_mission64_endpoint.v',
 'toolchain/mission/missionc.py','toolchain/hc/src/compiler.py',
 'simulation/wcm_scenario.c','verification/formal/prove.py',
 'verification/reports/formal_results.json',
 '.github/workflows/ci.yml','tests/test_lifecycle.py',
 'tests/test_c_mission_differential.py'
]
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args()
    missing=[x for x in REQUIRED if not (ROOT/x).is_file()]
    results=json.loads((ROOT/'verification/reports/formal_results.json').read_text()) if not missing else {}
    issues=[]
    if missing:issues.extend('missing '+x for x in missing)
    if not missing:
        if not results.get('passed'):issues.append('formal evidence not passing')
        if len(results.get('obligations',[]))<32:issues.append('less than 32 formal obligations')
        for e in results.get('obligations',[]):
            path=ROOT/'verification/formal/smt2'/(e['name']+'.smt2')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=e['query_sha256']:
                issues.append('SMT file mismatch '+e['name'])
    source=(ROOT/'devices/virtual-node/virtual_device.c').read_text()
    if 'wcm_frame_decode(' in source:issues.append('virtual endpoint links station receiver')
    hw=(ROOT/'hardware/film/rtl/wcm_mission64_endpoint.v').read_text()
    if 'station_command' in hw or 'acknowledgment_input' in hw:issues.append('unexpected downlink input')
    if issues:
        for issue in issues:print('AUDIT FAIL',issue,file=sys.stderr)
        return 1
    print(f'RELEASE SOURCE AUDIT PASS: {len(REQUIRED)} required paths; '+
          f'{len(results["obligations"])} matched formal evidence queries')
    print('Separate checks: HDL execution, RTL correspondence and target hardware validation')
    return 0
if __name__=='__main__':raise SystemExit(main())
