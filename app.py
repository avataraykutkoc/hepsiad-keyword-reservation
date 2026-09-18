import streamlit as st
import uuid
from datetime import datetime
from google.cloud import bigquery
from google.oauth2 import service_account

# Sayfa Ayarları
st.set_page_config(
    page_title="HepsiAd - PLP Kelime Rezervasyon Portalı",
    page_icon="🚀",
    layout="centered"
)

# BigQuery Client Bağlantısı (Lokal Test Modu)
@st.cache_resource
def get_bigquery_client():
    try:
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"]
        )
        return bigquery.Client(credentials=credentials, project=credentials.project_id)
    except Exception:
        return None

client = get_bigquery_client()

# Arayüz Başlığı
st.markdown(
    """
    <div style="display: flex; justify-content: center; margin-bottom: -10px; margin-top: -10px;">
        <div style="background-color: #1e1e2e; padding: 10px 18px; border-radius: 12px; border: 1.5px solid #00d2ff; text-align: center; box-shadow: 0 4px 12px rgba(0, 210, 255, 0.2);">
            <span style="color: #a6adc8; font-size: 14px; font-weight: bold; margin-right: 5px;">👨‍💻 Creator:</span> 
            <span style="color: #00d2ff; font-size: 16px; font-weight: bold;">Aykut Koç</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)
st.title("🚀 HepsiAd PLP Kelime Rezervasyon Portalı")
st.markdown("Looker Studio üzerinden seçtiğiniz **Boş (Fırsat)** kelimeleri rezerve etmek için formu doldurun.")

st.divider()

# URL Parametresi
query_params = st.query_params
default_keyword = query_params.get("keyword", "")

# REZERVASYON FORMU
with st.form("reservation_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        plp_kelime = st.text_input("Rezerve Edilecek Kelime / Filtre", value=default_keyword, placeholder="ör. Kapama Şekli")
        brand_name = st.text_input("Marka / Satıcı Adı", placeholder="ör. Nike, Samsung")
        start_date = st.date_input("Rezervasyon Başlangıç Tarihi")
        
    with col2:
        kategori = st.text_input("Kategori", placeholder="ör. top, Ayakkabı")
        sales_rep_email = st.text_input("Müşteri Temsilcisi E-Posta", placeholder="ör. aykut.koc@hepsiburada.com")
        end_date = st.date_input("Rezervasyon Bitiş Tarihi")

    submitted = st.form_submit_button("🔥 Rezervasyonu Onayla ve Kaydet")

# FORM GÖNDERİLDİĞİNDE
if submitted:
    if not plp_kelime or not brand_name or not sales_rep_email:
        st.error("⚠️ Lütfen zorunlu alanları (Kelime, Marka Adı ve Temsilci E-Posta) doldurun!")
    elif start_date >= end_date:
        st.error("⚠️ Bitiş tarihi başlangıç tarihinden sonra olmalıdır!")
    else:
        try:
            reservation_id = str(uuid.uuid4())
            created_at = datetime.utcnow().isoformat()
            
            rows_to_insert = [
                {
                    "reservation_id": reservation_id,
                    "plp_kelime": plp_kelime,
                    "kategori": kategori,
                    "brand_name": brand_name,
                    "sales_rep_email": sales_rep_email,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "created_at": created_at,
                    "status": "APPROVED"
                }
            ]

            if client:
                table_id = "hb-dataanalytics-prod.filter_dashboard.keyword_reservations"
                errors = client.insert_rows_json(table_id, rows_to_insert)
                if errors == []:
                    st.success(f"🎉 **'{plp_kelime}'** kelimesi **{brand_name}** markası adına başarıyla rezerve edildi!")
                    st.info(f"📋 **Rezervasyon ID:** `{reservation_id}`")
                else:
                    st.error(f"❌ BigQuery hatası: {errors}")
            else:
                st.success(f"🧪 **[LOKAL TEST]** **'{plp_kelime}'** kelimesi **{brand_name}** markası adına başarıyla rezerve edildi!")
                st.info(f"📋 **Rezervasyon ID:** `{reservation_id}`")
                st.json(rows_to_insert[0])
                
        except Exception as e:
            st.error(f"🚨 Bağlantı hatası: {str(e)}")
