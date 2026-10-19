import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from ml.inference import features_from_history, load_trusted_bundle, predict_bundle, sha256
from ml.train import metrics


def must_reject(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Se aceptó una entrada inválida.')


def verify(folder):
    for name, expected in json.loads((folder/'checksums.json').read_text(encoding='utf-8')).items():
        assert sha256(folder/name) == expected, f'Hash distinto: {name}'
    bundle, contract = load_trusted_bundle(folder)
    example = json.loads((folder/'inference_example.json').read_text(encoding='utf-8'))
    frame = pd.DataFrame(example['input'])
    predicted = predict_bundle(bundle, frame, allow_simulated=True)
    np.testing.assert_allclose(predicted.ventas_estimadas_7d,
                               [r['ventas_estimadas_7d'] for r in example['output']], rtol=1e-9)
    must_reject(lambda: predict_bundle(bundle, frame))
    must_reject(lambda: predict_bundle(bundle, frame.drop(columns=['ventas_7d']), allow_simulated=True))
    bad = frame.copy()
    bad.loc[0, 'sku'] = 'SKU-NO-ENTRENADO'
    must_reject(lambda: predict_bundle(bundle, bad, allow_simulated=True))
    bad = frame.copy()
    bad.loc[0, 'ventas_7d'] = np.nan
    must_reject(lambda: predict_bundle(bundle, bad, allow_simulated=True))
    bad = frame.copy()
    bad.loc[0, 'ventas_7d'] = -1
    must_reject(lambda: predict_bundle(bundle, bad, allow_simulated=True))
    bad = frame.copy()
    bad.loc[0, 'disponible_fin'] += 1
    must_reject(lambda: predict_bundle(bundle, bad, allow_simulated=True))
    assert metrics([0, 0], [0, 1])['wape_pct'] is None
    assert metrics([0, 0], [0, 1])['r2'] is None
    assert metrics([1, 3], [2, 2])['mae'] == 1
    summary = json.loads((folder/'dashboard.json').read_text(encoding='utf-8'))
    assert summary['selection']['locked_before_test'] is True
    assert len([r for r in summary['selection']['comparisons'] if r['kind'] == 'ML']) == 5
    assert len(summary['evaluation']['models']) == 7
    assert len(summary['assets']) == 12
    for fold in json.loads((folder/'search.json').read_text(encoding='utf-8')):
        assert fold['train_label_end'] < fold['evaluation_start']
    # Replay the raw history that produced the first test features, independently of CSV feature storage.
    skus = list(frame.sku.head(3))
    cutoff = summary['data']['dates']['prueba']['start']
    raw = pd.read_csv(ROOT/'data/ml/roda-v1/inventario_ventas_diarias.csv.gz', encoding='utf-8-sig')
    history = raw[raw.sku.isin(skus) & (raw.fecha <= cutoff)].copy()
    derived = features_from_history(history).set_index('sku')
    expected = frame.set_index('sku')
    numeric = contract['numeric_features']
    for sku in skus:
        np.testing.assert_allclose(derived.loc[sku, numeric].astype(float), expected.loc[sku, numeric].astype(float), rtol=1e-5, atol=1e-5)
    must_reject(lambda: features_from_history(history.drop(history.index[50])))
    must_reject(lambda: features_from_history(pd.concat([history, history.iloc[:1]])))
    print(json.dumps({'status': 'passed', 'mode': summary['mode'], 'models': 5,
                      'images': 12, 'feature_parity_skus': len(skus),
                      'checks': ['checksums', 'joblib_roundtrip', 'temporal_purge', 'invalid_inputs',
                                 'zero_metrics', 'history_feature_parity', 'history_gaps']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    verify(parser.parse_args().folder)
