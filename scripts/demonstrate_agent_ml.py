"""Replay an actual reference forecast through inventory tools in a temporary database."""
import json,sys,tempfile,gc
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.agent_scenarios import seed
from backend.services import agent_data as data

source=json.loads((db.ROOT/'artifacts/agent-ml-input.json').read_text(encoding='utf-8'))
p=source['sample']
if not p or p['review']:raise SystemExit('No existe una predicción sin observaciones; no se fuerza la aprobación.')
original=db.DB
with tempfile.TemporaryDirectory(prefix='agent-controls-ml-',dir=db.ROOT/'.tmp') as folder:
    db.DB=Path(folder)/'control.db';seed()
    with db.transaction() as c:
        c.execute('UPDATE products SET sku=?,stock=2,minimum=1 WHERE id=1',(p['sku'],))
        c.execute('UPDATE inventory_policy SET maximum=3,lead_days=2 WHERE product_id=1')
    baseline=data.candidates(5)
    with db.transaction() as c:
        rid=c.execute("INSERT INTO ml_runs(source,cutoff,model_hash,created_at,user_id,count,summary) VALUES('operacion',?,?,?,1,1,?)",(source['cutoff'],source['model_hash'],db.now(),json.dumps({'academic_replay':True}))).lastrowid
        c.execute('''INSERT INTO ml_predictions(run_id,product_id,sku,prediction,lower_bound,upper_bound,available,rotation,review,coverage,reasons,features,history)
            VALUES(?,1,?,?,?,?,?,?,0,?,?,?,?)''',(rid,p['sku'],p['prediction'],p['lower_bound'],p['upper_bound'],p['available'],p['rotation'],p['coverage'],json.dumps(p['reasons']),json.dumps(p['features']),json.dumps(p['history'])))
    replay_day=(date.fromisoformat(source['cutoff'])+timedelta(days=1)).isoformat()+'T12:00:00-05:00'
    with patch.object(data,'now',return_value=replay_day):
        after=data.candidates(5)
    item=next(i for i in after['items'] if i['id']==1)
    result={'sku':p['sku'],'prediction':p['prediction'],'rounded_units':item['forecast_units'],
        'available':2,'minimum':1,'policy_target':3,'without_ml':sum(i['needed'] for i in baseline['items']),
        'with_ml':item['needed'],'basis':item['basis'],'cutoff':source['cutoff'],'model_hash':source['model_hash'],
        'review':p['review'],'passed':item['basis']=='ml_operativo' and item['needed']>0 and not baseline['items'],
        'note':'Demostración aislada: predicción real del modelo sobre historial académico. Se recrea la fecha del pronóstico y un stock de ejemplo; no se altera la tienda ni se crea evidencia operativa actual.'}
    c.close();db.DB=original;gc.collect()
(db.ROOT/'artifacts/agent-ml-demonstration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
release=db.ROOT/'ml/evaluations/agents/ml-replenishment.json'
release.parent.mkdir(parents=True,exist_ok=True)
release.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
