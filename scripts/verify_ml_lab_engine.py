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
from ml.lab_engine import FEATURES, compare, digest, feature_names, frame, predict


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


if __name__ == '__main__':
    verify()
