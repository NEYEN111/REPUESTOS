import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import shutil
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from statistics import pstdev

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'data/ml_simulation_config.json'
CATALOG = ROOT / 'data/ml_catalog_snapshot.json'
DAY = timedelta(days=1)

RAW_FIELDS = '''fecha sku categoria familia marca universal fuente_datos
stock_inicio reservado_inicio ingresos_compra devoluciones_reingresadas mermas
ventas_pagadas reservas_creadas reservas_pagadas reservas_canceladas
stock_fin reservado_fin disponible_fin compras_solicitadas compras_transito_fin
compras_vencidas_fin minimo maximo plazo_proveedor_dias lote_compra
precio_lista_centimos descuento_pct precio_centimos costo_unitario_centimos
ingreso_bruto_centimos importe_devuelto_centimos unidades_devueltas
vistas_producto adiciones_carrito chequeos_disponibilidad chequeos_con_stock
quiebre_observado'''.split()

CATEGORICAL_FEATURES = ['sku', 'categoria', 'familia', 'marca']
NUMERIC_FEATURES = '''universal dia_semana_siguiente mes_siguiente dia_mes_siguiente
fin_mes_proximos_7d ventas_hoy ventas_lag_1 ventas_lag_7 ventas_lag_14 ventas_lag_28
ventas_7d ventas_14d ventas_28d ventas_56d desviacion_ventas_28d dias_sin_ventas_28d
dias_desde_ultima_venta diferencia_ventas_semanas vistas_7d vistas_28d carritos_7d
carritos_28d devoluciones_28d quiebres_7d quiebres_28d proporcion_stock_28d
stock_fin reservado_fin disponible_fin compras_transito_fin compras_vencidas_fin
minimo maximo plazo_proveedor_dias lote_compra precio_centimos costo_unitario_centimos
descuento_pct'''.split()
TARGET = 'objetivo_ventas_7d'
TRAIN_FIELDS = ['fecha_corte', *CATEGORICAL_FEATURES, 'fuente_datos', 'particion',
                *NUMERIC_FEATURES, 'fecha_objetivo_inicio', 'fecha_objetivo_fin', TARGET,
                'diagnostico_quiebre_futuro_7d', 'base_ultima_semana', 'base_promedio_28d']


def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'big')


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot_catalog(database, output):
    # Explicit read-only connection. Never initialize, migrate or seed the live store here.
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        products = [dict(row) for row in conn.execute('''
            SELECT p.id AS producto_id, p.sku, p.name AS nombre, c.slug AS categoria,
                   parent.slug AS familia, b.name AS marca, p.universal,
                   p.price_cents AS precio_referencia_centimos,
                   p.cost_cents AS costo_referencia_centimos,
                   ip.lead_days AS plazo_proveedor_dias, ip.pack_size AS lote_compra
            FROM products p JOIN categories c ON c.id=p.category_id
            JOIN categories parent ON parent.id=c.parent_id
            JOIN brands b ON b.id=p.brand_id
            JOIN inventory_policy ip ON ip.product_id=p.id
            ORDER BY p.sku
        ''')]
        count = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
        if len(products) != count:
            raise ValueError('Hay productos sin categoría, marca o política de inventario.')
    validate_catalog(products)
    save_json(output, {'source': 'catalogo_demo_roda', 'contains_customer_data': False,
                       'note': 'Precios y costos del catálogo académico, no historia de precios reales.',
                       'products': products})


def validate_catalog(products):
    if not products or len({p['sku'] for p in products}) != len(products):
        raise ValueError('El catálogo debe contener SKU únicos y no estar vacío.')
    for p in products:
        if not (0 < p['costo_referencia_centimos'] < p['precio_referencia_centimos']):
            raise ValueError(f"Precio/costo inválido: {p['sku']}")
        if p['plazo_proveedor_dias'] < 1 or p['lote_compra'] < 1:
            raise ValueError(f"Política inválida: {p['sku']}")


