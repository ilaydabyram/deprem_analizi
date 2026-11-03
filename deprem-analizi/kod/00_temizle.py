"""Adım 0: AFAD'dan indirilen ham dosyayı okunabilir bir tabloya çevirir.

Ham dosyada her satır tek bir tırnak içine sarılmış, bu yüzden pandas tüm satırı
tek sütun sanıyor. Burada tırnakları açıp sütunları ayırıyoruz, sonra tarih ve
sayı türlerini düzeltiyoruz.

Çalıştırma (proje klasörünün içinden):  python kod/00_temizle.py
"""
import csv
from pathlib import Path

import pandas as pd

KOK = Path(__file__).resolve().parent.parent  # proje klasörü
HAM = KOK / "veri" / "afad_ham.csv"
CIKTI = KOK / "veri" / "depremler_temiz.csv"

# utf-8-sig: dosyanın başındaki görünmez BOM karakterini atar
satirlar = HAM.read_text(encoding="utf-8-sig").splitlines()
baslik = satirlar[0].split(",")

kayitlar = []
for satir in satirlar[1:]:
    if not satir.strip():
        continue
    # Satırı saran dış tırnağı kaldır, içteki çift tırnakları ("") tekle indir
    if satir.startswith('"') and satir.endswith('"'):
        satir = satir[1:-1].replace('""', '"')
    alanlar = next(csv.reader([satir]))
    if len(alanlar) != len(baslik):
        raise ValueError(f"Beklenmeyen sütun sayısı: {alanlar}")
    kayitlar.append(alanlar)

df = pd.DataFrame(kayitlar, columns=baslik)

for sutun in ["Longitude", "Latitude", "Depth", "Rms", "Magnitude", "EventID"]:
    df[sutun] = pd.to_numeric(df[sutun], errors="raise")
df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y %H:%M:%S", errors="raise")

# Basit kalite kontrolleri
assert df.isna().sum().sum() == 0, "Eksik değer var"
assert not df["EventID"].duplicated().any(), "Tekrar eden olay var"

df.to_csv(CIKTI, index=False)
print(f"{len(df)} kayıt yazıldı: {CIKTI.name}  ({df.Date.min()} – {df.Date.max()})")
