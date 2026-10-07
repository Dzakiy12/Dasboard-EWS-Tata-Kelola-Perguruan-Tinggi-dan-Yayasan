#!/usr/bin/env python3
"""Reset database ke DATA SINTETIS TERBARU + buat akun uji. HANYA untuk uji coba.

Pakai:  python siapkan_demo.py --ya
- ews.db lama TIDAK dihapus, tetapi dipindah menjadi ews_cadangan_<waktu>.db.
- Password dibuat acak dan dicetak SEKALI di layar. Catat sebelum menutup terminal.
- Jangan pakai skrip ini pada data asli.
"""
import os
import secrets
import shutil
import sys
from datetime import datetime

if "--ya" not in sys.argv:
    print(__doc__)
    print("Tambahkan --ya untuk melanjutkan.")
    sys.exit(1)

if not os.environ.get("EWS_ADMIN_PASSWORD"):
    os.environ["EWS_ADMIN_PASSWORD"] = secrets.token_urlsafe(9) + "7"
admin_pw = os.environ["EWS_ADMIN_PASSWORD"]

import auth  # noqa: E402
import db  # noqa: E402
import pengajuan  # noqa: E402
import servis  # noqa: E402
import tindak  # noqa: E402

if db.DB_PATH.exists():
    cad = db.DB_PATH.with_name(f"ews_cadangan_{datetime.now():%Y%m%d_%H%M%S}.db")
    shutil.move(str(db.DB_PATH), str(cad))
    print(f"Database lama disimpan sebagai {cad.name}")

db.init_db()
auth.init_users()
tindak.init()
pengajuan.init()

AKUN = [("pengawas1", "Pengawas Demo", "Pengawas", None, None),
        ("pembaca1", "Pembaca Demo", "Pembaca", None, None),
        ("yayasan46", "Pengelola Yayasan Y046", "Pengelola", "Y046", None),
        ("pt69", "Pengelola PT P069", "Pengelola", "Y046", "P069")]
hasil = [("admin", "Admin", admin_pw, "-")]
c = db.conn()
for u, nama, peran, y, p in AKUN:
    pw = secrets.token_urlsafe(9) + "7"
    c.execute("INSERT INTO pengguna(username,nama,peran,password_hash,aktif,wajib_ganti,dibuat,id_yayasan,kode_pt) VALUES(?,?,?,?,1,0,?,?,?)",
              (u, nama, peran, auth.hash_pw(pw), datetime.now().isoformat(timespec="seconds"), y, p))
    hasil.append((u, peran, pw, f"{y or '-'}/{p or '*'}"))
c.commit()
c.close()
servis.refresh_status("awal (data sintetis)")

print("\nDatabase siap dengan data sintetis terbaru. Akun uji (catat sekarang):\n")
print(f"{'username':12s} {'peran':12s} {'cakupan':10s} password")
for u, peran, pw, cak in hasil:
    print(f"{u:12s} {peran:12s} {cak:10s} {pw}")
print("\nJalankan:  streamlit run app.py")
