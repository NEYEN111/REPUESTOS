"""Evaluación de ventas intermitentes y reglas de revisión antes de usar un pronóstico."""
import argparse
import gzip
import hashlib
import json
import math
import shutil
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ml.inference import load_trusted_bundle, nonnegative_predict, predict_bundle, rotation, sha256

ROOT = Path(__file__).resolve().parents[1]
BASELINE_CONFIGS = {
    'CrostonSBA': [{'alpha': a, 'beta': a} for a in (0.05, 0.1, 0.2)],
    'TSB': [{'alpha': 0.1, 'beta': b} for b in (0.02, 0.05, 0.1)],
}
POLICY_CONFIG = {'min_improvement': 0.02, 'max_abs_bias_pct': 20,
                 'min_weekly_rows': 100, 'min_window_wins': 2,
                 'max_interval_width_to_prediction': 2.0}


def intermittent_forecasts(values, method, alpha=0.1, beta=0.1):
    """Forecast t+1..t+7 after consuming t. No future-based initialization."""
    y = np.asarray(values, dtype=float)
    if method not in BASELINE_CONFIGS or not 0 < alpha <= 1 or not 0 < beta <= 1:
        raise ValueError('Método o coeficientes de suavizado inválidos.')
    if y.ndim != 1 or not np.isfinite(y).all() or (y < 0).any():
        raise ValueError('Se requieren ventas diarias finitas y no negativas.')
    output = np.zeros(len(y), dtype=float)
    size, interval, probability, previous = 0.0, 1.0, 0.0, None
    for t, value in enumerate(y):
        if previous is None:
            if value <= 0:
                continue
            size, interval, probability, previous = value, float(t+1), 1.0/(t+1), t
        else:
            if method == 'TSB':
                probability += beta*(float(value > 0)-probability)
            if value > 0:
                size += alpha*(value-size)
                interval += beta*((t-previous)-interval)
                previous = t
        rate = (1-beta/2)*size/interval if method == 'CrostonSBA' else probability*size
        output[t] = 7*rate
    return output


