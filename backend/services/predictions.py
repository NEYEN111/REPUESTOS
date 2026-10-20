import csv
import io
import json
import math
import os
import subprocess
import threading
from datetime import date,timedelta
from pathlib import Path
from backend.db import ROOT,connect,transaction,rows,one,now,audit
from backend.services.catalog import normalize

BUNDLE=ROOT/'ml/deployed/roda-v2'
EVALUATION=ROOT/'ml/evaluations/roda-v2'
EXTERNAL_WEEKLY=ROOT/'ml/evaluations/uci-weekly-v1'
LOCK=threading.Lock()
REASONS={
 'evidencia_insuficiente_global':'El modelo necesita revisión en este conjunto de datos.',
 'evidencia_insuficiente_baja':'En baja rotación, el modelo no supera consistentemente la referencia.',
 'evidencia_insuficiente_media':'La mejora no es suficiente en rotación media.',
 'evidencia_insuficiente_alta':'La mejora no es suficiente en rotación alta.',
 'ventas_limitadas_por_stock_reciente':'Hubo quiebres de stock en los últimos 28 días.',
 'sin_stock_disponible':'No había unidades disponibles al cierre.',
 'intervalo_amplio':'El intervalo es amplio respecto al pronóstico.',
 'plazo_proveedor_mayor_al_horizonte':'El proveedor tarda más de los siete días que cubre el modelo.'}

def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def runtime():
    return Path(os.environ.get('ML_PYTHON',str(ROOT/('.venv-ml/Scripts/python.exe' if os.name=='nt' else '.venv-ml/bin/python'))))
def contract(): return load_json(BUNDLE/'contract.json')

def readiness():
    cutoff=(date.fromisoformat(now()[:10])-timedelta(days=1)).isoformat()
    first=(date.fromisoformat(cutoff)-timedelta(days=55)).isoformat()
    with connect() as c:
        total=one(c,'SELECT COUNT(*) n FROM products WHERE active=1')['n']
        data=rows(c, '''SELECT p.id,p.sku,p.name,COUNT(d.date) days,MIN(d.date) first,MAX(d.date) last,
          COALESCE(SUM(d.complete),0) complete_days,
          SUM(CASE WHEN d.complete=1 AND d.date>=? AND d.date<=? THEN 1 ELSE 0 END) window_days,
          MAX(CASE WHEN d.complete=1 THEN json_extract(d.payload,'$.ventas_pagadas') ELSE 0 END) sold
          FROM products p LEFT JOIN ml_daily d ON d.product_id=p.id WHERE p.active=1 GROUP BY p.id''',(first,cutoff))
        sample=one(c,'SELECT MIN(first_seen) first,MAX(last_seen) last,COUNT(DISTINCT date) days FROM ml_daily')
        continuous={r['product_id']:r for r in rows(c, '''WITH history AS (
          SELECT product_id,date,json_extract(payload,'$.ventas_pagadas') sales,
            ROW_NUMBER() OVER(PARTITION BY product_id ORDER BY date DESC)-1 offset
          FROM ml_daily WHERE complete=1 AND date<=?)
          SELECT product_id,COUNT(*) days,MAX(sales>0) sold FROM history
          WHERE CAST(julianday(?)-julianday(date) AS INTEGER)=offset GROUP BY product_id''',(cutoff,cutoff))}
    known=set(contract()['known_skus'])
    for row in data:
        sequence=continuous.get(row['id'],{})
        row['ready']=row['sku'] in known and sequence.get('days',0)>=56 and bool(sequence.get('sold'))
        row['reason']='Listo para calcular' if row['ready'] else 'Producto fuera del entrenamiento' if row['sku'] not in known else 'Se requieren 56 cierres completos consecutivos y una venta conocida'
    return {'cutoff':cutoff,'total':total,'ready':sum(r['ready'] for r in data),'capture':sample,'products':data,
       'requirements':['56 cierres completos y consecutivos por producto, hasta ayer.',
         '12 observaciones de disponibilidad por día; captura al inicio y al final del día.',
         'Sin cambios de negocio posteriores a la última observación del cierre.',
         'Precio, costo, política de inventario y fecha prevista de compras pendientes.',
         'Fecha de última venta conocida dentro del historial continuo.'],
       'note':'La aplicación debe permanecer encendida para registrar los cierres. Un día incompleto no equivale a cero ventas.'}

