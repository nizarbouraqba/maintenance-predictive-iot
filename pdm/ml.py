import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from pdm.schema import FEATURES, NUMERIC


class Features(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        out = pd.DataFrame(X)[FEATURES].copy()
        out['delta_temperature_k'] = out.process_temperature_k - out.air_temperature_k
        out['power_w'] = out.torque_nm * out.rotational_speed_rpm * (2 * np.pi / 60)
        return out


def make_pipeline():
    numeric = NUMERIC + ['delta_temperature_k', 'power_w']
    return Pipeline([
        ('features', Features()),
        ('preprocessing', ColumnTransformer([
            ('type', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['type']),
            ('numbers', SimpleImputer(strategy='median'), numeric),
        ])),
        ('classifier', RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
             class_weight='balanced_subsample', random_state=42, n_jobs=1)),
    ])
