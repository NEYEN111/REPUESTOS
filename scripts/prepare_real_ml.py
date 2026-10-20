"""Descarga verificable y archivos de importación, sin completar ventas ausentes."""
import csv
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'ml/examples/carparts'
URL = 'https://zenodo.org/records/4656022/files/car_parts_dataset_with_missing_values.zip?download=1'
MD5 = '7b104f4549c0b10ad22299304d5fee63'


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = OUT/'source.zip'
    if not raw.exists():
        cached = ROOT/'data/ml/carparts/source.zip'
        raw.write_bytes(cached.read_bytes() if cached.exists() else urllib.request.urlopen(URL).read())
    if hashlib.md5(raw.read_bytes()).hexdigest() != MD5:
        raise ValueError('El archivo no coincide con el checksum publicado por Zenodo.')
    with zipfile.ZipFile(raw) as z:
        text = z.read('car_parts_dataset_with_missing_values.tsf').decode()
    stages = [[], [], []]
    total = missing = count = 0
    for line in text.splitlines():
        if not line.startswith('T'):
            continue
        sku, start, values = line.split(':')
        if start != '1998-01-01 00-00-00' or len(values.split(',')) != 51:
            raise ValueError('La estructura temporal de la fuente cambió. Revisar antes de dividir.')
        count += 1
        for i, value in enumerate(values.split(',')):
            period = f'{1998+i//12:04d}-{i%12+1:02d}'
            stage = 0 if i < 36 else 1 if i < 45 else 2
            stages[stage].append([period, sku, '' if value == '?' else value])
            total += 1
            missing += value == '?'
    files = []
    for name, rows in zip(['01_historial_inicial.csv', '02_datos_nuevos.csv', '03_ventas_posteriores.csv'], stages):
        path = OUT/name
        with path.open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f); writer.writerow(['periodo', 'sku', 'unidades']); writer.writerows(rows)
        files.append(dict(name=name, rows=len(rows), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    provenance = dict(title='Car Parts · Monash Forecasting Repository', source_url='https://zenodo.org/records/4656022',
        download_url=URL, doi='10.5281/zenodo.4656022', license='CC BY 4.0',
        authors=['Rakshitha Godahewa', 'Christoph Bergmeir', 'Geoff Webb', 'Rob Hyndman', 'Pablo Montero-Manso'],
        original='R expsmooth, carparts; Hyndman (2015)', frequency='monthly',
        start='1998-01', end='2002-03', series=count, rows=total, missing=missing,
        source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(), files=files,
        treatment='Valores ? preservados como vacíos. Ninguna venta ni fecha inventada. Series anónimas, sin asociación al catálogo RODA.',
        missing_fields=['Precios', 'Costos', 'Stock', 'Descripción de pieza', 'País verificable de cada serie'],
        limitation='Evaluación histórica mensual; no acredita precisión actual en Perú ni un horizonte de siete días.')
    (OUT/'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    return provenance


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False, indent=2))
