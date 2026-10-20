"""Entrenamiento temporal reproducible sobre cantidades observadas."""
import hashlib
import json
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge, PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metrics(y, pred):
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    error = pred-y
    return dict(n=len(y), mae=float(np.abs(error).mean()),
                rmse=float(np.sqrt((error**2).mean())),
                wape=float(np.abs(error).sum()/y.sum()*100) if y.sum() else None,
                bias=float(error.mean()),
                r2=float(1-(error**2).sum()/((y-y.mean())**2).sum()) if np.var(y) else None)


def frame(records, frequency):
    monthly = frequency == 'monthly'
    window, horizon, freq = (12, 1, 'M') if monthly else (28, 7, 'D')
    result = []
    for sku, group in pd.DataFrame(records).groupby('sku', sort=True):
        series = group.set_index(pd.PeriodIndex(group.period, freq=freq)).units.astype(float)
        grid = pd.period_range(series.index.min(), series.index.max(), freq=freq)
        values = series.reindex(grid).to_numpy()
        for i in range(window, len(grid)+1):
            past = values[i-window:i]
            if np.isfinite(past).sum() < (8 if monthly else 21):
                continue
            end = grid[i-1]+horizon
            f = {f'lag{k}': float(past[-k]) for k in (1, 2, 3, 6, 12)}
            f.update(mean=float(np.nanmean(past)), std=float(np.nanstd(past)),
                     recent=float(np.nanmean(past[-3:])) if np.isfinite(past[-3:]).any() else np.nan,
                     zero_share=float(np.mean(past[np.isfinite(past)] == 0)),
                     missing=int(np.isnan(past).sum()),
                     month_sin=float(np.sin(2*np.pi*end.month/12)),
                     month_cos=float(np.cos(2*np.pi*end.month/12)))
            future = values[i:i+horizon]
            target = float(future.sum()) if len(future) == horizon and np.isfinite(future).all() else np.nan
            result.append(dict(sku=sku, cutoff=str(grid[i-1]), period=str(end), target=target,
                               baseline=f['mean']*horizon, **f))
    if not result:
        raise ValueError('Historial insuficiente: se necesitan 12 meses o 28 días por producto.')
    return pd.DataFrame(result)


FEATURES = ['lag1', 'lag2', 'lag3', 'lag6', 'lag12', 'mean', 'std', 'recent',
            'zero_share', 'missing', 'month_sin', 'month_cos']


def candidates():
    trees = dict(n_estimators=60, max_depth=10, min_samples_leaf=5, n_jobs=2, random_state=42)
    return {
        'Ridge': make_pipeline(SimpleImputer(add_indicator=True), StandardScaler(), Ridge(alpha=10)),
        'Poisson': make_pipeline(SimpleImputer(add_indicator=True), StandardScaler(),
                                 PoissonRegressor(alpha=.1, max_iter=500)),
        'Random Forest': make_pipeline(SimpleImputer(add_indicator=True), RandomForestRegressor(**trees)),
        'Extra Trees': make_pipeline(SimpleImputer(add_indicator=True), ExtraTreesRegressor(**trees)),
        'Hist. Gradient Boosting': make_pipeline(SimpleImputer(add_indicator=True),
             HistGradientBoostingRegressor(max_iter=150, max_leaf_nodes=31, l2_regularization=1, random_state=42)),
    }


def train(request):
    data = frame(request['records'], request['frequency'])
    cutoff = max(r['period'] for r in request['records'])
    freq = 'M' if request['frequency'] == 'monthly' else 'D'
    split = str(pd.Period(cutoff, freq=freq)-(6 if freq == 'M' else 28))
    known = data[data.target.notna() & data.period.le(cutoff)]
    fit = known[known.period.le(split)]
    valid = known[known.cutoff.ge(split) & known.period.gt(split)]
    if len(fit) < 100 or len(valid) < 30 or fit.target.sum() <= 0:
        raise ValueError('Faltan observaciones para separar entrenamiento y validación temporal (mínimo 100/30 filas).')
    scores = []
    folds = [(fit, valid)]
    if freq == 'D':
        # Three disjoint 14-day windows; each target covers seven days.
        # Each fold is fitted only on targets fully known at its origin.
        folds = []
        for offset in (42, 28, 14):
            origin = pd.Period(cutoff, freq='D')-offset
            end = origin+14
            train_rows = known[known.period.le(str(origin))]
            validation = known[known.cutoff.ge(str(origin)) & known.period.le(str(end))]
            distance = (pd.to_datetime(validation.cutoff)-origin.to_timestamp()).dt.days
            validation = validation[distance.mod(7).eq(0)]
            if len(train_rows) < 100 or len(validation) < 2:
                raise ValueError('Faltan datos para tres ventanas temporales: mínimo 100 filas de entrenamiento y dos objetivos semanales por ventana.')
            folds.append((train_rows, validation))
        valid = pd.concat([v for _, v in folds])
        fit = folds[0][0]
    for name, model in candidates().items():
        predictions, actuals, fold_scores = [], [], []
        for training, validation in folds:
            model.fit(training[FEATURES], training.target)
            pred = np.maximum(0, model.predict(validation[FEATURES]))
            predictions.extend(pred)
            actuals.extend(validation.target)
            fold_scores.append(metrics(validation.target, pred))
        scores.append(dict(model=name, folds=fold_scores, **metrics(actuals, predictions)))
    winner = min(scores, key=lambda s: s['mae'])['model']
    final = candidates()[winner]
    final.fit(known[FEATURES], known.target)
    bundle = dict(model=final, features=FEATURES, frequency=request['frequency'],
                  cutoff=cutoff, skus=sorted(known.sku.unique().tolist()), schema=1)
    joblib.dump(bundle, request['bundle'])
    return dict(winner=winner, candidates=scores, validation_baseline=metrics(valid.target, valid.baseline),
                beats_baseline=min(s['mae'] for s in scores) < metrics(valid.target, valid.baseline)['mae'],
                cutoff=cutoff, split=split, fit_rows=len(fit), validation_rows=len(valid),
                refit_rows=len(known), features=FEATURES, model_sha256=digest(request['bundle']),
                temporal_windows=len(folds),
                windows=[dict(train_rows=len(t), validation_rows=len(v),
                              training_end=str(t.period.max()), validation_start=str(v.cutoff.min()),
                              validation_end=str(v.period.max())) for t, v in folds],
                validation_protocol='Tres ventanas de 14 días; objetivos semanales sin solapamiento.' if freq == 'D' else 'Últimos seis meses.',
                reason='Menor MAE en validación temporal. Reajustado con el historial disponible hasta el corte.',
                limitations=['No estima demanda perdida ni stock: solo cantidades observadas.',
                             'Las entradas ausentes se imputan dentro del entrenamiento; los objetivos ausentes se excluyen.',
                             'No demuestra precisión futura: debe evaluarse con nuevas ventas observadas.' if freq == 'D'
                             else 'No demuestra precisión en Perú ni correspondencia con los SKU de RODA.'])


