"""Ciclo persistente para el historial observado de la tienda, sin rellenar huecos."""
import json
import uuid
from datetime import date, datetime, timedelta
from backend.db import connect, now
from backend.services import ml_lab as lab

DATASET = 'roda-operacion-diaria'


def init():
    lab.init()
    with lab.connection() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS automation(
          id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 1,
          next_check TEXT,last_check TEXT,lease_until TEXT,lease_token TEXT,
          pending_job TEXT,candidate TEXT,last_training_cutoff TEXT,
          message TEXT,quality TEXT NOT NULL DEFAULT '{}');
        """)
        c.execute("""INSERT OR IGNORE INTO datasets VALUES(
          ?, 'RODA · ventas observadas', 'daily',
          'Cierres diarios completos de la tienda. Ventas pagadas; no incluye el carrito ni archivos externos.',
          0,0,NULL,?)""", (DATASET, now()))
        c.execute("INSERT OR IGNORE INTO automation(id,next_check,message) VALUES(1,?,?)",
                  (now(), 'Pendiente de revisar los cierres diarios.'))


def status():
    with lab.connection() as c:
        state = lab.row(c, 'SELECT * FROM automation WHERE id=1')
        state['quality'] = json.loads(state['quality'])
        state['dataset'] = DATASET
        state['active_version'] = lab.dataset(c, DATASET)['active_version']
        prediction = lab.row(c, "SELECT id,result FROM jobs WHERE dataset=? AND action='predict' AND status='done' ORDER BY rowid DESC LIMIT 1", (DATASET,))
        state['prediction'] = None
        if prediction:
            result = json.loads(prediction['result'])
            state['prediction'] = dict(id=prediction['id'], cutoff=result['cutoff'],
                                       count=len(result['items']), version=result['version'])
        state['versions'] = [dict(r) for r in c.execute(
            'SELECT id,label,created_at,report FROM versions WHERE dataset=? ORDER BY created_at', (DATASET,))]
        for v in state['versions']:
            v['report'] = json.loads(v['report'])
        state['history'] = [dict(r) for r in c.execute(
            'SELECT action,detail,created_at FROM activity WHERE dataset=? ORDER BY id DESC LIMIT 12', (DATASET,))]
        state.pop('lease_token', None)
        return state


def recover():
    # The local app runs one backend process. Resume interrupted orchestration on startup.
    with lab.connection() as c:
        c.execute('UPDATE automation SET lease_until=NULL,lease_token=NULL,next_check=? WHERE id=1 AND (pending_job IS NOT NULL OR lease_until IS NOT NULL)', (now(),))


def configure(enabled, uid):
    if not isinstance(enabled, bool):
        raise ValueError('Indica si la revisión automática estará activa.')
    with lab.connection() as c:
        c.execute('UPDATE automation SET enabled=?,next_check=? WHERE id=1', (int(enabled), now()))
        lab.event(c, DATASET, 'programacion', {'enabled': enabled}, uid)
    return status()


def sync():
    """Solo días cerrados: un día ausente no es un día de ventas cero."""
    today = now()[:10]
    with connect() as store:
        observations = [dict(r) for r in store.execute(
            'SELECT date,payload FROM ml_daily WHERE complete=1 AND date<? ORDER BY date', (today,))]
        total = store.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    records = []
    for r in observations:
        raw = json.loads(r['payload'])
        units = raw.get('ventas_pagadas')
        if (raw.get('fuente_datos') != 'operacion' or raw.get('_missing_policy')
                or raw.get('_incomplete_reason') or not isinstance(units, int) or units < 0):
            continue
        records.append((DATASET, raw['sku'], r['date'], units, None))
    with lab.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        valid_keys = {(r[1], r[2]) for r in records}
        saved_keys = {(r['sku'], r['period']) for r in c.execute(
            'SELECT sku,period FROM observations WHERE dataset=?', (DATASET,))}
        if not saved_keys <= valid_keys:
            raise ValueError('Un cierre utilizado dejó de estar completo o disponible. Revisa el origen del historial.')
        for record in records:
            old = c.execute('SELECT units FROM observations WHERE dataset=? AND sku=? AND period=?', record[:3]).fetchone()
            if old and old['units'] != record[3]:
                raise ValueError('Un cierre ya utilizado cambió. Revisa su trazabilidad antes de entrenar.')
        c.executemany('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)', records)
        rows = list(c.execute('SELECT sku,period,units FROM observations WHERE dataset=? ORDER BY sku,period', (DATASET,)))
    days = {}
    for r in rows:
        days.setdefault(r['sku'], {})[r['period']] = r['units']
    end = (date.fromisoformat(today)-timedelta(days=1)).isoformat()
    eligible, longest, positive, train_rows = [], 0, 0, 0
    for sku, history in days.items():
        cursor = date.fromisoformat(end)
        streak = 0
        while cursor.isoformat() in history:
            streak += 1
            cursor -= timedelta(days=1)
        longest = max(longest, streak)
        if streak >= 90:
            eligible.append(sku)
            train_rows += max(0, streak-76)
            positive += sum(v > 0 for k, v in history.items() if k > cursor.isoformat())
    return dict(rows=len(rows), products=len(days), catalog_products=total, eligible=len(eligible),
                consecutive_days=longest, required_days=90, positive_days=positive,
                required_positive_days=30, training_rows=train_rows,
                cutoff=end, ready=bool(eligible) and positive >= 30 and train_rows >= 100)


def tick(force=False, uid=None):
    """Claim persistente: una revisión a la vez, reintento tras interrupción."""
    stamp = now()
    token = uuid.uuid4().hex
    with lab.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        s = lab.row(c, 'SELECT * FROM automation WHERE id=1')
        if s['lease_until'] and s['lease_until'] > stamp:
            return dict(message='Ya hay una revisión en curso.')
        if not force and (not s['enabled'] or (s['next_check'] and s['next_check'] > stamp)):
            return None
        c.execute('UPDATE automation SET lease_until=?,lease_token=?,last_check=? WHERE id=1',
                  ((datetime.fromisoformat(stamp)+timedelta(minutes=20)).isoformat(), token, stamp))
    try:
        message, delay = review(s, uid)
    except Exception as exc:
        message, delay = 'Revisión pendiente de reintento: '+str(exc)[:600], 1
    with lab.connection() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT 1 FROM automation WHERE lease_token=?', (token,)).fetchone():
            c.execute('UPDATE automation SET message=?,next_check=?,lease_until=NULL,lease_token=NULL WHERE id=1',
                      (message, (datetime.fromisoformat(stamp)+timedelta(days=delay)).isoformat()))
            lab.event(c, DATASET, 'revision_automatica' if not force else 'revision_manual', {'message': message}, uid)
    return dict(message=message)


def update(**values):
    allowed = {'pending_job', 'candidate', 'last_training_cutoff', 'quality'}
    assert set(values) <= allowed
    with lab.connection() as c:
        c.execute('UPDATE automation SET '+','.join(k+'=?' for k in values)+' WHERE id=1', list(values.values()))


def refresh_prediction(active, cutoff, uid):
    if not active:
        return False
    with lab.connection() as c:
        last = lab.row(c, "SELECT result FROM jobs WHERE dataset=? AND action='predict' AND status='done' ORDER BY rowid DESC LIMIT 1", (DATASET,))
    if last:
        result = json.loads(last['result'])
        if result['version'] == active and result['cutoff'] >= cutoff:
            return False
    job = lab.start_job(DATASET, 'predict', uid, [active], managed=True)
    update(pending_job=job['id'])
    return True


def review(state, uid):
    quality = sync()
    update(quality=json.dumps(quality))
    with lab.connection() as c:
        d = lab.dataset(c, DATASET)
        pending = lab.row(c, 'SELECT * FROM jobs WHERE id=?', (state['pending_job'],)) if state['pending_job'] else None
    if pending:
        if pending['status'] == 'running':
            return 'Cálculo en curso. La tienda puede seguir recibiendo pedidos.', 1/1440
        if pending['status'] == 'error':
            update(pending_job=None)
            return 'El cálculo falló: '+(pending['error'] or '')+'. Se volverá a revisar.', 1
        result = json.loads(pending['result'])
        if pending['action'] == 'train':
            update(last_training_cutoff=result['cutoff'])
            if not result['beats_baseline'] or min(x['mae'] for x in result['candidates']) >= result['validation_baseline']['mae']*.99:
                update(candidate=None, pending_job=None)
                return 'Versión guardada, sin activar: no reduce al menos 1% el error frente a la referencia en validación.', 1
            update(candidate=pending['id'], pending_job=None)
            return ('Primera versión guardada, sin activar. Esperando 28 días posteriores para comprobarla frente al promedio histórico.'
                    if not d['active_version'] else 'Nueva candidata guardada. Esperando 28 días posteriores para compararla con la activa.'), 1
        if pending['action'] == 'compare':
            scores = {x['version']: x['mae'] for x in result['scores']}
            candidate = state['candidate']
            promote = (candidate in scores and candidate == result.get('recommended')
                       and scores[candidate] < result['baseline']['mae']*.99
                       and (not d['active_version'] or
                            d['active_version'] in scores and scores[candidate] < scores[d['active_version']]*.99))
            if promote:
                lab.activate(DATASET, candidate, uid, managed=True)
            update(candidate=None, pending_job=None)
            active = candidate if promote else d['active_version']
            if active:
                job = lab.start_job(DATASET, 'predict', uid, [active], managed=True)
                update(pending_job=job['id'])
                return ('Candidata aprobada y activada.' if promote else 'Se conserva la versión activa: la candidata no supera ambos controles.')+' Actualizando pronósticos.', 1/1440
            return 'Primera versión no aprobada: no supera al promedio histórico en ventas posteriores. Se reunirán más datos.', 1
        if pending['action'] == 'predict':
            update(pending_job=None)
            return 'Pronósticos actualizados con la versión activa. Comprobando el siguiente paso del ciclo.', 1/1440
    if state['candidate']:
        with lab.connection() as c:
            version = lab.row(c, 'SELECT report FROM versions WHERE id=?', (state['candidate'],))
        cutoff = json.loads(version['report'])['cutoff']
        elapsed = (date.fromisoformat(quality['cutoff'])-date.fromisoformat(cutoff)).days
        if elapsed < 28:
            if refresh_prediction(d['active_version'], quality['cutoff'], uid):
                return 'Actualizando pronósticos con la activa mientras la candidata reúne ventas posteriores para evaluación.', 1/1440
            return f'Candidata en observación: faltan {28-elapsed} días para evaluar ventas posteriores al entrenamiento.', 1
        ids = [d['active_version'], state['candidate']] if d['active_version'] else [state['candidate']]
        job = lab.start_job(DATASET, 'compare', uid, ids, managed=True)
        update(pending_job=job['id'])
        return 'Comparando ambas versiones sobre las mismas ventas posteriores, sin reentrenarlas.', 1/1440
    if not quality['ready']:
        return (f'Acumulando historial: {quality["consecutive_days"]}/90 cierres consecutivos; '
                f'{quality["positive_days"]}/30 observaciones con ventas; '
                f'{quality["training_rows"]}/100 ejemplos para la primera ventana. No se entrena todavía.'), 1
    if state['last_training_cutoff']:
        elapsed = (date.fromisoformat(quality['cutoff'])-date.fromisoformat(state['last_training_cutoff'])).days
        if elapsed < 30:
            # New inputs can change forecasts without creating a new trained version.
            if refresh_prediction(d['active_version'], quality['cutoff'], uid):
                return 'Actualizando el pronóstico con nuevos cierres; se mantiene el mismo modelo.', 1/1440
            return f'Versión conservada. Faltan {30-elapsed} días nuevos para revisar el siguiente entrenamiento.', 1
    job = lab.start_job(DATASET, 'train', uid, managed=True)
    update(pending_job=job['id'])
    return 'Entrenando cinco algoritmos con los cierres observados. Se guardará una nueva versión candidata.', 1/1440
