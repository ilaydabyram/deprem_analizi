"""Adım 2: kesik Gutenberg-Richter b-değeri (maksimum olabilirlik) ve grafik.

Girdi : veri/depremler_kumeli.csv  (önce 01_analiz.py çalışmalı)
Çıktı : sonuclar/b_kesik.json, grafikler/02_buyukluk_siklik.png

Fikir: Veri yalnızca 4.0–5.0 arasını içeriyor. Büyüklükleri 0.1'lik kutulara (4.0, 4.1, ... 4.9)
bölüp, her kutunun olasılığının 10^(-b·M) ile orantılı olduğunu varsayıyoruz. Olasılıkları
4.0–4.9 kutuları üzerinde normalize ettiğimiz için üst sınırın etkisi hesaba katılmış oluyor.
En olası b'yi gözlenen sayımlara en iyi uyan değer olarak buluyoruz.
5.0 kutusu atlanıyor, çünkü filtre 5.0'ın üstünü kestiği için o kutu yarım kalmış.

Çalıştırma (proje klasörünün içinden):  python kod/02_b_kesik.py
"""
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

matplotlib.use("Agg")
import matplotlib.pyplot as plt

KOK = Path(__file__).resolve().parent.parent
df = pd.read_csv(KOK / "veri" / "depremler_kumeli.csv", parse_dates=["Date"])

KUTULAR = np.round(np.arange(4.0, 5.0, 0.1), 1)   # 4.0 ... 4.9

def b_tahmin(magnitudler):
    m = np.round(np.asarray(magnitudler), 1)
    m = m[(m >= 4.0) & (m <= 4.95)]
    sayim = np.array([(m == k).sum() for k in KUTULAR])

    def eksi_loglik(b):
        w = 10 ** (-b * (KUTULAR - 4.0))
        p = w / w.sum()
        return -(sayim * np.log(p)).sum()

    return minimize_scalar(eksi_loglik, bounds=(0.1, 3), method="bounded").x, len(m)

rng = np.random.default_rng(1)   # sabit tohum: sonuçlar her çalıştırmada aynı çıkar

def bootstrap_aralik(magnitudler, tekrar=2000):
    m = np.asarray(magnitudler)
    b_dizisi = [b_tahmin(rng.choice(m, len(m)))[0] for _ in range(tekrar)]
    return np.percentile(b_dizisi, [2.5, 97.5])

gruplar = {
    "b_genel": df.Magnitude,
    "b_sindirgi": df[df.Il == "Balıkesir"].Magnitude,
    "b_diger": df[df.Il != "Balıkesir"].Magnitude,
    "b_kume_ici": df[df.Kume >= 0].Magnitude,
    "b_kume_disi": df[df.Kume < 0].Magnitude,
}
sonuc = {}
for ad, m in gruplar.items():
    b, n = b_tahmin(m)
    alt, ust = bootstrap_aralik(m)
    sonuc[ad] = {"b": round(b, 3), "n": n, "alt95": round(alt, 3), "ust95": round(ust, 3)}
    print(f"{ad:12s} b={b:.2f}  [{alt:.2f}–{ust:.2f}]  N={n}")

(KOK / "sonuclar" / "b_kesik.json").write_text(json.dumps(sonuc, indent=1), encoding="utf-8")

# ---- Grafik: gözlenen kümülatif sayım ve uyum eğrisi
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130})
b, n = b_tahmin(df.Magnitude)
w = 10 ** (-b * (KUTULAR - 4.0)); p = w / w.sum()
beklenen = n * p[::-1].cumsum()[::-1]                 # beklenen N(≥M)
gozlenen = [(np.round(df.Magnitude, 1) >= k - 1e-9).sum() for k in KUTULAR]

fig, ax = plt.subplots(figsize=(6.5, 4.5))
ax.semilogy(KUTULAR, gozlenen, "o", color="#2a6f97", label="Gözlenen (kümülatif, N≥M)")
g = sonuc["b_genel"]
ax.semilogy(KUTULAR, beklenen, "-", color="#c8553d",
            label=f"Kesik GR uyumu  b={g['b']:.2f} [{g['alt95']:.2f}–{g['ust95']:.2f}]")
ax.set_xlabel("Büyüklük (M)"); ax.set_ylabel("Deprem sayısı (N ≥ M)")
ax.set_title("Büyüklük-sıklık dağılımı", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(KOK / "grafikler" / "02_buyukluk_siklik.png"); plt.close()