def read_history(data_dir, manifest, skus):
    entry = manifest['files']['inventario_ventas_diarias.csv']
    path = Path(data_dir)/entry['gzip_file']
    if sha256(path) != entry['gzip_sha256']:
        raise ValueError('El historial no coincide con su manifest.')
    with gzip.open(path, 'rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
            raise ValueError('El CSV diario no coincide con su hash.')
    raw = pd.read_csv(path, usecols=['fecha', 'sku', 'ventas_pagadas'], dtype={'sku': 'string'})
    raw = raw[raw.sku.isin(skus)].copy()
    raw['fecha'] = pd.to_datetime(raw.fecha, errors='raise')
    if raw.isna().any().any() or raw.duplicated(['fecha', 'sku']).any():
        raise ValueError('Historial diario incompleto o duplicado.')
    raw = raw.sort_values(['sku', 'fecha']).reset_index(drop=True)
    gaps = raw.groupby('sku').fecha.diff().dropna()
    if not gaps.eq(pd.Timedelta(days=1)).all():
        raise ValueError('El historial contiene días desconocidos; no equivalen a cero ventas.')
    if set(raw.sku) != set(skus):
        raise ValueError('Faltan productos en el historial diario.')
    return raw


def build_baselines(raw, frame, config):
    from ml.train import folds_for, metrics
    keys = pd.MultiIndex.from_frame(frame[['sku', 'fecha_corte']])
    raw_keys = pd.MultiIndex.from_frame(raw[['sku', 'fecha']])
    positions = raw_keys.get_indexer(keys)
    if (positions < 0).any():
        raise ValueError('No hay historial para todas las fechas de corte.')
    train = frame[frame.particion.eq('entrenamiento')]
    trials, predictions, selected = [], {}, {}
    for method, candidates in BASELINE_CONFIGS.items():
        available = []
        for candidate, params in enumerate(candidates):
            daily = np.zeros(len(raw), dtype=float)
            for _, group in raw.groupby('sku', sort=False):
                daily[group.index] = intermittent_forecasts(group.ventas_pagadas, method, **params)
            aligned = daily[positions]
            scores = []
            for fold, fit, evaluation in folds_for(train, config):
                score = metrics(evaluation.objetivo_ventas_7d, aligned[evaluation.index])
                scores.append(score['mae'])
                trials.append({'model': method, 'candidate': candidate, 'parameters': params,
                               'fold': fold, 'train_label_end': str(fit.fecha_objetivo_fin.max().date()),
                               'evaluation_start': str(evaluation.fecha_corte.min().date()),
                               'evaluation_end': str(evaluation.fecha_corte.max().date()), **score})
            available.append((float(np.mean(scores)), candidate, params, aligned))
        score, _, params, values = min(available, key=lambda row: (row[0], row[1]))
        selected[method] = {'parameters': params, 'cv_mae': score}
        predictions[method] = values
    predictions['UltimaSemana'] = frame.base_ultima_semana.to_numpy(dtype=float)
    predictions['Promedio28Dias'] = frame.base_promedio_28d.to_numpy(dtype=float)
    predictions['Cero'] = np.zeros(len(frame))
    return predictions, trials, selected


def weekly_rows(frame):
    dates = frame.fecha_corte.drop_duplicates().sort_values().iloc[::7]
    return frame[frame.fecha_corte.isin(dates)].copy()


def make_policy(selection, chosen_prediction, baselines, config):
    from ml.train import metrics, paired_block_ci
    table = [{'model': name, **metrics(selection.objetivo_ventas_7d, values[selection.index])}
             for name, values in baselines.items()]
    best = min(table, key=lambda row: (row['mae'], row['model']))
    chosen = pd.Series(chosen_prediction, index=selection.index)
    reference = pd.Series(baselines[best['model']][selection.index], index=selection.index)
    frame = selection.assign(prediction=chosen, reference=reference,
                             rotation=rotation(selection.ventas_28d/4))
    groups = [('global', frame)] + list(frame.groupby('rotation'))
    policies = {}
    dates = frame.fecha_corte.drop_duplicates().sort_values()
    windows = np.array_split(dates.to_numpy(), 3)
    for label, part in groups:
        observed = metrics(part.objetivo_ventas_7d, part.prediction)
        base = metrics(part.objetivo_ventas_7d, part.reference)
        improvement = (base['mae']-observed['mae'])/base['mae'] if base['mae'] else None
        weekly_n = len(weekly_rows(part))
        wins = 0
        window_results = []
        for i, window in enumerate(windows):
            block = part[part.fecha_corte.isin(window)]
            if block.empty:
                continue
            ml_mae = metrics(block.objetivo_ventas_7d, block.prediction)['mae']
            base_mae = metrics(block.objetivo_ventas_7d, block.reference)['mae']
            wins += ml_mae < base_mae
            window_results.append({'window': i+1, 'start': str(block.fecha_corte.min().date()),
                                   'end': str(block.fecha_corte.max().date()),
                                   'model_mae': ml_mae, 'baseline_mae': base_mae})
        if part.fecha_corte.nunique() >= config['bootstrap_block_days']:
            ci = paired_block_ci(part, part.prediction, part.reference, config)
        else:
            ci = {'estimate': observed['mae']-base['mae'], 'lower_95': None, 'upper_95': None,
                  'limitation': 'Fechas insuficientes para remuestreo por bloques.'}
        reasons = []
        if improvement is None or improvement < POLICY_CONFIG['min_improvement']:
            reasons.append('mejora_insuficiente_frente_referencia')
        if observed['bias_pct'] is None or abs(observed['bias_pct']) > POLICY_CONFIG['max_abs_bias_pct']:
            reasons.append('sesgo_o_volumen_insuficiente')
        if weekly_n < POLICY_CONFIG['min_weekly_rows']:
            reasons.append('pocas_observaciones_semanales')
        if wins < POLICY_CONFIG['min_window_wins']:
            reasons.append('mejora_inestable_entre_periodos')
        if ci['upper_95'] is None or ci['upper_95'] >= 0:
            reasons.append('mejora_no_clara_en_remuestreo')
        policies[label] = {'review_required': bool(reasons), 'reasons': reasons,
                           'mae': observed['mae'], 'baseline_mae': base['mae'],
                           'relative_mae_improvement': improvement, 'bias_pct': observed['bias_pct'],
                           'weekly_rows': weekly_n, 'window_wins': int(wins), 'windows': window_results,
                           'paired_mae_difference': ci}
    return {'schema_version': 1, 'selection_only': True, 'baseline': best['model'],
            'thresholds': POLICY_CONFIG, 'groups': policies, 'baseline_selection': table,
            'automatic_purchasing_enabled': False,
            'meaning': 'Reglas de revisión para apoyo al administrador; no equivalen a garantía de exactitud.',
            'selection_start': str(selection.fecha_corte.min().date()),
            'selection_end': str(selection.fecha_corte.max().date())}


def plots(output, score_table, segments, weekly, policy):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from ml.reporting import INK, RED, GRAY
    assets = []
    def save(fig, slug, title, detail, top=.94):
        fig.suptitle(title, x=.03, ha='left', fontsize=15, fontweight='bold')
        fig.text(.03, .014, 'RODA · Evaluación con historial simulado · '+detail, fontsize=8, color=GRAY)
        fig.tight_layout(rect=(.01, .05, .99, top))
        for ext in ['png', 'svg']:
            fig.savefig(output/'images'/f'{slug}.{ext}', dpi=150)
        plt.close(fig)
        assets.append({'id': slug, 'title': title, 'description': detail,
                       'png': f'images/{slug}.png', 'svg': f'images/{slug}.svg'})
    ordered = pd.DataFrame(score_table).sort_values('mae', ascending=False)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.barh(ordered.model, ordered.mae, color=[RED if s else GRAY for s in ordered.selected])
    for i, v in enumerate(ordered.mae):
        ax.text(v, i, f' {v:.3f}', va='center', fontsize=9)
    ax.set(xlabel='MAE, unidades / SKU / 7 días', xlim=(0, ordered.mae.max()*1.12))
    save(fig, '13_referencias', 'Cinco modelos frente a referencias de ventas intermitentes', 'Prueba histórica ya examinada; no se cambia el ganador usando esta tabla.')
    table = pd.DataFrame(segments).pivot(index='model', columns='rotation', values='mae')
    table = table[[g for g in ['baja', 'media', 'alta'] if g in table.columns]]
    fig, ax = plt.subplots(figsize=(11, 6))
    arr = table.to_numpy()
    scaled = arr/np.maximum(np.nanmax(arr, axis=0), 1e-9)
    ax.imshow(scaled, cmap='Oranges', aspect='auto', vmin=0, vmax=1)
    ax.set_xticks(range(len(table.columns)), table.columns)
    ax.set_yticks(range(len(table.index)), table.index)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            ax.text(j, i, f'{arr[i,j]:.3f}', ha='center', va='center', color='white' if scaled[i,j]>.65 else INK)
    save(fig, '14_rotacion', 'Error por nivel de rotación y modelo', 'MAE en semanas sin solapamiento; color relativo dentro de cada columna.')
    fig, ax = plt.subplots(figsize=(12, 6))
    for name, group in pd.DataFrame(weekly).groupby('model'):
        ax.plot(pd.to_datetime(group.fecha_corte), group.mae, marker='.', label=name)
    ax.set(ylabel='MAE semanal', xlabel='Fecha de corte')
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', bbox_to_anchor=(.5, .92), ncol=3, fontsize=8)
    save(fig, '15_estabilidad', 'Estabilidad de los pronósticos durante doce semanas',
         'Cada punto agrupa el catálogo; horizontes de siete días sin solapamiento.', top=.76)
    fig, ax = plt.subplots(figsize=(11, 4.5))
    labels = [g for g in ['baja', 'media', 'alta'] if g in policy['groups']]
    gains = [100*(policy['groups'][g]['relative_mae_improvement'] or 0) for g in labels]
    ax.bar(labels, gains, color=[RED if policy['groups'][g]['review_required'] else '#237967' for g in labels])
    ax.axhline(2, color=GRAY, linestyle='--', label='Umbral de mejora: 2%')
    ax.set(ylabel='Reducción de MAE frente a referencia (%)', xlabel='Rotación observada al emitir la predicción')
    ax.legend()
    save(fig, '16_revision', 'Dónde requiere revisión el pronóstico', 'Reglas fijadas con selección; rojo = requiere revisión por uno o más criterios.')
    return assets


def strengthen_run(folder, data_dir=ROOT/'data/ml/roda-v1'):
    """Extend an owned run without refitting/reselecting its five frozen estimators."""
    from ml.train import dump_json, load_dataset, metrics
    folder, data_dir = Path(folder), Path(data_dir)
    summary = json.loads((folder/'dashboard.json').read_text(encoding='utf-8'))
    if 'robustness' in summary:
        raise ValueError('Esta ejecución ya tiene evaluación ampliada; usa una nueva carpeta.')
    bundle, contract = load_trusted_bundle(folder)
    config = json.loads((folder/'run_config.json').read_text(encoding='utf-8'))['config']
    frame, manifest = load_dataset(data_dir, smoke=summary['mode']=='smoke')
    raw = read_history(data_dir, manifest, frame.sku.unique())
    baselines, trials, parameters = build_baselines(raw, frame, config)
    print('Referencias intermitentes ajustadas con validación temporal.', flush=True)
    dates = summary['data']['dates']['seleccion']
    selection = frame[frame.fecha_corte.between(dates['start'], dates['end'])].copy()
    point_prediction = nonnegative_predict(bundle['pipeline'], selection[bundle['features']])
    policy = make_policy(selection, point_prediction, baselines, config)
    # Freeze review rules before evaluating them against the historical test outcomes.
    dump_json(folder/'quality_policy.json', policy)
    print('Reglas de revisión fijadas usando únicamente selección.', flush=True)
    test = frame[frame.particion.eq('prueba')].copy()
    saved = pd.read_csv(folder/'predicciones_prueba.csv.gz', parse_dates=['fecha_corte'])
    aligned = test[['sku', 'fecha_corte', 'objetivo_ventas_7d']].merge(saved, on=['sku', 'fecha_corte'],
                   how='left', validate='one_to_one', suffixes=('', '_saved'))
    if aligned.isna().any().any() or not aligned.objetivo_ventas_7d.eq(aligned.objetivo_ventas_7d_saved).all():
        raise ValueError('Predicciones guardadas y dataset no coinciden.')
    winner = bundle['model_name']
    ml_names = [row['model'] for row in summary['selection']['comparisons'] if row['kind']=='ML']
    predictions = {name: aligned['pred_'+name].to_numpy() for name in ml_names}
    predictions.update({name: value[test.index] for name, value in baselines.items()})
    test['rotation'] = rotation(test.ventas_28d/4)
    test['prediction'] = predictions[winner]
    test['lower'], test['upper'] = aligned.lower.to_numpy(), aligned.upper.to_numpy()
    test['coverage'] = test.objetivo_ventas_7d.between(test.lower, test.upper)
    test['reference'] = predictions[policy['baseline']]
    test = test.reset_index(drop=True)
    # MASE denominator from consecutive non-overlapping training weeks, per SKU.
    training_weeks = weekly_rows(frame[frame.particion.eq('entrenamiento')]).sort_values(['sku', 'fecha_corte'])
    scales = training_weeks.assign(delta=training_weeks.groupby('sku').objetivo_ventas_7d.diff().abs()).groupby('sku').delta.mean()
    test['mase_scale'] = test.sku.map(scales)
    weeks = weekly_rows(test)
    score_table, segments, weekly = [], [], []
    for name, values in predictions.items():
        score_table.append({'model': name, 'selected': name==winner, **metrics(test.objetivo_ventas_7d, values)})
        for group, part in weeks.groupby('rotation'):
            segments.append({'model': name, 'rotation': group, **metrics(part.objetivo_ventas_7d, values[part.index])})
        for cutoff, part in weeks.groupby('fecha_corte'):
            weekly.append({'model': name, 'fecha_corte': str(cutoff.date()), **metrics(part.objetivo_ventas_7d, values[part.index])})
    per_sku = []
    for sku, part in weeks.groupby('sku'):
        score = metrics(part.objetivo_ventas_7d, part.prediction)
        baseline = metrics(part.objetivo_ventas_7d, part.reference)
        scale = float(part.mase_scale.iloc[0])
        per_sku.append({'sku': sku, 'familia': str(part.familia.iloc[0]), **score,
                        'baseline_mae': baseline['mae'],
                        'relative_mae_improvement': (baseline['mae']-score['mae'])/baseline['mae'] if baseline['mae'] else None,
                        'mase': score['mae']/scale if math.isfinite(scale) and scale>0 else None,
                        'coverage_pct': float(part.coverage.mean()*100),
                        'nonzero_weeks': int(part.objetivo_ventas_7d.gt(0).sum())})
    availability = []
    for name, mask in [('con_quiebre_futuro', test.diagnostico_quiebre_futuro_7d.gt(0)),
                       ('sin_quiebre_futuro', test.diagnostico_quiebre_futuro_7d.eq(0))]:
        part = test[mask]
        if len(part):
            availability.append({'group': name, **metrics(part.objetivo_ventas_7d, part.prediction)})
    bundle['quality_policy'] = policy
    joblib.dump(bundle, folder/'model.joblib', compress=3)
    contract.update(model_sha256=sha256(folder/'model.joblib'), quality_policy=policy,
                    inference_outputs=['ventas_estimadas_7d', 'limite_inferior_90', 'limite_superior_90',
                                       'revision_recomendada', 'motivos_revision', 'cobertura_stock'])
    dump_json(folder/'contract.json', contract)
    inference = predict_bundle(bundle, test[bundle['features']], allow_simulated=True)
    np.testing.assert_allclose(inference.ventas_estimadas_7d, test.prediction, rtol=1e-6, atol=1e-6)
    example = json.loads((folder/'inference_example.json').read_text(encoding='utf-8'))
    example['output'] = predict_bundle(bundle, example['input'], allow_simulated=True).to_dict('records')
    dump_json(folder/'inference_example.json', example)
    reliability = {'rows': len(inference), 'review_rows': int(inference.revision_recomendada.sum()),
                   'review_fraction': float(inference.revision_recomendada.mean()),
                   'reason_counts': dict(Counter(reason for row in inference.motivos_revision for reason in row))}
    report = {'schema_version': 1, 'evaluation_id': folder.name,
              'point_model_unchanged': True, 'test_status': 'retrospectivo_previamente_examinado',
              'baseline_parameters': parameters, 'baseline_trials': trials, 'policy': policy,
              'models': score_table, 'segments': segments, 'weekly': weekly,
              'stockout_diagnostic': availability, 'inference_review': reliability,
              'per_sku_file': 'errores_por_sku.csv', 'policy_file': 'quality_policy.json',
              'methodology': [
                  'Croston SBA y TSB actualizan estado sólo con ventas hasta t. Suavizado elegido en folds de entrenamiento.',
                  'Cero se incluye para revelar el comportamiento del MAE ante series escasas; no es una recomendación de compra.',
                  'Los cinco modelos y sus predicciones se conservan; esta ampliación añade referencias y reglas de revisión.',
                  'Las reglas se fijan con selección. La prueba ya fue examinada en la versión anterior: evaluación retrospectiva.',
                  'MASE por SKU usa diferencias de ventas semanales consecutivas en entrenamiento. Sin variación: N/D.',
                  'El análisis por SKU contiene doce semanas: muestra limitada, no permite declarar confianza individual alta.',
                  'Los quiebres futuros son diagnósticos, nunca variables de entrada ni reglas de decisión.',
                  'El intervalo de ventas no calcula demanda perdida, probabilidades de quiebre ni cantidades óptimas de compra.',
                  'Datos de origen simulado; se requiere evaluación con transacciones reales para validar utilidad operativa.'],
              'references': ['https://arxiv.org/html/1409.1609',
                             'https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html']}
    dump_json(folder/'robustness.json', report)
    for name, rows in [('errores_por_sku', per_sku), ('comparacion_ampliada', score_table),
                       ('errores_por_rotacion', segments), ('estabilidad_semanal', weekly), ('busqueda_intermitente', trials)]:
        pd.DataFrame(rows).to_csv(folder/f'{name}.csv', index=False, encoding='utf-8-sig')
    summary['assets'] += plots(folder, score_table, segments, weekly, policy)
    summary['robustness'] = {'report': 'robustness.json', 'policy': policy,
                             'evaluation_id': folder.name,
                             'test_status': report['test_status'], 'inference_review': reliability}
    summary['limitations'] += report['methodology'][3:]
    for name in ['ml/robustness.py', 'ml/inference.py']:
        destination = folder/'source'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
    summary['quality_source_sha256'] = {p: sha256(ROOT/p) for p in ['ml/robustness.py', 'ml/inference.py']}
    dump_json(folder/'dashboard.json', summary)
    dump_json(folder/'checksums.json', {str(p.relative_to(folder)).replace('\\', '/'): sha256(p)
              for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'checksums.json'})
    shutil.make_archive(str(folder)+'-web', 'zip', folder)
    print(f'Evaluación ampliada completa: {folder}', flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Usa una carpeta nueva para conservar el resultado anterior.')
    shutil.copytree(args.source, args.output)
    strengthen_run(args.output)
