"""Independent, frozen weekly retail benchmark; never feeds RODA inventory."""
import csv
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

os.environ.setdefault('LOKY_MAX_CPU_COUNT', '2')

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ml/examples/uci-weekly/source.zip'
OUT = ROOT / 'ml/evaluations/uci-weekly-v1'
SOURCE_SHA256 = 'dededa20f199af8f2bb96184bb1696befda902849a700bde283fe763afc90ba9'
WEEKS = 52
TRAIN = range(8, 36)
VALIDATION = range(36, 44)
TEST = range(44, 52)
SMOOTHING = (0.05, 0.10, 0.20)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_source():
    content = SOURCE.read_bytes()
    if sha256(content) != SOURCE_SHA256:
        raise ValueError('La fuente UCI no coincide con el hash fijado antes de evaluar.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if names != ['Sales_Transactions_Dataset_Weekly.csv']:
            raise ValueError('El archivo UCI cambió de estructura.')
        raw = archive.read(names[0])
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    rows = list(reader)
    columns = [f'W{i}' for i in range(WEEKS)]
    if len(rows) != 811 or not all(c in reader.fieldnames for c in ['Product_Code', *columns]):
        raise ValueError('La fuente no contiene las 811 series y 52 semanas esperadas.')
    ids = [r['Product_Code'] for r in rows]
    if len(set(ids)) != len(ids) or any(not code for code in ids):
        raise ValueError('Los identificadores de productos no son únicos.')
    try:
        values = np.array([[int(r[c]) for c in columns] for r in rows], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError('Se requieren cantidades semanales enteras conocidas.') from exc
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Las cantidades deben ser finitas y no negativas.')
    return ids, values, sha256(raw)


def segment(history):
    zero_share = (history[:, :36] == 0).mean(axis=1)
    return np.where(zero_share >= .6, 'baja', np.where(zero_share >= .2, 'media', 'alta'))


def feature_matrix(values, weeks):
    frames = []
    for week in weeks:
        past = values[:, :week]
        recent = past[:, -8:]
        lag = {f'lag{i}': past[:, -i] for i in (1, 2, 3, 4, 8)}
        nonzero = past > 0
        last_sale = np.where(nonzero, np.arange(week)[None, :], -1).max(axis=1)
        frames.append(pd.DataFrame({
            **lag, 'media4': past[:, -4:].mean(axis=1),
            'media8': recent.mean(axis=1), 'desviacion8': recent.std(axis=1),
            'ceros8': (recent == 0).mean(axis=1),
            'semanas_desde_venta': np.where(last_sale < 0, week, week - 1 - last_sale),
            'ventas_acumuladas': past.sum(axis=1) / week,
        }))
    return pd.concat(frames, ignore_index=True), np.concatenate([values[:, w] for w in weeks])


def models():
    trees = dict(n_estimators=80, max_depth=10, min_samples_leaf=5, n_jobs=2, random_state=42)
    return {
        'Ridge': make_pipeline(StandardScaler(), Ridge(alpha=10)),
        'Poisson': make_pipeline(StandardScaler(), PoissonRegressor(alpha=.1, max_iter=500)),
        'Random Forest': RandomForestRegressor(**trees),
        'Extra Trees': ExtraTreesRegressor(**trees),
        'Hist. Gradient Boosting': HistGradientBoostingRegressor(max_iter=120, max_leaf_nodes=31,
                                                                  l2_regularization=1, random_state=42),
    }


def intermittent(values, method, alpha, beta):
    """Forecast week t using observations strictly before t."""
    count, total = values.shape
    out = np.zeros((count, total), dtype=np.float64)
    size = np.zeros(count)
    interval = np.ones(count)
    probability = np.zeros(count)
    last = np.full(count, -1)
    for week in range(total - 1):
        sold = values[:, week] > 0
        first = sold & (last < 0)
        old = last >= 0
        if method == 'TSB':
            probability[old] += beta * (sold[old].astype(float) - probability[old])
        repeat = sold & old
        size[repeat] += alpha * (values[repeat, week] - size[repeat])
        interval[repeat] += beta * ((week - last[repeat]) - interval[repeat])
        size[first] = values[first, week]
        interval[first] = week + 1
        probability[first] = 1 / (week + 1)
        last[sold] = week
        out[:, week + 1] = ((1 - beta / 2) * size / interval if method == 'Croston SBA'
                              else probability * size)
    return out


def metrics(actual, forecast):
    actual, forecast = np.asarray(actual), np.asarray(forecast)
    error = forecast - actual
    return {'n': int(actual.size), 'mae': float(np.abs(error).mean()),
            'rmse': float(np.sqrt(np.mean(error ** 2))),
            'wape_pct': float(np.abs(error).sum() / actual.sum() * 100) if actual.sum() else None,
            'bias': float(error.mean()), 'actual_units': int(actual.sum()),
            'predicted_units': float(forecast.sum())}


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def figures(selection, test_scores, by_rotation):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    pictures = OUT / 'images'
    pictures.mkdir(exist_ok=True)
    names = ['Ridge', 'Poisson', 'Random Forest', 'Extra Trees', 'Hist. Gradient Boosting',
             'Promedio 8 semanas', 'Croston SBA', 'TSB']
    val = {r['method']: r['mae'] for r in selection}
    test = {r['method']: r['mae'] for r in test_scores}
    positions = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(10, 5.4))
    ax.barh(positions - .19, [val[x] for x in names], height=.36, label='Validación W36–W43', color='#9aaab3')
    ax.barh(positions + .19, [test[x] for x in names], height=.36, label='Prueba W44–W51', color='#b6482a')
    ax.set_yticks(positions, names)
    ax.invert_yaxis()
    ax.set_xlabel('MAE · unidades por producto y semana (menor es mejor)')
    ax.set_title('Modelos y referencias · periodos separados')
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(pictures / '01_metodos.png', dpi=150)
    plt.close(fig)

    methods = ['Extra Trees', 'Croston SBA', 'TSB', 'Promedio 8 semanas', 'Política por rotación']
    groups = ['baja', 'media', 'alta']
    scores = {(r['rotation'], r['method']): r['mae'] for r in by_rotation}
    matrix = np.array([[scores.get((g, m), np.nan) for g in groups] for m in methods])
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.imshow(matrix, cmap='YlOrBr', aspect='auto')
    ax.set_xticks(range(3), ['Baja', 'Media', 'Alta'])
    ax.set_yticks(range(len(methods)), methods)
    ax.set_title('MAE en prueba por rotación fijada antes de validar')
    for i in range(len(methods)):
        for j in range(3):
            ax.text(j, i, f'{matrix[i,j]:.2f}', ha='center', va='center',
                    color='white' if matrix[i, j] > 2 else '#192127')
    fig.tight_layout()
    fig.savefig(pictures / '02_rotacion.png', dpi=150)
    plt.close(fig)


def run():
    ids, values, csv_hash = load_source()
    groups = segment(values)
    n = len(ids)
    x_train, y_train = feature_matrix(values, TRAIN)
    x_valid, y_valid = feature_matrix(values, VALIDATION)
    x_test, y_test = feature_matrix(values, TEST)
    x_refit, y_refit = feature_matrix(values, range(8, 44))
    predictions = {}
    fitted_models = {}
    selection = []
    with threadpool_limits(limits=2):
        for name, model in models().items():
            model.fit(x_train, y_train)
            valid = np.maximum(0, model.predict(x_valid))
            selection.append({'method': name, 'family': 'ML', **metrics(y_valid, valid)})
            model.fit(x_refit, y_refit)
            predictions[name] = np.maximum(0, model.predict(x_test))
            fitted_models[name] = model
    ml_winner = min((s for s in selection if s['family'] == 'ML'), key=lambda s: s['mae'])['method']

    # These references have fixed form; smoothing is chosen on W36-W43 only.
    baseline_matrices = {
        'Promedio 8 semanas': np.column_stack([
            values[:, max(0, week - 8):week].mean(axis=1) if week else np.zeros(n)
            for week in range(WEEKS)]),
        'Última semana': np.column_stack([values[:, max(week - 1, 0)] for week in range(WEEKS)]),
    }
    tuning = {}
    for method in ('Croston SBA', 'TSB'):
        candidates = []
        for alpha in SMOOTHING:
            for beta in SMOOTHING:
                forecast = intermittent(values, method, alpha, beta)
                candidates.append((metrics(values[:, list(VALIDATION)].ravel(),
                                           forecast[:, list(VALIDATION)].ravel())['mae'], alpha, beta, forecast))
        error, alpha, beta, forecast = min(candidates, key=lambda x: (x[0], x[1], x[2]))
        tuning[method] = {'alpha': alpha, 'beta': beta, 'validation_mae': error}
        baseline_matrices[method] = forecast
    for name, matrix in baseline_matrices.items():
        valid = matrix[:, list(VALIDATION)].T.ravel()
        test = matrix[:, list(TEST)].T.ravel()
        selection.append({'method': name, 'family': 'Referencia', **metrics(y_valid, valid)})
        predictions[name] = test

    best_reference = min((s for s in selection if s['family'] == 'Referencia'), key=lambda s: s['mae'])['method']
    # Segment assignments are fixed using W0-W35; method choice uses validation only.
    segment_choices = {}
    methods = list(predictions)
    validation_predictions = {}
    # Refit ML estimators for the segment policy using W0-W35, never the final test.
    with threadpool_limits(limits=2):
        for name, model in models().items():
            model.fit(x_train, y_train)
            validation_predictions[name] = np.maximum(0, model.predict(x_valid))
    for name, matrix in baseline_matrices.items():
        validation_predictions[name] = matrix[:, list(VALIDATION)].T.ravel()
    for group in ('baja', 'media', 'alta'):
        mask = np.tile(groups == group, len(VALIDATION))
        if not mask.any():
            continue
        segment_choices[group] = min(methods, key=lambda method: (
            metrics(y_valid[mask], validation_predictions[method][mask])['mae'], method))
    test_groups = np.tile(groups, len(TEST))
    segment_forecast = np.zeros_like(y_test)
    for group, method in segment_choices.items():
        segment_forecast[test_groups == group] = predictions[method][test_groups == group]
    predictions['Política por rotación'] = segment_forecast

    test_scores = [{'method': name, 'family': 'Política' if name == 'Política por rotación'
                    else 'Referencia' if name in baseline_matrices else 'ML',
                    **metrics(y_test, forecast)} for name, forecast in predictions.items()]
    test_scores.sort(key=lambda r: r['mae'])
    validation_reference = next(s['mae'] for s in selection if s['method'] == best_reference)
    validation_ml = next(s['mae'] for s in selection if s['method'] == ml_winner)
    test_reference = next(s['mae'] for s in test_scores if s['method'] == best_reference)
    test_ml = next(s['mae'] for s in test_scores if s['method'] == ml_winner)
    ml_approved = validation_ml < validation_reference * .99 and test_ml < test_reference * .99

    by_rotation = []
    for group in ('baja', 'media', 'alta'):
        mask = test_groups == group
        if not mask.any():
            continue
        for name in dict.fromkeys((ml_winner, best_reference, 'Croston SBA', 'TSB',
                                   'Promedio 8 semanas', 'Política por rotación')):
            by_rotation.append({'rotation': group, 'method': name,
                                **metrics(y_test[mask], predictions[name][mask])})
    forecast_rows = []
    for offset, week in enumerate(TEST):
        for index, sku in enumerate(ids):
            position = offset * n + index
            forecast_rows.append({'product_code': sku, 'week': f'W{week}', 'rotation': groups[index],
                                  'observed': int(y_test[position]),
                                  'ml_selected': round(float(predictions[ml_winner][position]), 4),
                                  'best_reference': round(float(predictions[best_reference][position]), 4),
                                  'croston_sba': round(float(predictions['Croston SBA'][position]), 4),
                                  'tsb': round(float(predictions['TSB'][position]), 4),
                                  'segment_policy': round(float(segment_forecast[position]), 4)})

    OUT.mkdir(parents=True, exist_ok=True)
    artifact = OUT / 'selected_model.joblib'
    joblib.dump(fitted_models[ml_winner], artifact, compress=3)
    write_csv(OUT / 'validation_methods.csv', sorted(selection, key=lambda r: r['mae']))
    write_csv(OUT / 'test_methods.csv', test_scores)
    write_csv(OUT / 'test_by_rotation.csv', by_rotation)
    write_csv(OUT / 'test_predictions.csv', forecast_rows)
    figures(selection, test_scores, by_rotation)
    report = {
        'source': {'title': 'Sales Transactions Weekly', 'publisher': 'UCI Machine Learning Repository',
                   'url': 'https://archive.ics.uci.edu/dataset/396/Sales%2BTransactions%2BDataset%2BWeekly',
                   'doi': '10.24432/C5XS4Q', 'license': 'CC BY 4.0',
                   'archive_sha256': SOURCE_SHA256, 'csv_sha256': csv_hash,
                   'products': n, 'weeks': WEEKS,
                   'scope': 'Productos anónimos de venta minorista; no son SKU de RODA ni repuestos verificados.',
                   'excluded_columns': 'MIN, MAX y Normalized 0..51, derivados de la serie completa.'},
        'protocol': {'train_targets': 'W8-W35', 'validation_targets': 'W36-W43',
                     'test_targets': 'W44-W51', 'test_locked_before_selection': True,
                     'forecast_horizon': 'Una semana, con ventas previas conocidas al emitir cada pronóstico.',
                     'segments_fixed_from': 'W0-W35',
                     'refit': 'W8-W43 después de elegir algoritmo y parámetros con W36-W43.'},
        'data': {'training_rows': len(y_train), 'validation_rows': len(y_valid),
                 'test_rows': len(y_test), 'zero_fraction': float((values == 0).mean()),
                 'products_by_rotation': {group: int((groups == group).sum()) for group in ('baja','media','alta')}},
        'selection': {'ml_winner': ml_winner, 'reference_winner': best_reference,
                      'selected_model_artifact': artifact.name,
                      'selected_model_sha256': sha256(artifact.read_bytes()),
                      'intermittent_parameters': tuning, 'segment_choices': segment_choices,
                      'methods': sorted(selection, key=lambda r: r['mae'])},
        'test': {'methods': test_scores, 'by_rotation': by_rotation,
                 'ml_approved_against_reference': ml_approved,
                 'decision': 'Modelo ML supera la referencia en validación y prueba final.' if ml_approved
                 else 'No aprobar ML: no supera por al menos 1% la mejor referencia elegida en validación y en prueba.',
                 'limitation': 'Evaluación externa semanal de productos anónimos. No acredita precisión ni política de compra para RODA.'},
    }
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    result = run()
    print(json.dumps({'winner': result['selection']['ml_winner'],
                      'reference': result['selection']['reference_winner'],
                      'decision': result['test']['decision']}, ensure_ascii=False))
