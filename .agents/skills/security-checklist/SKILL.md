---
name: security-checklist
description: Daftar kontrol keamanan untuk setiap fitur baru: injection di teks JD, redaksi data pribadi, host blocklist LinkedIn, validasi upload, penyimpanan rahasia, dan log. Gunakan sebelum menyatakan fitur selesai.
---

# Security checklist

- LLM yang membaca JD atau email tidak diberi tool.
- Data pribadi diredaksi sebelum dikirim ke LLM.
- Semua HTTP lewat klien dengan blocklist host (termasuk linkedin.com).
- Upload dibatasi ukuran dan tipe, di-parse di subprocess dengan timeout.
- Tidak ada rahasia di repo atau log. Tidak ada teks CV atau JD di log.
