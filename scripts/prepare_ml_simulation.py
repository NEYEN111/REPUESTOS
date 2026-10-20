"""Prepara un ensayo diario reproducible calibrado con Car Parts (Zenodo).

Los SKU, fechas y asignaciones diarias son sintéticos. No se escriben ventas
ni existencias en la base operativa de RODA.
"""
import argparse
import calendar
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from backend.db import ROOT, connect


SOURCE = ROOT/'ml/examples/carparts/01_historial_inicial.csv'
SOURCE_META = ROOT/'ml/examples/carparts/provenance.json'
OUT = ROOT/'ml/examples/roda-ensayo'
N_PRODUCTS = 120
SEED = 104729


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(end=None):
    end = end or date(2026, 10, 19)
    if end >= datetime.now(ZoneInfo('America/Lima')).date():
        raise ValueError('El último día debe estar cerrado.')
    with connect() as c:
        skus = sorted(r['sku'] for r in c.execute('SELECT sku FROM products WHERE active=1'))
    if len(skus) < N_PRODUCTS:
        raise ValueError('Se necesitan al menos 120 productos activos en el catálogo.')
    metadata = json.loads(SOURCE_META.read_text(encoding='utf-8'))
    if sha(ROOT/'ml/examples/carparts/source.zip') != metadata['source_sha256']:
        raise ValueError('La fuente Car Parts no coincide con la procedencia verificada.')
    source_entry = next(f for f in metadata['files'] if f['name'] == SOURCE.name)
    if sha(SOURCE) != source_entry['sha256']:
        raise ValueError('Los datos Car Parts fueron modificados.')

    series = defaultdict(list)
    with SOURCE.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['unidades'] != '':
                series[row['sku']].append((row['periodo'], int(row['unidades'])))
    eligible = [(name, values) for name, values in series.items()
                if len(values) >= 30 and sum(units for _, units in values) >= 12]
    eligible.sort(key=lambda item: (sum(v for _, v in item[1]), item[0]))
    chosen = [eligible[min(len(eligible)-1, (i*len(eligible)+len(eligible)//2)//N_PRODUCTS)]
              for i in range(N_PRODUCTS)]
    if len({name for name, _ in chosen}) != N_PRODUCTS:
        raise ValueError('La selección de series no produjo 120 patrones distintos.')

    start = end-timedelta(days=149)
    stages = [[], [], []]
    mapping = []
    for i, (sku, (source_id, values)) in enumerate(zip(skus[:N_PRODUCTS], chosen)):
        mapping.append({'sku': sku, 'serie_fuente': source_id})
        by_month = defaultdict(list)
        for period, units in values:
            by_month[int(period[-2:])].append(units)
        rng = random.Random(SEED+i)
        month = date(start.year, start.month, 1)
        while month <= end:
            days = calendar.monthrange(month.year, month.month)[1]
            total = rng.choice(by_month[month.month] or [v for _, v in values])
            # La fuente es mensual. Se reparte exactamente el total escogido
            # entre días completos con una pauta de días hábiles reproducible.
            weights = [0.65 if date(month.year, month.month, d).weekday() == 6 else 1.0
                       for d in range(1, days+1)]
            daily = [0]*days
            for _ in range(total):
                daily[rng.choices(range(days), weights=weights, k=1)[0]] += 1
            for day, units in enumerate(daily, 1):
                observed = date(month.year, month.month, day)
                if start <= observed <= end:
                    age = (observed-start).days
                    stages[0 if age < 90 else 1 if age < 120 else 2].append((observed.isoformat(), sku, units))
            month = date(month.year+month.month//12, month.month%12+1, 1)

    OUT.mkdir(parents=True, exist_ok=True)
    previous_path = OUT/'provenance.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else {}
    old_csv = next((f for f in previous.get('stages', []) if f['name'] == '02_datos_nuevos_30_dias.csv'), None)
    old_excel = next((f for f in previous.get('stages', []) if f['name'] == '02_datos_nuevos_30_dias.xlsx'), None)
    names = ['01_historial_90_dias.csv', '02_datos_nuevos_30_dias.csv',
             '03_ventas_posteriores_30_dias.csv']
    files = []
    for name, rows in zip(names, stages):
        path = OUT/name
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['periodo', 'sku', 'unidades'])
            writer.writerows(sorted(rows))
        files.append({'name': name, 'rows': len(rows), 'sha256': sha(path),
                      'start': min(row[0] for row in rows), 'end': max(row[0] for row in rows)})
    # Conservar la derivación Excel solo si el CSV nuevo es idéntico al usado
    # al crearla. Si cambia el periodo, el archivo se excluye del manifiesto.
    excel_path = OUT/'02_datos_nuevos_30_dias.xlsx'
    new_csv = next(f for f in files if f['name'] == '02_datos_nuevos_30_dias.csv')
    if (old_csv and old_excel and excel_path.exists()
            and old_csv['sha256'] == new_csv['sha256']
            and old_excel['sha256'] == sha(excel_path)):
        files.append(old_excel)
    manifest = {
        'kind': 'synthetic_calibrated_trial', 'label': 'Ensayo calibrado, no ventas reales de RODA',
        'source_url': metadata['source_url'], 'source_doi': metadata['doi'],
        'source_license': metadata['license'], 'source_sha256': metadata['source_sha256'],
        'source_frequency': 'monthly', 'output_frequency': 'daily',
        'method': '120 series con al menos 30 meses conocidos y 12 unidades, seleccionadas por cuantiles de volumen. Para cada mes se elige determinísticamente un valor mensual histórico del mismo mes y se distribuye entre días con semilla fija. Asociación de series anónimas a SKU existentes solo para el ensayo.',
        'limitations': 'No son transacciones observadas en Perú. La distribución diaria, la fecha y la asociación de SKU son simuladas. La precisión del ensayo no acredita precisión operativa.',
        'seed': SEED, 'products': N_PRODUCTS, 'start': start.isoformat(), 'end': end.isoformat(),
        'stages': files, 'sku_mapping': mapping,
    }
    (OUT/'provenance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--end', type=date.fromisoformat)
    args = parser.parse_args()
    result = prepare(args.end)
    print(f"Ensayo calibrado: {result['products']} SKU, 150 días, "
          f"{sum(f['rows'] for f in result['stages'] if f['name'].endswith('.csv')):,} filas; termina {result['end']}.")
