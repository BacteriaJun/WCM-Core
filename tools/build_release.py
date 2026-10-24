#!/usr/bin/env python3
# Modified for v1.0.0: normalized public identifiers and technical documentation.
"""Package source and formal-model evidence with deterministic ordering and timestamps.
"""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED_DIRS={'.git','build','dist','__pycache__','.pytest_cache'}
EXCLUDED_NAMES={'SOURCE_MANIFEST.sha256','.DS_Store'}
SOURCE_DATE=(2026,10,24,0,0,0)

def candidates():
    return sorted((p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()
      and not any(part in EXCLUDED_DIRS for part in p.relative_to(ROOT).parts)
      and p.name not in EXCLUDED_NAMES and not p.name.endswith(('.pyc','.o','.so','.vvp'))),
      key=lambda p:p.relative_to(ROOT).as_posix())
def add(z,arcname,data):
    info=zipfile.ZipInfo(arcname,date_time=SOURCE_DATE)
    info.create_system=3;info.external_attr=0o100644<<16
    info.compress_type=zipfile.ZIP_DEFLATED
    z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    files=candidates()
    listing={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest=''.join(f'{digest}  {path}\n' for path,digest in listing.items()).encode()
    (ROOT/'SOURCE_MANIFEST.sha256').write_bytes(manifest)
    source=out/'WCM-Core_v1.0.0_Conceptual_Complete_Source.zip'
    with zipfile.ZipFile(source,'w') as z:
        for p in files:add(z,'WCM-Core/'+p.relative_to(ROOT).as_posix(),p.read_bytes())
        add(z,'WCM-Core/SOURCE_MANIFEST.sha256',manifest)
    result={'source_file_count':len(files)+1,'source_zip':str(source),
        'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    formal=out/'WCM-Core_v1.0.0_Formal_Evidence.zip'
    incl=[p for p in files if p.relative_to(ROOT).as_posix().startswith('verification/')
          or p.relative_to(ROOT).as_posix() in ('docs/FORMAL_VERIFICATION.md',
          'docs/FORMAL_VERIFICATION_APPENDIX.md','docs/RELEASE_SCOPE.md')]
    with zipfile.ZipFile(formal,'w') as z:
        for p in incl:add(z,p.relative_to(ROOT).as_posix(),p.read_bytes())
    result['formal_zip']=str(formal)
    result['formal_sha256']=hashlib.sha256(formal.read_bytes()).hexdigest()
    (out/'SHA256SUMS.txt').write_text(f'{result["sha256"]}  {source.name}\n{result["formal_sha256"]}  {formal.name}\n')
    print(json.dumps(result,indent=2));return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();generate(args.out)
