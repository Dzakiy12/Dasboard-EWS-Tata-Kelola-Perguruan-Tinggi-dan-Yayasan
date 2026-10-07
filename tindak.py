"""Tindak lanjut pengawasan atas temuan merah/kuning.

Prinsip: warna TETAP dihitung dari data. Tindak lanjut hanya mencatat langkah pengawasan
(verifikasi, klarifikasi, pembinaan/teguran, eskalasi); menutupnya tidak mengubah warna.

Tahapan (usulan awal, sesuaikan dengan SOP resmi):
  Verifikasi internal -> Menunggu tanggapan -> Evaluasi tanggapan -> Pembinaan/Teguran -> Eskalasi -> Selesai
Pengawas: sampai Pembinaan/Teguran. Admin: juga Eskalasi dan Selesai.
Catatan INTERNAL tidak terlihat oleh yayasan/PT; hanya isi_publik, nomor/tanggal surat, tenggat, dan tanggapan yang terlihat.
"""
from datetime import date, datetime

import pandas as pd

import db

VI, MT, ET, PT_, ES, SE = ("Verifikasi internal", "Menunggu tanggapan", "Evaluasi tanggapan", "Pembinaan/Teguran", "Eskalasi", "Selesai")
STATUS = [VI, MT, ET, PT_, ES, SE]
SLA_HARI = {"Merah": 14, "Kuning": 30}          # target selesai verifikasi internal
NEXT = {VI: [MT, SE], MT: [ET, PT_], ET: [SE, PT_, MT], PT_: [ET, ES], ES: [SE], SE: []}
HANYA_ADMIN = {ES, SE}
JENIS_TINDAKAN = ["Pembinaan", "Teguran tertulis"]
ALASAN_TUTUP = ["Terselesaikan (data diperbaiki/dilengkapi)", "Tidak terbukti (kesalahan data)",
                "Diteruskan ke pejabat berwenang", "Diterima dengan catatan"]
# kolom wajib per tahap tujuan
WAJIB = {MT: ["no_surat", "tgl_surat", "tenggat", "isi_publik"], ET: ["tgl_tanggapan", "catatan"],
         PT_: ["jenis_tindakan", "no_surat", "tgl_surat", "tenggat", "isi_publik"], ES: ["no_surat", "tgl_surat", "catatan"],
         SE: ["alasan_penutupan", "catatan"]}
NAMA_KOLOM = {"no_surat": "Nomor surat", "tgl_surat": "Tanggal surat", "tenggat": "Tenggat tanggapan/perbaikan",
              "isi_publik": "Isi permintaan (terlihat yayasan/PT)", "tgl_tanggapan": "Tanggal tanggapan diterima",
              "catatan": "Catatan internal", "jenis_tindakan": "Jenis tindakan", "alasan_penutupan": "Alasan penutupan"}
RANK = {"Merah": 2, "Kuning": 1}
KOLOM_BARU = {"jenis_tindakan": "TEXT", "no_surat": "TEXT", "tgl_surat": "TEXT", "alasan_penutupan": "TEXT",
              "tanggapan_baru": "INTEGER DEFAULT 0"}
KOLOM_LOG_BARU = {"isi_publik": "TEXT", "no_surat": "TEXT", "tgl_surat": "TEXT", "tenggat": "TEXT", "jenis_tindakan": "TEXT",
                  "tgl_tanggapan": "TEXT"}
