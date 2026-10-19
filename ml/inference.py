import hashlib
import json
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def nonnegative_predict(pipeline, features):
    values = np.asarray(pipeline.predict(features), dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('El modelo produjo valores no finitos.')
    return np.maximum(values, 0)


def rotation(values):
    return np.where(np.asarray(values) < 1, 'baja', np.where(np.asarray(values) < 5, 'media', 'alta'))


def load_trusted_bundle(folder):
    """Sólo para paquetes propios. Un checksum no autentica un archivo joblib de terceros."""
    folder = Path(folder)
    contract = json.loads((folder/'contract.json').read_text(encoding='utf-8'))
    if sha256(folder/'model.joblib') != contract['model_sha256']:
        raise ValueError('El modelo no coincide con el contrato de exportación.')
    for package, expected in contract['runtime_versions'].items():
        if version(package) != expected:
            raise ValueError(f'Versión incompatible de {package}: se requiere {expected}.')
    bundle = joblib.load(folder/'model.joblib')
    if bundle['run_id'] != contract['run_id'] or bundle['features'] != contract['features']:
        raise ValueError('Modelo y contrato pertenecen a exportaciones diferentes.')
    if bundle.get('quality_policy') != contract.get('quality_policy'):
        raise ValueError('Las reglas de revisión del modelo no coinciden con su contrato.')
    return bundle, contract


def predict_bundle(bundle, records, *, allow_simulated=False):
    if bundle['data_source'] == 'simulado' and not allow_simulated:
        raise ValueError('Modelo académico: habilita explícitamente el uso de datos simulados.')
    frame = pd.DataFrame(records).copy()
    missing = sorted(set(bundle['features']) - set(frame.columns))
    if missing:
        raise ValueError('Faltan variables requeridas: ' + ', '.join(missing))
    numeric = bundle['numeric_features']
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors='raise').astype('float32')
    if frame.empty or frame[bundle['features']].isna().any().any() or not np.isfinite(frame[numeric]).all().all():
        raise ValueError('Las variables deben estar completas y contener valores finitos.')
    nonnegative = [c for c in numeric if c != 'diferencia_ventas_semanas']
    if (frame[nonnegative] < 0).any().any():
        raise ValueError('Las cantidades, precios y fechas de calendario no pueden ser negativos.')
    bounds = {'dia_semana_siguiente': (0, 6), 'mes_siguiente': (1, 12),
              'dia_mes_siguiente': (1, 31), 'proporcion_stock_28d': (0, 1),
              'descuento_pct': (0, 100), 'universal': (0, 1), 'fin_mes_proximos_7d': (0, 7)}
    if any(not frame[column].between(low, high).all() for column, (low, high) in bounds.items()):
        raise ValueError('Calendario, proporción de stock o descuento fuera de rango.')
    if not frame['sku'].isin(bundle['known_skus']).all():
        raise ValueError('SKU sin historial de entrenamiento; requiere evaluación de producto nuevo.')
    if (frame['disponible_fin'] != frame['stock_fin']-frame['reservado_fin']).any():
        raise ValueError('El stock disponible no concilia con el físico y reservado.')
    predictions = nonnegative_predict(bundle['pipeline'], frame[bundle['features']])
    groups = rotation(frame['ventas_28d']/4)
    radii = np.array([bundle['interval_radius'][group] for group in groups])
    lower, upper = np.maximum(0, predictions-radii), predictions+radii
    result = pd.DataFrame({'sku': frame['sku'].to_numpy(), 'ventas_estimadas_7d': predictions,
                          'limite_inferior_90': lower, 'limite_superior_90': upper,
                          'rotacion_observada': groups, 'origen_modelo': bundle['data_source']})
    policy = bundle.get('quality_policy')
    if policy:
        reasons = []
        for i, group in enumerate(groups):
            flags = []
            for level in ('global', group):
                rule = policy['groups'].get(level)
                if rule is None or rule['review_required']:
                    flags.append('evidencia_insuficiente_'+level)
            if frame.iloc[i]['quiebres_28d'] > 0:
                flags.append('ventas_limitadas_por_stock_reciente')
            if frame.iloc[i]['disponible_fin'] == 0:
                flags.append('sin_stock_disponible')
            limit = policy['thresholds']['max_interval_width_to_prediction']
            if upper[i]-lower[i] > limit*max(predictions[i], 1):
                flags.append('intervalo_amplio')
            if frame.iloc[i]['plazo_proveedor_dias'] > bundle['horizon_days']:
                flags.append('plazo_proveedor_mayor_al_horizonte')
            reasons.append(flags)
        available = frame.disponible_fin.to_numpy()
        result['revision_recomendada'] = [bool(flags) for flags in reasons]
        result['motivos_revision'] = reasons
        result['cobertura_stock'] = np.where(available < lower, 'insuficiente_en_intervalo',
                                    np.where(available < upper, 'posible_faltante', 'cubre_intervalo'))
    return result


def features_from_history(records):
    """Reutiliza exactamente las ventanas del CSV. Exige observaciones diarias completas."""
    from scripts.build_ml_dataset import RAW_FIELDS, features_at
    frame = pd.DataFrame(records)
    missing = sorted(set(RAW_FIELDS) - set(frame.columns))
    if missing:
        raise ValueError('Historial incompleto para inferencia: ' + ', '.join(missing))
    if frame[RAW_FIELDS].isna().any().any() or frame.duplicated(['sku', 'fecha']).any():
        raise ValueError('Hay observaciones faltantes o fechas/SKU repetidos.')
    result = []
    cutoffs = set()
    for sku, group in frame.groupby('sku', sort=True):
        group = group.sort_values('fecha').copy()
        dates = pd.to_datetime(group['fecha'], errors='raise')
        if len(group) < 56 or not dates.diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
            raise ValueError(f'{sku}: se necesitan 56 días continuos; los días desconocidos no son ceros.')
        if not ((group['stock_fin'] >= group['reservado_fin']) & (group['reservado_fin'] >= 0)).all():
            raise ValueError(f'{sku}: inventario inválido.')
        if not group['disponible_fin'].eq(group['stock_fin']-group['reservado_fin']).all():
            raise ValueError(f'{sku}: disponibilidad inválida.')
        sold = np.flatnonzero(group['ventas_pagadas'].to_numpy() > 0)
        if not len(sold):
            raise ValueError(f'{sku}: falta fecha de última venta; no se puede inventar ese dato.')
        rows = group.to_dict('records')
        rows[-1]['_days_since_sale'] = len(rows)-1-int(sold[-1])
        feature = features_at(rows, len(rows)-1)
        feature['fecha_corte'] = dates.iloc[-1].date().isoformat()
        cutoffs.add(feature['fecha_corte'])
        result.append(feature)
    if len(cutoffs) > 1:
        raise ValueError('Los productos deben compartir la misma fecha de corte.')
    return pd.DataFrame(result)
