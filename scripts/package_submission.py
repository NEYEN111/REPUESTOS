"""Package only the explicit, reviewed academic evidence; never copy environment secrets."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/entrega-2026-10-23'
OUT.mkdir(parents=True,exist_ok=True)
evidence=ROOT/'artifacts/entrega-2026-10-23'
shutil.copytree(evidence,OUT/'Evidencias',dirs_exist_ok=True)
mapping={}
def add(path,name=None):
    path=Path(path)
    if path.is_file():mapping[name or str(path.relative_to(ROOT)).replace('\\','/')]=path
def tree(folder,prefix):
    for p in sorted(folder.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.zip':
            add(p,prefix+'/'+p.relative_to(folder).as_posix())
add(OUT/'Informe_RODA.pdf','Informe_RODA.pdf')
add(ROOT/'README.md','README.md')
tree(OUT/'Evidencias','Evidencias')
tree(ROOT/'ml/evaluations/entrega-2026-10-23','ML')
tree(ROOT/'ml/examples/carparts','Datos')
for name in ['entrega-2026-10-23.json','entrega-2026-10-23.csv','llm-entrega-2026-10-23.json','llm-entrega-2026-10-23.csv']:
    add(ROOT/'ml/evaluations/agents'/name,'Agentes/'+name)
for file in ['notebooks/RODA_ML_Datos_Reales.ipynb','ml/lab_engine.py','ml/requirements.txt',
             'scripts/prepare_ml_delivery.py','scripts/evaluate_agent_modes.py','scripts/evaluate_assistant.py',
             'scripts/build_submission.py','scripts/package_submission.py','requirements.txt','render.yaml']:
    add(ROOT/file)
manifest=[{'file':k,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
          for k,p in sorted(mapping.items())]
target=OUT/'RODA_Entrega_Completa.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=7) as z:
    for name,path in sorted(mapping.items()):
        assert Path(name).name not in {'.env','.env.local'}
        z.write(path,name)
    z.writestr('MANIFIESTO_SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    assert any(n.endswith('.joblib') for n in z.namelist())
    assert any(n.endswith('.xlsx') for n in z.namelist())
    assert any('Ejecutado.ipynb' in n for n in z.namelist())
print(json.dumps({'archive':str(target),'files':len(mapping)+1,'bytes':target.stat().st_size,
                  'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},ensure_ascii=False))
