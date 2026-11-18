"""Entraînement reproductible, séparation train/validation/test sans fuite."""
import hashlib
import json
import os
from pathlib import Path
import joblib
os.environ.setdefault('MPLCONFIGDIR', str(Path('runtime/matplotlib').resolve()))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.calibration import calibration_curve
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score, PrecisionRecallDisplay)
from sklearn.model_selection import train_test_split
from pdm.ml import make_pipeline
from pdm.schema import FEATURES, RENAME


def evaluate(y, scores, threshold):
    pred = scores > threshold
    return {'threshold_strict_gt': threshold, 'precision': precision_score(y, pred, zero_division=0),
            'recall': recall_score(y, pred, zero_division=0), 'f1': f1_score(y, pred, zero_division=0),
            'accuracy': accuracy_score(y, pred), 'confusion_matrix_tn_fp_fn_tp': confusion_matrix(y, pred).ravel().tolist()}


def main():
    for folder in ['data', 'models', 'reports']:
        Path(folder).mkdir(exist_ok=True)
    source = Path('data/ai4i2020.csv')
    df = pd.read_csv(source).rename(columns=RENAME)
    train_val, test = train_test_split(df, test_size=.2, stratify=df['Machine failure'], random_state=42)
    train, val = train_test_split(train_val, test_size=.25, stratify=train_val['Machine failure'], random_state=42)
    model = make_pipeline().fit(train[FEATURES], train['Machine failure'])
    val_scores = model.predict_proba(val[FEATURES])[:, 1]
    # Seuil exploratoire choisi exclusivement sur validation. Le seuil métier reste 0,7.
    thresholds = np.linspace(.05, .95, 91)
    best = float(max(thresholds, key=lambda t: f1_score(val['Machine failure'], val_scores > t)))
    scores = model.predict_proba(test[FEATURES])[:, 1]
    y = test['Machine failure']
    version = 'rf-ai4i-' + hashlib.sha256(source.read_bytes()).hexdigest()[:10]
    report = {'model_version': version, 'sklearn_version': sklearn.__version__, 'seed': 42,
        'dataset_rows': len(df), 'failures': int(df['Machine failure'].sum()),
        'split_sizes': {'train': len(train), 'validation': len(val), 'test': len(test)},
        'test_failure_count': int(y.sum()), 'average_precision': average_precision_score(y, scores),
        'roc_auc': roc_auc_score(y, scores), 'brier_score': brier_score_loss(y, scores),
        'baseline_all_healthy': evaluate(y, np.zeros(len(y)), .5),
        'at_0_5': evaluate(y, scores, .5), 'at_0_7': evaluate(y, scores, .7),
        'validation_selected_threshold': best, 'at_validation_threshold': evaluate(y, scores, best),
        'limitations': ['Données synthétiques.', 'Classification de la panne courante, aucun horizon futur.',
             'Split stratifié aléatoire : pas de preuve de généralisation temporelle ou à une autre usine.',
             'Score non calibré ; courbe de calibration fournie.']}
    joblib.dump({'pipeline': model, 'version': version, 'features': FEATURES}, 'models/random_forest.joblib', compress=3)
    for name, frame in [('train', train), ('validation', val), ('test', test)]:
        frame.to_csv(f'data/{name}.csv', index=False)
    predictions = test[['UDI', 'Machine failure']].copy()
    predictions['score'] = scores
    predictions.to_csv('reports/test_predictions.csv', index=False)
    Path('reports/ml_metrics.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    PrecisionRecallDisplay.from_predictions(y, scores, ax=axes[0], name='Random Forest')
    axes[0].axhline(y.mean(), color='grey', linestyle='--', label='Prévalence')
    axes[0].legend()
    observed, predicted = calibration_curve(y, scores, n_bins=8, strategy='quantile')
    axes[1].plot(predicted, observed, 'o-'); axes[1].plot([0, 1], [0, 1], '--', color='grey')
    axes[1].set(xlabel='Score moyen', ylabel='Fréquence observée', title='Calibration (quantiles)')
    cm = confusion_matrix(y, scores > .7)
    axes[2].imshow(cm, cmap='Blues')
    for (i, j), value in np.ndenumerate(cm):
        axes[2].text(j, i, str(value), ha='center', color='red')
    axes[2].set(xticks=[0, 1], yticks=[0, 1], xlabel='Classe prédite', ylabel='Classe réelle', title='Seuil strict > 0,7')
    fig.tight_layout(); fig.savefig('reports/ml_evaluation.png', dpi=160); plt.close(fig)
    lines = ['# Rapport de performance ML', '', f"Modèle : `{version}`. Split : 6 000 / 2 000 / 2 000, graine 42.", '',
       '| Politique | Précision | Rappel | F1 | TN / FP / FN / TP |', '|---|---:|---:|---:|---|']
    for label, key in [('Toujours sain', 'baseline_all_healthy'), ('Seuil 0,5', 'at_0_5'), ('Seuil métier 0,7', 'at_0_7'), (f'Seuil validation {best:.2f}', 'at_validation_threshold')]:
        r = report[key]
        lines.append(f"| {label} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | {r['confusion_matrix_tn_fp_fn_tp']} |")
    lines += ['', f"Average Precision : {report['average_precision']:.4f} ; ROC-AUC : {report['roc_auc']:.4f} ; Brier : {report['brier_score']:.4f}.", '',
       'Le seuil 0,7 respecte la consigne, mais peut manquer des défaillances. Le seuil exploratoire optimise F1 sur validation uniquement. Aucun réglage ne repose sur le test.', '',
       '![Évaluation](ml_evaluation.png)', '', *['- ' + s for s in report['limitations']], '',
       'Variables utilisées : Type, températures, vitesse, couple, usure, écart thermique et puissance mécanique. Les identifiants, la cible et les cinq modes de panne sont exclus des features.']
    Path('reports/performance_ml.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == '__main__':
    main()
