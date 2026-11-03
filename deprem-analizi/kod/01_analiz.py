"""Adım 1: keşifsel analiz, DBSCAN kümeleme ve grafikler.

Girdi : veri/depremler_temiz.csv
Çıktı : veri/depremler_kumeli.csv, sonuclar/kume_ozeti.csv, sonuclar/sonuclar.json,
        grafikler/*.png

Çalıştırma (proje klasörünün içinden):  python kod/01_analiz.py
"""
import json
import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.cluster import DBSCAN

matplotlib.use("Agg")
import matplotlib.pyplot as plt

KOK = Path(__file__).resolve().parent.parent
df = (pd.read_csv(KOK / "veri" / "depremler_temiz.csv", parse_dates=["Date"])
        .sort_values("Date").reset_index(drop=True))

# ---------------------------------------------------------------- bölge bilgisi
# "Sındırgı (Balıkesir)" -> il = Balıkesir; "Ege Denizi - [165 km] Datça (Muğla)" -> deniz = Ege Denizi
def il_bul(yer):
    m = re.search(r"\(([^)]+)\)\s*$", yer)
    return m.group(1) if m else "Açık deniz"

def deniz_bul(yer):
    for ad in ["Ege Denizi", "Akdeniz", "Marmara Denizi"]:
        if yer.startswith(ad):
            return ad
    return None

df["Il"] = df.Location.map(il_bul)
df["Deniz"] = df.Location.map(deniz_bul)
df["Ilce"] = df.Location.str.replace(r"\s*\([^)]*\)\s*$", "", regex=True)
df["Ay"] = df.Date.dt.to_period("M")

R = {}
R["n"] = len(df)
R["tarih_min"], R["tarih_max"] = str(df.Date.min()), str(df.Date.max())
R["deniz_n"] = int(df.Deniz.notna().sum())
R["il_top10"] = df[df.Deniz.isna()].Il.value_counts().head(10).to_dict()
R["deniz_say"] = df.Deniz.value_counts().to_dict()
R["tip"] = df.Type.value_counts().to_dict()

# ---------------------------------------------------------------- derinlik ve veri kalitesi
R["depth_med"] = float(df.Depth.median())
R["depth_q10_q90"] = df.Depth.quantile([.1, .9]).tolist()
R["depth_tam_7km"] = int((df.Depth == 7).sum())   # AFAD'ın sabit varsayılan derinliği olabilir
R["depth_gt30"] = df[df.Depth > 30][["Date", "Location", "Depth", "Magnitude"]].astype(str).values.tolist()
R["rms_gt2"] = df[df.Rms > 2][["Date", "Location", "Depth", "Rms", "Magnitude"]].astype(str).values.tolist()
R["spearman_depth_mag"] = list(spearmanr(df.Depth, df.Magnitude))

# ---------------------------------------------------------------- zamansal dağılım
aylik = df.groupby("Ay").size()
R["aylik"] = {str(k): int(v) for k, v in aylik.items()}
R["ay_ort"], R["ay_med"] = float(aylik.mean()), float(aylik.median())
gun = df.groupby(df.Date.dt.date).size()
R["en_yogun_gunler"] = {str(k): int(v) for k, v in gun.sort_values(ascending=False).head(5).items()}

# ---------------------------------------------------------------- DBSCAN
# haversine: yeryüzü eğriliğini hesaba katan uzaklık. eps radyan ister, bu yüzden km / 6371.
def kumele(eps_km, min_ornek):
    X = np.radians(df[["Latitude", "Longitude"]].values)
    return DBSCAN(eps=eps_km / 6371.0, min_samples=min_ornek, metric="haversine").fit_predict(X)

EPS_KM, MIN_ORNEK = 25, 5
df["Kume"] = kumele(EPS_KM, MIN_ORNEK)           # -1 = hiçbir kümeye ait değil
R["kume_sayisi"] = int(df.Kume.max() + 1)
R["kume_disi"] = int((df.Kume == -1).sum())
R["kume_payi"] = float((df.Kume >= 0).mean())

ozet = []
for k in sorted(set(df.Kume) - {-1}):
    g = df[df.Kume == k]
    ozet.append(dict(kume=int(k), n=len(g), lat=g.Latitude.mean(), lon=g.Longitude.mean(),
                     il=g.Il.value_counts().index[0], ilce=g.Ilce.value_counts().index[0],
                     basla=str(g.Date.min().date()), bitis=str(g.Date.max().date()),
                     sure_gun=(g.Date.max() - g.Date.min()).days,
                     mmax=g.Magnitude.max(), mort=g.Magnitude.mean(), depth_med=g.Depth.median()))
K = pd.DataFrame(ozet).sort_values("n", ascending=False).reset_index(drop=True)
R["kumeler"] = K.round(3).to_dict("records")

# Duyarlılık: parametreleri değiştirince sonuç ne kadar değişiyor?
CEKIRDEKLER = {"Sındırgı": (39.196, 28.187), "Simav": (39.23, 28.969), "Marmara": (40.84, 28.269),
               "Adana": (37.769, 36.119), "Malatya": (38.289, 38.689)}
def km(lat, lon, a, b):
    return 6371 * np.hypot(np.radians(lat - a), np.radians(lon - b) * np.cos(np.radians(a)))

duy = {}
for eps in [15, 25, 40]:
    for mn in [4, 5, 8]:
        etiket = kumele(eps, mn)
        kayit = {"kume_sayisi": int(etiket.max() + 1), "kume_disi": int((etiket == -1).sum())}
        for ad, (a, b) in CEKIRDEKLER.items():   # çekirdeğe 15 km içindeki depremler kümede mi?
            yakin = etiket[km(df.Latitude, df.Longitude, a, b) < 15]
            kayit[ad] = bool((yakin >= 0).all())
        duy[f"eps{eps}_min{mn}"] = kayit
