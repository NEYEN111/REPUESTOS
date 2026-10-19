import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix, mean_absolute_error

from ml.inference import nonnegative_predict

INK, RED, GRAY, GREEN = '#20272b', '#c84b32', '#7b858c', '#237967'


def negative_mae(estimator, x, y):
    return -mean_absolute_error(y, nonnegative_predict(estimator, x))


def create_reports(output, train, test, comparisons, scores, trials, predictions, pipeline, features, config, winner):
    from ml.train import dump_json
    output = Path(output)
    images = output/'images'
    images.mkdir(exist_ok=True)
    assets = []
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.labelcolor': INK, 'text.color': INK,
                         'axes.titleweight': 'bold', 'figure.facecolor': 'white', 'savefig.facecolor': 'white'})

    def save(fig, slug, title, description):
        fig.suptitle(title, x=0.035, ha='left', fontsize=15, fontweight='bold')
        fig.text(0.035, 0.015, 'RODA · Datos simulados · '+description, fontsize=8, color=GRAY)
        fig.tight_layout(rect=(0.02, 0.05, 0.98, 0.94))
        fig.savefig(images/f'{slug}.png', dpi=150)
        fig.savefig(images/f'{slug}.svg')
        plt.close(fig)
        assets.append({'id': slug, 'title': title, 'description': description,
                       'png': f'images/{slug}.png', 'svg': f'images/{slug}.svg'})

    y = test.objetivo_ventas_7d.to_numpy()
    p = test.prediction.to_numpy()
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    histogram = train.objetivo_ventas_7d.value_counts().sort_index()
    ax[0].bar(histogram.index, histogram.values, color=INK)
    ax[0].set(xlabel='Ventas en los próximos 7 días', ylabel='Filas de entrenamiento', yscale='log')
    daily_train = train.groupby('fecha_corte').objetivo_ventas_7d.mean()
    ax[1].plot(daily_train.index, daily_train.values, color=RED)
    ax[1].set(ylabel='Ventas medias / SKU / horizonte', xlabel='Fecha de corte')
    ax[1].tick_params(axis='x', rotation=25)
    save(fig, '01_distribucion', 'Distribución y evolución del objetivo', 'Exploración del entrenamiento; horizontes diarios solapados.')
    dump_json(output/'eda.json', {'training_target_distribution': [{'units': int(k), 'rows': int(v)} for k, v in histogram.items()],
                                 'training_target_by_cutoff': [{'date': str(k.date()), 'mean': float(v)} for k, v in daily_train.items()]})

    cv = pd.DataFrame([{k: v for k, v in r.items() if k != 'parameters'} for r in trials])
    cv.to_csv(output/'busqueda_temporal.csv', index=False, encoding='utf-8-sig')
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for name, rows in cv.groupby('model'):
        best = rows.groupby('candidate').mae.mean().idxmin()
        subset = rows[rows.candidate.eq(best)]
        ax.plot(subset.fold, subset.mae, marker='o', label=name)
    ax.set(xlabel='Fold temporal (entrenamiento creciente)', ylabel='MAE, unidades/SKU/7 días')
    ax.set_xticks(sorted(cv.fold.unique()))
    ax.legend(fontsize=8, ncol=2)
    save(fig, '02_validacion_temporal', 'Estabilidad durante la validación temporal', 'Hiperparámetros elegidos dentro de entrenamiento; purga de 7 días.')

    comparison = pd.DataFrame(comparisons).drop(columns=['parameters'])
    comparison.to_csv(output/'comparacion_seleccion.csv', index=False, encoding='utf-8-sig')
    ordered = comparison.sort_values('mae', ascending=False)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.barh(ordered.model, ordered.mae, color=[RED if m == winner else GRAY for m in ordered.model])
    ax.set(xlabel='MAE, unidades/SKU/7 días (menor es mejor)')
    for i, value in enumerate(ordered.mae):
        ax.text(value, i, f'  {value:.3f}', va='center', fontsize=9)
    ax.set_xlim(0, ordered.mae.max()*1.18)
    save(fig, '03_comparacion', 'Cinco modelos y dos referencias de comparación', 'Elección basada sólo en el bloque de selección, anterior a calibración y prueba.')

    score_table = pd.DataFrame(scores).set_index('model')
    score_table.to_csv(output/'metricas_prueba.csv', encoding='utf-8-sig')
    columns = ['mae', 'rmse', 'wape_pct', 'bias_pct', 'r2']
    values = score_table[columns].astype(float).to_numpy()
    # Color normalizes each metric separately; displayed numbers retain their real units.
    cost = values.copy()
    cost[:, 3] = np.abs(cost[:, 3])
    cost[:, 4] = -cost[:, 4]
    low, high = np.nanmin(cost, axis=0), np.nanmax(cost, axis=0)
    scaled = (cost-low)/np.where(high > low, high-low, 1)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.imshow(scaled, cmap='Oranges', vmin=0, vmax=1, aspect='auto')
    ax.set_xticks(range(len(columns)), ['MAE', 'RMSE', 'WAPE (%)', 'Sesgo (%)', 'R²'])
    ax.set_yticks(range(len(score_table)), score_table.index)
    for i in range(len(values)):
        for j in range(len(columns)):
            ax.text(j, i, 'N/D' if not np.isfinite(values[i, j]) else f'{values[i,j]:.3f}', ha='center', va='center',
                    color='white' if scaled[i, j] > 0.65 else INK)
    save(fig, '04_matriz_metricas', 'Matriz de métricas del conjunto de prueba', 'Color por columna; oscuro = peor. La elección ya estaba congelada.')

    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    hb = ax[0].hexbin(y, p, gridsize=28, mincnt=1, bins='log', cmap='Oranges')
    extent = max(float(y.max()), float(p.max()), 1)
    ax[0].plot([0, extent], [0, extent], '--', color=GRAY)
    ax[0].set(xlabel='Ventas observadas', ylabel='Ventas estimadas')
    fig.colorbar(hb, ax=ax[0], label='Densidad de observaciones')
    ax[1].hist(p-y, bins=45, color=RED, alpha=0.9)
    ax[1].axvline(0, color=INK, linestyle='--')
    ax[1].set(xlabel='Error: estimación − observado', ylabel='Frecuencia')
    save(fig, '05_errores', 'Predicciones y distribución de errores del modelo elegido', 'El error positivo significa sobreestimación.')

    bands = [-0.1, 0.5, 2.5, 5.5, 10.5, np.inf]
    labels = ['0', '1–2', '3–5', '6–10', '11+']
    actual_band, predicted_band = np.digitize(y, bands)-1, np.digitize(p, bands)-1
    matrix = confusion_matrix(actual_band, predicted_band, labels=range(5))
    percent = np.divide(matrix*100, matrix.sum(axis=1, keepdims=True),
                        out=np.zeros_like(matrix, dtype=float), where=matrix.sum(axis=1, keepdims=True) > 0)
    dump_json(output/'matriz_rangos.json', {'labels': labels, 'counts': matrix.tolist(), 'row_percent': percent.tolist(),
                                           'meaning': 'Diagnóstico de regresión agrupada; no es un clasificador ni una métrica de exactitud.'})
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(percent, vmin=0, vmax=100, cmap='Oranges')
    ax.set_xticks(range(5), labels)
    ax.set_yticks(range(5), labels)
    ax.set(xlabel='Rango estimado', ylabel='Rango observado')
    for i in range(5):
        for j in range(5):
            ax.text(j, i, f'{matrix[i,j]:,}\n{percent[i,j]:.1f}%', ha='center', va='center', color='white' if percent[i,j] > 65 else INK)
    save(fig, '06_matriz_rangos', 'Matriz de ventas observadas y estimadas por rangos', 'Porcentajes por fila; agrupación diagnóstica de una regresión.')

    corr_cols = ['ventas_hoy', 'ventas_7d', 'ventas_28d', 'ventas_56d', 'vistas_28d',
                 'carritos_28d', 'quiebres_28d', 'disponible_fin', 'precio_centimos', 'objetivo_ventas_7d']
    corr = train[corr_cols].corr(method='spearman')
    corr.to_csv(output/'correlaciones_entrenamiento.csv', encoding='utf-8-sig')
    fig, ax = plt.subplots(figsize=(11, 8))
    im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr_cols)), corr_cols, rotation=45, ha='right', fontsize=8)
    ax.set_yticks(range(len(corr_cols)), corr_cols, fontsize=8)
    for i in range(len(corr_cols)):
        for j in range(len(corr_cols)):
            ax.text(j, i, f'{corr.iloc[i,j]:.2f}', ha='center', va='center', fontsize=8,
                    color='white' if abs(corr.iloc[i,j]) > 0.6 else INK)
    fig.colorbar(im, ax=ax, shrink=0.7)
    save(fig, '07_correlaciones', 'Matriz de correlaciones de Spearman', 'Sólo entrenamiento; asociación no demuestra causalidad.')

    sample = test.sample(n=min(config['permutation_rows'], len(test)), random_state=config['seed'])
    result = permutation_importance(pipeline, sample[features], sample.objetivo_ventas_7d,
                                   scoring=negative_mae, n_repeats=config['permutation_repeats'],
                                   random_state=config['seed'], n_jobs=1)
    importance = pd.DataFrame({'feature': features, 'mae_increase': result.importances_mean,
                               'std': result.importances_std}).sort_values('mae_increase', ascending=False)
    importance.to_csv(output/'importancia_variables.csv', index=False, encoding='utf-8-sig')
    dump_json(output/'importance.json', {'rows': len(sample), 'repeats': config['permutation_repeats'],
                                         'values': importance.to_dict('records'),
                                         'limitation': 'Permutación marginal; las variables correlacionadas pueden ocultar importancia. No mide causalidad.'})
    shown = importance.head(15).sort_values('mae_increase')
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(shown.feature, shown.mae_increase, xerr=shown['std'], color=RED, capsize=2)
    ax.axvline(0, color=GRAY)
    ax.set(xlabel='Incremento de MAE al permutar la variable')
    save(fig, '08_importancia', 'Variables que utiliza el modelo elegido', 'Diagnóstico sobre muestra de prueba; no se usa para volver a elegir variables.')

    pred_export = test[['fecha_corte', 'sku', 'familia', 'categoria', 'rotation', 'objetivo_ventas_7d',
                        'stockout_diagnostic', 'lower', 'upper']].copy()
    for name, values in predictions.items():
        pred_export[f'pred_{name}'] = values
    pred_export.to_csv(output/'predicciones_prueba.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    # Pick examples by training sales only; never select favorable test cases.
    ranking = train.groupby('sku').ventas_28d.mean().sort_values()
    chosen_skus = [ranking.index[int((len(ranking)-1)*q)] for q in (0.15, 0.5, 0.9)]
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    example_rows = []
    for ax, sku in zip(axes, chosen_skus):
        rows = test[test.sku.eq(sku)].sort_values('fecha_corte').iloc[::7]
        ax.plot(rows.fecha_corte, rows.objetivo_ventas_7d, color=INK, marker='o', label='Observado')
        ax.plot(rows.fecha_corte, rows.prediction, color=RED, marker='o', label='Estimado')
        ax.fill_between(rows.fecha_corte, rows.lower, rows.upper, color=RED, alpha=0.15, label='Intervalo nominal 90%')
        ax.set(title=sku, ylabel='Unidades / 7 días')
        example_rows += rows[['fecha_corte', 'sku', 'objetivo_ventas_7d', 'prediction', 'lower', 'upper']].assign(
            fecha_corte=rows.fecha_corte.dt.strftime('%Y-%m-%d')).to_dict('records')
    axes[0].legend(ncol=3, fontsize=8)
    save(fig, '09_series', 'Pronóstico semanal en tres productos', 'Productos elegidos por rotación histórica; fechas sin solapamiento.')
    dump_json(output/'forecast_examples.json', example_rows)

    dates = test.fecha_corte.drop_duplicates().sort_values().iloc[::7]
    weeks = test[test.fecha_corte.isin(dates)].copy()
    weekly_errors = weeks.assign(abs_error=np.abs(weeks.prediction-weeks.objetivo_ventas_7d)).groupby('fecha_corte').agg(
        mae=('abs_error', 'mean'), coverage=('interval_hit', 'mean'))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    ax[0].plot(weekly_errors.index, weekly_errors.mae, color=RED, marker='o')
    ax[0].set(ylabel='MAE', xlabel='Corte semanal')
    ax[1].plot(weekly_errors.index, weekly_errors.coverage*100, color=GREEN, marker='o')
    ax[1].axhline(90, color=GRAY, linestyle='--', label='Nominal 90%')
    ax[1].set(ylim=(0, 105), ylabel='Cobertura observada (%)', xlabel='Corte semanal')
    ax[1].legend()
    for axis in ax:
        axis.tick_params(axis='x', rotation=25)
    save(fig, '10_cobertura', 'Error y cobertura de intervalos a lo largo del tiempo', 'Intervalos empíricos calibrados antes de la prueba final.')
    dump_json(output/'weekly_errors.json', weekly_errors.reset_index().assign(
        fecha_corte=lambda f: f.fecha_corte.dt.strftime('%Y-%m-%d')).to_dict('records'))

    family = test.assign(abs_error=np.abs(p-y)).groupby('familia').agg(mae=('abs_error', 'mean'), n=('abs_error', 'size')).sort_values('mae')
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(family.index, family.mae, color=INK)
    ax.set(xlabel='MAE por familia, unidades/SKU/7 días')
    save(fig, '11_familias', 'Errores por familia del catálogo', 'Comparar junto con volumen y rotación; MAE mayor no implica peor error relativo.')

    # One-period stock decision diagnostic, NOT counterfactual demand estimation or a logistics simulator.
    decisions = []
    selected_indices = test.index.get_indexer(weeks.index)
    for name, values in predictions.items():
        target_stock = np.ceil(values[selected_indices]).astype(int)
        actual = weeks.objetivo_ventas_7d.to_numpy()
        shortages = np.maximum(actual-target_stock, 0)
        excess = np.maximum(target_stock-actual, 0)
        decisions.append({'model': name, 'sku_weeks': len(weeks), 'uncovered_observed_units': int(shortages.sum()),
                          'excess_target_units': int(excess.sum()), 'weeks_fully_covered_pct': float((shortages == 0).mean()*100),
                          'mean_target_units': float(target_stock.mean())})
    dump_json(output/'inventory_scenario.json', {
        'assumptions': ['Inicio de cada semana con stock igual a techo(predicción).',
                        'Horizontes sin solapamiento; sin recepciones, reservas, plazos ni costos dentro del periodo.',
                        'Se compara contra ventas observadas censuradas por el stock del simulador.',
                        'No calcula demanda perdida real, ahorro en soles ni órdenes de compra recomendadas.'], 'values': decisions})
    decisions_frame = pd.DataFrame(decisions).set_index('model')
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
    for axis, column, title in [(ax[0], 'uncovered_observed_units', 'Unidades observadas sin cobertura'),
                                (ax[1], 'excess_target_units', 'Unidades objetivo en exceso')]:
        axis.barh(decisions_frame.index, decisions_frame[column], color=[RED if m == winner else GRAY for m in decisions_frame.index])
        axis.set_xlabel(title)
    save(fig, '12_inventario', 'Escenario de cobertura de inventario a una semana', 'Diagnóstico simplificado; no representa ahorro económico ni reposición real.')
    return assets
