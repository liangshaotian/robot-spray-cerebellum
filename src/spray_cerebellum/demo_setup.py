"""Install the bundled, checksum-verified E350 demo into the local asset registry."""
from __future__ import annotations
import gzip,hashlib,json,pathlib,shutil,uuid
from .common import REPO

ASSET_ID='artec_e350_door_v2'
BUNDLE=REPO/'demo'/ASSET_ID

def sha256(path):
    digest=hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def install_precise_demo(state_dir=None,bundle_dir=BUNDLE):
    bundle=pathlib.Path(bundle_dir)
    checks=json.loads((bundle/'checksums.json').read_text(encoding='utf-8'))
    for name,expected in checks['files'].items():
        if pathlib.Path(name).name!=name:raise ValueError('Invalid bundle member name')
        if sha256(bundle/name)!=expected:raise ValueError('Demo bundle checksum mismatch: '+name)
    manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
    root=pathlib.Path(state_dir or REPO/'.local')/'assets';root.mkdir(parents=True,exist_ok=True)
    destination=root/ASSET_ID
    mesh=checks['expanded_mesh']
    if destination.exists():
        current=json.loads((destination/'manifest.json').read_text(encoding='utf-8'))
        expected={mesh['filename']:mesh['sha256'],manifest['surface_file']:checks['files'][manifest['surface_file']],
                  manifest['policy_file']:checks['files'][manifest['policy_file']]}
        if current['asset_id']!=ASSET_ID or current.get('policy_id')!=manifest['policy_id']:
            raise ValueError('A different asset/policy is registered with this ID; use a separate --state-dir')
        for name,value in expected.items():
            if sha256(destination/name)!=value:raise ValueError('Existing demo differs; use a separate --state-dir: '+name)
        return destination
    staging=root/(ASSET_ID+'.staging-'+uuid.uuid4().hex)
    staging.mkdir()
    try:
        for name in checks['files']:
            if name.endswith('.gz'):continue
            shutil.copy2(bundle/name,staging/name)
        with gzip.open(bundle/(mesh['filename']+'.gz'),'rb') as source,(staging/mesh['filename']).open('wb') as output:
            shutil.copyfileobj(source,output)
        if sha256(staging/mesh['filename'])!=mesh['sha256']:raise ValueError('Expanded mesh checksum mismatch')
        staging.rename(destination)
    except Exception:
        if staging.resolve().parent!=root.resolve():raise RuntimeError('Refusing cleanup outside demo asset root')
        if staging.exists():shutil.rmtree(staging)
        raise
    return destination
