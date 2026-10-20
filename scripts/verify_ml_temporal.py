"""Ejercicio numérico con fixtures artificiales, guardados únicamente en .tmp."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml.lab_engine import train, frame, predict, compare, FEATURES


def run():
    folder = Path(tempfile.mkdtemp(prefix='ml-temporal-', dir=ROOT/'.tmp'))
    rng = np.random.default_rng(42)
    records = [
        dict(sku=f'TEST-{sku}', period=(date(2020, 1, 1)+timedelta(days=day)).isoformat(),
             units=int(rng.poisson(1+sku/4)))
        for sku in range(10) for day in range(100)
    ]
    original = frame(records, 'daily')
    changed = [dict(r, units=999 if r['period'] > '2020-03-01' else r['units']) for r in records]
    modified = frame(changed, 'daily')
    left = original[original.cutoff <= '2020-03-01'][FEATURES].to_numpy()
    right = modified[modified.cutoff <= '2020-03-01'][FEATURES].to_numpy()
    assert np.allclose(left, right, equal_nan=True), 'Las variables incorporaron ventas futuras.'
    # Removing a day creates unknown targets; it does not silently create zero sales.
    gap = frame([r for r in records if r['period'] != '2020-03-15'], 'daily')
    assert gap[(gap.period >= '2020-03-15') & (gap.cutoff < '2020-03-15')].target.isna().all()
    with threadpool_limits(limits=2):
        report = train(dict(records=records, frequency='daily', bundle=str(folder/'fixture.joblib')))
        assert len(report['candidates']) == 5
        assert report['temporal_windows'] == 3
        assert all(len(m['folds']) == 3 for m in report['candidates'])
        assert report['validation_rows'] == 60  # 10 SKU × 2 weeks × 3 disjoint windows.
        result = predict(dict(records=records, bundle=str(folder/'fixture.joblib'), sha256=report['model_sha256'], id='fixture'))
        assert len(result['items']) == 10 and all(r['prediction'] >= 0 for r in result['items'])
        later = records + [
            dict(sku=f'TEST-{sku}', period=(date(2020, 1, 1)+timedelta(days=day)).isoformat(),
                 units=int(rng.poisson(1+sku/4)))
            for sku in range(10) for day in range(100, 140)
        ]
        checked = compare(dict(records=later, versions=[
            dict(id='fixture', bundle=str(folder/'fixture.joblib'), sha256=report['model_sha256'])]))
        assert len(checked['scores']) == 1 and checked['recommended'] == 'fixture'
        assert checked['rows'] >= 30 and checked['start'] > report['cutoff']
    print('PASS: cinco algoritmos entrenados; tres ventanas sin solapamiento; sin fuga futura; objetivos desconocidos excluidos; joblib, predicción y primera comparación verificados.')
    print('Fixture artificial de verificación, no incorporada a la tienda. Ganador:', report['winner'])


if __name__ == '__main__':
    run()
