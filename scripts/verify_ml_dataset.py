import argparse
import csv
import itertools
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from build_ml_dataset import (ROOT, CATEGORICAL_FEATURES, NUMERIC_FEATURES,
                              digest, features_at, save_json, simulate_product)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(folder, catalog_path=ROOT/'data/ml_catalog_snapshot.json'):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    config = manifest['config']
    require(digest(catalog_path) == manifest['catalog_sha256'], 'El catálogo cambió desde la generación.')
    start, end = (date.fromisoformat(config[k]) for k in ('start_date', 'end_date'))
    day = timedelta(days=1)
    counts, observed_skus, boundaries = Counter(), set(), {}
    for name, info in manifest['files'].items():
        require(digest(folder/name) == info['sha256'], f'Hash incorrecto: {name}')
        require(digest(folder/info['gzip_file']) == info['gzip_sha256'], f'Hash gzip incorrecto: {name}')
    with (folder/'inventario_ventas_diarias.csv').open(encoding='utf-8-sig', newline='') as raw_file, \
            (folder/'entrenamiento_ventas_7d.csv').open(encoding='utf-8-sig', newline='') as train_file:
        raw_reader, train_reader = csv.DictReader(raw_file), csv.DictReader(train_file)
        require(raw_reader.fieldnames == manifest['raw_columns'], 'Esquema diario distinto al manifest.')
        require(train_reader.fieldnames == manifest['training_columns'], 'Esquema de entrenamiento distinto.')
        train_groups = iter(itertools.groupby(train_reader, key=lambda x: x['sku']))
        for sku, records in itertools.groupby(raw_reader, key=lambda x: x['sku']):
            require(sku not in observed_skus, f'SKU duplicado fuera de orden: {sku}')
            observed_skus.add(sku)
            raw = list(records)
            text = {'fecha', 'sku', 'categoria', 'familia', 'marca', 'fuente_datos'}
            raw = [{k: v if k in text else int(v) for k, v in r.items()} for r in raw]
            require(len(raw) == (end-start).days+1, f'Días faltantes: {sku}')
            sums = {key: [0] for key in ['ventas_pagadas', 'vistas_producto', 'adiciones_carrito',
                                       'unidades_devueltas', 'quiebre_observado', 'chequeos_con_stock']}
            for i, r in enumerate(raw):
                require(r['fecha'] == (start+i*day).isoformat(), f'Día repetido o fuera de secuencia: {sku}')
                require(r['fuente_datos'] == 'simulado', 'Fuente no identificada.')
                require(all(v >= 0 for k, v in r.items() if k not in text), 'Valor diario negativo.')
                require(r['stock_fin'] == r['stock_inicio']+r['ingresos_compra']+
                        r['devoluciones_reingresadas']-r['mermas']-r['ventas_pagadas'], 'Balance físico incorrecto.')
                require(r['reservado_fin'] == r['reservado_inicio']+r['reservas_creadas']-
                        r['reservas_pagadas']-r['reservas_canceladas'], 'Balance de reserva incorrecto.')
                require(r['disponible_fin'] == r['stock_fin']-r['reservado_fin'], 'Disponible incorrecto.')
                require(r['adiciones_carrito'] <= r['vistas_producto'], 'Más carritos que vistas.')
                require(r['chequeos_con_stock'] <= r['chequeos_disponibilidad'], 'Exposición incorrecta.')
                require(r['devoluciones_reingresadas'] <= r['unidades_devueltas'], 'Devoluciones incorrectas.')
                require(r['compras_vencidas_fin'] <= r['compras_transito_fin'], 'Compra vencida fuera de tránsito.')
                previous = raw[i-1] if i else None
                expected_revenue = ((r['ventas_pagadas']-r['reservas_pagadas'])*r['precio_centimos'] +
                                    r['reservas_pagadas']*(previous['precio_centimos'] if previous else 0))
                require(r['ingreso_bruto_centimos'] == expected_revenue, 'Importes no concilian con ventas y reservas.')
                require(r['precio_centimos'] > r['costo_unitario_centimos'], 'Precio inferior al costo supuesto.')
                incoming = previous['compras_transito_fin'] if previous else 0
                require(r['compras_transito_fin'] == incoming+r['compras_solicitadas']-r['ingresos_compra'], 'Compras no concilian.')
                if previous:
                    require((r['stock_inicio'], r['reservado_inicio']) ==
                            (previous['stock_fin'], previous['reservado_fin']), 'Discontinuidad de inventario.')
                for key, series in sums.items():
                    series.append(series[-1]+r[key])
                counts['daily_rows_checked'] += 1
            train_sku, records = next(train_groups)
            require(train_sku == sku, 'SKU de entrenamiento sin historia correspondiente.')
            expected_dates = set()
            for i in range(55, len(raw)-7):
                cutoff = start+i*day
                if any(cutoff < date.fromisoformat(config[k]) <= cutoff+7*day
                       for k in ['validation_start', 'test_start']):
                    continue
                expected_dates.add(cutoff.isoformat())
            actual_dates = set()
            for row in records:
                cutoff = date.fromisoformat(row['fecha_corte'])
                i = (cutoff-start).days
                require(row['fecha_corte'] not in actual_dates, 'Clave fecha/SKU duplicada.')
                actual_dates.add(row['fecha_corte'])
                require(55 <= i < len(raw)-7, 'Ventana insuficiente.')
                require(row['fecha_objetivo_inicio'] == (cutoff+day).isoformat() and
                        row['fecha_objetivo_fin'] == (cutoff+7*day).isoformat(), 'Horizonte incorrecto.')
                require(int(row['objetivo_ventas_7d']) == sums['ventas_pagadas'][i+8]-sums['ventas_pagadas'][i+1],
                        'Objetivo no coincide con los 7 días siguientes.')
                require(int(row['diagnostico_quiebre_futuro_7d']) ==
                        sums['quiebre_observado'][i+8]-sums['quiebre_observado'][i+1], 'Diagnóstico futuro incorrecto.')
                for window in (7, 14, 28, 56):
                    require(int(row[f'ventas_{window}d']) == sums['ventas_pagadas'][i+1]-sums['ventas_pagadas'][i+1-window],
                            'Ventana de ventas contiene fechas incorrectas.')
                for lag in (0, 1, 7, 14, 28):
                    name = 'ventas_hoy' if lag == 0 else f'ventas_lag_{lag}'
                    require(int(row[name]) == raw[i-lag]['ventas_pagadas'], 'Lag incorrecto.')
                for window in (7, 28):
                    for prefix, key in [('vistas', 'vistas_producto'), ('carritos', 'adiciones_carrito'), ('quiebres', 'quiebre_observado')]:
                        require(int(row[f'{prefix}_{window}d']) == sums[key][i+1]-sums[key][i+1-window], 'Ventana auxiliar incorrecta.')
                require(float(row['base_promedio_28d']) == int(row['ventas_28d'])/4 and
                        int(row['base_ultima_semana']) == int(row['ventas_7d']), 'Baseline incorrecto.')
                expected_split = ('prueba' if cutoff >= date.fromisoformat(config['test_start']) else
                                  'validacion' if cutoff >= date.fromisoformat(config['validation_start']) else 'entrenamiento')
                require(row['particion'] == expected_split, 'Partición temporal incorrecta.')
                limits = boundaries.setdefault(expected_split, [cutoff, cutoff, cutoff+7*day])
                limits[0], limits[1], limits[2] = min(limits[0], cutoff), max(limits[1], cutoff), max(limits[2], cutoff+7*day)
                counts['training_rows_checked'] += 1
            require(actual_dates == expected_dates, 'Faltan filas o se incluyeron fechas sin purgar.')
        require(next(train_groups, None) is None, 'Existen SKU adicionales de entrenamiento.')
    require(boundaries['entrenamiento'][2] < boundaries['validacion'][0], 'Etiquetas de entrenamiento invaden validación.')
    require(boundaries['validacion'][2] < boundaries['prueba'][0], 'Etiquetas de validación invaden prueba.')
    require(counts['daily_rows_checked'] == manifest['counts']['daily_rows'] and
            counts['training_rows_checked'] == manifest['counts']['training_rows'], 'Conteos distintos del manifest.')
    require(len(observed_skus) == manifest['products'], 'Cantidad de productos incorrecta.')
    feature_names = set(CATEGORICAL_FEATURES + NUMERIC_FEATURES)
    require(not feature_names.intersection(manifest['excluded_from_features']), 'Metadatos/objetivos incluidos en features.')
    # Independent deterministic replay and prefix test on five SKUs: extending the future
    # must not change earlier inventory, prices, events or predictors.
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))['products']
    for product in catalog[::max(1, len(catalog)//5)][:5]:
        full = simulate_product(product, config)
        prefix = simulate_product(product, config, start+365*day)
        require(full[:366] == prefix, 'La simulación usa información posterior al corte.')
        require(features_at(full, 300) == features_at(prefix, 300), 'Features cambian al agregar datos futuros.')
        altered = full[:301] + [{**r, 'ventas_pagadas': 99999} for r in full[301:]]
        require(features_at(full, 300) == features_at(altered, 300), 'Filtración de ventas futuras en features.')
    report = {'status': 'passed', **counts, 'products_checked': len(observed_skus),
              'prefix_invariance_skus': 5, 'future_label_purge': 'passed',
              'inventory_reservations_purchases_revenue': 'passed', 'hashes': 'passed',
              'note': 'Verifica coherencia del dataset simulado; no evalúa precisión predictiva real.'}
    save_json(folder/'quality.json', report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, default=ROOT/'data/ml/roda-v1')
    parser.add_argument('--catalog', type=Path, default=ROOT/'data/ml_catalog_snapshot.json')
    args = parser.parse_args()
    verify(args.folder, args.catalog)
