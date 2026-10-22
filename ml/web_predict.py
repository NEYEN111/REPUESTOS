"""Proceso de inferencia aislado; recibe JSON por stdin y devuelve JSON por stdout."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
from threadpoolctl import threadpool_limits
from ml.inference import load_trusted_bundle, features_from_history, predict_bundle, sha256

ROOT=Path(__file__).resolve().parents[1]


def reference_groups(path):
    """Read the SKU-sorted reference history without loading two years at once."""
    pending=pd.DataFrame()
    previous=''
    for chunk in pd.read_csv(path,encoding='utf-8-sig',chunksize=4096):
        frame=pd.concat((pending,chunk),ignore_index=True) if not pending.empty else chunk
        if not frame.sku.is_monotonic_increasing or (previous and frame.sku.iloc[0]<previous):
            raise ValueError('El historial de referencia debe estar ordenado por SKU.')
        final_sku=frame.sku.iloc[-1]
        pending=frame.loc[frame.sku.eq(final_sku)].copy()
        for sku,group in frame.loc[frame.sku.ne(final_sku)].groupby('sku',sort=False):
            yield sku,group
            previous=sku
    if not pending.empty:
        yield pending.sku.iloc[0],pending


def predict(request):
    bundle,contract=load_trusted_bundle(ROOT/'ml/deployed/roda-v2')
    if request['source']=='referencia':
        folder=ROOT/'data/ml/roda-v1'
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        entry=manifest['files']['inventario_ventas_diarias.csv']
        path=folder/entry['gzip_file']
        if sha256(path)!=entry['gzip_sha256']: raise ValueError('El historial de referencia no coincide con su hash.')
        cutoff=manifest['config']['end_date']
        groups=reference_groups(path)
    elif request['source']=='operacion':
        history=pd.DataFrame(request['history'])
        cutoff=request['cutoff']
        if history.empty: return {'items':[],'rejected':[],'cutoff':cutoff}
        history=history[history.sku.isin(request['skus']) & history.fecha.le(cutoff)]
        groups=history.groupby('sku',sort=True)
    else: raise ValueError('Origen de historial no permitido.')
    items=[]; rejected=[]
    features=[]; histories={}
    allowed=set(request['skus'])
    seen=set()
    for sku,group in groups:
        if sku not in allowed: continue
        seen.add(sku)
        try:
            group=group[group.fecha.le(cutoff)]
            if group.empty: raise ValueError('No hay observaciones completas anteriores al corte.')
            group=group.sort_values('fecha')
            if sku not in bundle['known_skus']: raise ValueError('Producto nuevo: no existe en el entrenamiento.')
            if str(group.fecha.iloc[-1])!=cutoff: raise ValueError('Falta el cierre de la fecha de corte.')
            # Keep only the final continuous sequence; never bridge unknown dates.
            gap=pd.to_datetime(group.fecha).diff().ne(pd.Timedelta(days=1)).to_numpy()
            starts=[i for i,value in enumerate(gap) if value]
            group=group.iloc[starts[-1]:]
            f=features_from_history(group).iloc[0].to_dict()
            features.append(f)
            histories[sku]=group[['fecha','ventas_pagadas','disponible_fin']].tail(56).to_dict('records')
        except ValueError as exc:
            rejected.append({'sku':sku,'reason':str(exc)})
    rejected.extend({'sku':sku,'reason':'No hay observaciones completas anteriores al corte.'}
                    for sku in sorted(allowed-seen))
    if features:
        frame=pd.DataFrame(features)
        with threadpool_limits(limits=2): results=predict_bundle(bundle,frame,allow_simulated=True)
        for f,result in zip(features,results.to_dict('records')):
            items.append({'sku':result['sku'],'prediction':result['ventas_estimadas_7d'],
                'lower_bound':result['limite_inferior_90'],'upper_bound':result['limite_superior_90'],
                'available':int(f['disponible_fin']),'rotation':result['rotacion_observada'],
                'review':bool(result['revision_recomendada']),'coverage':result['cobertura_stock'],
                'reasons':result['motivos_revision'],'features':f,'history':histories[result['sku']]})
    return {'items':items,'rejected':rejected,'cutoff':cutoff,'model_hash':contract['model_sha256'],
            'horizon_start':(date.fromisoformat(cutoff)+timedelta(days=1)).isoformat(),
            'horizon_end':(date.fromisoformat(cutoff)+timedelta(days=7)).isoformat()}


if __name__=='__main__':
    try:
        result=predict(json.load(sys.stdin))
        print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False))
        sys.exit(1)
