import sys
import pandas as pd
import numpy as np
import re
sys.path.insert(0, "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT/scripts")

CSV_INPUT  = "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT/data/raw/amalsholeh_NewPreprocessing.csv"
CSV_OUTPUT = "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT/data/processed/amalsholeh_final2.csv"

FINAL_COLUMNS = [
    "no", "url", "slug", "platform", "scraped_at", "title", "organizer",
    "collected_amount", "target_amount", "profile_url", "organizer_description",
    "ind1_has_profile", "ind1_has_contact_direct", "ind1_has_legal",
    "ind2_has_mission", "ind2_word_count", "ind3_has_fund_report",
    "donor_count", "ind4_has_updates", "update_count",
    "ind5_has_disbursement", "disbursement_count",
    "ind6_has_admin_fee", "ind7_has_anonymity", "ind8_has_transaction_id",
    "total_indicators_detected", "campaign_story", "latest_news_json", "disbursement_json"
]

BOOL_COLS = [
    "ind1_has_profile", "ind1_has_contact_direct", "ind1_has_legal",
    "ind2_has_mission", "ind3_has_fund_report", "ind4_has_updates",
    "ind5_has_disbursement", "ind6_has_admin_fee",
    "ind7_has_anonymity", "ind8_has_transaction_id",
]

INT_COLS = [
    "donor_count", "update_count", "disbursement_count",
    "total_indicators_detected", "ind2_word_count",
]

def normalize_bool(val):
    if pd.isna(val):
        return False
    s = str(val).strip().lower()
    return s in ["true", "1", "yes"]

def clean_to_int(value):
    if pd.isna(value):
        return 0
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return 0
    s = s.replace("Rp", "").replace(" ", "")

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s and "." not in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
            s = s.replace(".", "")

    try:
        return int(float(s))
    except:
        return 0