PETA_LAMA = {"Baru": VI, "Sedang ditangani": VI, "Menunggu verifikasi": ET, "Ditutup": SE}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def init():
    c = db.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS tindak_lanjut(id INTEGER PRIMARY KEY AUTOINCREMENT, kunci TEXT NOT NULL,
                 kode_aturan TEXT, id_referensi TEXT, referensi TEXT, id_yayasan TEXT, kode_pt TEXT, tingkat TEXT, uraian TEXT,
                 status TEXT NOT NULL DEFAULT 'Verifikasi internal', penanggung_jawab TEXT, tenggat TEXT, dibuat TEXT,
                 dibuat_oleh TEXT, diperbarui TEXT, ditutup TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tindak_lanjut_log(id INTEGER PRIMARY KEY AUTOINCREMENT, tl_id INTEGER NOT NULL,
                 waktu TEXT, pengguna TEXT, aksi TEXT, dari_status TEXT, ke_status TEXT, isi TEXT)""")
    for tabel, kolom in (("tindak_lanjut", KOLOM_BARU), ("tindak_lanjut_log", KOLOM_LOG_BARU)):   # migrasi versi lama
        ada = {r[1] for r in c.execute(f"PRAGMA table_info({tabel})")}
        for k, tipe in kolom.items():
            if k not in ada:
                c.execute(f"ALTER TABLE {tabel} ADD COLUMN {k} {tipe}")
    for lama, baru in PETA_LAMA.items():
        c.execute("UPDATE tindak_lanjut SET status=? WHERE status=?", (baru, lama))
        c.execute("UPDATE tindak_lanjut_log SET dari_status=? WHERE dari_status=?", (baru, lama))
        c.execute("UPDATE tindak_lanjut_log SET ke_status=? WHERE ke_status=?", (baru, lama))
    c.execute("DROP INDEX IF EXISTS ux_tl_terbuka")
    c.execute("CREATE UNIQUE INDEX ux_tl_terbuka ON tindak_lanjut(kunci) WHERE status <> 'Selesai'")
    c.commit()
    c.close()


def with_key(findings):
    """Satu baris per (aturan + objek). Jika ganda, ambil tingkat terburuk."""
    if findings.empty:
        return findings.assign(id_ref=[], kunci=[])
    df = findings.copy()
    df["id_ref"] = df.referensi.str.split(" - ").str[0]
    df["kunci"] = df.kode_aturan + "|" + df.id_ref
    df = df.sort_values("tingkat", key=lambda s: s.map(RANK), ascending=False)
    return df.drop_duplicates("kunci").reset_index(drop=True)


def read():
    c = db.conn()
    df = pd.read_sql("SELECT * FROM tindak_lanjut ORDER BY id DESC", c)
    c.close()
    return df


def history(tl_id, publik=False):
    c = db.conn()
    q = ("SELECT id, waktu, pengguna, aksi, dari_status, ke_status, no_surat, tgl_surat, tenggat, jenis_tindakan, tgl_tanggapan, "
         "isi_publik, isi FROM tindak_lanjut_log WHERE tl_id=?")
    if publik:
        q += " AND (isi_publik IS NOT NULL OR aksi='TANGGAPAN')"
    df = pd.read_sql(q + " ORDER BY id DESC", c, params=(int(tl_id),))
    c.close()
    if publik:
        df = df.drop(columns=["isi", "dari_status", "pengguna"]).assign(pengguna_tampil="")
    return df


def users():
    c = db.conn()
    r = [x[0] for x in c.execute("SELECT username FROM pengguna WHERE aktif=1 AND peran<>'Pengelola' ORDER BY username")]
    c.close()
    return r


def _log(c, tl_id, user, aksi, dari=None, ke=None, isi=None, **kw):
    kol = ["tl_id", "waktu", "pengguna", "aksi", "dari_status", "ke_status", "isi"] + list(kw)
    val = [int(tl_id), _now(), user, aksi, dari, ke, isi] + [None if v in (None, "") else str(v) for v in kw.values()]
    cur = c.execute(f"INSERT INTO tindak_lanjut_log({','.join(kol)}) VALUES({','.join('?' * len(kol))})", val)
    return cur.lastrowid


def buat(f, pj, tenggat, catatan, user):
    """f = satu baris hasil with_key(). Tahap awal: Verifikasi internal."""
    c = db.conn()
    try:
        ada = c.execute("SELECT id FROM tindak_lanjut WHERE kunci=? AND status<>?", (f["kunci"], SE)).fetchone()
        if ada:
            return False, f"Sudah ada tindak lanjut terbuka untuk temuan ini (#{ada[0]})."
        cur = c.execute("""INSERT INTO tindak_lanjut(kunci,kode_aturan,id_referensi,referensi,id_yayasan,kode_pt,tingkat,uraian,status,
                           penanggung_jawab,tenggat,dibuat,dibuat_oleh,diperbarui) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (f["kunci"], f["kode_aturan"], f["id_ref"], f["referensi"], f["id_yayasan"], f["kode_pt"], f["tingkat"],
                         f["uraian"], VI, pj, str(tenggat), _now(), user, _now()))
        _log(c, cur.lastrowid, user, "DIBUAT", None, VI, catatan or None)
        c.commit()
        return True, f"Tindak lanjut #{cur.lastrowid} dibuat."
    finally:
        c.close()


def pilihan_status(status, is_admin):
    return [n for n in NEXT[status] if is_admin or n not in HANYA_ADMIN]


