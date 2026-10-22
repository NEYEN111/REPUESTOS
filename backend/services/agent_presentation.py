"""Durable, admin-only academic demonstrations, isolated from shop operations."""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime,timedelta
from backend.db import ROOT,connect,transaction,one,now,audit
from backend.services.agent_data import require_admin,dump

def latest():
    with connect() as c:record=one(c,'SELECT * FROM agent_presentations ORDER BY id DESC LIMIT 1')
    if record:record['result']=json.loads(record['result'])
    return record

def start(uid,key):
    from backend.services.agents import status
    with transaction() as c:
        require_admin(c,uid)
        previous=one(c,'SELECT id,user_id FROM agent_presentations WHERE request_key=?',(key,))
        if previous:
            if previous['user_id']!=uid:raise ValueError('La solicitud pertenece a otro administrador.')
            return {'id':previous['id']}
        if not status()['configured']:raise ValueError('Configura el proveedor LLM en el backend antes de ejecutar la demostración.')
        if one(c,"SELECT id FROM agent_presentations WHERE status IN ('en_cola','en_curso')"):
            raise ValueError('Ya hay una demostración pendiente. Espera su resultado.')
        ident=c.execute('INSERT INTO agent_presentations(user_id,request_key,created_at) VALUES(?,?,?)',(uid,key,now())).lastrowid
        audit(c,'agent_presentations',ident,'solicitar',uid)
    return {'id':ident}

async def execute_next():
    with transaction() as c:
        c.execute("UPDATE agent_presentations SET status='error',error='La ejecución se interrumpió. Puedes repetirla.',finished_at=? WHERE status='en_curso' AND lease_until<?",(now(),now()))
        if one(c,"SELECT id FROM agent_runs WHERE status='en_curso'") or one(c,"SELECT id FROM agent_presentations WHERE status='en_curso'"):return False
        job=one(c,"SELECT * FROM agent_presentations WHERE status='en_cola' ORDER BY id LIMIT 1")
        if not job:return False
        require_admin(c,job['user_id'])
        lease=(datetime.fromisoformat(now())+timedelta(minutes=6)).isoformat()
        c.execute("UPDATE agent_presentations SET status='en_curso',started_at=?,lease_until=? WHERE id=?",(now(),lease,job['id']))
    process=None
    try:
        (ROOT/'.tmp').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='agent-controls-presentation-',dir=ROOT/'.tmp') as folder:
            env=os.environ.copy();env.pop('DATABASE_URL',None);env['RODA_FORCE_SQLITE']='1';env['DATABASE_PATH']=os.path.join(folder,'demo.db');env['PYTHONUTF8']='1'
            process=await asyncio.create_subprocess_exec(sys.executable,'-m','backend.agent_presentation',cwd=ROOT,env=env,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
                creationflags=getattr(__import__('subprocess'),'CREATE_NO_WINDOW',0))
            try:out,_=await asyncio.wait_for(process.communicate(),timeout=270)
            finally:
                if process.returncode is None:
                    process.kill();await process.communicate()
            if process.returncode:raise ValueError('No se completó la demostración. Revisa la conexión y vuelve a ejecutarla.')
            result=json.loads(out.decode('utf-8'))
        with transaction() as c:
            c.execute("UPDATE agent_presentations SET status='completada',result=?,finished_at=?,lease_until=NULL WHERE id=?",(dump(result),now(),job['id']))
            audit(c,'agent_presentations',job['id'],'completar',job['user_id'],detail={'passed':sum(case['passed'] for case in result['cases'])})
    except asyncio.CancelledError:
        if process and process.returncode is None:process.kill();await process.communicate()
        with transaction() as c:c.execute("UPDATE agent_presentations SET status='error',error='El servidor se reinició. Repite la demostración.',finished_at=? WHERE id=?",(now(),job['id']))
        raise
    except Exception:
        with transaction() as c:c.execute("UPDATE agent_presentations SET status='error',error='No se completó la demostración. Comprueba la conexión LLM y vuelve a intentarlo.',finished_at=?,lease_until=NULL WHERE id=?",(now(),job['id']))
    return True
