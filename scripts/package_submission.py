"""Package only the explicit, reviewed academic evidence; never copy environment secrets."""
import hashlib
import json
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/entrega-2026-10-23'
OUT.mkdir(parents=True,exist_ok=True)
evidence=ROOT/'artifacts/entrega-2026-10-23'
if evidence.is_dir():
    shutil.copytree(evidence,OUT/'Evidencias',dirs_exist_ok=True)
else:
    evidence=OUT/'Evidencias'
mapping={}

def read(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).is_file() else default

# A plain evidence index makes the submission auditable without executing notebooks.
summary=read(ROOT/'ml/evaluations/entrega-2026-10-23/resumen_ejecucion.json',{})
agent=read(ROOT/'ml/evaluations/agents/entrega-2026-10-23.json',{})
llm=read(ROOT/'ml/evaluations/agents/llm-entrega-2026-10-23.json',{})
mode_rows=defaultdict(list)
for row in agent.get('results',[]):mode_rows[row['mode']].append(row)
results_folders=[p/'resultados' for p in sorted((ROOT/'ml/evaluations/entrega-2026-10-23/ejecuciones').glob('*'))
                 if (p/'resultados/comparison.json').is_file()]
index={
    'schema_version':1,
    'project':'RODA · reposición asistida de repuestos',
    'date':'2026-10-23',
    'purpose':'Índice de artefactos y resultados comprobados para una entrega académica; no sustituye los archivos fuente.',
    'package_scope':'Paquete de informe y evidencias; la aplicación completa se obtiene clonando el repositorio GitHub. Los comandos de reproducción se ejecutan desde ese clon.',
    'links':{
        'system':'https://roda-repuestos.onrender.com',
        'repository':'https://github.com/NEYEN111/REPUESTOS',
        'colab':'https://colab.research.google.com/github/NEYEN111/REPUESTOS/blob/main/notebooks/RODA_ML_Datos_Reales.ipynb',
    },
    'report':read(OUT/'METADATOS_INFORME.json',{}),
    'ml':{
        'task':'Unidades observadas del siguiente mes por serie anónima externa',
        'algorithms':['Ridge','Poisson','Random Forest','Extra Trees','Hist. Gradient Boosting'],
        'execution':summary.get('execution',{}),
        'source':summary.get('source',{}),
        'evaluation':read(results_folders[-1]/'comparison.json',{}) if results_folders else {},
        'executed_notebook':'ML/RODA_ML_Datos_Reales_Ejecutado.ipynb',
        'environment_notice':'La ejecución adjunta fue local en Windows; el enlace Colab permite repetirla, pero no es evidencia de una ejecución realizada allí.',
    },
    'agents':{
        'roles':8,'provider':agent.get('provider_configured',{}),
        'isolated_database':agent.get('isolated_database'),
        'real_provider_calls':agent.get('real_provider_calls'),
        'results_file':'Agentes/entrega-2026-10-23.json',
        'modalities':{mode:{'passed':sum(bool(r['passed']) for r in rows),'total':len(rows),
                             'mean_seconds':mean(r['seconds'] for r in rows),
                             'provider_attempts':sum(r['provider_attempts'] for r in rows)}
                      for mode,rows in mode_rows.items()},
        'limit':'Muestra exploratoria de tres escenarios con dos repeticiones; no demuestra superioridad estadística ni económica del equipo.',
    },
    'assistant':{'passed':sum(bool(r.get('passed')) for r in llm.get('results',[])),
                  'total':len(llm.get('results',[])),
                  'results_file':'Agentes/llm-entrega-2026-10-23.json'},
    'deployment_evidence':read(evidence/'render.json',{}),
    'demo_access_evidence':read(evidence/'render-demo.json',{}),
    'provider_recovery_evidence':read(evidence/'render-provider-recovery.json',{}),
    'provider_diagnostics':read(evidence/'proveedor-diagnostico.json',{}),
    'reproduction':'README.md; scripts/prepare_ml_delivery.py; scripts/build_submission.py; scripts/package_submission.py',
    'integrity':'MANIFIESTO_SHA256.json dentro del ZIP: tamaño y hash de todos los archivos incluidos.',
}
index_path=OUT/'INDICE_ENTREGA.json'
index_path.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def add(path,name=None):
    path=Path(path)
    if path.is_file():mapping[name or str(path.relative_to(ROOT)).replace('\\','/')]=path
def tree(folder,prefix):
    for p in sorted(folder.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.zip':
            add(p,prefix+'/'+p.relative_to(folder).as_posix())
add(OUT/'Informe_RODA.pdf','Informe_RODA.pdf')
add(index_path,'INDICE_ENTREGA.json')
add(OUT/'METADATOS_INFORME.json','METADATOS_INFORME.json')
add(OUT/'VERIFICACION_ENTREGA.json','VERIFICACION_ENTREGA.json')
add(ROOT/'README.md','README.md')
tree(OUT/'Evidencias','Evidencias')
tree(ROOT/'ml/evaluations/entrega-2026-10-23','ML')
tree(ROOT/'ml/examples/carparts','Datos')
for name in ['entrega-2026-10-23.json','entrega-2026-10-23.csv','llm-entrega-2026-10-23.json','llm-entrega-2026-10-23.csv']:
    add(ROOT/'ml/evaluations/agents'/name,'Agentes/'+name)
for file in ['notebooks/RODA_ML_Datos_Reales.ipynb','ml/lab_engine.py','ml/requirements.txt',
             'scripts/prepare_ml_delivery.py','scripts/evaluate_agent_modes.py','scripts/evaluate_assistant.py',
             'scripts/verify_llm_provider.py',
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
