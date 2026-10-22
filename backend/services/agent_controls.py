import json
import os
import subprocess
import sys
import tempfile
from backend.db import ROOT,connect,transaction,one,now,audit
from backend.services.agent_data import require_admin,dump

def latest():
    with connect() as c: row=one(c,'SELECT id,result,created_at FROM agent_case_checks ORDER BY id DESC LIMIT 1')
    if row: row['result']=json.loads(row['result'])
    return row

def run(uid):
    with connect() as c: require_admin(c,uid)
    folder=ROOT/'.tmp';folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='agent-controls-',dir=folder) as directory:
        env=os.environ.copy();env.pop('DATABASE_URL',None);env['RODA_FORCE_SQLITE']='1';env['DATABASE_PATH']=str(os.path.join(directory,'controls.db'));env['PYTHONUTF8']='1'
        try:
            result=subprocess.run([sys.executable,'-m','backend.agent_scenarios'],cwd=ROOT,env=env,capture_output=True,
                text=True,encoding='utf-8',timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),check=True)
            payload=json.loads(result.stdout)
        except (subprocess.SubprocessError,ValueError):
            raise ValueError('No se pudieron completar los controles aislados. La tienda conserva sus datos.') from None
    with transaction() as c:
        require_admin(c,uid)
        ident=c.execute('INSERT INTO agent_case_checks(user_id,result,created_at) VALUES(?,?,?)',(uid,dump(payload),now())).lastrowid
        audit(c,'agent_case_checks',ident,'ejecutar',uid,detail={'passed':sum(bool(v['passed']) for v in payload['cases'])})
    return {'id':ident,'result':payload,'created_at':now()}
