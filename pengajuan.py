"""Pengajuan perubahan data oleh Pengelola (yayasan/PT).

Prinsip: perubahan dari pihak yang diawasi TIDAK langsung berlaku dan TIDAK mengubah warna.
Ia masuk antrean "Menunggu verifikasi"; pengawas melihat dampak warna (simulasi) sebelum menyetujui.
"""
import json
from datetime import date, datetime

import pandas as pd

import db
import lampiran
import rules
import scope
import tindak
from schema import TABLES

MENUNGGU, SETUJU, TOLAK = "Menunggu verifikasi", "Disetujui", "Ditolak"
TAMBAH_BOLEH = {"akta", "organ_yayasan", "pimpinan_pt", "aturan_statuta"}   # PT/yayasan baru = keputusan kementerian


def _now():
    return datetime.now().isoformat(timespec="seconds")


def init():
    c = db.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS pengajuan(id INTEGER PRIMARY KEY AUTOINCREMENT, id_yayasan TEXT, kode_pt TEXT,
                 tabel TEXT, kunci TEXT, aksi TEXT, data_lama TEXT, data_baru TEXT, kolom_berubah TEXT, alasan TEXT, tl_id INTEGER,
                 status TEXT NOT NULL DEFAULT 'Menunggu verifikasi', diajukan_oleh TEXT, diajukan_pada TEXT, ditinjau_oleh TEXT,
                 ditinjau_pada TEXT, catatan_peninjau TEXT)""")
    c.commit()
    c.close()
    lampiran.init()


def _ser(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, str):
        return v.strip() or None
    return v


def _coerce(tabel, d):
    meta, out = TABLES[tabel], {}
    for c, v in d.items():
        if c in meta["dates"]:
            out[c] = pd.Timestamp(v) if v else pd.NaT
        elif c in meta["ints"]:
            out[c] = int(v) if v not in (None, "") else pd.NA
        else:
            out[c] = v
    return out


def _cek_cakupan(me, tabel, row, data):
    err = []
    pts = scope.scope_pts(me, data)
    if row.get("kode_pt") and row["kode_pt"] not in pts:
        err.append(f"kode_pt {row['kode_pt']} di luar cakupan Anda.")
    if "id_yayasan" in row and row["id_yayasan"] and row["id_yayasan"] != me["id_yayasan"]:
        err.append("id_yayasan di luar cakupan Anda.")
    if row.get("id_akta_sumber"):
        a = data["akta"]
        if row["id_akta_sumber"] not in set(a[a.id_yayasan == me["id_yayasan"]].id_akta):
            err.append("id_akta_sumber bukan akta milik yayasan Anda.")
    return err


def ajukan(me, tabel, aksi, kunci, baru, alasan, tl_id=None, files=()):
    """files = [(nama, bytes)]. Mengembalikan (ok, pesan, id)."""
    if me["peran"] != "Pengelola":
        return False, "Hanya Pengelola yang mengajukan perubahan.", None
    if tabel not in scope.tabel_diizinkan(me):
        return False, "Tabel ini tidak dapat diajukan perubahannya oleh akun Anda.", None
    if aksi not in ("UBAH", "TAMBAH") or (aksi == "TAMBAH" and tabel not in TAMBAH_BOLEH):
        return False, "Jenis pengajuan tidak diizinkan untuk tabel ini.", None
    if len((alasan or "").strip()) < 10:
        return False, "Alasan wajib diisi (minimal 10 karakter).", None
    data = db.load_all()
    full, pk = data[tabel], TABLES[tabel]["pk"]
    cols = list(full.columns)
    ro = scope.READONLY.get(tabel, set())
    if aksi == "UBAH":
        view = scope.scope_view(tabel, full, me, data)
        m = view[view[pk].map(db.norm) == kunci]
        if m.empty:
            return False, "Data tidak ditemukan dalam cakupan Anda.", None
        lama = {c: _ser(m.iloc[0][c]) for c in cols}
        row = dict(lama)
        for c in cols:
            if c in baru:
                nv = _ser(baru[c])
                if c in ro:
                    if str(nv) != str(lama[c]):
                        return False, f"Kolom '{c}' dikendalikan kementerian dan tidak dapat diubah.", None
                else:
                    row[c] = nv
        berubah = [c for c in cols if str(row[c]) != str(lama[c])]
        if not berubah:
            return False, "Tidak ada perubahan yang diajukan.", None
        tmpid = kunci
    else:
        lama = None
        row = {c: _ser(baru.get(c)) for c in cols}
        for c in scope.KOLOM_KEPEMILIKAN[tabel]:
            row[c] = me["id_yayasan"]
        row[pk] = None
        berubah = [c for c in cols if c != pk and row[c] is not None]
        tmpid = db.next_id(tabel, full[pk])
    err = _cek_cakupan(me, tabel, row, data)
    test = dict(row)
    test[pk] = tmpid
    one = pd.DataFrame([_coerce(tabel, test)])
    nf = pd.concat([full[full[pk].map(db.norm) != tmpid], one], ignore_index=True)
    err += db.validate(tabel, one, {**data, tabel: nf})
    if [c for c in berubah if c.startswith("ada_dok_") and row[c] == "Ya"] and not files:
        err.append("Perubahan yang menyatakan dokumen 'Ya' wajib disertai lampiran bukti.")
    for nama, b in files:
        e = lampiran.validasi(nama, b)
        if e:
            err.append(f"{nama}: {e}")
    if tl_id is not None:
        if int(tl_id) not in set(tindak.visible_pengelola(tindak.read(), me).id):
            err.append("Permintaan kementerian yang dituju tidak ditemukan dalam cakupan Anda.")
    if err:
        return False, " | ".join(err), None
    kpt = row.get("kode_pt") or me.get("kode_pt")
    c = db.conn()
    cur = c.execute("""INSERT INTO pengajuan(id_yayasan,kode_pt,tabel,kunci,aksi,data_lama,data_baru,kolom_berubah,alasan,tl_id,status,
                       diajukan_oleh,diajukan_pada) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (me["id_yayasan"], kpt, tabel, kunci if aksi == "UBAH" else None, aksi,
                     json.dumps(lama, ensure_ascii=False) if lama else None, json.dumps(row, ensure_ascii=False),
                     json.dumps(berubah), alasan.strip(), int(tl_id) if tl_id is not None else None, MENUNGGU,
                     me["username"], _now()))
    pid = cur.lastrowid
    c.commit()
    c.close()
    for nama, b in files:
        lampiran.simpan(nama, b, me["username"], pengajuan_id=pid)
    return True, f"Pengajuan #{pid} terkirim dan menunggu verifikasi kementerian. Data dan status Anda belum berubah.", pid


