"""Download only the official robot data model; never application/license files."""
import pathlib,urllib.request,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
target=root/'demo/assets/Han-s-E12.robot'
expected='3940ae4987a56c9791238064b5b68423f3d3a3f024a44c82f52092f4afabcd56'
if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==expected:
    print('Official E12 model already present')
else:
    content=urllib.request.urlopen('https://cdn.robodk.com/downloads-library/library-robots/Han-s-E12.robot',timeout=40).read()
    if hashlib.sha256(content).hexdigest()!=expected:raise SystemExit('Robot model changed upstream; inspect version before updating expected hash')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    print('Official E12 model downloaded and verified')
