"""Repeated comparison with real provider calls and disposable SQLite fixtures.

Request instrumentation records real HTTP attempts; no response is mocked.
Dated output never replaces the previous exploratory evaluation.
"""
import argparse
import asyncio
import csv
import gc
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import httpx

os.environ['RODA_FORCE_SQLITE'] = '1'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import db
from backend.agent_scenarios import seed
from backend.services import agents, agent_data as data, llm_provider


class ProviderMeasurements:
    """Observe actual requests, including fallback and failures; never store keys."""
    def __init__(self):
        self.attempts = []
        self.original = llm_provider._request

    async def request(self, provider, model, key, instruction, context, schema):
        started = time.monotonic()
        item = {'provider': provider, 'model': model, 'success': False, 'tokens': 0,
                'error_type': '', 'http_status': None}
        original_post = httpx.AsyncClient.post
        async def observe_http(client, *args, **kwargs):
            response = await original_post(client, *args, **kwargs)
            item['http_status'] = response.status_code
            # Format/usage metadata only: never persist content or reasoning text.
            try:
                payload = response.json()
                usage = payload.get('usage', {})
                if isinstance(usage, dict):
                    item['tokens'] = int(usage.get('total_tokens') or 0)
                    item['usage'] = usage
                choice = (payload.get('choices') or [{}])[0]
                message = choice.get('message') or {}
                item['finish_reason'] = choice.get('finish_reason')
                item['content_characters'] = len(message.get('content') or '')
                item['reasoning_characters'] = len(message.get('reasoning_content') or '')
            except (ValueError, KeyError, TypeError, IndexError):
                item['http_metadata_available'] = False
            return response
        httpx.AsyncClient.post = observe_http
        try:
            result, tokens = await self.original(provider, model, key, instruction, context, schema)
            item.update(success=True, tokens=tokens)
            return result, tokens
        except BaseException as exc:
            item['error_type'] = type(exc).__name__
            item['http_status'] = getattr(getattr(exc, 'response', None), 'status_code', None) or item['http_status']
            if isinstance(exc, json.JSONDecodeError):
                item['json_error_position'] = exc.pos
                item['json_error_document_characters'] = len(exc.doc)
                item['starts_with_json_object'] = exc.doc.lstrip().startswith('{')
            raise
        finally:
            httpx.AsyncClient.post = original_post
            item['seconds'] = round(time.monotonic() - started, 3)
            self.attempts.append(item)

    def begin(self):
        llm_provider._request = self.request
        return self

    def end(self):
        llm_provider._request = self.original


def code_version():
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def save(path, output):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')


def summary(results):
    return {mode: {
        'runs': len(items), 'passed': sum(v['passed'] for v in items),
        'provider_attempts': sum(v['provider_attempts'] for v in items),
        'provider_errors': sum(not a['success'] for v in items for a in v['requests']),
        'tokens_reported': sum(v['tokens_reported'] for v in items),
        'seconds_total': round(sum(v['seconds'] for v in items), 3),
        'seconds_median': round(statistics.median(v['seconds'] for v in items), 3),
    } for mode in ['reglas', 'un_agente', 'multiagente']
        if (items := [r for r in results if r['mode'] == mode])}


