"""One durable daily administrative review, with local-time catch-up and no purchases."""
from datetime import datetime,timedelta
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
from backend.db import connect,transaction,one,now,audit
from backend.services import agent_data as data

class ScheduleInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled: bool = Field(strict=True)
    kind: Literal['reposicion','pedidos','finanzas','catalogo']='reposicion'
    at_time: str = Field(default='09:00',pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    budget_cents: int = Field(default=200000,strict=True,ge=100,le=100000000)
    product_limit: int = Field(default=12,strict=True,ge=1,le=20)

def get():
    with connect() as c: s=one(c,'SELECT * FROM agent_schedules WHERE id=1')
    if not s: s={'enabled':False,'kind':'reposicion','at_time':'09:00','budget_cents':200000,'product_limit':12,'last_date':'','last_run_id':None,'last_message':''}
    s['enabled']=bool(s['enabled'])
    stamp=datetime.fromisoformat(now())
    scheduled=stamp.replace(hour=int(s['at_time'][:2]),minute=int(s['at_time'][3:]),second=0,microsecond=0)
    if s['last_date']>=stamp.date().isoformat(): scheduled+=timedelta(days=1)
    s['next_at']=scheduled.isoformat() if s['enabled'] else None
    s['catch_up']=bool(s['enabled'] and scheduled<stamp)
    return s

def save(d,uid):
    with transaction() as c:
        data.require_admin(c,uid)
        c.execute('''INSERT INTO agent_schedules(id,enabled,kind,at_time,budget_cents,product_limit,user_id,updated_at)
            VALUES(1,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled,kind=excluded.kind,
            at_time=excluded.at_time,budget_cents=excluded.budget_cents,product_limit=excluded.product_limit,
            user_id=excluded.user_id,updated_at=excluded.updated_at''',
            (int(d.enabled),d.kind,d.at_time,d.budget_cents,d.product_limit,uid,now()))
        audit(c,'agent_schedules',1,'guardar',uid,detail=d.model_dump())
    return get()

def tick(model):
    stamp=now(); today=stamp[:10]
    with transaction() as c:
        s=one(c,'SELECT * FROM agent_schedules WHERE id=1 AND enabled=1')
        if not s or s['last_date']>=today or stamp[11:16]<s['at_time']: return None
        if not one(c,"SELECT id FROM users WHERE id=? AND role='admin'",(s['user_id'],)):
            c.execute("UPDATE agent_schedules SET enabled=0,last_message='Se pausó: la cuenta responsable ya no es administradora.' WHERE id=1")
            return None
        from backend.services.llm_provider import status as llm_status
        if not llm_status()['configured']: return None
        if one(c,"SELECT COUNT(*) n FROM agent_runs WHERE status IN ('en_cola','en_curso')")['n']>=3: return None
        key=f"agent-daily-{today}"
        prior=one(c,'SELECT id FROM agent_runs WHERE request_key=?',(key,))
        if prior: rid=prior['id']
        else:
            rid=c.execute('''INSERT INTO agent_runs(kind,request_key,user_id,budget_cents,product_limit,created_at,model)
                VALUES(?,?,?,?,?,?,?)''',(s['kind'],key,s['user_id'],s['budget_cents'],s['product_limit'],stamp,model)).lastrowid
            c.execute("INSERT INTO agent_steps(run_id,agent,kind,target,message,data,created_at) VALUES(?,'orquestador','programacion','','Revisión diaria encolada. Las compras conservarán su aprobación humana.','{}',?)",(rid,stamp))
            audit(c,'agent_runs',rid,'revision_diaria',s['user_id'],actor='sistema')
        c.execute("UPDATE agent_schedules SET last_date=?,last_run_id=?,last_message='Revisión del día encolada.' WHERE id=1",(today,rid))
        return rid
