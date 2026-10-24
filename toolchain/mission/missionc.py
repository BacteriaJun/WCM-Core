#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""WCM-Core Mission-64 v1 compiler, decoder and *offline* batch programmer.
No OTA delivery, command receiver, packet decoding, or hardware writer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import tempfile
import tomllib

FIELDS=(("version",4),("task",4),("sensor",4),("threshold",6),
        ("sample_period",6),("report_period",6),("max_reports",6),
        ("seed",12),("flags",8))
TASKS={"threshold-report":1,"periodic-report":2}
SENSORS={"scalar":1}

class MissionError(ValueError): pass

def crc8(data:bytes)->int:
    c=0
    for byte in data:
        c ^= byte
        for _ in range(8):
            c=((c<<1)^0x07)&0xff if c&0x80 else (c<<1)&0xff
    return c

def validate(v:dict)->dict:
    if set(v)!={k for k,_ in FIELDS}:
        raise MissionError('mission has missing/unknown keys')
    if any(type(v[k]) is not int or not 0<=v[k]<(1<<n) for k,n in FIELDS):
        raise MissionError('mission fields must fit fixed unsigned bit widths')
    if v['version']!=1 or v['task'] not in (1,2) or v['sensor']!=1:
        raise MissionError('unsupported mission/sensor/version')
    if (v['task']==1 and v['threshold']==0) or (v['task']==2 and v['threshold']!=0):
        raise MissionError('threshold must be nonzero only for threshold-report')
    if not(v['sample_period'] and v['report_period'] and v['max_reports']) or v['flags']!=0:
        raise MissionError('zero period/repeats or unsupported flags')
    return v

def parse_spec(path:pathlib.Path)->dict:
    spec=tomllib.loads(path.read_text(encoding='utf-8'))
    if set(spec)!={'mission'} or not isinstance(spec['mission'],dict):
        raise MissionError('expected a single [mission] table')
    raw=spec['mission']; required={'task','sensor','threshold','sample_period','report_period','max_reports','seed'}
    if set(raw)!=required:raise MissionError('unknown/missing mission specification fields')
    if raw['task'] not in TASKS or raw['sensor'] not in SENSORS:
        raise MissionError('unknown task or sensor')
    return validate({'version':1,'task':TASKS[raw['task']],'sensor':SENSORS[raw['sensor']],
        'threshold':raw['threshold'],'sample_period':raw['sample_period'],
        'report_period':raw['report_period'],'max_reports':raw['max_reports'],
        'seed':raw['seed'],'flags':0})

def pack(v:dict)->bytes:
    validate(v)
    word=0
    for name,nbits in FIELDS:
        word=(word<<nbits)|v[name]
    body=word.to_bytes(7,'big')
    return body+bytes([crc8(body)])

def unpack(img:bytes)->dict:
    if len(img)!=8 or crc8(img[:7])!=img[7]:raise MissionError('Mission-64 size/CRC mismatch')
    word=int.from_bytes(img[:7],'big');out={}
    for name,width in reversed(FIELDS):
        out[name]=word & ((1<<width)-1)
        word >>= width
    return validate(out)

def atomic_write(path:pathlib.Path, data:bytes):
    if path.exists(): raise MissionError('refusing overwrite: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    # Use exclusive creation so an earlier mission is never silently overwritten.
    with path.open('xb') as f:f.write(data)

def provision(img:bytes,count:int,out:pathlib.Path,seed_step:int=1)->dict:
    base=unpack(img)
    if not 1<=count<=4096:raise MissionError('batch count out of range 1..4096')
    if seed_step<=0 or seed_step>=4096:raise MissionError('invalid seed step')
    seeds={(base['seed']+i*seed_step)%4096 for i in range(count)}
    if len(seeds)!=count:raise MissionError('per-node personalization seeds repeat; choose an odd seed step')
    if out.exists():raise MissionError('refusing overwrite existing batch')
    # Batch preparation is one atomic-ish stage, then move into place. This
    # models factory NVM programming and readback, not physical programming.
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wcm-mission-',dir=out.parent) as temp:
        stage=pathlib.Path(temp)/'batch';stage.mkdir()
        records=[]
        for i in range(count):
            values={**base,'seed':(base['seed']+i*seed_step)%4096}
            content=pack(values)
            rel=f'node-{i:05d}.bin';p=stage/rel
            p.write_bytes(content)
            if unpack(p.read_bytes())!=values: raise MissionError('write/readback error')
            records.append({'node_index':i,'file':rel,'sha256':hashlib.sha256(content).hexdigest(),'seed':values['seed']})
        (stage/'batch.json').write_text(json.dumps({'schema':1,'kind':'offline-provisioning-simulation',
             'format':'WCM-Mission-64-v1','device_count':count,
             'hardware_written':False,'records':records},indent=2)+'\n')
        os.replace(stage,out)
    return {'count':count,'destination':str(out),'hardware_written':False}

def main(argv=None)->int:
    p=argparse.ArgumentParser(prog='missionc',description='Compile/preprovision WCM Mission-64 offline')
    commands=p.add_subparsers(dest='action',required=True)
    c=commands.add_parser('compile');c.add_argument('--source',type=pathlib.Path,required=True);c.add_argument('--out',type=pathlib.Path,required=True)
    d=commands.add_parser('decode');d.add_argument('--image',type=pathlib.Path,required=True)
    b=commands.add_parser('provision');b.add_argument('--image',type=pathlib.Path,required=True);b.add_argument('--count',type=int,required=True);b.add_argument('--out',type=pathlib.Path,required=True);b.add_argument('--seed-step',type=int,default=1)
    args=p.parse_args(argv)
    try:
        if args.action=='compile':
            image=pack(parse_spec(args.source));atomic_write(args.out,image)
            result={'image':str(args.out),'bytes':len(image),'hex':image.hex(),'format':'WCM-Mission-64-v1'}
        elif args.action=='decode':result=unpack(args.image.read_bytes())
        else:result=provision(args.image.read_bytes(),args.count,args.out,args.seed_step)
        print(json.dumps(result,indent=2,sort_keys=True));return 0
    except (OSError,MissionError,TypeError) as exc:
        p.exit(2,'WCM Mission error: '+str(exc)+'\n')
if __name__=='__main__':raise SystemExit(main())