def pindah(tl_id, user, is_admin, ke, isi, masih_ada=False, paksa_tutup=False):
    """Pindahkan tahap. isi = dict(no_surat, tgl_surat, tenggat, isi_publik, tgl_tanggapan, catatan, jenis_tindakan, alasan_penutupan)."""
    c = db.conn()
    try:
        r = c.execute("SELECT * FROM tindak_lanjut WHERE id=?", (int(tl_id),)).fetchone()
        if not r:
            return False, "Tindak lanjut tidak ditemukan."
        dari = r["status"]
        if ke not in pilihan_status(dari, is_admin):
            return False, "Perpindahan tahap ini tidak diizinkan untuk peran Anda."
        isi = {k: (str(v).strip() if v not in (None, "") else "") for k, v in isi.items()}
        kosong = [NAMA_KOLOM[k] for k in WAJIB.get(ke, []) if not isi.get(k)]
        if kosong:
            return False, "Wajib diisi: " + ", ".join(kosong) + "."
        if ke == SE and masih_ada and not paksa_tutup:
            return False, "Temuan masih muncul pada penilaian saat ini. Centang konfirmasi jika tetap ingin menutup."
        sets, vals = ["status=?", "diperbarui=?"], [ke, _now()]
        for k in ("no_surat", "tgl_surat", "jenis_tindakan", "alasan_penutupan"):
            if isi.get(k):
                sets.append(f"{k}=?"); vals.append(isi[k])
        if isi.get("tenggat"):
            sets.append("tenggat=?"); vals.append(isi["tenggat"])
        if ke == ET:
            sets.append("tanggapan_baru=0")
        if ke == SE:
            sets.append("ditutup=?"); vals.append(_now())
        catatan = isi.get("catatan") or ""
        if ke == SE and masih_ada:
            catatan = (catatan + " [ditutup meski temuan masih muncul]").strip()
        _log(c, tl_id, user, "TAHAP", dari, ke, catatan or None, isi_publik=isi.get("isi_publik"), no_surat=isi.get("no_surat"),
             tgl_surat=isi.get("tgl_surat"), tenggat=isi.get("tenggat"), jenis_tindakan=isi.get("jenis_tindakan"),
             tgl_tanggapan=isi.get("tgl_tanggapan"))
        c.execute(f"UPDATE tindak_lanjut SET {','.join(sets)} WHERE id=?", vals + [int(tl_id)])
        c.commit()
        return True, f"Dipindahkan ke tahap: {ke}."
    finally:
        c.close()


def catat(tl_id, user, catatan, pj=None, tenggat=None):
    """Catatan internal / ganti PJ / ubah tenggat tanpa pindah tahap."""
    c = db.conn()
    try:
        r = c.execute("SELECT * FROM tindak_lanjut WHERE id=?", (int(tl_id),)).fetchone()
        if not r:
            return False, "Tindak lanjut tidak ditemukan."
        sets, vals = ["diperbarui=?"], [_now()]
        if pj and pj != r["penanggung_jawab"]:
            sets.append("penanggung_jawab=?"); vals.append(pj)
            _log(c, tl_id, user, "GANTI_PJ", isi=f"{r['penanggung_jawab']} -> {pj}")
        if tenggat and str(tenggat) != r["tenggat"]:
            sets.append("tenggat=?"); vals.append(str(tenggat))
            _log(c, tl_id, user, "GANTI_TENGGAT", isi=f"{r['tenggat']} -> {tenggat}")
        if (catatan or "").strip():
            _log(c, tl_id, user, "CATATAN", isi=catatan.strip())
        c.execute(f"UPDATE tindak_lanjut SET {','.join(sets)} WHERE id=?", vals + [int(tl_id)])
        c.commit()
        return True, "Tersimpan."
    finally:
        c.close()


def tanggapan(tl_id, user, isi):
    """Tanggapan dari yayasan/PT. Mengembalikan (ok, pesan, log_id) agar lampiran bisa ditautkan."""
    if not (isi or "").strip():
        return False, "Isi tanggapan wajib diisi.", None
    c = db.conn()
    try:
        r = c.execute("SELECT status FROM tindak_lanjut WHERE id=?", (int(tl_id),)).fetchone()
        if not r or r["status"] not in (MT, PT_):
            return False, "Tindak lanjut ini tidak sedang menunggu tanggapan.", None
        lid = _log(c, tl_id, user, "TANGGAPAN", isi_publik=isi.strip())
        c.execute("UPDATE tindak_lanjut SET tanggapan_baru=1, diperbarui=? WHERE id=?", (_now(), int(tl_id)))
        c.commit()
        return True, "Tanggapan terkirim.", lid
    finally:
        c.close()


def visible_pengelola(tl, me):
    """Tindak lanjut yang boleh dilihat Pengelola: dalam cakupan dan sudah punya komunikasi publik."""
    if tl.empty:
        return tl
    t = tl[tl.id_yayasan == me["id_yayasan"]]
    if me.get("kode_pt"):
        t = t[t.kode_pt == me["kode_pt"]]
    c = db.conn()
    ids = {r[0] for r in c.execute("SELECT DISTINCT tl_id FROM tindak_lanjut_log WHERE isi_publik IS NOT NULL")}
    c.close()
    return t[t.id.isin(ids)]


def attach(findings):
    """Tambahkan kolom status tindak lanjut ke tabel temuan."""
    f = findings.copy()
    if f.empty:
        f["tindak_lanjut"] = []
        return f
    f["kunci"] = f.kode_aturan + "|" + f.referensi.str.split(" - ").str[0]
    t = read()
    t = t[t.status != SE].set_index("kunci").status
    f["tindak_lanjut"] = f.kunci.map(t).fillna("Belum ada")
    return f.drop(columns="kunci")


def terlambat(tl, today=None):
    today = str(today or date.today())
    return (tl.status != SE) & (tl.tenggat.fillna("9999") < today)