R["duyarlilik"] = duy

# ---------------------------------------------------------------- klasik b-değeri (karşılaştırma için)
# Aki-Utsu formülü üst sınır olmadığını varsayar. Verimiz 5.0'da kesik olduğu için
# bu değer yukarı sapar. Doğru tahmin 02_b_kesik.py içinde.
def aki_utsu(m, mc=4.0, dm=0.1):
    m = np.asarray(m)
    m = m[m >= mc]
    b = np.log10(np.e) / (m.mean() - (mc - dm / 2))
    return b, b / np.sqrt(len(m)), len(m)
R["b_klasik_aki_utsu"] = aki_utsu(df.Magnitude)

# ---------------------------------------------------------------- kaydet
df.to_csv(KOK / "veri" / "depremler_kumeli.csv", index=False)
K.to_csv(KOK / "sonuclar" / "kume_ozeti.csv", index=False)
(KOK / "sonuclar" / "sonuclar.json").write_text(
    json.dumps(R, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

# ================================================================= GRAFİKLER
G = KOK / "grafikler"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130})
MAVI, KIRMIZI, GRI = "#2a6f97", "#c8553d", "#9aa5b1"

# 1) Aylık sayım
fig, ax = plt.subplots(figsize=(10, 4))
a = aylik.reindex(pd.period_range(aylik.index.min(), aylik.index.max(), freq="M"), fill_value=0)
ax.bar(a.index.astype(str), a.values, color=MAVI)
ax.set_title("Aylık deprem sayısı (M 4.0–5.0)", loc="left", fontweight="bold")
ax.set_ylabel("Deprem sayısı")
plt.xticks(rotation=60, ha="right")
fig.tight_layout(); fig.savefig(G / "01_aylik_sayim.png"); plt.close()

# 3) Harita: kümeler (nokta boyutu büyüklükle orantılı)
fig, ax = plt.subplots(figsize=(11, 5.2))
disi = df[df.Kume < 0]
ax.scatter(disi.Longitude, disi.Latitude, s=(disi.Magnitude - 3.5) ** 2 * 30, c=GRI, alpha=.6,
           edgecolor="none", label=f"Küme dışı ({len(disi)})")
renkler = ["#c8553d", "#2a6f97", "#6a994e", "#8e5ba6", "#d98c1f", "#3b9ba8", "#a0522d", "#555555"]
for i, satir in K.iterrows():
    g = df[df.Kume == satir.kume]
    ax.scatter(g.Longitude, g.Latitude, s=(g.Magnitude - 3.5) ** 2 * 30, c=renkler[i % len(renkler)],
               alpha=.8, edgecolor="white", linewidth=.4, label=f"{satir.il} ({satir.n})")
ax.set_xlim(24.5, 45); ax.set_ylim(34, 42.5); ax.set_aspect(1.25)
ax.set_xlabel("Boylam"); ax.set_ylabel("Enlem")
ax.set_title("Depremlerin konumu ve DBSCAN kümeleri (nokta boyutu ∝ büyüklük)", loc="left", fontweight="bold")
ax.legend(frameon=False, fontsize=8.5, ncol=2, loc="lower right")
fig.tight_layout(); fig.savefig(G / "03_harita_kumeler.png"); plt.close()

# 4) İl bazında sayım
fig, ax = plt.subplots(figsize=(7, 5))
t = df[df.Deniz.isna()].Il.value_counts().head(10)[::-1]
ax.barh(t.index, t.values, color=MAVI)
ax.set_title("En çok deprem olan 10 il (kara)", loc="left", fontweight="bold")
ax.set_xlabel("Deprem sayısı")
fig.tight_layout(); fig.savefig(G / "04_il_sayim.png"); plt.close()

# 5) Derinlik
fig, axs = plt.subplots(1, 2, figsize=(11, 4))
axs[0].hist(df.Depth[df.Depth < 45], bins=30, color=MAVI)
axs[0].set_title("Derinlik dağılımı (<45 km)", loc="left", fontweight="bold")
axs[0].set_xlabel("Derinlik (km)"); axs[0].set_ylabel("Deprem sayısı")
axs[1].scatter(df.Depth, df.Magnitude, s=14, c=MAVI, alpha=.6); axs[1].set_xscale("log")
axs[1].set_xlabel("Derinlik (km, log)"); axs[1].set_ylabel("Büyüklük")
axs[1].set_title("Derinlik ve büyüklük", loc="left", fontweight="bold")
fig.tight_layout(); fig.savefig(G / "05_derinlik.png"); plt.close()

# 6) En büyük kümenin zaman çizgisi
g = df[df.Kume == K.kume.iloc[0]]
fig, ax = plt.subplots(figsize=(10, 3.8))
ax.scatter(g.Date, g.Magnitude, s=(g.Magnitude - 3.5) ** 2 * 40, c=KIRMIZI, alpha=.7)
ax.set_title(f"En büyük küme: {g.Ilce.value_counts().index[0]} ({len(g)} deprem) zaman çizgisi",
             loc="left", fontweight="bold")
ax.set_ylabel("Büyüklük")
fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(G / "06_en_buyuk_kume_zaman.png"); plt.close()

print(f"{R['kume_sayisi']} küme, küme payı %{R['kume_payi']*100:.0f}; çıktılar yazıldı.")
