"""Precompute the fixed academic reference forecast with the trained model."""
import gzip
import json
from pathlib import Path

from ml.web_predict import predict

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'ml/deployed/roda-v2'
DATA=ROOT/'data/ml/roda-v1'


def main():
    contract=json.loads((BUNDLE/'contract.json').read_text(encoding='utf-8'))
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    result=predict({'source':'referencia','skus':contract['known_skus'],
                    'cutoff':manifest['config']['end_date'],'history':[]})
    if len(result['items'])+len(result['rejected'])!=len(contract['known_skus']):
        raise RuntimeError('El pronóstico no cubre el catálogo entrenado.')
    payload={'schema_version':1,'model_sha256':contract['model_sha256'],
             'dataset_sha256':manifest['files']['inventario_ventas_diarias.csv']['gzip_sha256'],
             'cutoff':result['cutoff'],'result':result}
    target=BUNDLE/'reference_predictions.json.gz'
    with target.open('wb') as file:
        with gzip.GzipFile(filename='',mode='wb',fileobj=file,mtime=0) as stream:
            stream.write(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8'))
    print(f'{target.name}: {len(result["items"])} pronósticos, {len(result["rejected"])} excluidos')


if __name__=='__main__':
    main()
