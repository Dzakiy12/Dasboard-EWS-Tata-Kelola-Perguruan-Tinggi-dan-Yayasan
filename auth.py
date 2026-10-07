"""Login, peran, dan manajemen pengguna (hanya pustaka standar Python).

Peran kementerian: Pembaca < Pengawas < Admin. Peran Pengelola = yayasan/PT, dibatasi pada cakupan datanya sendiri.
- Password disimpan sebagai hash scrypt (tidak pernah teks asli).
- Akun terkunci sementara setelah beberapa kali gagal login.
- Sesi berakhir otomatis jika tidak aktif.
- Admin pertama dibuat dari EWS_ADMIN_PASSWORD (env) / admin_password (st.secrets).
  Jika tidak diatur, password acak dicetak sekali di terminal/log dan wajib diganti saat login pertama.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import db

ROLES = ["Pembaca", "Pengawas", "Admin"]      # sisi kementerian
PENGELOLA = "Pengelola"                       # pihak yang diawasi (yayasan/PT), dibatasi cakupan
ALL_ROLES = ROLES + [PENGELOLA]
MAX_GAGAL, KUNCI_MENIT, IDLE_MENIT, MIN_PW = 5, 10, 30, 10


def level(me):
    """Tingkat hak sisi kementerian: Pembaca 0, Pengawas 1, Admin 2. Pengelola = -1."""
    return ROLES.index(me["peran"]) if me["peran"] in ROLES else -1


def is_pengelola(me):
    return me["peran"] == PENGELOLA


def is_admin(me):
    return me["peran"] == "Admin"


# ---------- password ----------
def hash_pw(pw):
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def verify_pw(pw, stored):
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def cek_password_baru(pw, pw2=None, username=""):
    if len(pw) < MIN_PW:
        return f"Password minimal {MIN_PW} karakter."
    if username and username.lower() in pw.lower():
        return "Password tidak boleh memuat username."
    if pw.isdigit() or pw.isalpha():
        return "Password harus memadukan huruf dan angka/simbol."
    if pw2 is not None and pw != pw2:
        return "Konfirmasi password tidak sama."
    return None


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _audit(me_user, kunci, aksi, kolom=None, lama=None, baru=None):
    c = db.conn()
    c.execute("INSERT INTO audit_log(waktu,pengguna,tabel,kunci,aksi,kolom,nilai_lama,nilai_baru) VALUES(?,?,?,?,?,?,?,?)",
              (_now(), me_user, "pengguna", kunci, aksi, kolom, lama, baru))
    c.commit()
    c.close()


# ---------- mode demo (Streamlit Cloud: tanpa terminal) ----------
DEMO_AKUN = [("pengawas1", "Pengawas Demo", "Pengawas", None, None),
             ("pembaca1", "Pembaca Demo", "Pembaca", None, None),
             ("yayasan46", "Pengelola Yayasan Y046", "Pengelola", "Y046", None),
             ("pt69", "Pengelola PT P069", "Pengelola", "Y046", "P069")]


def _secret(nama, env):
    v = os.environ.get(env)
    if v:
        return v
    try:
        return st.secrets.get(nama)
    except Exception:
        return None


def demo_aktif():
    v = _secret("demo_mode", "EWS_DEMO")
    return str(v).strip().lower() in ("1", "true", "ya", "yes")


def _akun_demo(c):
    """Buat akun uji jika mode demo aktif dan demo_password diatur. Tidak menimpa akun yang sudah ada."""
    pw = _secret("demo_password", "EWS_DEMO_PASSWORD")
    if not (demo_aktif() and pw):
        return
    for u, nama, peran, y, p in DEMO_AKUN:
        if c.execute("SELECT 1 FROM pengguna WHERE username=?", (u,)).fetchone():
            continue
        err = cek_password_baru(str(pw), None, u)
        if err:
            print(f"[demo] akun {u} tidak dibuat: {err}", flush=True)
            continue
        c.execute("INSERT INTO pengguna(username,nama,peran,password_hash,aktif,wajib_ganti,dibuat,id_yayasan,kode_pt) VALUES(?,?,?,?,1,0,?,?,?)",
                  (u, nama, peran, hash_pw(str(pw)), _now(), y, p))


# ---------- penyimpanan ----------
def init_users():
    c = db.conn()
    c.execute("""CREATE TABLE IF NOT EXISTS pengguna(username TEXT PRIMARY KEY, nama TEXT, peran TEXT,
                 password_hash TEXT, aktif INTEGER DEFAULT 1, wajib_ganti INTEGER DEFAULT 0, dibuat TEXT,
                 id_yayasan TEXT, kode_pt TEXT)""")
    kolom = {r[1] for r in c.execute("PRAGMA table_info(pengguna)")}
    for k in ("id_yayasan", "kode_pt"):
        if k not in kolom:
            c.execute(f"ALTER TABLE pengguna ADD COLUMN {k} TEXT")
    c.execute("UPDATE pengguna SET peran='Pengawas' WHERE peran='Petugas data'")
    c.execute("""CREATE TABLE IF NOT EXISTS percobaan_login(id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT,
                 username TEXT, berhasil INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, pengguna TEXT,
                 tabel TEXT, kunci TEXT, aksi TEXT, kolom TEXT, nilai_lama TEXT, nilai_baru TEXT)""")
    if c.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0:
        pw = os.environ.get("EWS_ADMIN_PASSWORD")
        if not pw:
            try:
                pw = st.secrets.get("admin_password")
            except Exception:
                pw = None
        wajib = 0
        if not pw:
            pw, wajib = secrets.token_urlsafe(12), 1
            print("\n" + "=" * 60 + f"\nAKUN ADMIN AWAL DIBUAT\n  username: admin\n  password: {pw}\n"
                  "Wajib diganti saat login pertama. Pesan ini hanya muncul sekali.\n" + "=" * 60 + "\n", flush=True)
        c.execute("INSERT INTO pengguna(username,nama,peran,password_hash,aktif,wajib_ganti,dibuat) VALUES(?,?,?,?,1,?,?)",
                  ("admin", "Administrator", "Admin", hash_pw(pw), wajib, _now()))
    _akun_demo(c)
    c.commit()
    c.close()


def _get(username):
    c = db.conn()
    r = c.execute("SELECT * FROM pengguna WHERE username=?", (username,)).fetchone()
    c.close()
    return dict(r) if r else None


def _terkunci(username):
    c = db.conn()
    batas = (datetime.now() - timedelta(minutes=KUNCI_MENIT)).isoformat(timespec="seconds")
    ok = c.execute("SELECT MAX(waktu) FROM percobaan_login WHERE username=? AND berhasil=1", (username,)).fetchone()[0]
    mulai = max(batas, ok or "")
    n = c.execute("SELECT COUNT(*) FROM percobaan_login WHERE username=? AND berhasil=0 AND waktu>?", (username, mulai)).fetchone()[0]
    c.close()
    return n >= MAX_GAGAL


def _catat(username, berhasil):
    c = db.conn()
    c.execute("INSERT INTO percobaan_login(waktu,username,berhasil) VALUES(?,?,?)", (_now(), username, int(berhasil)))
    c.commit()
    c.close()


def set_password(username, pw, wajib_ganti=0):
    c = db.conn()
    c.execute("UPDATE pengguna SET password_hash=?, wajib_ganti=? WHERE username=?", (hash_pw(pw), wajib_ganti, username))
    c.commit()
    c.close()


# ---------- alur login ----------
def _me(row):
    return dict(username=row["username"], nama=row["nama"], peran=row["peran"], wajib_ganti=bool(row["wajib_ganti"]),
                id_yayasan=row.get("id_yayasan"), kode_pt=row.get("kode_pt"))


def require_login():
    init_users()
    a = st.session_state.get("auth")
    if a:
        row = _get(a["username"])
        idle = datetime.now() - a["last"] > timedelta(minutes=IDLE_MENIT)
        if not row or not row["aktif"] or idle:
            st.session_state.pop("auth", None)
            if idle:
                st.warning("Sesi berakhir karena tidak aktif. Silakan masuk kembali.")
        else:
            a["last"] = datetime.now()
            return {**_me(row), "last": a["last"]}
    st.title("🚦 EWS Yayasan & Perguruan Tinggi")
    st.caption("Silakan masuk untuk melanjutkan.")
    if demo_aktif():
        st.info("**Mode demo — data sintetis (rekaan).** Akun uji: pengawas1, pembaca1, yayasan46, pt69. "
                "Password diberikan oleh penyelenggara demo.")
    with st.form("login"):
        u = st.text_input("Username", key="login_user")
        p = st.text_input("Password", type="password", key="login_pw")
        ok = st.form_submit_button("Masuk", type="primary")
    if ok:
        u = u.strip().lower()
        row = _get(u)
        if _terkunci(u):
            st.error(f"Terlalu banyak percobaan gagal. Coba lagi dalam {KUNCI_MENIT} menit.")
        elif row and row["aktif"] and verify_pw(p, row["password_hash"]):
            _catat(u, True)
            st.session_state["auth"] = dict(username=u, last=datetime.now())
            st.rerun()
        else:
            if row:
                _catat(u, False)
            else:
                hash_pw("dummy")  # samakan waktu respons
            st.error("Username atau password salah, atau akun tidak aktif.")
    st.stop()


def logout():
    st.session_state.pop("auth", None)
    st.rerun()


def change_password_form(me, wajib=False):
    with st.form("ganti_pw", clear_on_submit=True):
        old = st.text_input("Password saat ini", type="password")
        n1 = st.text_input("Password baru", type="password")
        n2 = st.text_input("Ulangi password baru", type="password")
        ok = st.form_submit_button("Simpan password", type="primary")
    if ok:
        row = _get(me["username"])
        err = cek_password_baru(n1, n2, me["username"])
        if not verify_pw(old, row["password_hash"]):
            st.error("Password saat ini salah.")
        elif err:
            st.error(err)
        elif verify_pw(n1, row["password_hash"]):
            st.error("Password baru harus berbeda dari yang lama.")
        else:
            set_password(me["username"], n1, 0)
            _audit(me["username"], me["username"], "GANTI_PASSWORD")
            st.success("Password diperbarui.")
            if wajib:
                st.rerun()


def force_change(me):
    st.title("Ganti password")
    st.info("Demi keamanan, Anda harus mengganti password sebelum melanjutkan.")
    change_password_form(me, wajib=True)
    if st.button("Keluar"):
        logout()
    st.stop()


# ---------- halaman admin ----------
def page_users(me):
    st.title("Manajemen pengguna")
    c = db.conn()
    df = pd.read_sql("SELECT username, nama, peran, id_yayasan, kode_pt, aktif, wajib_ganti, dibuat FROM pengguna ORDER BY username", c)
    c.close()
    st.dataframe(df.assign(aktif=df.aktif.astype(bool), wajib_ganti=df.wajib_ganti.astype(bool)), hide_index=True, width="stretch")
    st.markdown("**Sisi kementerian:** Pembaca (lihat saja) · Pengawas (+ ubah data, kelola tindak lanjut, verifikasi pengajuan) · "
                "Admin (+ hapus data, eskalasi/tutup tindak lanjut, ubah aturan, kelola pengguna)  \n"
                "**Pihak diawasi:** Pengelola (yayasan/PT) hanya melihat dan mengajukan perubahan untuk data miliknya; "
                "perubahan baru berlaku setelah diverifikasi pengawas.")
    yy = db.load_table("yayasan")
    pt = db.load_table("pt")
    y_opts = dict(zip(yy.id_yayasan, yy.id_yayasan + " - " + yy.nama_yayasan))

    def pilih_cakupan(key, y_def=None, p_def=None):
        y = st.selectbox("Yayasan (cakupan)", list(y_opts), format_func=y_opts.get, key=f"{key}_y",
                         index=list(y_opts).index(y_def) if y_def in y_opts else 0)
        pts = pt[pt.id_yayasan == y]
        p_opts = {"(semua PT milik yayasan ini)": None} | dict(zip(pts.nama_pt, pts.kode_pt))
        label = next((k for k, v in p_opts.items() if v == p_def), "(semua PT milik yayasan ini)")
        pl = st.selectbox("Batasi ke satu PT (opsional)", list(p_opts), index=list(p_opts).index(label), key=f"{key}_p")
        return y, p_opts[pl]

    t1, t2 = st.tabs(["Tambah pengguna", "Ubah / reset"])
    with t1:
        pr = st.selectbox("Peran", ALL_ROLES, key="np_peran")
        y_sc, p_sc = (pilih_cakupan("np") if pr == PENGELOLA else (None, None))
        with st.form("tambah_user", clear_on_submit=True):
            u = st.text_input("Username (huruf kecil, angka, titik, strip)").strip().lower()
            nm = st.text_input("Nama lengkap")
            pw = st.text_input("Password awal", type="password")
            if st.form_submit_button("Tambah", type="primary"):
                if not re.fullmatch(r"[a-z0-9._-]{3,30}", u):
                    err = "Username 3-30 karakter: huruf kecil, angka, titik, garis bawah, strip."
                elif _get(u):
                    err = "Username sudah dipakai."
                elif not nm.strip():
                    err = "Nama lengkap wajib diisi."
                else:
                    err = cek_password_baru(pw, None, u)
                if err:
                    st.error(err)
                else:
                    cn = db.conn()
                    cn.execute("INSERT INTO pengguna(username,nama,peran,password_hash,aktif,wajib_ganti,dibuat,id_yayasan,kode_pt) "
                               "VALUES(?,?,?,?,1,1,?,?,?)", (u, nm.strip(), pr, hash_pw(pw), _now(), y_sc, p_sc))
                    cn.commit()
                    cn.close()
                    _audit(me["username"], u, "TAMBAH", "peran", None, pr + (f" ({y_sc}/{p_sc or '*'})" if y_sc else ""))
                    st.success(f"Pengguna {u} dibuat. Yang bersangkutan wajib mengganti password saat login pertama.")
                    st.rerun()
    with t2:
        pilih = st.selectbox("Pengguna", df.username.tolist())
        row = _get(pilih)
        peran = st.selectbox("Peran", ALL_ROLES, index=ALL_ROLES.index(row["peran"]) if row["peran"] in ALL_ROLES else 0, key=f"pr_{pilih}")
        y_new, p_new = (pilih_cakupan(f"ed_{pilih}", row.get("id_yayasan"), row.get("kode_pt")) if peran == PENGELOLA else (None, None))
        aktif = st.checkbox("Aktif", value=bool(row["aktif"]), key=f"ak_{pilih}")
        if st.button("Simpan perubahan peran/status"):
            admins_lain = db_count_admin_aktif(exclude=pilih)
            if pilih == me["username"] and (peran != "Admin" or not aktif):
                st.error("Anda tidak bisa menurunkan atau menonaktifkan akun Anda sendiri.")
            elif row["peran"] == "Admin" and (peran != "Admin" or not aktif) and admins_lain == 0:
                st.error("Harus tersisa minimal satu Admin aktif.")
            else:
                cn = db.conn()
                cn.execute("UPDATE pengguna SET peran=?, aktif=?, id_yayasan=?, kode_pt=? WHERE username=?",
                           (peran, int(aktif), y_new, p_new, pilih))
                cn.commit()
                cn.close()
                if peran != row["peran"]:
                    _audit(me["username"], pilih, "UBAH", "peran", row["peran"], peran)
                if (y_new, p_new) != (row.get("id_yayasan"), row.get("kode_pt")):
                    _audit(me["username"], pilih, "UBAH", "cakupan", f"{row.get('id_yayasan')}/{row.get('kode_pt')}", f"{y_new}/{p_new}")
                if int(aktif) != row["aktif"]:
                    _audit(me["username"], pilih, "UBAH", "aktif", str(row["aktif"]), str(int(aktif)))
                st.success("Tersimpan.")
                st.rerun()
        st.divider()
        with st.form(f"reset_{pilih}", clear_on_submit=True):
            npw = st.text_input("Password sementara baru", type="password")
            if st.form_submit_button("Reset password"):
                err = cek_password_baru(npw, None, pilih)
                if err:
                    st.error(err)
                else:
                    set_password(pilih, npw, 1)
                    _audit(me["username"], pilih, "RESET_PASSWORD")
                    st.success("Password direset. Pengguna wajib menggantinya saat login berikutnya.")


def db_count_admin_aktif(exclude=None):
    c = db.conn()
    n = c.execute("SELECT COUNT(*) FROM pengguna WHERE peran='Admin' AND aktif=1 AND username<>?", (exclude or "",)).fetchone()[0]
    c.close()
    return n
