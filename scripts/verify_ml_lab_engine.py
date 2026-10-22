"""Comprobaciones focalizadas de causalidad y compatibilidad de versiones."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from ml.lab_engine import FEATURES, compare, digest, feature_names, frame, predict


def filtered_origins(folder):
    reductions = []
    for frequency, count, window, freq in [('daily', 100, 28, 'D'), ('monthly', 36, 12, 'M')]:
        periods = pd.period_range('2020-01-01', periods=count, freq=freq).astype(str).tolist()
        records = []
        for sku in ['REGULAR', 'GAPS', 'NULLS', 'SHORT', 'STALE', 'UNKNOWN']:
            for i, period in enumerate(periods):
                if sku == 'GAPS' and i in {10, count-4}:
                    continue
                if sku == 'SHORT' and i < count-window+2:
                    continue
                if sku == 'STALE' and i == count-1:
                    continue
                units = None if sku == 'NULLS' and i in {14, count-2} else int(i % 4 == 0)*(1+i % 3)
                records.append(dict(sku=sku, period=period, units=units))
        original = frame(records, frequency)
        origins = {periods[-1], periods[-3], periods[-8]}
        filtered = frame(records, frequency, origins=origins)
        expected = original[original.cutoff.isin(origins)].reset_index(drop=True)
        # Compare every column, including the extended features, missing flags,
        # targets and baselines. Filtering must not shorten signal history.
        pd.testing.assert_frame_equal(filtered, expected)
        assert 'SHORT' not in set(filtered.sku)
        latest = filtered[filtered.cutoff.eq(periods[-1])]
        assert 'STALE' not in set(latest.sku) and latest.missing.max() > 0
        try:
            frame([r for r in records if r['sku'] == 'SHORT'], frequency, origins={periods[-1]})
        except ValueError:
            pass
        else:
            raise AssertionError('La predicción aceptó historial insuficiente.')
        known = ['REGULAR', 'GAPS', 'NULLS', 'SHORT', 'STALE']
        expected = original[original.cutoff.eq(periods[-1]) & original.sku.isin(known)]
        for label, features in [('stable', FEATURES), ('extended', feature_names(frequency))]:
            # A feature-sensitive estimator checks prediction parity as well as
            # frame parity; this is a tiny disposable fixture, not a new model.
            model = make_pipeline(SimpleImputer(), Ridge(alpha=10))
            training = original[original.target.notna()]
            model.fit(training[features], training.target)
            path = str(Path(folder)/f'{frequency}-{label}.joblib')
            joblib.dump(dict(model=model, features=features, frequency=frequency,
                             cutoff=periods[-8], skus=known), path)
            spec = dict(id=label, bundle=path, sha256=digest(path))
            result = predict(dict(records=records, **spec))
            assert [r['sku'] for r in result['items']] == expected.sku.tolist()
            np.testing.assert_array_equal([r['prediction'] for r in result['items']],
                                          np.maximum(0, model.predict(expected[features])))
            assert result['excluded'] == 3  # Unknown, stale and insufficient.
            json.dumps(result, allow_nan=False)
            # The global cutoff is not silently moved back when only an unknown
            # product has a newer observation.
            newer = str(pd.Period(periods[-1], freq=freq)+1)
            try:
                predict(dict(records=records+[dict(sku='UNKNOWN', period=newer, units=0)], **spec))
            except ValueError:
                pass
            else:
                raise AssertionError('La predicción retrocedió su fecha de corte.')
        reductions.append(f'{frequency}: {len(original)} -> {len(latest)} filas al corte')
    return '; '.join(reductions)


def verify():
    records = [dict(sku=f'SKU-{sku}', period=str(day.date()), units=int((i+sku) % 5 == 0))
               for sku in range(12)
               for i, day in enumerate(pd.date_range('2025-01-01', periods=150))]
    original = frame(records, 'daily')
    changed = frame([dict(r, units=99) if r['period'] > '2025-04-01' else r for r in records], 'daily')
    names = feature_names('daily')
    pd.testing.assert_frame_equal(original.loc[original.cutoff.le('2025-04-01'), names],
                                  changed.loc[changed.cutoff.le('2025-04-01'), names])
    # Old and new artifacts must use their own saved feature contract.
    scratch = Path(__file__).resolve().parents[1]/'.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        reductions = filtered_origins(folder)
        versions = []
        for index, features in enumerate((FEATURES, names)):
            model = DummyRegressor(strategy='constant', constant=1.)
            model.fit(original[features], np.ones(len(original)))
            path = str(Path(folder)/f'v{index}.joblib')
            joblib.dump(dict(model=model, features=features, frequency='daily',
                             cutoff='2025-04-01', skus=sorted(original.sku.unique())), path)
            spec = dict(id=str(index), bundle=path, sha256=digest(path))
            versions.append(spec)
            assert len(predict(dict(records=records, **spec))['items']) == 12
        result = compare(dict(records=records, versions=versions))
        assert result['rows'] == 12*8
        assert len(result['references']) == 3
        assert result['scores'][0]['mae'] == result['scores'][1]['mae']
        json.dumps(result, allow_nan=False)
    print('OK: sin fuga temporal, versiones anteriores compatibles, comparación semanal y JSON válidos.')
    print('OK: orígenes filtrados e inferencia idénticos con ceros, huecos y faltantes; '+reductions)


if __name__ == '__main__':
    verify()
