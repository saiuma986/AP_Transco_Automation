import streamlit as st
import pandas as pd
import io
import re

# --- Page Config ---
st.set_page_config(page_title="Power System Data Merger", layout="wide")
st.title("⚡ Power System Master Report Builder")

# --- Session State Initialization ---
if 'master_df' not in st.session_state:
    # Initialize Backbone
    blocks = list(range(1, 97))
    times = pd.date_range("00:00", "23:45", freq="15min").strftime('%H:%M:%S').tolist()
    
    backbone = pd.DataFrame({'Block': blocks, 'Time': times})
    # We set the index, but then convert it to a MultiIndex immediately 
    # so that the "Levels" match (2 levels on left, 2 levels on right)
    backbone.set_index(['Block', 'Time'], inplace=True)
    backbone.columns = pd.MultiIndex.from_tuples([('Index', 'Index')], names=['File', 'Column'])[:0] 
    
    st.session_state.master_df = backbone

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Helpers ---
def get_all_sections(df):
    candidates = df[0].dropna().astype(str).str.strip()
    sections = [s for s in candidates.unique() if s.lower() not in ['block', 'time', 'date'] and not s.isdigit() and len(s) > 3]
    return sections

def find_table_by_title(df, section_title):
    df_str = df.astype(str)
    escaped_title = re.escape(section_title)
    mask = df_str.apply(lambda x: x.str.contains(escaped_title, case=False, na=False))
    if not mask.any().any(): return None
    
    section_row_idx = mask.any(axis=1).idxmax()
    search_limit = min(section_row_idx + 100, len(df))
    search_area = df_str.iloc[section_row_idx : search_limit]
    
    for i, row in search_area.iterrows():
        combined = "".join(row.values).replace(" ", "").upper()
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
                    
                    # 'Block' and 'Time' are hidden from selection to prevent duplication
                    data_cols = [c for c in df_clean.columns if c.lower() not in ['block', 'time', 'nan', 'none', ''] and not c.startswith('Unnamed')]
                    
                    selected_cols = st.multiselect("Columns to merge:", data_cols, key=f"c_{uploaded_file.name}")
                    
                    if st.button("Append to Master", key=f"b_{uploaded_file.name}"):
                        if not selected_cols:
                            st.error("Select columns first!")
                        else:
                            temp_df = df_clean[['Block', 'Time'] + selected_cols].copy()
                            temp_df.set_index(['Block', 'Time'], inplace=True)
                            
                            # Create 2-level header to match master
                            header_label = f"{uploaded_file.name} | {selected_sec}"
                            temp_df.columns = pd.MultiIndex.from_product([[header_label], selected_cols])
                            
                            # JOIN LOGIC: Use the session state directly
                            # We re-assign to ensure the master keeps growing horizontally
                            st.session_state.master_df = st.session_state.master_df.join(temp_df, how='outer')
                            st.success("Merged successfully!")
                else:
                    st.error("Block header not found.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- Preview & Export ---
if not st.session_state.master_df.empty and len(st.session_state.master_df.columns) > 0:
    st.divider()
    st.subheader("📊 Master Report Preview")
    
    # Clean up the display: Remove the dummy 'Index' level if it exists from initialization
    display_df = st.session_state.master_df.copy()
    
    st.dataframe(display_df, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        display_df.to_excel(writer)
    
    st.download_button("📥 Download Excel", output.getvalue(), "Master_Report.xlsx", "application/vnd.ms-excel")