async def evaluate(repetitions, path):
    if path.exists():
        raise SystemExit('La salida ya existe. Usa otro nombre para conservar la evidencia previa.')
    original_db = db.DB
    output = {
        'created_at': db.now(), 'status': 'running', 'code_version': code_version(),
        'provider_configured': llm_provider.status(), 'model': agents.model_name(),
        'repetitions': repetitions, 'cases': ['presupuesto', 'ofertas', 'vencidas'],
        'modalities': ['reglas', 'un_agente', 'multiagente'],
        'dataset': 'Fixture académico CONTROL-001, dos ofertas, misma base nueva en cada ejecución.',
        'isolated_database': True, 'real_provider_calls': True,
        'protocol': {
            'design': 'Tres escenarios por tres modalidades, dos repeticiones consecutivas por escenario/modalidad.',
            'expected': 'Presupuesto/ofertas: propuesta por aprobar. Ofertas vencidas: bloqueo.',
            'acceptance': ['Estado esperado', 'Importe dentro del presupuesto', 'Solo ofertas registradas vigentes', 'Sin compras automáticas'],
            'performance_limit_seconds': 360,
            'shared_controls': 'Mismos servicios Python y auditoría determinista. Equipo: revisión por roles. Agente único: interpretación de Compras.',
            'limits': 'Muestra pequeña y académica, un producto. No demuestra superioridad estadística, beneficio económico ni calidad completa de las explicaciones.',
            'tokens': 'Tokens informados por el proveedor. Si una solicitud falla antes de informar uso, cero significa uso desconocido; puede existir cobro no contabilizado.',
        }, 'results': [],
    }
    save(path, output)
    try:
        for case, budget in [('presupuesto', 5000), ('ofertas', 25000), ('vencidas', 25000)]:
            for mode in ['reglas', 'un_agente', 'multiagente']:
                for repetition in range(1, repetitions + 1):
                    with tempfile.TemporaryDirectory(prefix='agent-controls-eval-', dir=ROOT / '.tmp') as folder:
                        db.DB = Path(folder) / 'control.db'
                        seed()
                        if case == 'vencidas':
                            with db.transaction() as c:
                                c.execute("UPDATE supplier_offers SET valid_until='2000-01-01'")
                        rid = data.create_run(data.RunInput(kind='reposicion', budget_cents=budget, product_limit=5,
                            request_key=f'evaluation-{case}-{mode}-{repetition}'), 1, agents.model_name())
                        run = agents.claim()
                        started = time.monotonic()
                        error = ''
                        observed = ProviderMeasurements().begin()
                        try:
                            if mode == 'multiagente':
                                await asyncio.wait_for(agents.execute(run), timeout=360)
                            else:
                                state = {'quality': data.quality('reposicion'), 'inventory': data.candidates(5)}
                                state['plan'] = data.purchase_plan(state['inventory'], 'costo', budget, True)
                                if mode == 'un_agente':
                                    messages = []
                                    decision = await asyncio.wait_for(
                                        agents.specialist('compras', run, state, messages, fit_budget=True), timeout=360)
                                    if decision.action != 'finish' or decision.decision != 'continuar':
                                        state['blocked_reason'] = decision.message or 'Revisión pendiente'
                                    state['explanation'] = decision.message
                                    state['messages'] = messages
                                state['audit'] = data.audit_result(run, state)
                                agents.finish(run, 'revision' if state['audit']['passed'] and not state.get('blocked_reason') else 'bloqueada', state)
                        except Exception as exc:
                            error = type(exc).__name__
                            agents.finish(run, 'error', {'error_type': error})
                        finally:
                            observed.end()
                        result = data.get_run(rid)
                        plan = result['result'].get('plan', {})
                        criteria = {
                            'estado_esperado': result['status'] == ('bloqueada' if case == 'vencidas' else 'revision'),
                            'presupuesto': plan.get('total_cents', 0) <= budget,
                            'ofertas_vigentes': all(l['source'] == 'manual' for l in plan.get('lines', []))
                                and (not plan.get('lines') if case == 'vencidas' else bool(plan.get('lines'))),
                        }
                        with db.connect() as c:
                            criteria['sin_compras_automaticas'] = c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0] == 0
                            criteria['sin_ventas'] = c.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 0
                        elapsed = round(time.monotonic() - started, 3)
                        criteria['dentro_del_plazo'] = elapsed <= 360
                        if mode != 'reglas':
                            criteria['proveedor_real'] = any(v['success'] for v in observed.attempts)
                        entry = {
                            'case': case, 'mode': mode, 'repetition': repetition, 'passed': all(criteria.values()),
                            'criteria': criteria, 'status': result['status'], 'calls': result['calls'],
                            'tokens': result['tokens'], 'provider_attempts': len(observed.attempts),
                            'provider_successes': sum(v['success'] for v in observed.attempts),
                            'tokens_reported': sum(v['tokens'] for v in observed.attempts),
                            'seconds': elapsed, 'total_cents': plan.get('total_cents', 0), 'error': error,
                            'requests': observed.attempts,
                            'effective_models': sorted({v['provider'] + '/' + v['model'] for v in observed.attempts if v['success']}),
                            'evidence': result,
                        }
                        output['results'].append(entry)
                        output['summary'] = summary(output['results'])
                        save(path, output)
                        print(f'{case}/{mode}/{repetition}: {result["status"]}, passed={entry["passed"]}, {elapsed}s, requests={len(observed.attempts)}', flush=True)
                        c.close()
                        db.DB = original_db
                        gc.collect()
        output['status'] = 'completed'
    finally:
        db.DB = original_db
        output['finished_at'] = db.now()
        output['summary'] = summary(output['results'])
        save(path, output)
        fields = ['case', 'mode', 'repetition', 'passed', 'status', 'seconds', 'calls', 'provider_attempts', 'provider_successes', 'tokens_reported', 'total_cents', 'error']
        with path.with_suffix('.csv').open('w', newline='', encoding='utf-8-sig') as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(output['results'])
    print(str(path), flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repetitions', type=int, choices=[1, 2], default=2)
    parser.add_argument('--output', type=Path, default=ROOT / 'ml/evaluations/agents/entrega-2026-10-23.json')
    options = parser.parse_args()
    (ROOT / '.tmp').mkdir(exist_ok=True)
    asyncio.run(evaluate(options.repetitions, options.output.resolve()))