def main():
    print("=" * 60)
    print("PREPROCESSING - Amalsholeh")
    print("=" * 60)

    # 1. Load
    print(f"\n[1] Load CSV...")
    df = pd.read_csv(CSV_INPUT, dtype=str)
    print(f"    → {len(df)} baris, {len(df.columns)} kolom")
    print(f"    Kolom: {list(df.columns)}")

    # 2. Drop kolom tidak relevan
    print(f"\n[2] Drop kolom tidak relevan...")
    drop_cols = ["days_left", "template"]
    existing = [c for c in drop_cols if c in df.columns]
    if existing:
        df.drop(columns=existing, inplace=True)
        print(f"    → Di-drop: {existing}")
    else:
        print(f"    → Tidak ada yang perlu di-drop")

    # 3. Duplikasi
    print(f"\n[3] Cek duplikasi...")
    dup_url = df[df.duplicated(subset=["url"], keep=False)]
    print(f"    Duplikat URL: {len(dup_url)} baris")
    if len(dup_url) > 0:
        print(dup_url[["no", "slug", "url"]].to_string(index=False))
        df.drop_duplicates(subset=["url"], keep="first", inplace=True)
        print(f"    → Sisa: {len(df)} baris")
    else:
        print(f"    ✓ Tidak ada duplikat")

    # 4. Normalisasi collected_amount ke integer
    print(f"\n[4] Normalisasi collected_amount → integer...")
    before = df["collected_amount"].dropna().head(3).tolist()
    df["collected_amount"] = df["collected_amount"].apply(clean_to_int)
    print(f"    Sebelum : {before}")
    print(f"    Sesudah : {df['collected_amount'].head(3).tolist()}")

    # 5. Normalisasi kolom count ke integer
    print(f"\n[5] Normalisasi kolom count → integer...")
    for col in INT_COLS:
        if col in df.columns:
            df[col] = df[col].apply(clean_to_int)
            print(f"    {col}: sample {df[col].head(3).tolist()}")

    # 6. Normalisasi boolean
    print(f"\n[6] Normalisasi boolean...")
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].apply(normalize_bool)
    print(f"    ✓ Semua kolom boolean distandarisasi")

    # 7. Fix ind8_has_transaction_id → semua True
    print(f"\n[7] Fix ind8_has_transaction_id → semua True...")
    df["ind8_has_transaction_id"] = True
    print(f"    ✓ Semua {len(df)} baris diset True")

    # 8. Terapkan ind1_has_legal dari deteksi kontekstual tiga lapis (dokumen berbeda)
    print(f"\n[8a] Muat ind1_has_legal dari deteksi kontekstual tiga lapis...")
    _ctx = pd.read_csv(
        "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT/data/processed/amalsholeh_final3_legal_context.csv",
        dtype=str, usecols=["slug", "ind1_has_legal"]
    ).fillna("")
    _legal_map = dict(zip(_ctx["slug"], _ctx["ind1_has_legal"].str.lower() == "true"))
    df["ind1_has_legal"] = df["slug"].map(_legal_map).fillna(False).astype(bool)
    print(f"    ind1_has_legal True  : {df['ind1_has_legal'].sum()}")

    # 8b. Hitung ulang ind1_combined & total_indicators_detected
    print(f"\n[8b] Hitung ulang total_indicators_detected...")
    df["ind1_combined"] = (
        df["ind1_has_profile"] |
        df["ind1_has_contact_direct"] |
        df["ind1_has_legal"]
    )
    ind_cols_main = [
        "ind1_combined", "ind2_has_mission", "ind3_has_fund_report",
        "ind4_has_updates", "ind5_has_disbursement", "ind6_has_admin_fee",
        "ind7_has_anonymity", "ind8_has_transaction_id",
    ]
    old_total = df["total_indicators_detected"].copy()
    df["total_indicators_detected"] = df[ind_cols_main].sum(axis=1).astype(int)
    df.drop(columns=["ind1_combined"], inplace=True)

    changed = (old_total != df["total_indicators_detected"]).sum()
    print(f"    Baris yang berubah dari nilai sebelumnya: {changed}")
    print(f"    Distribusi total_indicators_detected:")
    print(df["total_indicators_detected"].value_counts().sort_index().to_string())

    # 9. Validasi konsistensi
    print(f"\n[9] Validasi konsistensi...")
    inkon_updates = df[(df["ind4_has_updates"] == True) & (df["update_count"] == 0)]
    inkon_disb    = df[(df["ind5_has_disbursement"] == True) & (df["disbursement_count"] == 0)]
    inkon_updates2 = df[(df["ind4_has_updates"] == False) & (df["update_count"] > 0)]
    inkon_disb2    = df[(df["ind5_has_disbursement"] == False) & (df["disbursement_count"] > 0)]

    print(f"    ind4=True tapi update_count=0       : {len(inkon_updates)} baris")
    print(f"    ind5=True tapi disbursement_count=0 : {len(inkon_disb)} baris")
    print(f"    ind4=False tapi update_count>0      : {len(inkon_updates2)} baris")
    print(f"    ind5=False tapi disbursement_count>0: {len(inkon_disb2)} baris")

    for name, subset in [("ind4=True/update=0", inkon_updates), ("ind5=True/disb=0", inkon_disb),
                          ("ind4=False/update>0", inkon_updates2), ("ind5=False/disb>0", inkon_disb2)]:
        if len(subset) > 0:
            print(f"\n    Detail {name}:")
            cols_show = ["no", "slug"] + (["update_count"] if "update" in name else ["disbursement_count"])
            print(subset[cols_show].head(5).to_string(index=False))

    # 10. Distribusi indikator
    print(f"\n[10] Distribusi per indikator ({len(df)} kampanye):")
    indikator_labels = {
        "ind1_has_profile"        : "Ind1a - Has Profile",
        "ind1_has_contact_direct" : "Ind1b - Has Contact",
        "ind1_has_legal"          : "Ind1c - Has Legal",
        "ind2_has_mission"        : "Ind2  - Misi dan Tujuan",
        "ind3_has_fund_report"    : "Ind3  - Laporan Dana",
        "ind4_has_updates"        : "Ind4  - Pembaruan",
        "ind5_has_disbursement"   : "Ind5  - Penyaluran Dana",
        "ind6_has_admin_fee"      : "Ind6  - Biaya Admin",
        "ind7_has_anonymity"      : "Ind7  - Anonimitas",
        "ind8_has_transaction_id" : "Ind8  - Nomor Transaksi",
    }
    for col, label in indikator_labels.items():
        if col in df.columns:
            t = df[col].sum()
            pct = t / len(df) * 100
            print(f"    {label}: True={t} ({pct:.1f}%)")

    # 11. Cek missing values
    print(f"\n[11] Missing values:")
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    if len(missing) == 0:
        print("     ✓ Tidak ada missing values")
    else:
        for col, count in missing.items():
            print(f"     {col}: {count} ({count/len(df)*100:.1f}%)")

    # 12. Pastikan urutan kolom sesuai final
    print(f"\n[12] Sesuaikan urutan kolom...")
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
            print(f"     → Kolom baru ditambahkan (kosong): {col}")
    extra_cols = [c for c in df.columns if c not in FINAL_COLUMNS]
    if extra_cols:
        print(f"     → Kolom ekstra di-drop: {extra_cols}")
    df = df[FINAL_COLUMNS]
    print(f"     ✓ Kolom final: {len(df.columns)} kolom")

    # 13. Simpan
    print(f"\n[13] Simpan ke: {CSV_OUTPUT}")
    df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"     ✓ Selesai! {len(df)} baris, {len(df.columns)} kolom tersimpan.")

    print("\n" + "=" * 60)
    print("PREPROCESSING AMALSHOLEH SELESAI → amalsholeh_final.csv")
    print("=" * 60)

if __name__ == "__main__":
    main()