def overview():
    info=contract(); ready=readiness()
    with connect() as c:
        runs=rows(c,'SELECT * FROM ml_runs ORDER BY id DESC LIMIT 30')
    for run in runs: run['summary']=json.loads(run['summary'])
    return {'model':info['model_name'],'horizon':info['horizon_days'],'trained_until':info['training_end'],
        'runtime_ready':runtime().is_file(),'runs':runs,'readiness':ready,
        'reference_cutoff':load_json(ROOT/'data/ml/roda-v1/manifest.json')['config']['end_date']}

def calculate(source,uid):
    if source not in ['referencia','operacion']: raise ValueError('Selecciona un origen de historial válido.')
    if not LOCK.acquire(blocking=False): raise ValueError('Ya se está calculando un pronóstico. Espera un momento.')
    try:
        info=contract()
        cutoff=overview()['reference_cutoff'] if source=='referencia' else readiness()['cutoff']
        with connect() as c:
            prior=one(c,'SELECT id FROM ml_runs WHERE source=? AND cutoff=? AND model_hash=?',(source,cutoff,info['model_sha256']))
            if prior: return {'id':prior['id'],'reused':True}
            products=rows(c,'SELECT id,sku FROM products WHERE active=1')
            history=[json.loads(r['payload']) for r in rows(c,'SELECT payload FROM ml_daily WHERE complete=1 AND date<=? ORDER BY product_id,date',(cutoff,))] if source=='operacion' else []
        if source=='operacion' and not history: raise ValueError('Todavía no hay cierres completos. Revisa Calidad del historial.')
        if not runtime().is_file(): raise ValueError('Falta el entorno de inferencia. Reinicia con start.cmd para prepararlo.')
        request={'source':source,'skus':[p['sku'] for p in products],'cutoff':cutoff,'history':history}
        env=dict(os.environ,PYTHONUTF8='1',LOKY_MAX_CPU_COUNT='2')
        try:
            result=subprocess.run([str(runtime()),'-m','ml.web_predict'],input=json.dumps(request),
                    capture_output=True,text=True,encoding='utf-8',cwd=ROOT,env=env,timeout=120,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            output=json.loads(result.stdout)
        except subprocess.TimeoutExpired: raise ValueError('El cálculo excedió el tiempo disponible. Intenta nuevamente.')
        except (OSError,json.JSONDecodeError): raise ValueError('No se pudo iniciar el modelo. Revisa el entorno de inferencia.')
        if result.returncode or 'error' in output: raise ValueError(output.get('error','El modelo no pudo completar el cálculo.'))
        if not output['items']: raise ValueError('Ningún producto tiene las 56 observaciones continuas requeridas y una última venta conocida.')
        ids={p['sku']:p['id'] for p in products}
        summary={k:v for k,v in output.items() if k!='items'}
        summary['review']=sum(p['review'] for p in output['items'])
        summary['units']=sum(p['prediction'] for p in output['items'])
        with transaction() as c:
            rid=c.execute('INSERT INTO ml_runs(source,cutoff,model_hash,created_at,user_id,count,summary) VALUES(?,?,?,?,?,?,?)',
                (source,cutoff,info['model_sha256'],now(),uid,len(output['items']),json.dumps(summary,ensure_ascii=False))).lastrowid
            for p in output['items']:
                c.execute('''INSERT INTO ml_predictions(run_id,product_id,sku,prediction,lower_bound,upper_bound,available,rotation,review,coverage,reasons,features,history)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(rid,ids[p['sku']],p['sku'],p['prediction'],p['lower_bound'],p['upper_bound'],p['available'],p['rotation'],int(p['review']),p['coverage'],
                  json.dumps(p['reasons'],ensure_ascii=False),json.dumps(p['features'],ensure_ascii=False),json.dumps(p['history'],ensure_ascii=False)))
            audit(c,'ml_runs',rid,'calcular',uid,detail={'source':source,'cutoff':cutoff,'model_hash':info['model_sha256']})
        return {'id':rid,'reused':False}
    finally: LOCK.release()

def listing(rid,q='',rotation='',review='',sort='prediction',direction='desc',page=1,limit=15):
    with connect() as c:
        run=one(c,'SELECT * FROM ml_runs WHERE id=?',(rid,))
        if not run: raise ValueError('No se encontró el pronóstico.')
        data=rows(c,'''SELECT m.id,m.sku,m.product_id,m.prediction,m.lower_bound,m.upper_bound,m.available,m.rotation,m.review,
          m.coverage,m.reasons,m.actual,p.name,p.stock-p.reserved current_available,c.name category,
          (SELECT thumb FROM product_images WHERE product_id=p.id ORDER BY is_primary DESC,id LIMIT 1) image
          FROM ml_predictions m JOIN products p ON p.id=m.product_id JOIN categories c ON c.id=p.category_id WHERE m.run_id=?''',(rid,))
    for p in data:
        p['reasons']=[REASONS.get(r,r) for r in json.loads(p['reasons'])]
    if q: data=[p for p in data if normalize(q) in normalize(p['name']+' '+p['sku']+' '+p['category'])]
    if rotation: data=[p for p in data if p['rotation']==rotation]
    if review in ['si','no']: data=[p for p in data if bool(p['review'])==(review=='si')]
    key=sort if sort in ['name','sku','prediction','available','rotation'] else 'prediction'
    data.sort(key=lambda p:p[key],reverse=direction=='desc')
    total=len(data);limit=min(100,max(1,limit));page=max(1,page)
    run['summary']=json.loads(run['summary'])
    run['stale']=run['source']=='operacion' and run['cutoff']<(date.fromisoformat(now()[:10])-timedelta(days=1)).isoformat()
    return {'items':data[(page-1)*limit:page*limit],'total':total,'pages':math.ceil(total/limit),'page':page,'run':run}

def detail(pid):
    with connect() as c:
        p=one(c,'''SELECT m.*,p.name,p.stock-p.reserved current_available,r.source,r.cutoff,r.created_at,
            ip.lead_days,ip.pack_size FROM ml_predictions m JOIN products p ON p.id=m.product_id
            JOIN ml_runs r ON r.id=m.run_id LEFT JOIN inventory_policy ip ON ip.product_id=p.id WHERE m.id=?''',(pid,))
    if not p: raise ValueError('Pronóstico no encontrado.')
    for key in ['features','history','reasons']: p[key]=json.loads(p[key])
    p['reasons']=[REASONS.get(r,r) for r in p['reasons']]
    return p

def evaluation():
    summary=load_json(EVALUATION/'dashboard.json')
    quality=load_json(EVALUATION/'robustness.json')
    return {'data':summary['data'],'selection':summary['selection'],'evaluation':summary['evaluation'],
       'models':quality['models'],'assets':summary['assets'],'policy':quality['policy'],
       'methodology':quality['methodology'],'limitations':summary['limitations'],
       'test_status':quality['test_status'],'run_id':quality['evaluation_id'],
       'external_weekly':load_json(EXTERNAL_WEEKLY/'report.json')}

def external_image(name):
    if name not in {'01_metodos.png','02_rotacion.png'}:
        raise ValueError('Gráfico no encontrado.')
    return EXTERNAL_WEEKLY/'images'/name

def asset(name):
    allowed={Path(a['png']).name for a in load_json(EVALUATION/'dashboard.json')['assets']}
    if name not in allowed: raise ValueError('Gráfico no encontrado.')
    return EVALUATION/'images'/name

def export(rid):
    # Export through the same authorization as the screen; escaped spreadsheet cells.
    with connect() as c:
        run=one(c,'SELECT source,cutoff FROM ml_runs WHERE id=?',(rid,))
        if not run: raise ValueError('Pronóstico no encontrado.')
        data=rows(c,'''SELECT m.sku,p.name,m.prediction,m.lower_bound,m.upper_bound,m.available,m.rotation,m.review,m.actual
            FROM ml_predictions m JOIN products p ON p.id=m.product_id WHERE run_id=? ORDER BY m.sku''',(rid,))
    out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['origen','fecha_corte','sku','producto','ventas_7d','limite_inferior','limite_superior','disponible_al_corte','rotacion','revision','ventas_observadas'])
    for p in data:
        values=[run['source'],run['cutoff'],*p.values()]
        writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in values])
    return '\ufeff'+out.getvalue()
