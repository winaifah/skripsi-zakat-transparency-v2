import sys
import pandas as pd
import numpy as np
import json
import re
import os
sys.path.insert(0, "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT/scripts")

PROJECT_ROOT = "/Users/arwinamrullah/Documents/SKRIPSI_ZAKAT"
CSV_INPUT    = f"{PROJECT_ROOT}/data/raw/bersedekah_NewPreprocessing.csv"
CSV_OUTPUT   = f"{PROJECT_ROOT}/data/processed/bersedekah_final2.csv"

# 29 kolom final + location (dipertahankan untuk NER)
FINAL_COLUMNS = [
    "no", "url", "slug", "platform", "scraped_at", "title", "organizer",
    "collected_amount", "collected_amount_detail", "target_amount", "profile_url", "organizer_description",
    "ind1_has_profile", "ind1_has_contact_direct", "ind1_has_legal",
    "ind2_has_mission", "ind2_word_count", "ind3_has_fund_report",
    "donor_count", "ind4_has_updates", "update_count",
    "ind5_has_disbursement", "disbursement_count",
    "ind6_has_admin_fee", "ind7_has_anonymity", "ind8_has_transaction_id",
    "total_indicators_detected", "campaign_story", "latest_news_json", "disbursement_json",
    "location",
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

RUPIAH = r'Rp\s?[\d.,]+'

DISBURSEMENT_KEYWORDS = re.compile(
    r'(pencairan\s+dana\s+sebesar\s+' + RUPIAH + r'|'
    r'cair\s+sebesar\s+' + RUPIAH + r'|'
    r'(telah\s+)?(tersalurkan|disalurkan|dicairkan)\s+sebesar\s+' + RUPIAH + r'|'
    + RUPIAH + r'\s*(telah\s+)?(tersalurkan|disalurkan|dicairkan)|'
    r'(realisasi|laporan)\s+penyaluran\s+.{0,30}?' + RUPIAH + r'|'
    r'penyaluran\s+dana\s+sebesar\s+' + RUPIAH + r'|'
    r'(penggunaan|alokasi)\s+dana\s+.{0,30}?' + RUPIAH + r')',
    re.IGNORECASE | re.DOTALL
)

def normalize_bool(val):
    if pd.isna(val):
        return False
    s = str(val).strip().lower()
    return s in ["true", "1", "yes"]

def clean_to_int(value):
    if pd.isna(value):
        return 0
    s = str(value).strip()
    if s == "" or s.lower() in ["nan", "n/a"]:
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

# Pattern untuk parsing collected_amount breakdown (Tunai/Cash, Transfer Bank, dll)
BLOCK_PATTERN = re.compile(
    r'Rp\s?([\d.]+)\s*([A-Za-z][A-Za-z /]*?)(?=Rp|\Z)'
)
RP_PATTERN = re.compile(r'Rp\s?([\d.]+)')

def parse_collected_amount(value):
    """
    Return (total_int, detail_structured_or_empty)
    Detail format: "Tunai / Cash: Rp 25.488.700; Transfer Bank: Rp 23.395.800"
    """
    if pd.isna(value):
        return 0, ""
    s = str(value).strip()
    if s == "" or s.lower() in ["nan", "n/a"]:
        return 0, ""
    if "belum ada transaksi" in s.lower():
        return 0, ""

    all_rp = RP_PATTERN.findall(s)
    if len(all_rp) == 0:
        cleaned = re.sub(r'[^\d]', '', s)
        return (int(cleaned), "") if cleaned else (0, "")
    if len(all_rp) == 1:
        return int(all_rp[0].replace(".", "")), ""

    blocks = BLOCK_PATTERN.findall(s)
    if not blocks:
        total = sum(int(m.replace(".", "")) for m in all_rp)
        return total, s

    detail_parts = []
    total = 0
    for amount_str, label in blocks:
        amount = int(amount_str.replace(".", ""))
        total += amount
        label_clean = label.strip()
        formatted_amount = f"Rp {amount:,}".replace(",", ".")
        if label_clean:
            detail_parts.append(f"{label_clean}: {formatted_amount}")
        else:
            detail_parts.append(formatted_amount)

    return total, "; ".join(detail_parts)

def resolve_file_ref(value, project_root, col_name, row_no):

    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith("FILE:"):
        rel_path = stripped[5:].strip()
        filepath = os.path.join(project_root, rel_path)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        else:
            print(f"  [WARNING] Row {row_no} | {col_name}: file tidak ditemukan -> {filepath}")
            return "[]"
    return stripped

def extract_disbursement_from_news(latest_news_val):
    if pd.isna(latest_news_val) or str(latest_news_val).strip() in ["", "[]", "nan", "INDUK", "N/A"]:
        return False, "no disbursement", 0

    raw = str(latest_news_val).strip()
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        return False, "no disbursement", 0

    if not isinstance(entries, list):
        return False, "no disbursement", 0

    disbursement_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        title   = str(entry.get("title", ""))
        content = str(entry.get("content", ""))
        if DISBURSEMENT_KEYWORDS.search(title) or DISBURSEMENT_KEYWORDS.search(content):
            disbursement_entries.append({
                "date"   : entry.get("date", ""),
                "title"  : title,
                "content": content,
            })

    if disbursement_entries:
        return True, json.dumps(disbursement_entries, ensure_ascii=False), len(disbursement_entries)
    return False, "no disbursement", 0

def main():
    print("=" * 60)
    print("PREPROCESSING - Bersedekah")
    print("=" * 60)

    # 1. Load
    print(f"\n[1] Load CSV...")
    df = pd.read_csv(CSV_INPUT, dtype=str)
    print(f"    -> {len(df)} baris, {len(df.columns)} kolom")
    print(f"    Kolom: {list(df.columns)}")

    # 2. Drop kolom tidak relevan
    print(f"\n[2] Drop kolom tidak relevan...")
    drop_cols = ["days_left", "template"]
    existing = [c for c in drop_cols if c in df.columns]
    if existing:
        df.drop(columns=existing, inplace=True)
        print(f"    -> Di-drop: {existing}")
    else:
        print(f"    -> Tidak ada yang perlu di-drop")

    if "location" in df.columns:
        print(f"    -> Kolom 'location' dipertahankan (untuk NER nanti)")
    else:
        print(f"    [WARNING] Kolom 'location' tidak ditemukan!")

    # 3. Duplikasi
    print(f"\n[3] Cek duplikasi...")
    dup_url = df[df.duplicated(subset=["url"], keep=False)]
    print(f"    Duplikat URL: {len(dup_url)} baris")
    if len(dup_url) > 0:
        print(dup_url[["no", "slug", "url"]].to_string(index=False))
        df.drop_duplicates(subset=["url"], keep="first", inplace=True)
        print(f"    -> Sisa: {len(df)} baris")
    else:
        print(f"    OK - Tidak ada duplikat")

    # 4. Resolve FILE: reference di latest_news_json
    print(f"\n[4] Resolve referensi FILE: di latest_news_json...")
    file_ref_count = df["latest_news_json"].str.startswith("FILE:", na=False).sum()
    print(f"    Ditemukan {file_ref_count} baris dengan FILE: reference")

    df["latest_news_json"] = [
        resolve_file_ref(v, PROJECT_ROOT, "latest_news_json", df.at[i, "no"])
        for i, v in df["latest_news_json"].items()
    ]

    sisa = df["latest_news_json"].str.startswith("FILE:", na=False).sum()
    print(f"    FILE: tersisa setelah resolve: {sisa}")

    induk_count = (df["latest_news_json"] == "INDUK").sum()
    if induk_count > 0:
        print(f"    Kampanye INDUK: {induk_count}")

    # 5. Normalisasi numerik -> integer
    print(f"\n[5] Normalisasi kolom numerik -> integer...")

    before = df["collected_amount"].head(3).tolist()
    results = df["collected_amount"].apply(parse_collected_amount)
    df["collected_amount"]        = results.apply(lambda x: x[0]).astype(int)
    df["collected_amount_detail"] = results.apply(lambda x: x[1])
    print(f"    collected_amount: {before} -> {df['collected_amount'].head(3).tolist()}")

    n_breakdown = (df["collected_amount_detail"].str.strip() != "").sum()
    n_zero      = (df["collected_amount"] == 0).sum()
    print(f"    Baris dengan format breakdown (multi-Rp) : {n_breakdown}")
    print(f"    Baris dengan collected_amount = 0        : {n_zero}")
    if n_breakdown > 0:
        print(f"\n    Sample breakdown:")
        sample = df[df["collected_amount_detail"].str.strip() != ""][
            ["no", "slug", "collected_amount", "collected_amount_detail"]
        ].head(5)
        for _, row in sample.iterrows():
            print(f"    [{row['no']}] {row['slug']}")
            print(f"        Total  : Rp {row['collected_amount']:,}".replace(",", "."))
            print(f"        Detail : {row['collected_amount_detail']}")

    before_target = df["target_amount"].head(3).tolist()
    df["target_amount"] = df["target_amount"].apply(clean_to_int)
    print(f"    target_amount: {before_target} -> {df['target_amount'].head(3).tolist()}")

    for col in INT_COLS:
        if col in df.columns:
            df[col] = df[col].apply(clean_to_int)
            print(f"    {col}: sample {df[col].head(3).tolist()}")

    # 6. Normalisasi boolean
    print(f"\n[6] Normalisasi boolean...")
    for col in BOOL_COLS:
        if col in df.columns:
            df[col] = df[col].apply(normalize_bool)
    print(f"    OK - distandarisasi (ind1_has_contact_direct & ind8_has_transaction_id TIDAK diubah nilainya)")

    # 7. Deteksi disbursement dari latest_news_json
    print(f"\n[7] Deteksi disbursement dari latest_news_json...")
    results = df["latest_news_json"].apply(extract_disbursement_from_news)
    df["ind5_has_disbursement"] = results.apply(lambda x: x[0])
    df["disbursement_json"]     = results.apply(lambda x: x[1])
    df["disbursement_count"]    = results.apply(lambda x: x[2])

    disb_true = df["ind5_has_disbursement"].sum()
    print(f"    Kampanye dengan disbursement terdeteksi: {disb_true}")
    print(f"    Total entry disbursement: {df['disbursement_count'].sum()}")
    if disb_true > 0:
        print(f"\n    Sample kampanye dengan disbursement:")
        sample = df[df["ind5_has_disbursement"]][["no", "slug", "disbursement_count"]].head(5)
        print(sample.to_string(index=False))

    # 8. Terapkan ind1_has_legal dari deteksi kontekstual tiga lapis 
    print(f"\n[8a] Muat ind1_has_legal dari deteksi kontekstual tiga lapis...")
    _ctx = pd.read_csv(
        f"{PROJECT_ROOT}/data/processed/bersedekah_final2_legal_context.csv",
        dtype=str, usecols=["no", "ind1_has_legal"]
    ).fillna("")
    _legal_map = dict(zip(_ctx["no"], _ctx["ind1_has_legal"].str.lower() == "true"))
    df["ind1_has_legal"] = df["no"].map(_legal_map).fillna(False).astype(bool)
    print(f"    ind1_has_legal True  : {df['ind1_has_legal'].sum()}")

    # 8b. Hitung ulang total_indicators_detected
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
    inkon_updates  = df[(df["ind4_has_updates"] == True) & (df["update_count"] == 0)]
    inkon_updates2 = df[(df["ind4_has_updates"] == False) & (df["update_count"] > 0)]
    inkon_disb     = df[(df["ind5_has_disbursement"] == True) & (df["disbursement_count"] == 0)]
    inkon_disb2    = df[(df["ind5_has_disbursement"] == False) & (df["disbursement_count"] > 0)]

    print(f"    ind4=True tapi update_count=0       : {len(inkon_updates)} baris")
    print(f"    ind4=False tapi update_count>0      : {len(inkon_updates2)} baris")
    print(f"    ind5=True tapi disbursement_count=0 : {len(inkon_disb)} baris")
    print(f"    ind5=False tapi disbursement_count>0: {len(inkon_disb2)} baris")

    for name, subset, col in [
        ("ind4=True/update=0", inkon_updates, "update_count"),
        ("ind4=False/update>0", inkon_updates2, "update_count"),
        ("ind5=True/disb=0", inkon_disb, "disbursement_count"),
        ("ind5=False/disb>0", inkon_disb2, "disbursement_count"),
    ]:
        if len(subset) > 0:
            print(f"\n    Detail {name}:")
            print(subset[["no", "slug", col]].head(5).to_string(index=False))

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

    # 11. Missing values
    print(f"\n[11] Missing values:")
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    if len(missing) == 0:
        print("     OK - Tidak ada missing values")
    else:
        for col, count in missing.items():
            print(f"     {col}: {count} ({count/len(df)*100:.1f}%)")

    # 12. Sesuaikan kolom 
    print(f"\n[12] Sesuaikan urutan kolom (29 final + location)...")
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
            print(f"     -> Kolom baru ditambahkan (kosong): {col}")
    extra_cols = [c for c in df.columns if c not in FINAL_COLUMNS]
    if extra_cols:
        print(f"     -> Kolom ekstra di-drop: {extra_cols}")
    df = df[FINAL_COLUMNS]
    print(f"     OK - Kolom final: {len(df.columns)} kolom")

    # 13. Simpan
    print(f"\n[13] Simpan ke: {CSV_OUTPUT}")
    df.to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"     OK - Selesai! {len(df)} baris, {len(df.columns)} kolom tersimpan.")

    print("\n" + "=" * 60)
    print("PREPROCESSING BERSEDEKAH SELESAI -> bersedekah_final.csv")
    print("=" * 60)

if __name__ == "__main__":
    main()