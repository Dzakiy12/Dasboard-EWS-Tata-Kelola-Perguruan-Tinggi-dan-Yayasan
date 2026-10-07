"""Halaman Streamlit: portal Pengelola (yayasan/PT), verifikasi pengajuan, dan tindak lanjut pengawasan."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import auth
import db
import lampiran
import pengajuan
import rules
import scope
import servis
import tindak
from schema import ENUMS, FKS, TABLES

EMO = {"Merah": "🔴", "Kuning": "🟡", "Hijau": "🟢"}
LABEL_P = {"Merah": "🔴 Perlu klarifikasi/perbaikan segera", "Kuning": "🟡 Perlu dilengkapi/ditinjau", "Hijau": "🟢 Sesuai"}
HINT = {
    "PIM-01": "Siapkan dokumen/berita acara proses penjaringan calon pimpinan.",
    "PIM-02": "Siapkan risalah/keputusan pertimbangan senat atas pengangkatan pimpinan.",
    "PIM-03": "Jelaskan dan lampirkan SK terkait rangkap jabatan, atau perbaiki data jika keliru.",
    "PIM-04": "Lampirkan dokumen pemberhentian pimpinan sesuai prosedur statuta.",
    "PIM-05": "Lampirkan SK perpanjangan jabatan atau SK pimpinan baru.",
    "PIM-06": "Lampirkan bukti periode jabatan dan dasar pengangkatan kembali.",
    "PIM-07": "Periksa tanggal SK pengangkatan dan tanggal mulai jabatan.",
    "PIM-08": "Tetapkan pimpinan definitif dan ajukan datanya.",
    "PIM-09": "Lengkapi data statuta yang berlaku pada tanggal pengangkatan.",
    "PIM-10": "Lampirkan dasar kewenangan pengangkatan setelah perubahan Anggaran Dasar.",
    "PIM-11": "Verifikasi status rangkap jabatan dan perbaiki data bila perlu.",
    "PT-02": "Sampaikan tindak lanjut pembinaan kepada kementerian.",
    "PT-03": "Lampirkan SK penyelenggara PT yang berlaku dan perbaiki data ganda.",
    "PT-04": "Lampirkan SK alih kelola.",
    "PT-05": "Ajukan data statuta PT.",
    "PT-06": "Tinjau kewenangan akademik dalam statuta bersama pembina dan pengurus.",
    "PT-08": "Tetapkan pimpinan PT dan ajukan datanya.",
    "YAY-01": "Sampaikan perkembangan penyelesaian sengketa.",
    "YAY-02": "Ajukan data organ yayasan terbaru beserta akta/SK Kemenkum.",
    "YAY-03": "Samakan nomor SK badan hukum dengan akta pendirian.",
}
AKSI_LABEL = {"DIBUAT": "Dibuat", "TAHAP": "Tahap", "TANGGAPAN": "Tanggapan Anda", "CATATAN": "Catatan"}


# ------------------------------------------------------------------ util
def _colcfg(tabel, cols, me, data, disabled):
    meta, cc = TABLES[tabel], {}
    pts = sorted(scope.scope_pts(me, data))
    akta = data["akta"]
    akta_ids = sorted(akta[akta.id_yayasan == me["id_yayasan"]].id_akta)
    for c in cols:
        if c in meta["dates"]:
            cc[c] = st.column_config.DateColumn(c, format="YYYY-MM-DD", disabled=c in disabled)
        elif c in meta["ints"]:
            cc[c] = st.column_config.NumberColumn(c, step=1, disabled=c in disabled)
        elif c == "kode_pt" and tabel != "pt":
            cc[c] = st.column_config.SelectboxColumn(c, options=pts, disabled=c in disabled)
        elif c == "id_akta_sumber":
            cc[c] = st.column_config.SelectboxColumn(c, options=akta_ids, disabled=c in disabled)
        elif c in ENUMS:
            cc[c] = st.column_config.SelectboxColumn(c, options=ENUMS[c], disabled=c in disabled)
        else:
            cc[c] = st.column_config.TextColumn(c, disabled=c in disabled)
    return cc


def _unduh(me, lamp_df, prefix):
    for _, r in lamp_df.iterrows():
        lamp = lampiran.ambil(r["id"])
        if lamp and lampiran.boleh_akses(me, lamp):
            st.download_button(f"📎 {lamp['nama_file']} ({lamp['ukuran'] // 1024} KB · {lamp['diunggah_oleh']})", lamp["isi"],
                               file_name=lamp["nama_file"], mime=lamp["mime"], key=f"{prefix}_{lamp['id']}")


def _tampil_status(s):
    return "Diproses lebih lanjut oleh kementerian" if s in (tindak.ES, tindak.ET) else s


# ------------------------------------------------------------------ portal Pengelola
def pengelola_app(me):
    data = db.load_all()
    cfg = rules.load_cfg()
    findings, st_y, st_p = rules.evaluate(data, cfg, include_historis=False)
    y, pts = me["id_yayasan"], scope.scope_pts(me, data)
    yy = data["yayasan"]
    nama_y = yy[yy.id_yayasan == y].nama_yayasan.iloc[0]
    st.sidebar.title("🚦 Portal Yayasan & PT")
    st.sidebar.markdown(f"👤 **{me['nama']}**  \n{nama_y}" + (f"  \nPT: {me['kode_pt']}" if me.get("kode_pt") else ""))
    page = st.sidebar.radio("Menu", ["Beranda", "Permintaan Kementerian", "Ajukan Perubahan", "Pengajuan Saya"])
    with st.sidebar.expander("Akun saya"):
        auth.change_password_form(me)
    if st.sidebar.button("Keluar"):
        auth.logout()
    st.sidebar.caption("Perubahan data Anda berlaku setelah diverifikasi kementerian.")
    if auth.demo_aktif():
        st.sidebar.warning("MODE DEMO: data sintetis. Jangan masukkan data asli.")
    tl_all = tindak.visible_pengelola(tindak.read(), me)
    ajuan = pengajuan.daftar(me)

    if page == "Beranda":
        st.title(nama_y)
        st.caption("Penilaian awal sistem berdasarkan data yang tercatat. Ini bukan penetapan pelanggaran; "
                   "hal yang ditandai dapat dijelaskan atau dilengkapi melalui menu di samping.")
        c = st.columns(3)
        if not me.get("kode_pt"):
            sy = st_y[st_y.id == y].iloc[0].status
            c[0].markdown(f"**Status yayasan**  \n{LABEL_P[sy]}")
        c[1].metric("Permintaan kementerian aktif", int(tl_all.status.isin([tindak.MT, tindak.PT_]).sum()))
        c[2].metric("Pengajuan menunggu verifikasi", int((ajuan.status == pengajuan.MENUNGGU).sum()))
        sp = st_p[st_p.id.isin(pts)]
        st.subheader("Perguruan tinggi")
        st.dataframe(sp.assign(status=sp.status.map(LABEL_P))[["status", "id", "nama", "jenis_pt", "alasan_utama"]], hide_index=True, width="stretch")
        st.subheader("Hal yang perlu diperhatikan")
        f = scope.temuan_dalam_cakupan(findings, me, data)
        f = f[f.aktif]
        if f.empty:
            st.success("Tidak ada hal yang ditandai pada penilaian saat ini.")
        else:
            f = f.assign(tingkat=f.tingkat.map(LABEL_P), saran=f.kode_aturan.map(HINT).fillna(""))
            st.dataframe(f[["tingkat", "kode_aturan", "referensi", "uraian", "saran", "dasar"]], hide_index=True, width="stretch")
        st.subheader("Data Anda (hanya lihat)")
        for t in scope.tabel_diizinkan(me):
            v = scope.scope_view(t, data[t], me, data)
            with st.expander(f"{TABLES[t]['label']} ({len(v)})"):
                st.dataframe(v, hide_index=True, width="stretch")

    elif page == "Permintaan Kementerian":
        st.title("Permintaan dari kementerian")
        if tl_all.empty:
            st.info("Belum ada permintaan dari kementerian.")
        else:
            v = tl_all.assign(status_tampil=tl_all.status.map(_tampil_status))
            st.dataframe(v[["id", "kode_aturan", "referensi", "status_tampil", "tenggat", "jenis_tindakan", "no_surat", "tgl_surat"]],
                         hide_index=True, width="stretch")
            tid = st.selectbox("Buka permintaan", v.id.tolist(), format_func=lambda i: f"#{i} · {v[v.id == i].iloc[0].kode_aturan} · {v[v.id == i].iloc[0].referensi}")
            r = v[v.id == tid].iloc[0]
            st.markdown(f"**{r.kode_aturan}** · {r.referensi}  \n{r.uraian}")
            st.caption(f"Tahap: {r.status_tampil} · Tenggat: {r.tenggat}")
            hp = tindak.history(tid, publik=True)
            if len(hp):
                hp = hp.assign(aksi=hp.aksi.map(AKSI_LABEL).fillna(hp.aksi))
                st.dataframe(hp[["waktu", "aksi", "jenis_tindakan", "no_surat", "tgl_surat", "tenggat", "isi_publik"]], hide_index=True, width="stretch")
            _unduh(me, lampiran.daftar(tl_id=tid), f"pl{tid}")
            if r.status in (tindak.MT, tindak.PT_):
                st.markdown("**Kirim tanggapan**")
                with st.form(f"tanggap_{tid}", clear_on_submit=True):
                    isi = st.text_area("Isi tanggapan", placeholder="Jelaskan tindak lanjut atau perbaikan yang Anda lakukan.")
                    fl = st.file_uploader("Lampiran (PDF/JPG/PNG, maks 5 MB per file)", accept_multiple_files=True, type=["pdf", "jpg", "jpeg", "png"])
                    if st.form_submit_button("Kirim tanggapan", type="primary"):
                        files = [(f.name, f.getvalue()) for f in fl]
                        galat = [e for n, b in files if (e := lampiran.validasi(n, b))]
                        if galat:
                            st.error(" | ".join(galat))
                        else:
                            ok, msg, lid = tindak.tanggapan(tid, me["username"], isi)
                            if ok:
                                for n, b in files:
                                    lampiran.simpan(n, b, me["username"], tl_id=tid, log_id=lid)
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                st.caption("Jika tanggapan memerlukan perubahan data, gunakan menu **Ajukan Perubahan** lalu tautkan ke permintaan ini.")

    elif page == "Ajukan Perubahan":
        st.title("Ajukan perubahan data")
        st.caption("Perubahan **tidak langsung berlaku**. Kementerian akan memverifikasi dan melihat dampaknya sebelum menyetujui.")
        if st.session_state.get("aj_msg"):
            st.success(st.session_state.pop("aj_msg"))
        izin = scope.tabel_diizinkan(me)
        tabel = st.selectbox("Data yang akan diubah", izin, format_func=lambda t: TABLES[t]["label"])
        aksi_opsi = ["Ubah data yang sudah ada"] + (["Tambah data baru"] if tabel in pengajuan.TAMBAH_BOLEH else [])
        aksi = "UBAH" if st.radio("Jenis pengajuan", aksi_opsi, horizontal=True) == aksi_opsi[0] else "TAMBAH"
        full, pk = data[tabel], TABLES[tabel]["pk"]
        ro = set(scope.READONLY.get(tabel, set())) | {pk}
        ver = st.session_state.get("ver_aj", 0)
        if aksi == "UBAH":
            view = scope.scope_view(tabel, full, me, data)
            if view.empty:
                st.info("Tidak ada data pada cakupan Anda untuk tabel ini.")
                st.stop()
            if "tgl_mulai" in view.columns:
                view = view.sort_values("tgl_mulai", ascending=False)
            kunci = st.selectbox("Pilih data", view[pk].tolist(), format_func=lambda k: scope.label_record(tabel, view[view[pk] == k].iloc[0]))
            awal = view[view[pk] == kunci].reset_index(drop=True)
            kunci_norm = db.norm(kunci)
        else:
            awal = full.iloc[0:0].reindex([0])
            for c in scope.KOLOM_KEPEMILIKAN[tabel]:
                awal[c] = me["id_yayasan"]
            kunci_norm = None
        cc = _colcfg(tabel, list(full.columns), me, data, ro)
        edit = st.data_editor(awal, column_config=cc, hide_index=True, num_rows="fixed", width="stretch", disabled=list(ro),
                              key=f"aj_{tabel}_{aksi}_{kunci_norm}_{ver}")
        baru = {c: pengajuan._ser(edit.iloc[0][c]) for c in full.columns}
        lama = {c: pengajuan._ser(awal.iloc[0][c]) for c in full.columns}
        selisih = [c for c in full.columns if c not in ro and str(baru[c]) != str(lama[c]) and (aksi == "UBAH" or baru[c] is not None)]
        if selisih:
            st.markdown("**Perubahan yang akan diajukan**")
            st.dataframe(pd.DataFrame({"kolom": selisih, "sebelum": [lama[c] for c in selisih], "sesudah": [baru[c] for c in selisih]}),
                         hide_index=True, width="stretch")
        alasan = st.text_area("Alasan / penjelasan perubahan (wajib)", key=f"aj_alasan_{ver}")
        opsi_tl = [None] + tl_all[tl_all.status.isin([tindak.MT, tindak.PT_, tindak.ET])].id.tolist()
        tl_id = st.selectbox("Tautkan ke permintaan kementerian (opsional)", opsi_tl,
                             format_func=lambda i: "(tidak ditautkan)" if i is None else f"#{i} · {tl_all[tl_all.id == i].iloc[0].referensi}", key=f"aj_tl_{ver}")
        fl = st.file_uploader("Lampiran bukti (PDF/JPG/PNG, maks 5 MB per file)", accept_multiple_files=True, type=["pdf", "jpg", "jpeg", "png"], key=f"aj_file_{ver}")
        if any(c.startswith("ada_dok_") for c in selisih):
            st.warning("Perubahan yang menyatakan dokumen 'Ya' wajib disertai lampiran bukti.")
        if st.button("Kirim pengajuan", type="primary"):
            ok, msg, _ = pengajuan.ajukan(me, tabel, aksi, kunci_norm, baru, alasan, tl_id, [(f.name, f.getvalue()) for f in fl])
            if ok:
                st.session_state["aj_msg"] = msg
                st.session_state["ver_aj"] = ver + 1
                st.rerun()
            else:
                st.error(msg)

    else:  # Pengajuan Saya
        st.title("Pengajuan saya")
        if ajuan.empty:
            st.info("Belum ada pengajuan.")
        else:
            st.dataframe(ajuan[["id", "tabel", "aksi", "kunci", "status", "diajukan_pada", "ditinjau_oleh", "catatan_peninjau"]],
                         hide_index=True, width="stretch")
            pid = st.selectbox("Lihat rincian", ajuan.id.tolist(), format_func=lambda i: f"#{i} · {ajuan[ajuan.id == i].iloc[0].tabel} · {ajuan[ajuan.id == i].iloc[0].status}")
            p = pengajuan.get(pid)
            st.markdown(f"**Alasan:** {p['alasan']}")
            if p["catatan_peninjau"]:
                st.info(f"Catatan kementerian: {p['catatan_peninjau']}")
            st.dataframe(pengajuan.diff_df(p), hide_index=True, width="stretch")
            _unduh(me, lampiran.daftar(pengajuan_id=pid), f"pj{pid}")


# ------------------------------------------------------------------ verifikasi pengajuan (kementerian)
def page_verifikasi(me, data, cfg):
    st.title("Verifikasi pengajuan perubahan")
    st.caption("Perubahan dari yayasan/PT baru berlaku setelah Anda setujui. Dampak pada warna dihitung lebih dulu.")
    can_decide = auth.level(me) >= 1
    df = pengajuan.daftar()
    sf = st.multiselect("Status", [pengajuan.MENUNGGU, pengajuan.SETUJU, pengajuan.TOLAK], default=[pengajuan.MENUNGGU])
    v = df[df.status.isin(sf)]
    st.caption(f"{len(v)} pengajuan")
    if v.empty:
        return
    st.dataframe(v[["id", "id_yayasan", "kode_pt", "tabel", "aksi", "kunci", "status", "diajukan_oleh", "diajukan_pada"]], hide_index=True, width="stretch")
    pid = st.selectbox("Buka pengajuan", v.id.tolist(), format_func=lambda i: f"#{i} · {v[v.id == i].iloc[0].id_yayasan} · {v[v.id == i].iloc[0].tabel}")
    p = pengajuan.get(pid)
    st.markdown(f"**{p['aksi']} {TABLES[p['tabel']]['label']}** ({p['kunci'] or 'baru'}) · diajukan oleh {p['diajukan_oleh']} · {p['diajukan_pada'][:16]}")
    st.markdown(f"**Alasan pengaju:** {p['alasan']}")
    if p["tl_id"]:
        st.caption(f"Terkait permintaan/tindak lanjut #{p['tl_id']}")
    st.dataframe(pengajuan.diff_df(p), hide_index=True, width="stretch")
    lamp = lampiran.daftar(pengajuan_id=pid)
    st.markdown(f"**Lampiran ({len(lamp)})**")
    _unduh(me, lamp, f"vp{pid}")
    if p["status"] != pengajuan.MENUNGGU:
        st.info(f"{p['status']} oleh {p['ditinjau_oleh']} · {str(p['ditinjau_pada'])[:16]}. Catatan: {p['catatan_peninjau'] or '-'}")
        return
    sim, err = pengajuan.simulasi(p, data, cfg)
    if err:
        st.error(" ".join(err))
    else:
        st.markdown("**Dampak jika disetujui**")
        if sim["status"].empty:
            st.write("Tidak ada perubahan warna.")
        else:
            s = sim["status"].assign(status_sebelum=sim["status"].status_sebelum.map(lambda x: f"{EMO[x]} {x}"),
                                     status_sesudah=sim["status"].status_sesudah.map(lambda x: f"{EMO[x]} {x}"))
            st.dataframe(s, hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        c1.write("Temuan yang hilang: " + (", ".join(f"{a} {b}" for a, b, _ in sim["hilang"]) or "-"))
        c2.write("Temuan yang muncul: " + (", ".join(f"{a} {b}" for a, b, _ in sim["muncul"]) or "-"))
    if not can_decide:
        st.info("Peran Pembaca hanya dapat melihat.")
        return
    cat = st.text_area("Catatan peninjau (wajib jika menolak)", key=f"cat_{pid}")
    b1, b2 = st.columns(2)
    if b1.button("✅ Setujui", type="primary", disabled=bool(err), key=f"ok_{pid}"):
        ok, msg = pengajuan.setujui(pid, me["username"], cat)
        if ok:
            ch = servis.refresh_status(f"pengajuan #{pid} oleh {p['diajukan_oleh']}")
            st.success(msg + (f" {len(ch)} entitas berubah warna." if len(ch) else ""))
            st.rerun()
        else:
            st.error(msg)
    if b2.button("❌ Tolak", key=f"no_{pid}"):
        ok, msg = pengajuan.tolak(pid, me["username"], cat)
        (st.success if ok else st.error)(msg)
        if ok:
            st.rerun()


# ------------------------------------------------------------------ tindak lanjut (kementerian)
def page_tindak_lanjut(me, findings):
    st.title("Tindak lanjut pengawasan")
    st.caption("Warna tetap mengikuti data. Tahap tindak lanjut hanya mencatat langkah pengawasan; menutupnya tidak mengubah warna.")
    user, is_admin, can_edit = me["username"], auth.is_admin(me), auth.level(me) >= 1
    q = tindak.with_key(findings)
    tl = tindak.read()
    terbuka = tl[tl.status != tindak.SE]
    q = q.merge(terbuka[["kunci", "id", "status", "penanggung_jawab", "tenggat"]]
                .rename(columns={"id": "tl_id", "status": "tl_status", "penanggung_jawab": "pj"}), on="kunci", how="left")
    hari_ini = date.today()
    m = st.columns(4)
    m[0].metric("🔴 Merah belum ditindaklanjuti", int(((q.tingkat == "Merah") & q.tl_id.isna()).sum()))
    m[1].metric("🟡 Kuning belum ditindaklanjuti", int(((q.tingkat == "Kuning") & q.tl_id.isna()).sum()))
    m[2].metric("Terlambat", int(tindak.terlambat(tl).sum()))
    m[3].metric("Ada tanggapan baru", int((terbuka.tanggapan_baru == 1).sum()))
    t1, t2 = st.tabs(["Antrean temuan", "Daftar tindak lanjut"])
    with t1:
        c1, c2, c3 = st.columns(3)
        tf = c1.multiselect("Tingkat", ["Merah", "Kuning"], default=["Merah", "Kuning"], key="tl_tf")
        yf = c2.selectbox("Yayasan", ["(semua)"] + sorted(q.id_yayasan.unique()), key="tl_yf")
        hanya = c3.checkbox("Hanya yang belum ditindaklanjuti", value=True, key="tl_only")
        v = q[q.tingkat.isin(tf)]
        if yf != "(semua)":
            v = v[v.id_yayasan == yf]
        if hanya:
            v = v[v.tl_id.isna()]
        v = v.sort_values("tingkat", key=lambda s: s.map(tindak.RANK), ascending=False).reset_index(drop=True)
        st.caption(f"{len(v)} temuan")
        st.dataframe(v.assign(tingkat=v.tingkat.map(lambda s: f"{EMO[s]} {s}"), tl_status=v.tl_status.fillna("Belum ada"))
                     [["tingkat", "kode_aturan", "id_yayasan", "referensi", "uraian", "tl_status"]], hide_index=True, width="stretch")
        if can_edit and len(v):
            st.markdown("**Mulai tindak lanjut (tahap: Verifikasi internal)**")
            idx = st.selectbox("Temuan", range(len(v)), key="tl_pilih",
                               format_func=lambda i: f"{EMO[v.tingkat[i]]} {v.kode_aturan[i]} · {v.id_yayasan[i]} · {v.referensi[i]}")
            tingkat = v.tingkat[idx]
            with st.form("buat_tl", clear_on_submit=True):
                us = tindak.users()
                pj = st.selectbox("Penanggung jawab", us, index=us.index(user) if user in us else 0)
                tenggat = st.date_input("Target selesai verifikasi internal", value=hari_ini + timedelta(days=tindak.SLA_HARI[tingkat]),
                                        key=f"tl_tg_{tingkat}", help=f"Bawaan {tindak.SLA_HARI['Merah']} hari (merah) / {tindak.SLA_HARI['Kuning']} hari (kuning).")
                cat = st.text_area("Catatan internal awal (opsional)", placeholder="Mis. cek AHU/PDDikti sebelum menghubungi yayasan")
                if st.form_submit_button("Mulai", type="primary"):
                    ok, msg = tindak.buat(v.iloc[idx], pj, tenggat, cat, user)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
    with t2:
        c1, c2, c3, c4 = st.columns(4)
        sf = c1.multiselect("Tahap", tindak.STATUS, default=tindak.STATUS[:-1], key="tl_sf")
        pf = c2.multiselect("Penanggung jawab", sorted(tl.penanggung_jawab.dropna().unique()), key="tl_pf")
        lt = c3.checkbox("Hanya terlambat", key="tl_lt")
        tb = c4.checkbox("Ada tanggapan baru", key="tl_tb")
        d = tl.assign(terlambat=tindak.terlambat(tl), temuan_masih_ada=tl.kunci.isin(set(q.kunci)))
        d = d[d.status.isin(sf)]
        if pf:
            d = d[d.penanggung_jawab.isin(pf)]
        if lt:
            d = d[d.terlambat]
        if tb:
            d = d[d.tanggapan_baru == 1]
        st.dataframe(d.assign(tingkat=d.tingkat.map(lambda s: f"{EMO.get(s, '')} {s}"))
                     [["id", "tingkat", "kode_aturan", "id_yayasan", "referensi", "status", "penanggung_jawab", "tenggat", "terlambat", "tanggapan_baru"]],
                     hide_index=True, width="stretch")
        if len(d):
            sid = st.selectbox("Buka tindak lanjut", d.id.tolist(), key="tl_buka",
                               format_func=lambda i: f"#{i} · {d[d.id == i].iloc[0].kode_aturan} · {d[d.id == i].iloc[0].referensi}")
            r = tl[tl.id == sid].iloc[0]
            masih = r.kunci in set(q.kunci)
            st.markdown(f"**{EMO.get(r.tingkat, '')} {r.kode_aturan}** · {r.referensi}  \n{r.uraian}")
            st.caption(f"Tahap: **{r.status}** · PJ: {r.penanggung_jawab} · Tenggat: {r.tenggat} · Dibuat {str(r.dibuat)[:10]} oleh {r.dibuat_oleh}")
            if r.tanggapan_baru == 1:
                st.warning("Ada tanggapan baru dari yayasan/PT. Pindahkan ke tahap Evaluasi tanggapan setelah dibaca.")
            if r.status != tindak.SE and not masih:
                st.success("Temuan ini sudah tidak muncul pada penilaian saat ini (data sudah diperbaiki).")
            if r.status == tindak.SE and masih:
                st.warning("Tindak lanjut ini selesai, tetapi temuannya masih muncul pada penilaian saat ini.")
            lamp = lampiran.daftar(tl_id=sid)
            if len(lamp):
                st.markdown("**Lampiran dari yayasan/PT**")
                _unduh(me, lamp, f"tl{sid}")
            if can_edit and r.status != tindak.SE:
                opsi = tindak.pilihan_status(r.status, is_admin)
                ke = st.selectbox("Pindahkan ke tahap", ["(tidak pindah tahap)"] + opsi, key=f"tl_ke_{sid}_{r.status}")
                with st.form(f"tl_form_{sid}_{r.status}_{ke}", clear_on_submit=True):
                    isi = {}
                    if ke == "(tidak pindah tahap)":
                        us = tindak.users()
                        pj2 = st.selectbox("Penanggung jawab", us, index=us.index(r.penanggung_jawab) if r.penanggung_jawab in us else 0)
                        tg2 = st.date_input("Tenggat", value=date.fromisoformat(r.tenggat))
                        isi["catatan"] = st.text_area("Catatan internal (tidak terlihat yayasan/PT)")
                    else:
                        if ke == tindak.PT_:
                            isi["jenis_tindakan"] = st.selectbox("Jenis tindakan", tindak.JENIS_TINDAKAN)
                        if ke in (tindak.MT, tindak.PT_, tindak.ES):
                            isi["no_surat"] = st.text_input("Nomor surat")
                            isi["tgl_surat"] = str(st.date_input("Tanggal surat", value=hari_ini))
                        if ke in (tindak.MT, tindak.PT_):
                            isi["tenggat"] = str(st.date_input("Tenggat tanggapan/perbaikan", value=hari_ini + timedelta(days=14)))
                            isi["isi_publik"] = st.text_area("Isi permintaan (terlihat yayasan/PT)", placeholder="Tulis permintaan dengan jelas dan netral.")
                        if ke == tindak.ET:
                            isi["tgl_tanggapan"] = str(st.date_input("Tanggal tanggapan diterima", value=hari_ini))
                        if ke == tindak.SE:
                            isi["alasan_penutupan"] = st.selectbox("Alasan penutupan", tindak.ALASAN_TUTUP)
                        isi["catatan"] = st.text_area("Catatan internal (tidak terlihat yayasan/PT)")
                        paksa = st.checkbox("Tutup walau temuan masih muncul (mis. diterima/diputuskan pejabat)") if (ke == tindak.SE and masih) else False
                    if st.form_submit_button("Simpan", type="primary"):
                        if ke == "(tidak pindah tahap)":
                            ok, msg = tindak.catat(sid, user, isi["catatan"], pj2, tg2)
                        else:
                            ok, msg = tindak.pindah(sid, user, is_admin, ke, isi, masih_ada=masih, paksa_tutup=paksa)
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()
            elif not can_edit:
                st.info("Peran Pembaca hanya dapat melihat.")
            st.markdown("**Riwayat lengkap (internal)**")
            hh = tindak.history(sid)
            st.dataframe(hh.drop(columns=["id"]), hide_index=True, width="stretch")
