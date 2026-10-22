from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from backend.services import agent_data as data, agents
from backend.services import agent_schedule,agent_controls
from backend.services import agent_followup
from backend.db import connect, rows
from backend.db import ROOT
import json

class Approval(BaseModel):
    accept_references: bool = Field(default=False, strict=True)

class PresentationInput(BaseModel):
    request_key: str = Field(min_length=12,max_length=100,pattern=r'^[a-zA-Z0-9_-]+$')

def router(admin):
    api=APIRouter(prefix='/api/admin/agents',dependencies=[Depends(admin)])

    @api.get('/status')
    def status(): return agents.status()

    @api.get('/presentation')
    def presentation():
        from backend.services.agent_presentation import latest
        return latest()

    @api.post('/presentation')
    def start_presentation(d:PresentationInput,u=Depends(admin)):
        from backend.services.agent_presentation import start
        return start(u['id'],d.request_key)

    @api.get('/readiness')
    def readiness(): return agent_followup.readiness()

    @api.get('/evaluation')
    def evaluation():
        path=ROOT/'artifacts/agent-mode-evaluation.json'
        if not path.exists(): return None
        result=json.loads(path.read_text(encoding='utf-8'))
        result['results']=[{k:v for k,v in row.items() if k!='evidence'} for row in result['results']]
        ml_path=ROOT/'artifacts/agent-ml-demonstration.json'
        result['ml_demo']=json.loads(ml_path.read_text(encoding='utf-8')) if ml_path.exists() else None
        return result

    @api.get('/runs/{rid}/followup')
    def followup(rid:int): return agent_followup.followup(data.get_run(rid))

    @api.get('/schedule')
    def schedule(): return agent_schedule.get()

    @api.put('/schedule')
    def save_schedule(d:agent_schedule.ScheduleInput,u=Depends(admin)):
        return agent_schedule.save(d,u['id'])

    @api.get('/controls')
    def controls(): return agent_controls.latest()

    @api.post('/controls')
    def run_controls(u=Depends(admin)): return agent_controls.run(u['id'])

    @api.get('/runs')
    def runs(page:int=1,status:str=''): return data.list_runs(page,status)

    @api.post('/runs')
    def start(d:data.RunInput,u=Depends(admin)):
        if not agents.status()['configured']: raise ValueError('Configura THEHIVE_API_KEY o DEEPSEEK_API_KEY en el backend antes de iniciar.')
        return {'id':data.create_run(d,u['id'],agents.model_name())}

    @api.get('/runs/{rid}')
    def detail(rid:int): return data.get_run(rid)

    @api.post('/runs/{rid}/cancel')
    def cancel(rid:int,u=Depends(admin)):
        data.cancel(rid,u['id']);return {'ok':True}

    @api.post('/runs/{rid}/resume')
    def resume(rid:int,u=Depends(admin)):
        data.resume(rid,u['id']);return {'ok':True}

    @api.post('/runs/{rid}/approve')
    def approve(rid:int,d:Approval,u=Depends(admin)):
        return {'purchase_ids':data.approve(rid,u['id'],d.accept_references)}

    @api.get('/offers')
    def offers(q:str='',page:int=1): return data.offer_rows(q,page)

    @api.post('/offers')
    def save_offer(d:data.OfferInput,u=Depends(admin)):
        data.save_offer(d,u['id']);return {'ok':True}

    @api.post('/offers/references')
    def references(u=Depends(admin)): return {'count':data.import_references(u['id'])}

    @api.get('/products')
    def products(q:str=''):
        with connect() as c:
            return rows(c,'SELECT id,sku,name,cost_cents FROM products WHERE active=1 AND (sku LIKE ? OR name LIKE ?) ORDER BY name LIMIT 20',(f'%{q[:100]}%',)*2)
    return api
