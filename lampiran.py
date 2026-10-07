"""Lampiran dokumen (prototipe: disimpan di database; produksi sebaiknya di penyimpanan objek + pemindai virus)."""
import hashlib
import os
import re
from datetime import datetime

import pandas as pd

import db

MAKS_BYTE = 5 * 1024 * 1024
MAGIC = {".pdf": (b"%PDF",), ".png": (b"\x89PNG",), ".jpg": (b"\xff\xd8",), ".jpeg": (b"\xff\xd8",)}
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def init():
    c = db.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS lampiran(id INTEGER PRIMARY KEY AUTOINCREMENT, pengajuan_id INTEGER, tl_id INTEGER,
                 log_id INTEGER, nama_file TEXT, mime TEXT, ukuran INTEGER, sha256 TEXT, isi BLOB, diunggah_oleh TEXT, diunggah_pada TEXT)""")
    c.commit()
    c.close()


def validasi(nama, data):
    ext = os.path.splitext(nama)[1].lower()
    if ext not in MAGIC:
        return f"Format {ext or '(tanpa ekstensi)'} tidak diizinkan. Gunakan PDF, JPG, atau PNG."
    if len(data) == 0:
        return "File kosong."
    if len(data) > MAKS_BYTE:
        return f"Ukuran file melebihi {MAKS_BYTE // (1024 * 1024)} MB."
    if not any(data.startswith(m) for m in MAGIC[ext]):
        return "Isi file tidak sesuai dengan ekstensinya."
    return None


def _nama_aman(nama):
    base = os.path.basename(nama).replace("\\", "_")
    return re.sub(r"[^A-Za-z0-9._() -]", "_", base)[:120]


def simpan(nama, data, user, pengajuan_id=None, tl_id=None, log_id=None):
    err = validasi(nama, data)
    if err:
        return False, f"{nama}: {err}"
    ext = os.path.splitext(nama)[1].lower()
    c = db.conn()
    c.execute("""INSERT INTO lampiran(pengajuan_id,tl_id,log_id,nama_file,mime,ukuran,sha256,isi,diunggah_oleh,diunggah_pada)
                 VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (pengajuan_id, tl_id, log_id, _nama_aman(nama), MIME[ext], len(data), hashlib.sha256(data).hexdigest(), data, user,
               datetime.now().isoformat(timespec="seconds")))
    c.commit()
    c.close()
    return True, "ok"


def daftar(pengajuan_id=None, tl_id=None):
    c = db.conn()
    q = "SELECT id, log_id, nama_file, ukuran, sha256, diunggah_oleh, diunggah_pada FROM lampiran WHERE "
    if pengajuan_id is not None:
        df = pd.read_sql(q + "pengajuan_id=? ORDER BY id", c, params=(int(pengajuan_id),))
    else:
        df = pd.read_sql(q + "tl_id=? ORDER BY id", c, params=(int(tl_id),))
    c.close()
    return df


def ambil(lid):
    c = db.conn()
    r = c.execute("SELECT * FROM lampiran WHERE id=?", (int(lid),)).fetchone()
    c.close()
    return dict(r) if r else None


def boleh_akses(me, lamp):
    """Staf kementerian boleh semua. Pengelola hanya lampiran milik pengajuan/tindak lanjut di cakupannya."""
    if me["peran"] != "Pengelola":
        return True
    c = db.conn()
    y = None
    if lamp["pengajuan_id"]:
        r = c.execute("SELECT id_yayasan, kode_pt FROM pengajuan WHERE id=?", (lamp["pengajuan_id"],)).fetchone()
    else:
        r = c.execute("SELECT id_yayasan, kode_pt FROM tindak_lanjut WHERE id=?", (lamp["tl_id"],)).fetchone()
    c.close()
    if not r:
        return False
    if r["id_yayasan"] != me["id_yayasan"]:
        return False
    return not me.get("kode_pt") or r["kode_pt"] == me["kode_pt"]
