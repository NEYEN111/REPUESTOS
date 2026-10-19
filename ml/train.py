import argparse
import gc
import gzip
import hashlib
import json
import math
import platform
import shutil
import subprocess
import time
import warnings
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from ml.inference import load_trusted_bundle, nonnegative_predict, predict_bundle, rotation, sha256

ROOT = Path(__file__).resolve().parents[1]
MODEL_REASONS = {
    'Ridge': 'Referencia lineal regularizada: interpreta relaciones aditivas y controla coeficientes inestables.',
    'PoissonRegressor': 'Regresión para conteos no negativos con enlace logarítmico; contrasta una respuesta multiplicativa.',
    'RandomForestRegressor': 'Promedia árboles para captar relaciones no lineales e interacciones reduciendo varianza.',
    'ExtraTreesRegressor': 'Aleatoriza los cortes de los árboles; contrasta diversidad y regularización frente a Random Forest.',
    'HistGradientBoostingRegressor': 'Corrige errores de forma secuencial mediante histogramas; usa pérdida Poisson para conteos.'}
BASELINES = {'UltimaSemana': 'base_ultima_semana', 'Promedio28Dias': 'base_promedio_28d'}
PACKAGES = ['numpy', 'pandas', 'scipy', 'scikit-learn', 'joblib', 'threadpoolctl']


def dump_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                                    default=lambda x: x.item() if isinstance(x, np.generic) else str(x))+'\n',
                          encoding='utf-8', newline='\n')


def metrics(y, prediction):
    y, prediction = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float)
    if not len(y) or not np.isfinite(y).all() or not np.isfinite(prediction).all():
        raise ValueError('Métricas sin datos o con valores no finitos.')
    error, total = prediction-y, float(y.sum())
    r2 = float(r2_score(y, prediction)) if len(y) > 1 and np.var(y) > 0 else None
    return {'n': len(y), 'mae': float(mean_absolute_error(y, prediction)),
            'rmse': math.sqrt(mean_squared_error(y, prediction)), 'r2': r2,
            'wape_pct': 100*float(np.abs(error).sum())/total if total else None,
            'bias_units': float(error.mean()), 'bias_pct': 100*float(error.sum())/total if total else None,
            'actual_units': total, 'predicted_units': float(prediction.sum())}


