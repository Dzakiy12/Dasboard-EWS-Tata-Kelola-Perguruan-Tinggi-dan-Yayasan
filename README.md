# EWS Yayasan & Perguruan Tinggi (prototipe)

## Menjalankan
```bash
pip install -r requirements.txt
streamlit run app.py
```
Pertama kali dijalankan, database `ews.db` (SQLite) dibuat otomatis dari `data/Contoh_Data_50_Yayasan.xlsx`.
Untuk mulai ulang dari data contoh: hapus `ews.db`.

## Cara memperbarui data
- **Kelola Data**: edit sel, tambah baris (ID otomatis jika dikosongkan), hapus baris. Ada validasi relasi, tanggal, dan kolom wajib.
- **Unggah Excel**: tambah/perbarui massal dengan format sheet yang sama. Tidak menghapus data.
- Setiap perubahan dicatat di **Log** (siapa, kapan, nilai lama/baru), dan perubahan warna status dicatat di **Riwayat Status**.

## Struktur
- `rules.py` mesin aturan (merah/kuning/hijau, status terburuk menang)
- `rules_config.json` aturan aktif dan parameter (bisa diubah dari menu Aturan)
- `db.py` penyimpanan, validasi, audit; `schema.py` definisi tabel dan pilihan isian
- `app.py` dashboard

## Catatan penting
- Aturan adalah usulan awal dari kolom data; wajib divalidasi ahli hukum.
- Belum ada autentikasi. Tambahkan login/peran (mis. streamlit-authenticator atau SSO) sebelum dipakai bersama.
- Untuk produksi, ganti SQLite dengan PostgreSQL (cukup ubah `db.py`).

## Login
- Pertama kali dijalankan dibuat akun `admin`. Password diambil dari variabel lingkungan `EWS_ADMIN_PASSWORD`
  atau `admin_password` di `.streamlit/secrets.toml` (lihat `secrets.toml.example`).
  Jika tidak diatur, password acak dicetak sekali di terminal dan wajib diganti saat login pertama.
- Peran kementerian: Pembaca (lihat) < Pengawas (+ ubah/unggah data, tindak lanjut, verifikasi pengajuan) < Admin (+ hapus data, eskalasi/tutup, aturan, kelola pengguna).
- Peran Pengelola (yayasan/PT): lihat dan ajukan perubahan hanya untuk data miliknya. Cakupan (yayasan, opsional satu PT) diatur Admin di menu Pengguna.
- Akun lama berperan 'Petugas data' otomatis menjadi 'Pengawas'.
- Akun terkunci 10 menit setelah 5 kali gagal; sesi berakhir setelah 30 menit tidak aktif.
- Menghapus `ews.db` juga menghapus akun pengguna dan log.

## Data contoh (sintetis)
- `data/Data_Sintetis_50_Yayasan.xlsx` dipakai sebagai data awal. Seluruh isinya rekaan dan konsisten (tanggal berurutan,
  jabatan sesuai jenis PT, NIK terisi). Sheet `_kasus_uji` mencatat pelanggaran yang sengaja disisipkan.
- Buat ulang/ubah: `python buat_data_sintetis.py keluaran.xlsx` (seed tetap, hasil selalu sama).
- `data/Contoh_Data_50_Yayasan.xlsx` adalah data contoh lama (banyak ketidakkonsistenan), disimpan hanya sebagai pembanding.
- Untuk mulai dari database kosong, jalankan skema `schema_postgres.sql` (PostgreSQL) dan isi lewat dashboard.

## Tindak lanjut
- Menu **Tindak Lanjut**: antrean temuan merah/kuning yang belum ditangani, buat tindak lanjut (penanggung jawab, tenggat), dan daftar tindak lanjut.
- Alur: Baru -> Sedang ditangani -> Menunggu verifikasi -> Ditutup. Petugas data sampai "Menunggu verifikasi"; hanya Admin yang menutup atau mengembalikan.
- Catatan wajib saat diajukan verifikasi dan saat ditutup. Menutup saat temuan masih muncul butuh konfirmasi eksplisit.
- Tenggat bawaan: 14 hari (merah), 30 hari (kuning); ubah di `tindak.py` (`SLA_HARI`).
- **Warna tidak berubah karena tindak lanjut.** Warna hanya berubah bila data diperbaiki.

## Alur pengawasan (versi kementerian)
1. **Pengajuan perubahan**: yayasan/PT mengubah atau menambah data lewat Portal. Perubahan *tidak langsung berlaku* dan *tidak mengubah warna*.
   Perubahan yang menyatakan dokumen "Ya" wajib dilampiri bukti (PDF/JPG/PNG, maks 5 MB, isi file dicek).
2. **Verifikasi**: pengawas melihat selisih data, lampiran, dan *dampak warna sebelum menyetujui*. Jika data berubah sejak diajukan, persetujuan ditolak (konflik).
3. **Tindak lanjut** per temuan: Verifikasi internal -> Menunggu tanggapan -> Evaluasi tanggapan -> Pembinaan/Teguran -> Eskalasi -> Selesai.
   Surat (nomor, tanggal, tenggat) dicatat. Catatan internal tidak terlihat yayasan/PT; hanya isi permintaan, surat, dan tanggapan yang terlihat.
   Pengawas sampai Pembinaan/Teguran; Eskalasi dan Selesai hanya Admin. Tahapan ini USULAN; sesuaikan dengan peraturan dan SOP resmi (`tindak.py`).
4. Pembatasan akses dipaksa di sisi server (cakupan data, kolom yang dikendalikan kementerian, hak lampiran), bukan hanya disembunyikan di tampilan.

## Catatan keamanan prototipe
- Lampiran disimpan di database dan belum dipindai virus. Produksi: penyimpanan objek + pemindai.
- Tidak ada pengingat otomatis (email/WA) saat tenggat lewat; hanya penanda "Terlambat" di dashboard.
- Pembatasan "penanggung jawab bukan Pengelola" dijaga aplikasi, belum di tingkat database.

## Reset ke data sintetis terbaru (uji coba)
`python siapkan_demo.py --ya` memindahkan `ews.db` lama menjadi cadangan, membuat database baru dari data sintetis,
dan membuat akun uji (admin, pengawas1, pembaca1, yayasan46, pt69) dengan password acak yang dicetak sekali. Jangan dipakai untuk data asli.

## Deploy di Streamlit Community Cloud (hanya data sintetis)
1. Unggah ISI folder `ews` (bukan ZIP-nya) ke repository GitHub **privat**. `.gitignore` sudah menjaga `ews.db` dan `secrets.toml` tidak ikut.
2. Di share.streamlit.io: Create app -> pilih repository, branch, **Main file path = `app.py`**, dan beri nama/URL berbeda dari aplikasi lama.
3. Advanced settings -> Secrets: salin dari `.streamlit/secrets.toml.example` dan GANTI passwordnya (admin_password, demo_password).
4. Setelah deploy, aplikasi membuat database dari data sintetis dan akun uji otomatis (mode demo). Batasi penonton lewat daftar email.
5. Catatan: file database di hosting gratis bisa kembali ke kondisi awal saat aplikasi restart/deploy ulang. Jangan dipakai untuk data asli.
