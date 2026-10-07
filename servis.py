"""Fungsi bersama: hitung ulang status dan catat perubahan warna."""
import pandas as pd

import db
import rules


def refresh_status(pemicu):
    """Selalu memakai kondisi saat ini (tanpa temuan historis) agar riwayat status konsisten."""
    d = db.load_all()
    _, sy, sp = rules.evaluate(d, rules.load_cfg(), include_historis=False)
    return db.record_status(pd.concat([sy, sp]), pemicu)
