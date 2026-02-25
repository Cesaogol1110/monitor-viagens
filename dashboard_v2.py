import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Relatório Global de Carbono", page_icon="🌍")

# Nome do arquivo gerado pelo Robô Minerador
FILE_PATH = "VERRA_DETALHADO_FINAL.xlsx"

# --- DICIONÁRIO DE COORDENADAS (Para o Mapa) ---
# Como a Verra só dá o País, usamos o centróide do país para plotar
COUNTRY_COORDS = {
    'Brazil': [-14.2350, -51.9253],
    'India': [20.5937, 78.9629],
    'China': [35.8617, 104.1954],
    'Indonesia': [-0.7893, 113.9213],
    'Peru': [-9.1900, -75.0152],
    'Colombia': [4.5709, -74.2973],
    'Cambodia': [12.5657, 104.9910],
    'Kenya': [-0.0236, 37.9062],
    'Zambia': [-13.1339, 27.8493],
    'Congo': [-0.2280, 15.8277],
    'Democratic Republic of the Congo': [-4.0383, 21.7587],
    'Tanzania': [-6.3690, 34.8888],
    'United States': [37.0902, -95.7129],
    'Turkey': [38.9637, 35.2433],
    'Viet Nam': [14.0583, 108.2772],
    'Vietnam': [14.0583, 108.2772],
    'Malaysia': [4.2105, 101.9758],
    'Thailand': [15.8700, 100.9925],
    'Uruguay': [-32.5228, -55.7658],
    'Madagascar': [-18.7669, 46.8691],
    'Papua New Guinea': [-6.314993, 143.95555],
    'Ethiopia': [9.145, 40.489673]
}

@st.cache_data
def load_data():
    if not os.path.exists(FILE_PATH):
        return None
    
    df = pd.read_excel(FILE_PATH)
    
    # 1. ADICIONA A COLUNA DA CERTIFICADORA
    df['Certificadora'] = 'VERRA'
    
    # 2. LIMPEZA DE NÚMEROS (Annual Emission Reductions)
    # Remove textos, vírgulas e converte para numero
    def clean_number(x):
        try:
            if pd.isna(x): return 0
            x = str(x).replace(',', '').replace(' ', '')
            # Pega apenas a primeira parte numérica se houver texto
            import re
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", x)
            if numbers:
                return float(numbers[0])
            return 0
        except:
            return 0
            
    # Tenta usar a coluna minerada, se não existir, usa placeholder
    col_emissao = 'Annual Emission Reductions'
    if col_emissao not in df.columns:
        df[col_emissao] = 0
    else:
        df[col_emissao] = df[col_emissao].apply(clean_number)
        
    # 3. GEOREFERENCIAMENTO (Lookup simples)
    def get_lat(country):
        return COUNTRY_COORDS.get(str(country).strip(), [0, 0])[0]
    
    def get_lon(country):
        return COUNTRY_COORDS.get(str(country).strip(), [0, 0])[1]

    # Garante que a coluna País existe (o robô V22 usou 'País' ou 'State/Province' dependendo da versão)
    # Vamos assumir que existe uma coluna 'País' vinda do V16/V20, se não, tentamos extrair.
    if 'País' not in df.columns:
        # Tenta recuperar do Project Summary se tiver algo parecido
        df['País'] = 'Desconhecido' 
    
    df['lat'] = df['País'].apply(get_lat)
    df['lon'] = df['País'].apply(get_lon)
    
    return df

# --- INTERFACE VISUAL ---
def main():
    st.title("📊 Painel de Inteligência de Carbono (Multi-Registry)")
    st.markdown("Visualização consolidada de projetos REDD+ e ARR.")
    
    df = load_data()
    
    if df is None:
        st.error(f"Arquivo '{FILE_PATH}' não encontrado. Rode o Robô V22 primeiro.")
        return

    # --- FILTROS LATERAIS ---
    st.sidebar.header("Filtros")
    paises = st.sidebar.multiselect("País", options=df['País'].unique())
    status = st.sidebar.multiselect("Status", options=df['Project Status'].unique() if 'Project Status' in df.columns else [])
    
    # Aplica filtros
    df_filtered = df.copy()
    if paises:
        df_filtered = df_filtered[df_filtered['País'].isin(paises)]
    if status:
        df_filtered = df_filtered[df_filtered['Project Status'].isin(status)]

    # --- KPI CARDS ---
    col1, col2, col3, col4 = st.columns(4)
    total_vol = df_filtered['Annual Emission Reductions'].sum()
    
    col1.metric("Total de Projetos", len(df_filtered))
    col2.metric("Volume Anual (tCO2e)", f"{total_vol:,.0f}")
    col3.metric("Países Atuantes", df_filtered['País'].nunique())
    col4.metric("Certificadora", "VERRA (100%)")

    st.divider()

    # --- MAPA MUNDI ---
    st.subheader("🌍 Distribuição Geográfica dos Projetos")
    # Filtra lat/lon 0 (países não mapeados)
    map_data = df_filtered[(df_filtered['lat'] != 0) & (df_filtered['lon'] != 0)]
    
    if not map_data.empty:
        st.map(map_data, latitude='lat', longitude='lon', size=20, color='#00FF00')
        st.caption("*Nota: A localização é baseada no centróide do país, pois as coordenadas exatas não são públicas no resumo.*")
    else:
        st.warning("Sem dados geográficos suficientes para plotar o mapa.")

    st.divider()

    # --- GRÁFICOS ANALÍTICOS ---
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🏆 Top 10 Países por Volume")
        vol_by_country = df_filtered.groupby('País')['Annual Emission Reductions'].sum().sort_values(ascending=False).head(10)
        fig_vol = px.bar(vol_by_country, orientation='h', title="Volume de Créditos (tCO2e) por País")
        st.plotly_chart(fig_vol, use_container_width=True)
        
    with c2:
        st.subheader("📌 Status dos Projetos")
        if 'Project Status' in df_filtered.columns:
            status_counts = df_filtered['Project Status'].value_counts()
            fig_status = px.pie(values=status_counts.values, names=status_counts.index, title="Distribuição por Status")
            st.plotly_chart(fig_status, use_container_width=True)

    # --- TENDÊNCIA DE PROPONENTES ---
    st.subheader("🏢 Top Proponentes (Desenvolvedores)")
    if 'Proponent' in df_filtered.columns:
        top_props = df_filtered['Proponent'].value_counts().head(10)
        st.bar_chart(top_props)

    # --- TABELA DE DADOS ---
    with st.expander("📂 Ver Base de Dados Completa (Com coluna 'Certificadora')"):
        st.dataframe(
            df_filtered,
            column_config={
                "Link": st.column_config.LinkColumn("Link do Projeto"),
                "Annual Emission Reductions": st.column_config.NumberColumn("Redução Anual", format="%d")
            },
            use_container_width=True
        )

if __name__ == "__main__":
    main()
    python --version
    