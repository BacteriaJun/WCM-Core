#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Record and check source revisions associated with the formal model review.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PIN=ROOT/'verification/formal/implementation_pins.json'
FILES=[
 'hardware/film/rtl/wcm_mission64_engine.v',
 'hardware/film/rtl/wcm_mission64_endpoint.v',
 'toolchain/hc/rtl/core_template.v',
 'toolchain/mission/missionc.py',
 'system/mission/wcm_mission64.c',
 'hardware/film/model/mission64_reference.py',
 'devices/virtual-node/virtual_device.c',
 'simulation/wcm_scenario.c',
 'verification/formal/prove.py',
]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--freeze',action='store_true',help='record reviewed source hashes for a release')
    args=a.parse_args()
    found={name:digest(ROOT/name) for name in FILES}
    if args.freeze:
        PIN.write_text(json.dumps({'kind':'reviewed-source-digests',
          'limitations':'Source identity for model review; implementation correspondence and hardware validation are tracked separately',
          'sha256':found},indent=2)+'\n')
        print('Source hashes recorded for model review');return 0
    if not PIN.exists():print('ERROR: missing reviewed source pin manifest');return 2
    recorded=json.loads(PIN.read_text())['sha256']
    if recorded!=found:
        for key in sorted(set(found)|set(recorded)):
            if found.get(key)!=recorded.get(key):print('FAIL changed source:',key)
        return 1
    print(f'PASS reviewed source identity: {len(found)} files match the review manifest')
    return 0
if __name__=='__main__':raise SystemExit(main())
