"""Cakupan data untuk peran Pengelola (yayasan/PT). Semua pembatasan dipaksa di sisi server (bukan hanya di tampilan)."""
import pandas as pd

import db

# tabel yang boleh DIAJUKAN perubahannya oleh Pengelola
TABEL_YAYASAN = ["yayasan", "pt", "akta", "organ_yayasan", "pimpinan_pt", "aturan_statuta"]
TABEL_PT = ["pt", "pimpinan_pt", "aturan_statuta"]
# kolom yang dikendalikan kementerian atau kunci kepemilikan (tidak boleh diubah Pengelola)
READONLY = {
    "yayasan": {"id_yayasan", "status_yayasan", "sumber_data"},
    "pt": {"kode_pt", "id_yayasan", "status_pt", "akreditasi_pt", "sumber_data"},
    "akta": {"id_akta", "id_yayasan"},
    "organ_yayasan": {"id_organ", "id_yayasan"},
    "pimpinan_pt": {"id_pimpinan", "id_yayasan"},
    "aturan_statuta": {"id_statuta"},
}
KOLOM_KEPEMILIKAN = {"yayasan": [], "pt": ["id_yayasan"], "akta": ["id_yayasan"], "organ_yayasan": ["id_yayasan"],
                     "pimpinan_pt": ["id_yayasan"], "aturan_statuta": []}


def tabel_diizinkan(me):
    return TABEL_PT if me.get("kode_pt") else TABEL_YAYASAN


def scope_pts(me, data=None):
    data = data or {"pt": db.load_table("pt")}
    pt = data["pt"]
    if me.get("kode_pt"):
        return {me["kode_pt"]} & set(pt.kode_pt)
    return set(pt[pt.id_yayasan == me["id_yayasan"]].kode_pt)


def scope_view(table, df, me, data=None):
    """Baris tabel yang masuk cakupan akun Pengelola."""
    data = data or {"pt": db.load_table("pt")}
    y, pts = me["id_yayasan"], scope_pts(me, data)
    pt_level = bool(me.get("kode_pt"))
    if table == "yayasan":
        return df[df.id_yayasan == y] if not pt_level else df.iloc[0:0]
    if table == "pt":
        return df[df.kode_pt.isin(pts)]
    if table == "pimpinan_pt":
        return df[df.kode_pt.isin(pts) & (df.id_yayasan == y)]
    if table in ("aturan_statuta", "riwayat_penyelenggara"):
        return df[df.kode_pt.isin(pts)]
    if table in ("akta", "organ_yayasan"):
        return df[df.id_yayasan == y] if not pt_level else df.iloc[0:0]
    if table == "riwayat_perubahan":
        return df[df.id_entitas.isin(pts | ({y} if not pt_level else set()))]
    return df.iloc[0:0]


def temuan_dalam_cakupan(findings, me, data=None):
    data = data or {"pt": db.load_table("pt")}
    pts = scope_pts(me, data)
    f = findings[findings.id_yayasan == me["id_yayasan"]]
    if me.get("kode_pt"):
        return f[f.kode_pt.isin(pts)]
    return f[f.kode_pt.isin(pts) | f.kode_pt.isna()]


def entitas_dalam_cakupan(me, tipe, id_):
    """True jika entitas (Yayasan/PT) ada di cakupan akun."""
    if tipe == "Yayasan":
        return (not me.get("kode_pt")) and id_ == me["id_yayasan"]
    return id_ in scope_pts(me)


def label_record(table, r):
    for c in ("nama_lengkap", "nama_pt", "nama_yayasan", "versi_statuta", "jenis_perubahan"):
        if c in r.index and pd.notna(r[c]):
            extra = ""
            if table == "pimpinan_pt":
                extra = f" ({r['jabatan_pt']}, {r['tgl_mulai']:%Y-%m-%d})"
            if table == "organ_yayasan":
                extra = f" ({r['jabatan_yayasan']})"
            return f"{r[db_pk(table)]} · {r[c]}{extra}"
    return str(r[db_pk(table)])


def db_pk(table):
    from schema import TABLES
    return TABLES[table]["pk"]
