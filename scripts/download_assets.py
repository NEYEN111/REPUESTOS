"""Fetch the public reference photos declared in the academic demo catalog."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
from urllib.request import Request, urlopen
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'backend' / 'static'
HERO = 'https://images.unsplash.com/photo-1486262715619-67b85e0b08d3?auto=format&fit=crop&w=1920&q=85'

def fetch(url: str) -> bytes:
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if curl:
        result = subprocess.run([curl, '--fail', '--location', '--silent', '--show-error', '--max-time', '35', '--retry', '2', url], capture_output=True, check=True)
        return result.stdout
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=35) as response:
        return response.read()

def download(row: dict, force: bool = False) -> dict:
    target = STATIC / 'category' / (row['slug'] + '.webp')
    thumb = target.with_name(row['slug'] + '-thumb.webp')
    if force or not target.exists() or not thumb.exists():
        photo = Image.open(BytesIO(fetch(row['source_url']))).convert('RGB')
        photo.load()
        if min(photo.size) < 30:
            raise ValueError('Imagen de origen demasiado pequeña: ' + row['slug'])
        # Preserve the reference photo; place on a neutral square product canvas.
        for out, size in [(target, 720), (thumb, 240)]:
            fitted = ImageOps.contain(photo, (size - 32, size - 32), Image.Resampling.LANCZOS)
            canvas = Image.new('RGB', (size, size), 'white')
            canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
            canvas.save(out, 'WEBP', quality=88, method=6)
    return {'slug': row['slug'], 'name': row['name'], 'source_url': row['source_url'], 'image': row['image'], 'thumbnail': row['thumbnail'], 'usage': 'academic-local-demo', 'image_note': 'Fotografía referencial del tipo de repuesto; revisar la ficha y compatibilidad.'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'data' / 'catalog_seed.json').read_text(encoding='utf-8'))
    (STATIC / 'category').mkdir(parents=True, exist_ok=True)
    rows = [row for category in catalog for row in category['subcategories']]
    manifest, failures = [], []
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {pool.submit(download, row, args.force): row for row in rows}
        for future in as_completed(jobs):
            try:
                manifest.append(future.result())
            except Exception as exc:
                failures.append({'slug': jobs[future]['slug'], 'error': str(exc)})
                print('ERROR', jobs[future]['slug'], str(exc), flush=True)
    hero = STATIC / 'hero.webp'
    if args.force or not hero.exists():
        try:
            image = Image.open(BytesIO(fetch(HERO))).convert('RGB')
            image.thumbnail((1920, 1280), Image.Resampling.LANCZOS)
            image.save(hero, 'WEBP', quality=88, method=6)
        except Exception as exc:
            failures.append({'slug': 'hero', 'error': str(exc)})
    payload = {'images': sorted(manifest, key=lambda r: r['slug']), 'hero': {'source_url': HERO, 'image': '/static/hero.webp'}, 'failures': failures}
    (STATIC / 'category' / 'manifest.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Fotos listas: {len(manifest)}/{len(rows)}. Errores: {len(failures)}.', flush=True)
    if failures:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
