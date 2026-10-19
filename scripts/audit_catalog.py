import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.db import DB, init_db, now


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply-demo',action='store_true')
    args=parser.parse_args()
    backup=None
    if args.apply_demo:
        folder=ROOT/'data/backups';folder.mkdir(parents=True,exist_ok=True)
        backup=folder/f'catalog-audit-{now()[:19].replace(":", "-")}-{uuid4().hex[:6]}.db'
        with sqlite3.connect(DB) as source,sqlite3.connect(backup) as target: source.backup(target)
    init_db()
    from backend.services.catalog_quality import audit_catalog, normalize_demo
    if args.apply_demo:
        print('Respaldo:',backup)
        print('Cambios:',json.dumps(normalize_demo(),ensure_ascii=False))
    report=audit_catalog()
    folder=ROOT/'artifacts/catalog-audit';folder.mkdir(parents=True,exist_ok=True)
    for name,records in [('products',report['rows']),('issues',report['issues'])]:
        with (folder/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as output:
            writer=csv.DictWriter(output,fieldnames=list(records[0]) if records else ['product_id','sku'])
            writer.writeheader();writer.writerows(records)
    print(json.dumps({k:report[k] for k in ['checked_at','products','summary','empty_categories','checks']},ensure_ascii=False))


if __name__=='__main__': main()
