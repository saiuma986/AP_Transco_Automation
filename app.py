import streamlit as st
import pandas as pd
import io
import re

# --- Page Config ---
st.set_page_config(page_title="Power System Data Merger", layout="wide")
st.title("⚡ Power System Master Report Builder")

# --- Session State Initialization ---
if 'master_df' not in st.session_state:
    blocks = list(range(1, 97))
    times = pd.date_range("00:00", "23:45", freq="15min").strftime('%H:%M:%S').tolist()
    backbone = pd.DataFrame({'Block': blocks, 'Time': times})
    backbone.set_index(['Block', 'Time'], inplace=True)
    # Correcting level mismatch for future joins
    backbone.columns = pd.MultiIndex.from_tuples([], names=['File', 'Column'])
    st.session_state.master_df = backbone

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Robust Helpers ---
def get_all_sections(df):
    candidates = df[0].dropna().astype(str).str.strip()
    sections = [s for s in candidates.unique() if s.lower() not in ['block', 'time', 'date'] and not s.isdigit() and len(s) > 3]
    return sections

def find_table_by_title(df, section_title):
    # Escape special characters for regex safety
    escaped_title = re.escape(section_title)
    mask = df.astype(str).apply(lambda x: x.str.contains(escaped_title, case=False, na=False))
    
    if not mask.any().any(): return None
    
    section_row_idx = mask.any(axis=1).idxmax()
    search_limit = min(section_row_idx + 100, len(df))
    search_area = df.iloc[section_row_idx : search_limit]
    
    for i, row in search_area.iterrows():
        # FIX: Ensure all items are strings before joining to avoid 'float found' error
        row_values = [str(val) if val is not None else "" for val in row.values]
        combined = "".join(row_values).replace(" ", "").upper()
        if "BLOCK" in combined: return i
    return None

# --- UI ---
with st.sidebar:
    if st.button("🗑️ Reset Everything", type="primary"):
        reset_app()

uploaded_files = st.file_uploader("Upload Files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with st.expander(f"📄 {uploaded_file.name}"):
            try:
                if uploaded_file.name.endswith('.csv'):
                    raw_df = pd.read_csv(uploaded_file, header=None)
                else:
                    raw_df = pd.read_excel(uploaded_file, header=None)
                
                sections = get_all_sections(raw_df)
                selected_sec = st.selectbox("Section:", sections, key=f"s_{uploaded_file.name}")
                
                header_idx = find_table_by_title(raw_df, selected_sec)
                
                if header_idx is not None:
                    df_clean = raw_df.iloc[header_idx:].copy()
                    df_clean.columns = df_clean.iloc[0].astype(str).str.strip()
                    df_clean = df_clean[1:97]
                    
                    df_clean['Block'] = pd.to_numeric(df_clean['Block'], errors='coerce').fillna(0).astype(int)
                    df_clean['Time'] = df_clean['Time'].astype(str).str.strip()
                    
                    data_cols = [c for c in df_clean.columns if c.lower() not in ['block', 'time', 'nan', 'none', ''] and not str(c).startswith('Unnamed')]
                    
                    selected_cols = st.multiselect("Columns to merge:", data_cols, key=f"c_{uploaded_file.name}")
                    
                    if st.button("Append to Master", key=f"b_{uploaded_file.name}"):
                        if not selected_cols:
                            st.error("Select columns first!")
                        else:
                            temp_df = df_clean[['Block', 'Time'] + selected_cols].copy()
                            temp_df.set_index(['Block', 'Time'], inplace=True)
                            
                            header_label = f"{uploaded_file.name} | {selected_sec}"
                            temp_df.columns = pd.MultiIndex.from_product([[header_label], selected_cols])
                            
                            st.session_state.master_df = st.session_state.master_df.join(temp_df, how='outer')
                            st.success("Merged!")
                else:
                    st.error("Block header not found.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- Preview & Export ---
if not st.session_state.master_df.empty and len(st.session_state.master_df.columns) > 0:
    st.divider()
    st.subheader("📊 Master Report Preview")
    st.dataframe(st.session_state.master_df, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.master_df.to_excel(writer)
    
    st.download_button("📥 Download Excel", output.getvalue(), "Master_Report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