def load_dataset(folder, smoke=False):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    entry = manifest['files']['entrenamiento_ventas_7d.csv']
    path = folder/entry['gzip_file']
    if sha256(path) != entry['gzip_sha256']:
        raise ValueError('El dataset comprimido no coincide con el manifest.')
    with gzip.open(path, 'rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != entry['sha256']:
            raise ValueError('El CSV descomprimido no coincide con el manifest.')
    cats = manifest['categorical_features']
    df = pd.read_csv(path, encoding='utf-8-sig', dtype={c: 'string' for c in cats})
    if list(df.columns) != manifest['training_columns'] or len(df) != manifest['counts']['training_rows']:
        raise ValueError('El esquema o número de filas cambió.')
    if df.isna().any().any() or df.duplicated(['sku', 'fecha_corte']).any():
        raise ValueError('Dataset con valores faltantes o claves duplicadas.')
    features = manifest['feature_columns']
    if set(features).intersection(manifest['excluded_from_features']):
        raise ValueError('Las variables incluyen etiquetas o metadatos de evaluación.')
    for c in ['fecha_corte', 'fecha_objetivo_inicio', 'fecha_objetivo_fin']:
        df[c] = pd.to_datetime(df[c], errors='raise')
    if not (df.fecha_objetivo_inicio.eq(df.fecha_corte+pd.Timedelta(days=1)).all() and
            df.fecha_objetivo_fin.eq(df.fecha_corte+pd.Timedelta(days=7)).all()):
        raise ValueError('Objetivos fuera del horizonte de siete días.')
    target = manifest['target']
    numeric = [c for c in features if c not in cats]
    if not np.isfinite(df[numeric+[target]]).all().all() or (df[target] < 0).any():
        raise ValueError('Valores numéricos inválidos.')
    expected = {'entrenamiento', 'validacion', 'prueba'}
    if set(df.particion) != expected:
        raise ValueError('Se requieren entrenamiento, validación y prueba.')
    for first, second in [('entrenamiento', 'validacion'), ('validacion', 'prueba')]:
        if df.loc[df.particion.eq(first), 'fecha_objetivo_fin'].max() >= df.loc[df.particion.eq(second), 'fecha_corte'].min():
            raise ValueError('Hay etiquetas que invaden el siguiente bloque temporal.')
    if smoke:
        skus = sorted(df.sku.unique(), key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:48]
        df = df[df.sku.isin(skus)].copy()
    df[numeric] = df[numeric].astype('float32')
    df = df.sort_values(['fecha_corte', 'sku']).reset_index(drop=True)
    return df, manifest


def make_pipeline(name, params, manifest, config, smoke=False):
    cats = manifest['categorical_features']
    nums = [c for c in manifest['feature_columns'] if c not in cats]
    linear = name in ('Ridge', 'PoissonRegressor')
    # Sparse full categories for linear models. Dense bounded categories for trees:
    # rare levels are grouped using training counts only, avoiding arbitrary ordinal distances.
    encoder = OneHotEncoder(handle_unknown='infrequent_if_exist', sparse_output=linear,
                            max_categories=None if linear else 32, dtype=np.float32)
    preprocessing = ColumnTransformer([
        ('numeric', StandardScaler() if linear else 'passthrough', nums),
        ('categorical', encoder, cats)], sparse_threshold=1.0 if linear else 0.0)
    common = {'random_state': config['seed']}
    if name == 'Ridge':
        model = Ridge(solver='lsqr', tol=1e-5, max_iter=3000, **params)
    elif name == 'PoissonRegressor':
        model = PoissonRegressor(max_iter=1500, tol=1e-5, **params)
    elif name in ('RandomForestRegressor', 'ExtraTreesRegressor'):
        cls = RandomForestRegressor if name == 'RandomForestRegressor' else ExtraTreesRegressor
        model = cls(n_estimators=12 if smoke else config['forest_trees'], n_jobs=config['threads'],
                    max_features=0.5, max_leaf_nodes=256, **params, **common)
    else:
        model = HistGradientBoostingRegressor(loss='poisson', learning_rate=0.06,
                    max_iter=30 if smoke else 180, min_samples_leaf=40,
                    early_stopping=False, **params, **common)
    return Pipeline([('preprocess', preprocessing), ('model', model)])


def folds_for(train, config):
    last = train.fecha_corte.max()
    for fold in range(config['folds']):
        end = last-pd.Timedelta(days=(config['folds']-1-fold)*config['fold_days'])
        start = end-pd.Timedelta(days=config['fold_days']-1)
        fit = train[train.fecha_objetivo_fin < start]
        evaluation = train[train.fecha_corte.between(start, end)]
        if fit.empty or evaluation.empty or fit.fecha_objetivo_fin.max() >= start:
            raise ValueError('No hay suficientes datos para un fold temporal purgado.')
        yield fold+1, fit, evaluation


def fit_pipeline(pipeline, train, features, target):
    start = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always', ConvergenceWarning)
        pipeline.fit(train[features], train[target])
    issues = [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]
    if issues:
        raise RuntimeError('El modelo no convergió: '+'; '.join(issues))
    return time.perf_counter()-start


def calibrate_intervals(frame, prediction, config):
    groups = rotation(frame.ventas_28d/4)
    residuals = np.abs(frame.objetivo_ventas_7d.to_numpy()-prediction)
    # Non-overlapping target dates reduce overlap, but cross-SKU/time dependence remains.
    dates = frame.fecha_corte.drop_duplicates().sort_values().iloc[::7]
    use = frame.fecha_corte.isin(dates).to_numpy()
    radii, sizes = {}, {}
    for group in ('baja', 'media', 'alta'):
        selected = residuals[use & (groups == group)]
        sizes[group] = len(selected)
        if len(selected) < 30:
            selected = residuals[use]
        level = min(1, math.ceil((len(selected)+1)*config['interval_coverage'])/len(selected))
        radii[group] = float(np.quantile(selected, level, method='higher'))
    return radii, sizes


def paired_block_ci(frame, prediction, baseline, config):
    daily = pd.DataFrame({'date': frame.fecha_corte, 'delta': np.abs(frame.objetivo_ventas_7d-prediction)-
                          np.abs(frame.objetivo_ventas_7d-baseline)}).groupby('date').delta.agg(['sum', 'count'])
    rng = np.random.default_rng(config['seed'])
    n, block = len(daily), config['bootstrap_block_days']
    estimates = []
    for _ in range(config['bootstrap_repeats']):
        starts = rng.integers(0, n-block+1, size=math.ceil(n/block))
        indices = np.concatenate([np.arange(s, s+block) for s in starts])[:n]
        sample = daily.iloc[indices]
        estimates.append(float(sample['sum'].sum()/sample['count'].sum()))
    return {'metric': 'MAE modelo menos MAE baseline; negativo favorece al modelo',
            'estimate': float(daily['sum'].sum()/daily['count'].sum()),
            'lower_95': float(np.quantile(estimates, 0.025)), 'upper_95': float(np.quantile(estimates, 0.975)),
            'block_days': block, 'replicates': config['bootstrap_repeats'],
            'limitation': 'Intervalo exploratorio por bloques temporales; no prueba generalización fuera del simulador.'}


def run_training(data_dir=ROOT/'data/ml/roda-v1', output=None, smoke=False):
    config = json.loads((ROOT/'ml/config.json').read_text(encoding='utf-8'))
    if smoke:
        config.update(folds=1, permutation_rows=400, permutation_repeats=2, bootstrap_repeats=80)
        config['models'] = {k: v[:1] for k, v in config['models'].items()}
    output = Path(output or ROOT/'ml/runs'/datetime.now().strftime('%Y%m%d-%H%M%S'))
    if output.exists() and any(output.iterdir()):
        raise ValueError('La carpeta de resultados debe estar vacía para preservar ejecuciones anteriores.')
    output.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    df, manifest = load_dataset(Path(data_dir), smoke)
    features, target = manifest['feature_columns'], manifest['target']
    train = df[df.particion.eq('entrenamiento')]
    validation = df[df.particion.eq('validacion')]
    calibration_start = validation.fecha_corte.max()-pd.Timedelta(days=config['calibration_days']-1)
    selection = validation[validation.fecha_objetivo_fin < calibration_start]
    calibration = validation[validation.fecha_corte >= calibration_start]
    if selection.empty or calibration.empty:
        raise ValueError('Validación insuficiente para selección y calibración separadas.')
    run_id = output.name
    try:
        git_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        git_dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        git_commit = 'unavailable'
        git_dirty = None
    source_files = ['ml/train.py', 'ml/reporting.py', 'ml/inference.py', 'ml/config.json',
                    'ml/requirements.txt', 'scripts/build_ml_dataset.py']
    source_hashes = {name: sha256(ROOT/name) for name in source_files}
    for name in source_files:
        destination = output/'source'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
    data_info = {'source': manifest['source'], 'raw_rows': manifest['counts']['daily_rows'],
                 'training_csv_rows': len(df), 'skus': int(df.sku.nunique()),
                 'dataset_sha256': manifest['files']['entrenamiento_ventas_7d.csv']['sha256'],
                 'dates': {name: {'start': str(part.fecha_corte.min().date()), 'end': str(part.fecha_corte.max().date()),
                                 'label_end': str(part.fecha_objetivo_fin.max().date()), 'rows': len(part)}
                           for name, part in [('entrenamiento', train), ('seleccion', selection), ('calibracion', calibration),
                                              ('prueba', df[df.particion.eq('prueba')])]},
                 'zero_target_fraction_training': float(train[target].eq(0).mean()),
                 'missing_values': 0, 'duplicate_keys': 0,
                 'features': features, 'excluded': manifest['excluded_from_features']}
    dump_json(output/'run_config.json', {'started_utc': started, 'git_commit': git_commit,
                  'git_worktree_dirty': git_dirty, 'source_sha256': source_hashes, 'config': config,
                  'mode': 'smoke' if smoke else 'full', 'data': data_info})
    trials, comparisons, best_parameters, final_models = [], [], {}, {}
    with threadpool_limits(limits=config['threads']):
        for name, configurations in config['models'].items():
            print(f'\n{name}: búsqueda temporal', flush=True)
            candidates = []
            for candidate, params in enumerate(configurations):
                candidate_scores = []
                for fold, fit, evaluation in folds_for(train, config):
                    available_rows = len(fit)
                    if len(fit) > config['search_max_rows']:
                        fit = fit.sample(n=config['search_max_rows'], random_state=config['seed']+fold)
                    model = make_pipeline(name, params, manifest, config, smoke)
                    seconds = fit_pipeline(model, fit, features, target)
                    prediction = nonnegative_predict(model, evaluation[features])
                    score = metrics(evaluation[target], prediction)
                    trials.append({'model': name, 'candidate': candidate, 'parameters': params, 'fold': fold,
                                   'train_rows': len(fit), 'train_rows_available': available_rows,
                                   'train_end': str(fit.fecha_corte.max().date()),
                                   'train_label_end': str(fit.fecha_objetivo_fin.max().date()),
                                   'evaluation_start': str(evaluation.fecha_corte.min().date()),
                                   'evaluation_end': str(evaluation.fecha_corte.max().date()), 'fit_seconds': seconds, **score})
                    candidate_scores.append(score['mae'])
                    dump_json(output/'search.json', trials)
                    print(f'  configuración {candidate+1}, fold {fold}: MAE={score["mae"]:.4f}', flush=True)
                    del model
                    gc.collect()
                candidates.append((float(np.mean(candidate_scores)), candidate, params))
            cv_mae, _, params = min(candidates, key=lambda x: (x[0], x[1]))
            best_parameters[name] = params
            model = make_pipeline(name, params, manifest, config, smoke)
            seconds = fit_pipeline(model, train, features, target)
            start_predict = time.perf_counter()
            prediction = nonnegative_predict(model, selection[features])
            latency = 1000*(time.perf_counter()-start_predict)/len(selection)
            comparisons.append({'model': name, 'kind': 'ML', 'why_tested': MODEL_REASONS[name],
                                'parameters': params, 'cv_mae': cv_mae, 'fit_seconds': seconds,
                                'estimator_configuration': model.named_steps['model'].get_params(deep=False),
                                'final_fit_rows': len(train),
                                'predict_ms_per_row': latency, **metrics(selection[target], prediction)})
            path = output/f'{name}.joblib'
            joblib.dump(model, path, compress=3)
            final_models[name] = path
            del model
            gc.collect()
        for name, column in BASELINES.items():
            comparisons.append({'model': name, 'kind': 'baseline', 'why_tested': 'Referencia sin entrenamiento.',
                                'parameters': {}, 'cv_mae': None, 'fit_seconds': 0, 'predict_ms_per_row': 0,
                                **metrics(selection[target], selection[column])})
        # Freeze selection before reading test outcomes. No choice based on holdout performance.
        winner = min([r for r in comparisons if r['kind'] == 'ML'], key=lambda r: (r['mae'], r['model']))
        best_base = min([r for r in comparisons if r['kind'] == 'baseline'], key=lambda r: (r['mae'], r['model']))
        improvement = (best_base['mae']-winner['mae'])/best_base['mae'] if best_base['mae'] else 0
        eligible = improvement >= config['promotion_min_mae_improvement'] and abs(winner['bias_pct'] or 0) <= config['max_abs_bias_pct']
        reason = (f"{winner['model']} obtuvo el menor MAE de selección entre los cinco modelos: {winner['mae']:.4f} unidades/SKU/7 días. "
                  f"El baseline {best_base['model']} obtuvo {best_base['mae']:.4f}; mejora relativa {improvement*100:.2f}%. "
                  f"Sesgo {winner['bias_pct']:.2f}%. Los hiperparámetros se eligieron con {config['folds']} folds temporales dentro de entrenamiento. "
                  'La prueba final no participa en esta elección.')
        lock = {'winner': winner['model'], 'reason': reason, 'baseline': best_base['model'],
                'relative_mae_improvement': improvement, 'selection_gate_passed': eligible,
                'status': 'solo_prueba_tecnica' if smoke else ('candidato_academico' if eligible else 'no_supera_criterio_baseline'),
                'production_approved': False, 'locked_before_test': True, 'locked_at': datetime.now(timezone.utc).isoformat(),
                'rule': 'Menor MAE en selección; empate exacto por nombre. Gate: mejora >=2% vs mejor baseline y |sesgo|<=20%.',
                'comparisons': comparisons}
        dump_json(output/'selection.json', lock)
        print('\nElección registrada: '+reason, flush=True)
        chosen = joblib.load(final_models[winner['model']])
        radii, sizes = calibrate_intervals(calibration, nonnegative_predict(chosen, calibration[features]), config)
        bundle = {'schema_version': 1, 'run_id': run_id, 'pipeline': chosen, 'model_name': winner['model'],
                  'features': features, 'numeric_features': [c for c in features if c not in manifest['categorical_features']],
                  'known_skus': sorted(train.sku.unique().tolist()), 'horizon_days': 7, 'data_source': manifest['source'],
                  'interval_radius': radii, 'training_end': str(train.fecha_corte.max().date()),
                  'deployment_status': lock['status']}
        test = df[df.particion.eq('prueba')].copy()
        test_predictions, test_metrics = {}, []
        for name, path in final_models.items():
            model = joblib.load(path)
            test_predictions[name] = nonnegative_predict(model, test[features])
            test_metrics.append({'model': name, 'selected': name == winner['model'], **metrics(test[target], test_predictions[name])})
            del model
            gc.collect()
        for name, column in BASELINES.items():
            test_predictions[name] = test[column].to_numpy()
            test_metrics.append({'model': name, 'selected': False, **metrics(test[target], test_predictions[name])})
        chosen_prediction = test_predictions[winner['model']]
        intervals = predict_bundle(bundle, test[features], allow_simulated=True)
        test['prediction'] = chosen_prediction
        test['lower'] = intervals.limite_inferior_90.to_numpy()
        test['upper'] = intervals.limite_superior_90.to_numpy()
        test['rotation'] = rotation(test.ventas_28d/4)
        test['stockout_diagnostic'] = np.where(test.diagnostico_quiebre_futuro_7d > 0, 'con_quiebre_futuro', 'sin_quiebre_futuro')
        test['interval_hit'] = (test[target] >= test.lower) & (test[target] <= test.upper)
        segments = []
        for dimension in ['familia', 'categoria', 'rotation', 'stockout_diagnostic']:
            for group, part in test.groupby(dimension):
                segments.append({'dimension': dimension, 'group': str(group), **metrics(part[target], part.prediction),
                                 'coverage_pct': float(part.interval_hit.mean()*100)})
        ci = paired_block_ci(test, chosen_prediction, test_predictions[best_base['model']], config)
        evaluation = {'models': test_metrics, 'segments': segments, 'paired_mae_difference': ci,
                      'interval': {'nominal_coverage_pct': config['interval_coverage']*100,
                                   'observed_coverage_pct': float(test.interval_hit.mean()*100),
                                   'mean_width': float((test.upper-test.lower).mean()), 'radius_by_rotation': radii,
                                   'calibration_n_by_rotation': sizes,
                                   'method': 'Cuantil de errores absolutos en bloque temporal de calibración; cortes cada 7 días.',
                                   'limitation': 'Cobertura empírica, sin garantía formal por dependencia temporal y entre productos.'}}
        from ml.reporting import create_reports
        report_assets = create_reports(output, train, test, comparisons, test_metrics, trials,
                                      test_predictions, chosen, features, config, winner['model'])
        model_path = output/'model.joblib'
        joblib.dump(bundle, model_path, compress=3)
        runtime = {p: version(p) for p in PACKAGES}
        contract = {'schema_version': 1, 'run_id': run_id, 'model_name': winner['model'],
                    'model_sha256': sha256(model_path), 'runtime_versions': runtime,
                    'python': platform.python_version(), 'features': features,
                    'numeric_features': bundle['numeric_features'], 'known_skus': bundle['known_skus'],
                    'horizon_days': 7, 'cutoff': 'cierre del día t, America/Lima',
                    'output_unit': 'unidades de venta pagadas en t+1 a t+7', 'data_source': manifest['source'],
                    'selection': lock, 'training_end': bundle['training_end'],
                    'required_history': '56 días completos y fecha de última venta conocida; nunca rellenar faltantes con ceros.',
                    'integration': 'Cargar únicamente este paquete propio, comprobar versiones y usar ml.inference.predict_bundle.',
                    'operational_limit': 'La web necesita recopilar las mismas observaciones; este artefacto no activa compras ni modifica stock.'}
        dump_json(output/'contract.json', contract)
        (output/'runtime-requirements.txt').write_text(''.join(f'{p}=={v}\n' for p, v in runtime.items()), encoding='utf-8')
        loaded, _ = load_trusted_bundle(output)
        sample = test[features].head(12)
        restored = predict_bundle(loaded, sample, allow_simulated=True)
        np.testing.assert_allclose(restored.ventas_estimadas_7d, chosen_prediction[:12], rtol=1e-10, atol=1e-10)
        dump_json(output/'inference_example.json', {'input': sample.to_dict('records'), 'output': restored.to_dict('records')})
        summary = {'schema_version': 1, 'run_id': run_id, 'mode': 'smoke' if smoke else 'full',
                   'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                   'data': data_info, 'selection': lock, 'evaluation': evaluation, 'assets': report_assets,
                   'runtime': runtime, 'git_commit': git_commit, 'git_worktree_dirty': git_dirty,
                   'source_sha256': source_hashes, 'roundtrip_prediction_check': 'passed',
                   'limitations': manifest['limitations'] + [
                       'El objetivo son ventas observadas condicionadas por disponibilidad, no demanda sin restricciones.',
                       'Las ventanas diarias de 7 días se solapan: no sumar objetivos para calcular ventas de un periodo.',
                       'R2 puede ser negativo. WAPE no equivale a porcentaje de exactitud; se omite cuando el total real es cero.',
                       'La prueba se informa para todos los modelos después de congelar la elección; no cambiar ganador por esa tabla.',
                       'El archivo exportado conserva el ajuste evaluado, sin reentrenar usando la prueba final.',
                       'La agrupación de categorías infrecuentes en árboles puede ocultar diferencias entre SKU.',
                       'La búsqueda limita cada ajuste a 80,000 filas de entrenamiento seleccionadas con semilla fija; los ajustes finales usan todas las filas.',
                       'La simulación de inventario posterior es un escenario simplificado, no ahorro económico demostrado.']}
        dump_json(output/'dashboard.json', summary)
        # Archive only the selected model: the other candidates remain reproducible from code/config.
        for path in final_models.values():
            path.unlink()
        dump_json(output/'checksums.json', {str(p.relative_to(output)).replace('\\', '/'): sha256(p)
                    for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'checksums.json'})
        archive = shutil.make_archive(str(output)+'-web', 'zip', output)
        print(f'\nExportación completa: {archive}', flush=True)
    from ml.robustness import strengthen_run
    return strengthen_run(output, data_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=ROOT/'data/ml/roda-v1')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--smoke', action='store_true', help='48 SKU y búsqueda reducida: comprobación técnica, no resultados finales.')
    args = parser.parse_args()
    run_training(args.data, args.output, args.smoke)