def poisson(rng, mean):
    limit, probability, count = math.exp(-mean), 1.0, 0
    while probability > limit:
        probability *= rng.random()
        count += 1
    return max(0, count - 1)


def count_chances(rng, count, probability):
    return sum(rng.random() < probability for _ in range(count))


def scale_cents(value, basis_points):
    return (value * basis_points + 5000) // 10000


def simulate_product(product, config, end_date=None):
    rng = random.Random(stable_seed(config['seed'], product['sku']))
    start = date.fromisoformat(config['start_date'])
    end = end_date or date.fromisoformat(config['end_date'])
    group = rng.choices(range(3), config['rotation_probabilities'])[0]
    rate = rng.uniform(*config['daily_base_rate_ranges'][group])
    if product['familia'] in ('filtros', 'aceites-y-fluidos', 'frenos'):
        rate *= 1.25
    lead, pack = product['plazo_proveedor_dias'], product['lote_compra']
    minimum = max(1, math.ceil(rate * (lead + 5)))
    maximum = max(minimum + 2, math.ceil(rate * (lead + 26)))
    stock = rng.randint(minimum, maximum)
    reserved = 0
    pending, purchases, returns = [], [], []
    history = []
    price_base = product['precio_referencia_centimos']
    cost_base = product['costo_referencia_centimos']
    phase = rng.uniform(0, math.tau)
    trend = rng.uniform(-0.14, 0.20)
    elasticity = rng.uniform(0.6, 1.8)
    variation = 0.0
    promo_until, discount, last_sale = -1, 0, -1
    for index in range((end - start).days + 1):
        today = start + index * DAY
        row = dict.fromkeys(RAW_FIELDS, 0)
        row.update({k: product[k] for k in CATEGORICAL_FEATURES + ['universal']})
        row.update(fecha=today.isoformat(), fuente_datos=config['source'],
                   stock_inicio=stock, reservado_inicio=reserved,
                   plazo_proveedor_dias=lead, lote_compra=pack)
        due = [x for x in purchases if x['actual'] <= index]
        purchases = [x for x in purchases if x['actual'] > index]
        row['ingresos_compra'] = sum(x['quantity'] for x in due)
        stock += row['ingresos_compra']
        for quantity, paid_price in pending:
            paid = count_chances(rng, quantity, config['reservation_payment_probability'])
            row['reservas_pagadas'] += paid
            row['reservas_canceladas'] += quantity - paid
            row['ventas_pagadas'] += paid
            row['ingreso_bruto_centimos'] += paid * paid_price
            stock -= paid
            for _ in range(count_chances(rng, paid, config['return_probability'])):
                returns.append((index + rng.randint(2, 15), paid_price))
        pending, reserved = [], 0
        returned = [x for x in returns if x[0] <= index]
        returns = [x for x in returns if x[0] > index]
        row['unidades_devueltas'] = len(returned)
        row['importe_devuelto_centimos'] = sum(x[1] for x in returned)
        row['devoluciones_reingresadas'] = count_chances(
            rng, len(returned), config['return_restock_probability'])
        stock += row['devoluciones_reingresadas']
        if stock and rng.random() < config['loss_probability_per_sku_day']:
            row['mermas'] = 1
            stock -= 1
        if index > promo_until:
            discount = 0
            if rng.random() < 0.025:
                discount = rng.choice([5, 8, 10, 12])
                promo_until = index + rng.randint(3, 7)
        # Integer cents throughout. Changes use a fixed epoch, never the dataset end date.
        cost = scale_cents(cost_base, 10000 + 45 * (index // 90))
        list_price = max(scale_cents(price_base, 10000 + 55 * (index // 90)),
                         scale_cents(cost, 13000))
        price = scale_cents(list_price, 10000 - discount * 100)
        row.update(precio_lista_centimos=list_price, descuento_pct=discount,
                   precio_centimos=price, costo_unitario_centimos=cost)
        variation = 0.85 * variation + rng.gauss(0, 0.10)
        seasonal = 1 + 0.18 * math.sin(math.tau * today.timetuple().tm_yday / 365.25 + phase)
        seasonal *= 1.16 if today.month in (7, 12) else 1
        weekly = [1.02, 1.03, 1.0, 1.06, 1.20, 1.13, 0.65][today.weekday()]
        market = random.Random(stable_seed(config['seed'], 'market', index // 7)).uniform(0.8, 1.2)
        traffic = rate * seasonal * weekly * market * math.exp(variation + trend * index / 365.25)
        if group == 0:
            traffic *= 3.4 if rng.random() < 0.16 else 0.55
        traffic *= (price / price_base) ** -elasticity
        slots = config['availability_checks_per_day']
        row['chequeos_disponibilidad'] = slots
        for _ in range(slots):
            available = stock - reserved
            row['chequeos_con_stock'] += int(available > 0)
            views = poisson(rng, traffic / (0.18 * 0.45) / slots)
            row['vistas_producto'] += views
            carts = count_chances(rng, views, config['view_to_cart_probability']) if available else 0
            row['adiciones_carrito'] += carts
            for _ in range(count_chances(rng, carts, config['cart_to_checkout_probability'])):
                quantity = min(stock - reserved, 2 if rng.random() < 0.12 else 1)
                if not quantity:
                    continue
                if rng.random() < config['reservation_probability']:
                    pending.append((quantity, price))
                    reserved += quantity
                    row['reservas_creadas'] += quantity
                else:
                    stock -= quantity
                    row['ventas_pagadas'] += quantity
                    row['ingreso_bruto_centimos'] += quantity * price
                    for _ in range(count_chances(rng, quantity, config['return_probability'])):
                        returns.append((index + rng.randint(2, 15), price))
        if row['ventas_pagadas']:
            last_sale = index
        # The purchasing policy adapts only to earlier observed sales/exposure.
        if index >= 56 and index % 28 == 0:
            window = history[-56:]
            exposure = sum(x['chequeos_con_stock'] / slots for x in window)
            estimate = sum(x['ventas_pagadas'] for x in window) / max(14, exposure)
            minimum = max(1, math.ceil(estimate * (lead + 5)))
            maximum = max(minimum + 2, math.ceil(estimate * (lead + 26)))
        incoming = sum(x['quantity'] for x in purchases)
        if stock - reserved + incoming <= minimum:
            quantity = math.ceil((maximum - stock + reserved - incoming) / pack) * pack
            delay = rng.randint(2, 12) if rng.random() < config['supplier_delay_probability'] else 0
            first = max(1, quantity * 3 // 4)
            partial = quantity > 2 and rng.random() < config['supplier_partial_probability']
            purchases.append({'quantity': first if partial else quantity,
                              'promised': index + lead, 'actual': index + lead + delay})
            if partial:
                purchases.append({'quantity': quantity - first, 'promised': index + lead,
                                  'actual': index + lead + delay + rng.randint(2, 6)})
            row['compras_solicitadas'] = quantity
        row.update(stock_fin=stock, reservado_fin=reserved, disponible_fin=stock-reserved,
                   compras_transito_fin=sum(x['quantity'] for x in purchases),
                   compras_vencidas_fin=sum(x['quantity'] for x in purchases if x['promised'] < index),
                   minimo=minimum, maximo=maximum,
                   quiebre_observado=int(row['chequeos_con_stock'] < slots or stock == reserved))
        # Private state is never exported or used as an ML feature.
        row['_days_since_sale'] = index - last_sale if last_sale >= 0 else index + 1
        history.append(row)
    return history


def partition(cutoff, config):
    val = date.fromisoformat(config['validation_start'])
    test = date.fromisoformat(config['test_start'])
    label_end = cutoff + config['horizon_days'] * DAY
    if cutoff < val:
        return 'entrenamiento' if label_end < val else None
    if cutoff < test:
        return 'validacion' if label_end < test else None
    return 'prueba'


def features_at(history, index):
    current = history[index]
    next_day = date.fromisoformat(current['fecha']) + DAY
    result = {k: current[k] for k in CATEGORICAL_FEATURES + ['universal']}
    result.update(dia_semana_siguiente=next_day.weekday(), mes_siguiente=next_day.month,
                  dia_mes_siguiente=next_day.day,
                  fin_mes_proximos_7d=sum((next_day + j * DAY).day >= 25 for j in range(7)))
    for lag in (0, 1, 7, 14, 28):
        result['ventas_hoy' if lag == 0 else f'ventas_lag_{lag}'] = history[index-lag]['ventas_pagadas']
    for days in (7, 14, 28, 56):
        result[f'ventas_{days}d'] = sum(r['ventas_pagadas'] for r in history[index-days+1:index+1])
    recent = history[index-27:index+1]
    result.update(desviacion_ventas_28d=round(pstdev(r['ventas_pagadas'] for r in recent), 6),
                  dias_sin_ventas_28d=sum(r['ventas_pagadas'] == 0 for r in recent),
                  dias_desde_ultima_venta=current['_days_since_sale'],
                  diferencia_ventas_semanas=2*result['ventas_7d']-result['ventas_14d'],
                  devoluciones_28d=sum(r['unidades_devueltas'] for r in recent),
                  proporcion_stock_28d=round(sum(r['chequeos_con_stock'] for r in recent) /
                                            sum(r['chequeos_disponibilidad'] for r in recent), 6))
    for days in (7, 28):
        window = history[index-days+1:index+1]
        for output, source in [('vistas', 'vistas_producto'), ('carritos', 'adiciones_carrito'),
                               ('quiebres', 'quiebre_observado')]:
            result[f'{output}_{days}d'] = sum(r[source] for r in window)
    for field in NUMERIC_FEATURES:
        if field not in result:
            result[field] = current[field]
    return result


def training_rows(history, config):
    horizon = config['horizon_days']
    for index in range(config['history_days']-1, len(history)-horizon):
        cutoff = date.fromisoformat(history[index]['fecha'])
        split = partition(cutoff, config)
        if split is None:
            continue
        future = history[index+1:index+1+horizon]
        row = features_at(history, index)
        row.update(fecha_corte=cutoff.isoformat(), fuente_datos=config['source'], particion=split,
                   fecha_objetivo_inicio=future[0]['fecha'], fecha_objetivo_fin=future[-1]['fecha'],
                   objetivo_ventas_7d=sum(r['ventas_pagadas'] for r in future),
                   diagnostico_quiebre_futuro_7d=sum(r['quiebre_observado'] for r in future),
                   base_ultima_semana=row['ventas_7d'], base_promedio_28d=row['ventas_28d']/4)
        yield row


def check_daily(rows):
    previous_stock, previous_reserved, previous_incoming = None, None, 0
    sales, returns = 0, 0
    for r in rows:
        expected = (r['stock_inicio'] + r['ingresos_compra'] + r['devoluciones_reingresadas']
                    - r['mermas'] - r['ventas_pagadas'])
        if r['stock_fin'] != expected or r['stock_fin'] < r['reservado_fin'] or r['reservado_fin'] < 0:
            raise ValueError(f"Stock incoherente: {r['sku']} {r['fecha']}")
        if r['reservado_fin'] != (r['reservado_inicio'] + r['reservas_creadas']
                                  - r['reservas_pagadas'] - r['reservas_canceladas']):
            raise ValueError('No concilian las reservas.')
        if previous_stock is not None and (r['stock_inicio'], r['reservado_inicio']) != (previous_stock, previous_reserved):
            raise ValueError('Discontinuidad entre días.')
        if r['compras_transito_fin'] != previous_incoming + r['compras_solicitadas'] - r['ingresos_compra']:
            raise ValueError('No concilian compras y recepciones.')
        sales += r['ventas_pagadas']
        returns += r['unidades_devueltas']
        if returns > sales or not 0 <= r['devoluciones_reingresadas'] <= r['unidades_devueltas']:
            raise ValueError('Devoluciones superiores a ventas.')
        previous_stock, previous_reserved, previous_incoming = r['stock_fin'], r['reservado_fin'], r['compras_transito_fin']


def compressed_copy(path):
    output = path.with_suffix(path.suffix + '.gz')
    with path.open('rb') as source, output.open('wb') as target:
        with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as zipped:
            shutil.copyfileobj(source, zipped)
    return output


def build(config_path, catalog_path, output):
    config = json.loads(config_path.read_text(encoding='utf-8'))
    products = json.loads(catalog_path.read_text(encoding='utf-8'))['products']
    validate_catalog(products)
    if config['horizon_days'] != 7 or config['history_days'] != 56:
        raise ValueError('Esta versión define un horizonte de 7 días y ventanas de hasta 56 días.')
    start, end, val, test = [date.fromisoformat(config[k]) for k in
                           ('start_date', 'end_date', 'validation_start', 'test_start')]
    if not start + 63*DAY < val < test - 7*DAY < end - 14*DAY:
        raise ValueError('Las fechas no dejan suficiente historia, horizonte o separación temporal.')
    if config['source'] != 'simulado':
        raise ValueError('Este generador sólo produce datos identificados como simulados.')
    output.mkdir(parents=True, exist_ok=True)
    raw_path, train_path = output/'inventario_ventas_diarias.csv', output/'entrenamiento_ventas_7d.csv'
    counts, splits, months, zero_products, date_limits = Counter(), Counter(), {}, [], {}
    with raw_path.open('w', encoding='utf-8-sig', newline='') as raw, train_path.open('w', encoding='utf-8-sig', newline='') as train:
        raw_writer = csv.DictWriter(raw, RAW_FIELDS, extrasaction='ignore')
        train_writer = csv.DictWriter(train, TRAIN_FIELDS)
        raw_writer.writeheader()
        train_writer.writeheader()
        for position, product in enumerate(products, 1):
            history = simulate_product(product, config)
            check_daily(history)
            raw_writer.writerows(history)
            total_sales = sum(r['ventas_pagadas'] for r in history)
            if not total_sales:
                zero_products.append(product['sku'])
            for row in history:
                counts['daily_rows'] += 1
                counts['paid_units'] += row['ventas_pagadas']
                counts['zero_sales_days'] += int(row['ventas_pagadas'] == 0)
                counts['stockout_days'] += row['quiebre_observado']
                counts['returned_units'] += row['unidades_devueltas']
                counts['reserved_units'] += row['reservas_creadas']
                month = months.setdefault(row['fecha'][:7], Counter())
                month.update({k: row[k] for k in ['ventas_pagadas', 'ingreso_bruto_centimos', 'ingresos_compra', 'quiebre_observado']})
            for row in training_rows(history, config):
                train_writer.writerow(row)
                counts['training_rows'] += 1
                splits[row['particion']] += 1
                limits = date_limits.setdefault(row['particion'], {'cutoff_min': row['fecha_corte'],
                                'cutoff_max': row['fecha_corte'], 'label_end_max': row['fecha_objetivo_fin']})
                limits['cutoff_max'] = max(limits['cutoff_max'], row['fecha_corte'])
                limits['label_end_max'] = max(limits['label_end_max'], row['fecha_objetivo_fin'])
            if position % 100 == 0:
                print(f'{position}/{len(products)} productos procesados', flush=True)
    files = {}
    for path in [raw_path, train_path]:
        zipped = compressed_copy(path)
        files[path.name] = {'sha256': digest(path), 'bytes': path.stat().st_size,
                            'gzip_file': zipped.name, 'gzip_sha256': digest(zipped), 'gzip_bytes': zipped.stat().st_size}
    manifest = {
        'version': config['version'], 'source': 'simulado', 'timezone': config['timezone'],
        'config': config, 'catalog_sha256': digest(catalog_path),
        'generator_sha256': digest(Path(__file__)), 'products': len(products),
        'counts': dict(counts), 'partitions': dict(splits), 'partition_dates': date_limits,
        'files': files, 'raw_columns': RAW_FIELDS, 'training_columns': TRAIN_FIELDS,
        'feature_columns': CATEGORICAL_FEATURES + NUMERIC_FEATURES,
        'categorical_features': CATEGORICAL_FEATURES, 'target': TARGET,
        'excluded_from_features': [x for x in TRAIN_FIELDS if x not in CATEGORICAL_FEATURES + NUMERIC_FEATURES],
        'units': {'money': 'PEN en céntimos enteros; precio e ingreso bruto incluyen IGV.',
                  'quantities': 'Unidades de venta del catálogo; un juego o kit cuenta como una unidad.'},
        'definitions': {
            'grain': 'Una fila por SKU y día calendario. Orden físico: SKU, fecha.',
            'forecast_cutoff': 'Después del cierre del día t en America/Lima. Features incluyen t; objetivo t+1 hasta t+7.',
            'target': 'Unidades con pago confirmado. Incluye reservas pagadas; no descuenta devoluciones. No es demanda latente.',
            'stockout': 'Se observó disponibilidad cero en algún chequeo o al cierre. No cuantifica ventas perdidas.',
            'future_stockout': 'Sólo diagnóstico de evaluación. No usar como predictor ni excluir automáticamente estas filas.',
            'availability': '12 chequeos simulados por día; no representan horas exactas de disponibilidad.',
            'reserve': 'La reserva mantiene stock físico y reduce disponible. Al día siguiente se paga o cancela.',
            'cost': 'Costo unitario estándar supuesto; no valoración FIFO ni costo promedio del kardex real.',
            'revenue': 'Precio al pagar, o precio al reservar para reservas; devoluciones conservan precio original.',
            'split': 'Fechas comunes a todos los SKU; se omiten 7 fechas de corte antes de validación y prueba para purgar etiquetas.',
            'training': 'Usar sólo feature_columns como X. Ajustar imputación/codificación/escalado sólo con entrenamiento.',
            'backtesting': 'Validación/prueba simulan predicción diaria al cierre; el pasado reciente observado puede alimentar los lags sin reentrenar.',
            'walk_forward': 'En cada fold adicional purgar etiquetas cuyo fecha_objetivo_fin alcance el inicio del siguiente bloque.'},
        'limitations': [
            'Historia enteramente simulada, independiente de las ventas y clientes de la web.',
            'No valida precisión real del ML. El rendimiento mide aprendizaje de este escenario artificial.',
            'No hay estacionalidad ni tasas calibradas con transacciones reales peruanas.',
            'Se asume que todos los SKU existen desde el inicio y que la tienda recibe pedidos todos los días.',
            'No modela sustitución entre SKU, campañas externas, clima ni ubicación geográfica.',
            'El catálogo y sus compatibilidades siguen pendientes de validación comercial/técnica.'],
        'quality': {'inventory_balance_errors': 0, 'reservation_balance_errors': 0,
                    'purchase_balance_errors': 0, 'zero_sales_products': zero_products},
        'monthly_totals': months}
    save_json(output/'manifest.json', manifest)
    print(json.dumps({'output': str(output), 'products': len(products), **counts,
                      'partitions': dict(splits)}, ensure_ascii=False), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description='Genera CSV académicos aislados; no modifica la BD de la tienda.')
    parser.add_argument('--config', type=Path, default=CONFIG)
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    parser.add_argument('--output', type=Path, default=ROOT/'data/ml/roda-v1')
    parser.add_argument('--snapshot-from-db', type=Path, help='Exporta sólo el catálogo público desde SQLite de sólo lectura.')
    args = parser.parse_args()
    if args.snapshot_from_db:
        snapshot_catalog(args.snapshot_from_db, args.catalog)
    build(args.config, args.catalog, args.output)


if __name__ == '__main__':
    main()