def load_model(spec):
    if digest(spec['bundle']) != spec['sha256']:
        raise ValueError('El archivo del modelo no coincide con el hash registrado.')
    return joblib.load(spec['bundle'])


def predict(request):
    bundle = load_model(request)
    data = frame(request['records'], bundle['frequency'])
    cutoff = max(r['period'] for r in request['records'])
    selected = data[data.cutoff.eq(cutoff) & data.sku.isin(bundle['skus'])].copy()
    if selected.empty:
        raise ValueError('No hay productos conocidos con historial suficiente hasta el corte.')
    selected['prediction'] = np.maximum(0, bundle['model'].predict(selected[FEATURES]))
    return dict(cutoff=cutoff, version=request.get('id'), model_sha256=request['sha256'],
                frequency=bundle['frequency'],
                items=selected[['sku', 'period', 'prediction', 'baseline', 'missing']].to_dict('records'),
                excluded=len({r['sku'] for r in request['records']})-len(selected))


def compare(request):
    models = [load_model(s) for s in request['versions']]
    if len({b['frequency'] for b in models}) != 1:
        raise ValueError('Las versiones deben usar la misma frecuencia.')
    data = frame(request['records'], models[0]['frequency'])
    cutoff = max(b['cutoff'] for b in models)
    known = set.intersection(*(set(b['skus']) for b in models))
    common = data[data.cutoff.ge(cutoff) & data.period.gt(cutoff) &
                  data.target.notna() & data.sku.isin(known)].copy()
    if len(common) < 30:
        raise ValueError('Importa al menos 30 objetivos posteriores al corte más reciente para comparar las versiones.')
    # Weekly targets do not overlap in the comparison.
    if models[0]['frequency'] == 'daily':
        distance = (pd.to_datetime(common.cutoff)-pd.Timestamp(cutoff)).dt.days
        common = common[distance.mod(7).eq(0)]
    if len(common) < 30:
        raise ValueError('Faltan periodos completos y no superpuestos para evaluar.')
    scores, per_period = [], []
    for spec, bundle in zip(request['versions'], models):
        pred = np.maximum(0, bundle['model'].predict(common[FEATURES]))
        scores.append(dict(version=spec['id'], **metrics(common.target, pred)))
        tmp = common.assign(prediction=pred)
        for period, group in tmp.groupby('period'):
            per_period.append(dict(version=spec['id'], period=period, actual=float(group.target.sum()),
                                   predicted=float(group.prediction.sum()), **metrics(group.target, group.prediction)))
    # Model choice was already fixed using validation, never using this comparison.
    baseline_score = metrics(common.target, common.baseline)
    best_score = min(s['mae'] for s in scores)
    baseline_wins = baseline_score['mae'] <= best_score
    recommended = scores[1]['version'] if len(scores) > 1 and scores[1]['mae'] < scores[0]['mae']*.99 else scores[0]['version']
    recommended_score = next(s['mae'] for s in scores if s['version'] == recommended)
    return dict(start=common.period.min(), end=common.period.max(), rows=len(common),
                products=common.sku.nunique(), scores=scores,
                baseline=baseline_score, baseline_wins=baseline_wins,
                approved_recommendation=recommended_score < baseline_score['mae']*.99,
                periods=per_period,
                protocol='Mismas filas posteriores a ambos entrenamientos; avance temporal con historial observado anterior.',
                recommended=recommended)


if __name__ == '__main__':
    try:
        request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        with threadpool_limits(limits=2):
            result = {'train': train, 'predict': predict, 'compare': compare}[request['action']](request)
        Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    except Exception as exc:
        Path(sys.argv[2]).write_text(json.dumps({'error': str(exc)}, ensure_ascii=False), encoding='utf-8')
        raise
