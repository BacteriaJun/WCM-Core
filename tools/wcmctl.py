#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""WCM-Core image tools for the Linux virtual target and generated RTL sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
VIRTUAL_ID = "virtual-node"
FILM_ID = "film-reference"
DEVICES = (VIRTUAL_ID, FILM_ID)

class ReleaseError(Exception):
    pass

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(128 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def device_info(device: str) -> dict:
    if device not in DEVICES:
        raise ReleaseError(f"unknown target {device!r}; supported: {', '.join(DEVICES)}")
    with (ROOT / 'devices' / device / 'device.toml').open('rb') as f:
        info = tomllib.load(f)
    if info.get('schema') != 1 or info.get('id') != device:
        raise ReleaseError('invalid device descriptor')
    return info

def manifest_payload(device: str, info: dict, artifacts: list[str]) -> dict:
    return {
        'schema': 1, 'system': 'WCM-Core', 'release': VERSION,
        'device': device, 'kind': info['kind'], 'image_kind': info['image_kind'],
        'status': info['status'], 'physical_hardware': info['physical_hardware'],
        'deployable': info['deployable'], 'contract': 'spec/WCM-SYSTEM-CONTRACT.md',
        'hardware_qualified': False, 'cryptographically_signed': False,
        'build_host_arch': platform.machine() if device == VIRTUAL_ID else None,
        'build_host_os': sys.platform if device == VIRTUAL_ID else None,
        'artifacts': artifacts,
    }

def write_manifest(bundle: Path, meta: dict) -> None:
    recorded = {}
    for rel in meta['artifacts']:
        path = bundle / rel
        if not path.is_file() or path.is_symlink():
            raise ReleaseError('missing or symlink artifact: ' + rel)
        recorded[rel] = hash_file(path)
    meta['sha256'] = recorded
    (bundle / 'manifest.json').write_text(json.dumps(meta, indent=2, sort_keys=True) + '\n')

def inside(bundle: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute() or any(part in ('..','.') for part in rel_path.parts):
        raise ReleaseError('unsafe artifact path: ' + rel)
    dest = (bundle / rel_path).resolve(strict=False)
    if not dest.is_relative_to(bundle.resolve()):
        raise ReleaseError('artifact escapes image root')
    return dest

def verify_bundle(bundle: Path) -> dict:
    manifest = bundle / 'manifest.json'
    if not manifest.is_file() or manifest.is_symlink():
        raise ReleaseError('missing manifest.json')
    meta = json.loads(manifest.read_text())
    if (meta.get('schema') != 1 or meta.get('system') != 'WCM-Core'
            or meta.get('device') not in DEVICES
            or not isinstance(meta.get('artifacts'),list)
            or not isinstance(meta.get('sha256'),dict)):
        raise ReleaseError('invalid manifest schema or system')
    names = meta['artifacts']
    if len(names) == 0 or len(names) != len(set(names)) or set(names) != set(meta['sha256']):
        raise ReleaseError('invalid artifact listing')
    for rel in names:
        if not isinstance(rel, str) or rel.startswith('.'):
            raise ReleaseError('invalid artifact name')
        p = inside(bundle, rel)
        if p.is_symlink() or not p.is_file():
            raise ReleaseError('missing / linked file: ' + rel)
        if hash_file(p) != meta['sha256'][rel]:
            raise ReleaseError('sha256 mismatch: ' + rel)
    return meta

def mission_module():
    """Import offline mission tools from source tree or self-contained release image."""
    import importlib.util
    candidates=[ROOT/'toolchain/mission/missionc.py',ROOT/'tools/missionc.py']
    path=next((x for x in candidates if x.is_file()),None)
    if path is None:raise ReleaseError('mission compiler unavailable in distribution')
    spec=importlib.util.spec_from_file_location('wcm_missionc',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def build(device: str, out: Path, compiler='gcc', mission_image: Path | None = None) -> dict:
    info = device_info(device)
    if out.exists():
        raise ReleaseError('output exists; choose a new directory: ' + str(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wcm-build-', dir=out.parent) as scratch:
        staged=Path(scratch) / 'image'
        staged.mkdir()
        shutil.copy2(ROOT/'devices'/device/'device.toml', staged/'device.toml')
        (staged/'spec').mkdir()
        shutil.copy2(ROOT/'spec/WCM-SYSTEM-CONTRACT.md',staged/'spec/WCM-SYSTEM-CONTRACT.md')
        shutil.copy2(ROOT/'LICENSE',staged/'LICENSE')
        shutil.copy2(ROOT/'NOTICE',staged/'NOTICE')
        (staged/'tools').mkdir()
        shutil.copy2(ROOT/'tools/wcmctl.py',staged/'tools/wcmctl.py')
        shutil.copy2(ROOT/'toolchain/mission/missionc.py',staged/'tools/missionc.py')
        artifacts=['tools/missionc.py','device.toml','spec/WCM-SYSTEM-CONTRACT.md','LICENSE','NOTICE','tools/wcmctl.py']
        if device == VIRTUAL_ID:
            mod=mission_module()
            if mission_image is None:
                mission=mod.pack(mod.parse_spec(ROOT/'devices/virtual-node/mission.toml'))
            else:
                mission=mission_image.read_bytes()
            mod.unpack(mission)  # Reject malformed, mutated or unsupported images.
            (staged/'mission.bin').write_bytes(mission)
            artifacts.append('mission.bin')
            if os.name != 'posix' or sys.platform != 'linux':
                raise ReleaseError('virtual-node build currently requires Linux host')
            if not shutil.which(compiler):
                raise ReleaseError('C compiler unavailable: ' + compiler)
            (staged/'firmware').mkdir()
            executable=staged/'firmware'/'wcm_virtual_device'
            src=ROOT
            cmd=[compiler, '-std=c17','-Os','-Wall','-Wextra','-Wpedantic',
                 '-Wconversion','-Wshadow','-Werror', '-Wl,--build-id=none',
                 '-I'+str(src/'system/cell'),'-I'+str(src/'system/optical'),
                 '-I'+str(src/'system/energy'),'-I'+str(src/'system/mission'),
                 str(src/'devices/virtual-node/virtual_device.c'),
                 str(src/'system/cell/wcm_cell_r4.c'),
                 str(src/'system/energy/wcm_power_model.c'),
                 str(src/'system/optical/wcm_optical.c'),
                 str(src/'system/mission/wcm_mission64.c'),'-o',str(executable)]
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            executable.chmod(0o755)
            artifacts.append('firmware/wcm_virtual_device')
            # Host-controlled environmental scenarios use the actual Cell C17
            # controller, never a deployed station downlink protocol.
            scenario_executable=staged/'firmware'/'wcm_scenario'
            scenario_cmd=cmd[:]
            scenario_cmd[scenario_cmd.index(str(src/'devices/virtual-node/virtual_device.c'))]=str(src/'simulation/wcm_scenario.c')
            scenario_cmd[scenario_cmd.index(str(executable))]=str(scenario_executable)
            subprocess.run(scenario_cmd,check=True,capture_output=True,text=True)
            scenario_executable.chmod(0o755)
            artifacts.append('firmware/wcm_scenario')
        elif device == FILM_ID:
            mod=mission_module()
            if mission_image is None:
                mission=mod.pack(mod.parse_spec(ROOT/'devices/virtual-node/mission.toml'))
            else:
                mission=mission_image.read_bytes()
            mod.unpack(mission) # fail closed before preparing a film research artifact
            (staged/'mission.bin').write_bytes(mission)
            (staged/'rtl').mkdir()
            cmd=[sys.executable,str(ROOT/'toolchain/hc/src/compiler.py'),
                 str(ROOT/'devices/film-reference/control.toml'),'--out',str(staged/'rtl')]
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            shutil.copy2(ROOT/'devices/film-reference/control.toml',staged/'control.toml')
            shutil.copy2(ROOT/'hardware/film/rtl/wcm_mission64_engine.v',
                         staged/'rtl/wcm_mission64_engine.v')
            shutil.copy2(ROOT/'hardware/film/rtl/wcm_mission64_endpoint.v',
                         staged/'rtl/wcm_mission64_endpoint.v')
            shutil.copy2(ROOT/'hardware/film/tb/tb_wcm_mission64_engine.v',
                         staged/'rtl/tb_wcm_mission64_engine.v')
            # An explicit MSB-first factory-stream model, not a programmable OTP.
            (staged/'rtl/mission_serial_bits.txt').write_text(''.join(f'{b:08b}' for b in mission)+'\n')
            artifacts.extend(['mission.bin','control.toml','rtl/wcm_reference_core.v',
                'rtl/manifest.json','rtl/tb_wcm_reference_core.v',
                'rtl/wcm_mission64_engine.v','rtl/wcm_mission64_endpoint.v',
                'rtl/tb_wcm_mission64_engine.v','rtl/mission_serial_bits.txt'])
        else:
            raise ReleaseError('missing exact device backend')
        meta=manifest_payload(device,info,artifacts)
        write_manifest(staged,meta)
        shutil.copytree(staged,out)
    return verify_bundle(out)

def zip_image(bundle: Path, out: Path) -> None:
    meta=verify_bundle(bundle)
    _=meta
    if out.exists():
        raise ReleaseError('destination zip already exists: '+str(out))
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                rel=p.relative_to(bundle).as_posix()
                if rel not in ('manifest.json', *meta['artifacts']):
                    raise ReleaseError('unexpected file in image: '+rel)
                entry=zipfile.ZipInfo(rel,date_time=(2026,10,23,0,0,0))
                entry.external_attr=(0o100755 if p.stat().st_mode & 0o111 else 0o100644)<<16
                entry.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(entry,p.read_bytes())

def install(bundle: Path, device_root: Path) -> dict:
    if bundle.is_file():
        if bundle.suffix.lower() != '.zip':
            raise ReleaseError('only directory images or .zip packages supported')
        with tempfile.TemporaryDirectory(prefix='wcm-unpack-') as temp:
            temp_dir=Path(temp)
            try:
                with zipfile.ZipFile(bundle) as archive:
                    entries=archive.infolist()
                    if not entries or len(entries)>64 or sum(x.file_size for x in entries)>12*1024*1024:
                        raise ReleaseError('zip exceeds release image limits')
                    names=set()
                    for ent in entries:
                        if ent.is_dir() or ent.filename in names:
                            raise ReleaseError('unsupported or duplicate archive entry')
                        names.add(ent.filename)
                        target=inside(temp_dir,ent.filename)
                        mode=(ent.external_attr>>16)&0o170000
                        if mode not in (0,0o100000):
                            raise ReleaseError('linked or non-regular archive file rejected')
                        target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(archive.read(ent))
            except (zipfile.BadZipFile, RuntimeError) as exc:
                raise ReleaseError('invalid image ZIP') from exc
            return install(temp_dir,device_root)
    meta=verify_bundle(bundle)
    if (meta['device']!=VIRTUAL_ID or meta['kind']!='virtual-host' or
            meta['physical_hardware'] or not meta['deployable']):
        raise ReleaseError('REFUSED: research / physical target has no hardware-qualified installer')
    if meta.get('build_host_os') != sys.platform or meta.get('build_host_arch') != platform.machine():
        raise ReleaseError('REFUSED: virtual image architecture or host OS mismatch')
    with (bundle/'device.toml').open('rb') as descriptor:
        desc=tomllib.load(descriptor)
    if (desc.get('id')!=VIRTUAL_ID or desc.get('kind')!='virtual-host' or
            desc.get('physical_hardware') is not False or
            desc.get('deployable') is not True):
        raise ReleaseError('unsupported device descriptor')
    if device_root.exists():
        raise ReleaseError('device root already exists: '+str(device_root))
    device_root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wcm-install-',dir=device_root.parent) as scratch:
        stage=Path(scratch)/'installed'
        shutil.copytree(bundle,stage)
        verify_bundle(stage)
        (stage/'firmware/wcm_virtual_device').chmod(0o755)
        shutil.move(str(stage),str(device_root))
    return verify_bundle(device_root)

def boot(device_root: Path) -> dict:
    meta=verify_bundle(device_root)
    if meta['device']!=VIRTUAL_ID or meta['physical_hardware'] or meta['kind']!='virtual-host':
        raise ReleaseError('cannot boot a research-only physical/film target')
    if meta.get('build_host_arch') != platform.machine() or meta.get('build_host_os') != sys.platform:
        raise ReleaseError('virtual image architecture or OS mismatch')
    path=inside(device_root,'firmware/wcm_virtual_device')
    result=subprocess.run([str(path),str(inside(device_root,'mission.bin'))],capture_output=True,text=True,timeout=15)
    if result.returncode != 0:
        raise ReleaseError('virtual boot failed: '+result.stderr.strip())
    status=json.loads(result.stdout)
    expected=('device','system','boot','hardware_qualified','mission_version','reports_sent','optical_symbols_emitted','downlink_commands_received','acknowledgements_expected','receiver_algorithm_present')
    if any(k not in status for k in expected) or status['device']!=VIRTUAL_ID or status['boot']!='ok' or status['hardware_qualified'] is not False:
        raise ReleaseError('virtual device boot contract violation')
    if (status['mission_version']!=1 or status['optical_symbols_emitted']!=32*status['reports_sent']
            or status['downlink_commands_received']!=0 or status['acknowledgements_expected'] is not False
            or status['receiver_algorithm_present'] is not False):
        raise ReleaseError('virtual device uplink-only contract violation')
    return status

def simulate(device_root: Path, scenario: str, ticks: int) -> dict:
    """Offline host fixture; simulated sensor/power events are NOT downlink."""
    if scenario not in ('nominal','brownout','sensor-silent','energy-starve','fault-inflight'):
        raise ReleaseError('unsupported simulation scenario')
    if ticks < 1 or ticks > 100000:
        raise ReleaseError('simulation ticks outside 1..100000')
    meta=verify_bundle(device_root)
    if (meta.get('device') != VIRTUAL_ID or meta.get('kind')!='virtual-host' or
            meta.get('build_host_os') != sys.platform or
            meta.get('build_host_arch') != platform.machine()):
        raise ReleaseError('unsupported simulation target or architecture')
    executable=inside(device_root,'firmware/wcm_scenario')
    if 'firmware/wcm_scenario' not in meta['artifacts']:
        raise ReleaseError('missing verified scenario executable')
    r=subprocess.run([str(executable),str(inside(device_root,'mission.bin')),
                      scenario,str(ticks)],capture_output=True,text=True,timeout=30)
    if r.returncode:
        raise ReleaseError('simulation failure: '+r.stderr.strip())
    events=[json.loads(line) for line in r.stdout.splitlines()]
    if not events or events[-1].get('type')!='summary':
        raise ReleaseError('missing simulation summary')
    result=events[-1]
    if (result.get('downlink') is not False or result.get('ack') is not False or
            result.get('hardware_qualified') is not False or
            result.get('symbols',-1)!=32*result.get('completed',0)+4*result.get('interrupted',0)):
        raise ReleaseError('virtual reflection/Commit invariant violated')
    return {'summary':result,'events':events[:-1]}

def cmd_main(argv=None):
    parser=argparse.ArgumentParser(prog='wcmctl',description='WCM-Core complete-system preview builder / virtual-device installer')
    cmd=parser.add_subparsers(dest='command',required=True)
    cmd.add_parser('list-devices')
    cmd.add_parser('doctor')
    make=cmd.add_parser('build');make.add_argument('--device',required=True,choices=DEVICES)
    make.add_argument('--mission',type=Path,help='offline compiled 8-byte mission image; virtual or Film research build')
    make.add_argument('--out',type=Path,required=True);make.add_argument('--cc',default='gcc')
    pk=cmd.add_parser('package');pk.add_argument('--bundle',type=Path,required=True);pk.add_argument('--out',type=Path,required=True)
    ver=cmd.add_parser('verify');ver.add_argument('--bundle',type=Path,required=True)
    ins=cmd.add_parser('install');ins.add_argument('--bundle',type=Path,required=True);ins.add_argument('--device-root',type=Path,required=True)
    run=cmd.add_parser('boot');run.add_argument('--device-root',type=Path,required=True)
    sim=cmd.add_parser('simulate')
    sim.add_argument('--device-root',type=Path,required=True)
    sim.add_argument('--scenario',choices=('nominal','brownout','sensor-silent','energy-starve','fault-inflight'),default='nominal')
    sim.add_argument('--ticks',type=int,default=250)
    mc=cmd.add_parser('mission-compile');mc.add_argument('--source',type=Path,required=True);mc.add_argument('--out',type=Path,required=True)
    mi=cmd.add_parser('mission-inspect');mi.add_argument('--image',type=Path,required=True)
    pb=cmd.add_parser('provision-batch');pb.add_argument('--mission',type=Path,required=True);pb.add_argument('--count',type=int,required=True);pb.add_argument('--out',type=Path,required=True);pb.add_argument('--seed-step',type=int,default=1)
    args=parser.parse_args(argv)
    try:
        if args.command=='list-devices':
            output=[{k:device_info(d)[k] for k in ('id','kind','status','deployable','physical_hardware')} for d in DEVICES]
        elif args.command=='doctor':
            output={'python':sys.version.split()[0], 'platform':sys.platform,
                    'gcc':bool(shutil.which('gcc')), 'clang':bool(shutil.which('clang')),
                    'iverilog':bool(shutil.which('iverilog')), 'yosys':bool(shutil.which('yosys')),
                    'physical_hardware_supported':False}
        elif args.command=='build':
            # Both the virtual device and the non-deployable Film research image
            # may consume an offline Mission-64; neither accepts remote commands.
            output=build(args.device,args.out,args.cc,args.mission)
        elif args.command=='verify':output=verify_bundle(args.bundle)
        elif args.command=='package':zip_image(args.bundle,args.out);output={'package':str(args.out),'sha256':hash_file(args.out)}
        elif args.command=='install':output=install(args.bundle,args.device_root)
        elif args.command=='boot':output=boot(args.device_root)
        elif args.command=='simulate':output=simulate(args.device_root,args.scenario,args.ticks)
        elif args.command=='mission-compile':
            mod=mission_module();image=mod.pack(mod.parse_spec(args.source));mod.atomic_write(args.out,image)
            output={'image':str(args.out),'bytes':8,'sha256':hashlib.sha256(image).hexdigest()}
        elif args.command=='mission-inspect':output=mission_module().unpack(args.image.read_bytes())
        elif args.command=='provision-batch':
            output=mission_module().provision(args.mission.read_bytes(),args.count,args.out,args.seed_step)
        else:raise ReleaseError('unhandled command')
        print(json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True))
        return 0
    except (ReleaseError,OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as e:
        print('WCM-CORE ERROR: '+str(e),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(cmd_main())
