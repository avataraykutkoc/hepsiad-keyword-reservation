import streamlit as st
import pandas as pd
import os
import tempfile
import requests
import subprocess
import re
from google.cloud import bigquery
from google.oauth2 import service_account

# --- Streamlit Sayfa Yapılandırması ---
st.set_page_config(
    page_title="HepsiAd Video QC & BigQuery Laboratuvarı",
    page_icon="🎬",
    layout="wide"
)

# --- TRANSFER.SH YÜKLEME ---
def upload_to_transfer_sh(file_path):
    try:
        with open(file_path, 'rb') as f:
            file_name = os.path.basename(file_path)
            response = requests.put(f'https://transfer.sh/{file_name}', data=f)
            if response.status_code == 200:
                return response.text.strip()
    except Exception:
        return None
    return None

# --- FFMPEG İŞLEME VE ANALİZ ---
def process_video_ffmpeg(input_path, output_path, target_lufs=-23.0, crf=24):
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-af", f"loudnorm=I={target_lufs}:LRA=11:TP=-1.5",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, res.stderr
    except Exception as e:
        return False, str(e)

def analyze_video_ffmpeg(video_path):
    lufs_val = -23.0
    has_letterbox = "Yok (%0)"
    try:
        cmd = ["ffmpeg", "-i", video_path, "-af", "ebur128=peak=true", "-f", "null", "-"]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        matches = re.findall(r"I:\s+(-?\d+\.\d+)\s+LUFS", res.stderr)
        if matches:
            lufs_val = float(matches[-1])
    except Exception:
        pass

    try:
        cmd_crop = ["ffmpeg", "-i", video_path, "-vf", "cropdetect=24:16:0", "-vframes", "30", "-f", "null", "-"]
        res_crop = subprocess.run(cmd_crop, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        crops = re.findall(r"crop=(\d+:\d+:\d+:\d+)", res_crop.stderr)
        if crops:
            w, h, x, y = map(int, crops[-1].split(":"))
            if y > 10:
                has_letterbox = f"Var (Siyah Bant: {y}px)"
    except Exception:
        pass
        
    return lufs_val, has_letterbox

# --- BIGQUERY CANLI VERİ ÇEKME FONKSİYONU ---
@st.cache_data(ttl=1800) # Veriyi 30 dk önbellekte tutar
def fetch_bigquery_data():
    try:
        if "gcp_service_account" in st.secrets:
            creds = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
            client = bigquery.Client(credentials=creds, project="hb-dataanalytics-prod")
        else:
            client = bigquery.Client(project="hb-dataanalytics-prod")

        query = """
        SELECT 
            hunt_week AS haftalik_tarih,
            segment AS segment_adi,
            SUM(SAFE_CAST(listed_merchant_count AS INT64)) AS toplam_listelenen_merchant,
            SUM(SAFE_CAST(hitted_merchant_count AS INT64)) AS toplam_etkilesim_alan_merchant,
            SUM(SAFE_CAST(hunt_clicked_merchant_count AS INT64)) AS toplam_tiklama
        FROM 
            `hb-dataanalytics-prod.mp_campaign.hunt_business_report_weekly`
        GROUP BY 
            1, 2
        ORDER BY 
            1 DESC;
        """
        df = client.query(query).to_dataframe()
        return df, None
    except Exception as e:
        return None, str(e)

# --- HEADER / KÜNYE ---
st.markdown(
    """
    <div style="display: flex; justify-content: center; margin-bottom: 10px;">
        <div style="background-color: #1e1e2e; padding: 10px 18px; border-radius: 12px; border: 1.5px solid #00d2ff; text-align: center;">
            <span style="color: #a6adc8; font-size: 14px; font-weight: bold;">👨‍💻 Creator:</span> 
            <span style="color: #00d2ff; font-size: 16px; font-weight: bold;">Aykut Koç</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

st.title("🎬 HepsiAd - Video Standartlaştırma & BigQuery Analiz Portalı")

# TAB'LAR (SEKMELER)
tab1, tab2, tab3 = st.tabs([
    "📁 Doğrudan Video Normalizasyonu", 
    "📊 BigQuery P1 Merchant Paneli", 
    "🔗 VAST Tag Analizi"
])

# SEKMELER 1: VİDEO NORMALİZASYON
with tab1:
    st.subheader("🛠️ Ses Normalizasyonu (-23 LUFS) ve İşleme")
    uploaded_file = st.file_uploader("İşlenecek Video (MP4/MOV):", type=["mp4", "mov", "mkv"])
    
    if uploaded_file is not None:
        orig_size_mb = uploaded_file.size / (1024 * 1024)
        st.info(f"Yüklenen Dosya Boyutu: {orig_size_mb:.2f} MB")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_in:
            tmp_in.write(uploaded_file.read())
            input_path = tmp_in.name
            
        output_path = input_path.replace(".mp4", "_normalized.mp4")
        
        status_text.markdown("**🔊 Orijinal ses analiz ediliyor... (%30)**")
        progress_bar.progress(30)
        orig_lufs, letterbox_val = analyze_video_ffmpeg(input_path)
        
        status_text.markdown(f"**🔊 -23 LUFS Ses Normalizasyonu Yapılıyor... (%70)**")
        progress_bar.progress(70)
        
        success, _ = process_video_ffmpeg(input_path, output_path, target_lufs=-23.0)
        
        if success and os.path.exists(output_path):
            new_lufs, _ = analyze_video_ffmpeg(output_path)
            new_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            progress_bar.progress(100)
            status_text.markdown("**✅ İşlem Tamamlandı! (%100)**")
            
            st.success(f"✅ Ses Normalleştirildi! {orig_lufs:.2f} LUFS ➡️ {new_lufs:.2f} LUFS")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("İşlenmiş Ses", f"{new_lufs:.2f} LUFS")
            col2.metric("Orijinal Ses", f"{orig_lufs:.2f} LUFS")
            col3.metric("Siyah Bant", letterbox_val)
            
            with open(output_path, "rb") as f:
                st.download_button(
                    label=f"💾 İndir ({new_size_mb:.1f} MB)",
                    data=f,
                    file_name=f"normalized_{uploaded_file.name}",
                    mime="video/mp4"
                )

# SEKMELER 2: BIGQUERY P1 CANLI PANELİ
with tab2:
    st.subheader("📈 BigQuery Canlı Merchant & Kampanya Analizi (P1)")
    
    if st.button("🔄 Verileri Şimdi Yenile"):
        st.cache_data.clear()
        
    with st.spinner("hb-dataanalytics-prod BigQuery ortamından canlı veriler çekiliyor..."):
        df_bq, err = fetch_bigquery_data()
        
    if err:
        st.error(f"BigQuery Bağlantı Hatası: {err}")
    elif df_bq is not None and not df_bq.empty:
        st.success("✅ BigQuery Canlı Bağlantısı Aktif!")
        
        # Üst KPI Kartları
        total_list = df_bq["toplam_listelenen_merchant"].sum()
        total_hit = df_bq["toplam_etkilesim_alan_merchant"].sum()
        total_click = df_bq["toplam_tiklama"].sum()
        
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.metric("Toplam Listelenen Merchant", f"{total_list:,.0f}")
        m_col2.metric("Toplam Etkileşim Alan Merchant", f"{total_hit:,.0f}")
        m_col3.metric("Toplam Tıklama Sayısı", f"{total_click:,.0f}")
        
        st.markdown("---")
        
        # Filtreleme & Tablo
        segments = ["Tümü"] + list(df_bq["segment_adi"].dropna().unique())
        selected_seg = st.selectbox("Segment Filtrele:", segments)
        
        if selected_seg != "Tümü":
            filtered_df = df_bq[df_bq["segment_adi"] == selected_seg]
        else:
            filtered_df = df_bq
            
        st.markdown("### 📋 Canlı Veri Tablosu")
        st.dataframe(filtered_df, use_container_width=True)
        
        st.markdown("### 📊 Segment Bazlı Merchant Dağılımı")
        st.bar_chart(filtered_df, x="segment_adi", y="toplam_listelenen_merchant")
    else:
        st.warning("BigQuery üzerinde gösterilecek veri bulunamadı.")

# SEKMELER 3: VAST TAG
with tab3:
    st.subheader("🔗 VAST Tag Analizi")
    st.info("VAST Tag analiz modülü yakında eklenecek.")
