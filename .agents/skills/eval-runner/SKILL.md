---
name: eval-runner
description: Cara menjalankan eval, membaca gold label YAML di eval/gold, dan melaporkan agreement, stabilitas, tingkat ungrounded, dan akurasi struktur JD. Gunakan setelah mengubah prompt, model, atau scoring.
disable-model-invocation: true
---

# Eval runner

1. Jalankan CLI eval dan simpan laporan bersama hash prompt bundle.
2. Bandingkan dengan hasil terakhir; agreement tidak boleh turun lebih dari 2 poin persen.
3. Laporkan hasil apa adanya, termasuk yang gagal.