def get(pid):
    c = db.conn()
    r = c.execute("SELECT * FROM pengajuan WHERE id=?", (int(pid),)).fetchone()
    c.close()
    if not r:
        return None
    p = dict(r)
    for k in ("data_lama", "data_baru", "kolom_berubah"):
        p[k] = json.loads(p[k]) if p[k] else None
    return p


def daftar(me=None, status=None):
    c = db.conn()
    df = pd.read_sql("SELECT id,id_yayasan,kode_pt,tabel,kunci,aksi,status,diajukan_oleh,diajukan_pada,ditinjau_oleh,ditinjau_pada,"
                     "catatan_peninjau,alasan,tl_id FROM pengajuan ORDER BY id DESC", c)
    c.close()
    if me is not None and me["peran"] == "Pengelola":
        df = df[df.id_yayasan == me["id_yayasan"]]
        if me.get("kode_pt"):
            df = df[df.kode_pt == me["kode_pt"]]
    if status:
        df = df[df.status == status]
    return df


def diff_df(p):
    rows = [dict(kolom=c, lama=(p["data_lama"] or {}).get(c), baru=p["data_baru"].get(c)) for c in p["kolom_berubah"]]
    return pd.DataFrame(rows, columns=["kolom", "lama", "baru"])


def _bangun(p, data):
    tabel, full = p["tabel"], data[p["tabel"]]
    pk = TABLES[tabel]["pk"]
    cols = list(full.columns)
    if p["aksi"] == "UBAH":
        idx = full.index[full[pk].map(db.norm) == p["kunci"]]
        if len(idx) == 0:
            return None, None, ["Data asli sudah tidak ada."]
        cur = {c: _ser(full.loc[idx[0], c]) for c in cols}
        konflik = [c for c in p["kolom_berubah"] if str(cur[c]) != str(p["data_lama"][c])]
        if konflik:
            return None, None, [f"Data berubah sejak diajukan (kolom: {', '.join(konflik)}). Minta pengaju mengajukan ulang."]
        row = {c: (p["data_baru"][c] if c in p["kolom_berubah"] else cur[c]) for c in cols}
        coerced = _coerce(tabel, row)
        nf = full.copy()
        for c in cols:
            nf.loc[idx[0], c] = coerced[c]
    else:
        row = dict(p["data_baru"])
        row[pk] = db.next_id(tabel, full[pk])
        coerced = _coerce(tabel, row)
        nf = pd.concat([full, pd.DataFrame([coerced])], ignore_index=True)
    return nf, coerced, []


