import streamlit as st
import pandas as pd
import io
import re

# --- Page Config ---
st.set_page_config(page_title="Power System Data Merger", layout="wide")
st.title("⚡ Power System Master Report Builder")

# --- Session State Initialization ---
if 'master_df' not in st.session_state:
    # Initialize Fixed Backbone: 96 blocks
    blocks = list(range(1, 97))
    times = pd.date_range("00:00", "23:45", freq="15min").strftime('%H:%M:%S').tolist()
    
    backbone = pd.DataFrame({'Block': blocks, 'Time': times})
    backbone.set_index(['Block', 'Time'], inplace=True)
    
    # Initialize MultiIndex columns
    backbone.columns = pd.MultiIndex.from_tuples([], names=['File', 'Column'])
    st.session_state.master_df = backbone

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Helpers ---
def get_all_sections(df):
    if df.empty or 0 not in df.columns: return []
    candidates = df[0].dropna().astype(str).str.strip()
    return [s for s in candidates.unique() if s.lower() not in ['block', 'time', 'date'] and not s.isdigit() and len(s) > 3]

def find_table_by_title(df, section_title):
    df_str = df.astype(str)
    escaped_title = re.escape(section_title)
    mask = df_str.apply(lambda x: x.str.contains(escaped_title, case=False, na=False))
    if not mask.any().any(): return None
    
    idx = mask.any(axis=1).idxmax()
    search_area = df.iloc[idx : min(idx + 100, len(df))]
    
    for i, row in search_area.iterrows():
        row_str = "".join([str(v) if pd.notna(v) else "" for v in row.values]).replace(" ", "").upper()
        if "BLOCK" in row_str: return i
    return None

# --- UI ---
with st.sidebar:
    if st.button("🗑️ Reset Everything", type="primary"): reset_app()

uploaded_files = st.file_uploader("Upload Power System Files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with st.expander(f"📄 File: {uploaded_file.name}"):
            try:
                raw_df = pd.read_csv(uploaded_file, header=None) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, header=None)
                sections = get_all_sections(raw_df)
                selected_sec = st.selectbox("Select Section:", sections, key=f"s_{uploaded_file.name}")
                
                header_idx = find_table_by_title(raw_df, selected_sec)
                if header_idx is not None:
                    df_clean = raw_df.iloc[header_idx:].copy()
                    df_clean.columns = df_clean.iloc[0].astype(str).str.strip()
                    df_clean = df_clean[1:97] 
                    
                    # Convert types to match backbone
                    df_clean['Block'] = pd.to_numeric(df_clean['Block'], errors='coerce').fillna(0).astype(int)
                    df_clean['Time'] = df_clean['Time'].astype(str).str.strip()
                    
                    data_cols = [c for c in df_clean.columns if c not in ['nan', 'none', ''] and not str(c).startswith('Unnamed')]
                    selected_cols = st.multiselect("Select columns to merge:", data_cols, key=f"c_{uploaded_file.name}")
                    
                    if st.button("Append to Master", key=f"b_{uploaded_file.name}"):
                        if not selected_cols:
                            st.error("Select columns first!")
                        else:
                            # Create a clean slice for merging
                            merge_slice = df_clean[selected_cols].copy()
                            
                            # Use the actual Block and Time from df_clean as the keys
                            merge_slice['join_block'] = df_clean['Block']
                            merge_slice['join_time'] = df_clean['Time']
                            
                            merge_slice.set_index(['join_block', 'join_time'], inplace=True)
                            
                            # Set MultiIndex headers
                            header_label = f"{uploaded_file.name} | {selected_sec}"
                            merge_slice.columns = pd.MultiIndex.from_product([[header_label], selected_cols])
                            
                            # Join to Master
                            st.session_state.master_df = st.session_state.master_df.join(merge_slice, how='left')
                            st.success("Merged!")
                else:
                    st.error("Table header not found.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- Display & Export ---
if not st.session_state.master_df.empty and len(st.session_state.master_df.columns) > 0:
    st.divider()
    st.subheader("📊 Master Report Preview")
    
    # Sort index to ensure 1-96 order
    final_report = st.session_state.master_df.sort_index()
    st.dataframe(final_report, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_report.to_excel(writer, sheet_name='Master_Report')
    
    st.download_button(
        label="📥 Download Master Report (Excel)",
        data=output.getvalue(),
        file_name="AP_Transco_Master_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