def simulasi(p, data, cfg=None, today=None):
    """Dampak warna jika pengajuan disetujui. Mengembalikan (hasil, error)."""
    nf, row, err = _bangun(p, data)
    if err:
        return None, err
    cfg = cfg or rules.load_cfg()
    d2 = {**data, p["tabel"]: nf}
    f0, y0, p0 = rules.evaluate(data, cfg, today=today, include_historis=False)
    f1, y1, p1 = rules.evaluate(d2, cfg, today=today, include_historis=False)
    s0 = pd.concat([y0, p0])[["tipe", "id", "nama", "status"]]
    s1 = pd.concat([y1, p1])[["tipe", "id", "nama", "status"]]
    m = s0.merge(s1, on=["tipe", "id", "nama"], suffixes=("_sebelum", "_sesudah"))
    k = lambda f: {tuple(x) for x in f[["kode_aturan", "referensi", "tingkat"]].values}
    return dict(status=m[m.status_sebelum != m.status_sesudah].reset_index(drop=True),
                muncul=sorted(k(f1) - k(f0)), hilang=sorted(k(f0) - k(f1))), []


def setujui(pid, reviewer, catatan=""):
    p = get(pid)
    if not p or p["status"] != MENUNGGU:
        return False, "Pengajuan tidak ditemukan atau sudah diproses."
    data = db.load_all()
    nf, row, err = _bangun(p, data)
    if err:
        return False, " ".join(err)
    pk = TABLES[p["tabel"]]["pk"]
    errs = db.validate(p["tabel"], pd.DataFrame([row]), {**data, p["tabel"]: nf})
    if errs:
        return False, "Tidak valid: " + " | ".join(errs)
    db.apply_changes(p["tabel"], data[p["tabel"]], nf, f"{reviewer} (pengajuan #{pid} dari {p['diajukan_oleh']})", allow_delete=False)
    c = db.conn()
    c.execute("UPDATE pengajuan SET status=?, kunci=?, ditinjau_oleh=?, ditinjau_pada=?, catatan_peninjau=? WHERE id=?",
              (SETUJU, str(row[pk]), reviewer, _now(), (catatan or "").strip() or None, int(pid)))
    c.commit()
    c.close()
    return True, f"Pengajuan #{pid} disetujui dan data diperbarui."


def tolak(pid, reviewer, catatan):
    if len((catatan or "").strip()) < 5:
        return False, "Alasan penolakan wajib diisi."
    p = get(pid)
    if not p or p["status"] != MENUNGGU:
        return False, "Pengajuan tidak ditemukan atau sudah diproses."
    c = db.conn()
    c.execute("UPDATE pengajuan SET status=?, ditinjau_oleh=?, ditinjau_pada=?, catatan_peninjau=? WHERE id=?",
              (TOLAK, reviewer, _now(), catatan.strip(), int(pid)))
    c.commit()
    c.close()
    return True, f"Pengajuan #{pid} ditolak."
