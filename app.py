import streamlit as st
import pandas as pd
import io
import re

# --- Page Config ---
st.set_page_config(page_title="Power System Data Merger", layout="wide")
st.title("⚡ Power System Master Report Builder")

# --- Session State Initialization ---
if 'master_df' not in st.session_state:
    # 1. Create the fixed 1-96 backbone
    blocks = list(range(1, 97))
    times = pd.date_range("00:00", "23:45", freq="15min").strftime('%H:%M:%S').tolist()
    
    backbone = pd.DataFrame({'Block': blocks, 'Time': times})
    # Set index but keep it simple
    backbone.set_index(['Block', 'Time'], inplace=True)
    
    # Initialize empty MultiIndex columns
    backbone.columns = pd.MultiIndex.from_tuples([], names=['File', 'Column'])
    st.session_state.master_df = backbone

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Robust Helpers ---
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
    search_limit = min(idx + 100, len(df))
    search_area = df.iloc[idx : search_limit]
    
    for i, row in search_area.iterrows():
        row_str = "".join([str(v) if pd.notna(v) else "" for v in row.values]).replace(" ", "").upper()
        if "BLOCK" in row_str: return i
    return None

# --- UI Sidebar ---
with st.sidebar:
    if st.button("🗑️ Reset Everything", type="primary"):
        reset_app()

# --- File Processing ---
uploaded_files = st.file_uploader("Upload Files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with st.expander(f"📄 File: {uploaded_file.name}", expanded=True):
            try:
                # Load Raw Data
                raw_df = pd.read_csv(uploaded_file, header=None) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file, header=None)
                
                # Section Picker
                sections = get_all_sections(raw_df)
                selected_sec = st.selectbox("Select Section:", sections, key=f"s_{uploaded_file.name}")
                
                # Table Search
                header_idx = find_table_by_title(raw_df, selected_sec)
                
                if header_idx is not None:
                    df_extracted = raw_df.iloc[header_idx:].copy()
                    df_extracted.columns = df_extracted.iloc[0].astype(str).str.strip()
                    df_extracted = df_extracted[1:97] # Pick exactly 96 blocks
                    
                    # Normalize Block/Time to match Backbone perfectly
                    df_extracted['Block'] = pd.to_numeric(df_extracted['Block'], errors='coerce').fillna(0).astype(int)
                    df_extracted['Time'] = df_extracted['Time'].astype(str).str.strip()
                    
                    # Column Picker (Including Block/Time as requested)
                    available_cols = [c for c in df_extracted.columns if str(c) not in ['nan', 'none', ''] and not str(c).startswith('Unnamed')]
                    selected_cols = st.multiselect("Columns to merge:", available_cols, key=f"c_{uploaded_file.name}")
                    
                    if st.button("Append to Master", key=f"b_{uploaded_file.name}"):
                        if not selected_cols:
                            st.warning("Please select columns first.")
                        else:
                            # PREPARE DATA FOR MERGE
                            # 1. Take ONLY the selected columns
                            merge_data = df_extracted[selected_cols].copy()
                            
                            # 2. Add temporary join keys to ensure alignment
                            merge_data['temp_b'] = df_extracted['Block']
                            merge_data['temp_t'] = df_extracted['Time']
                            merge_data.set_index(['temp_b', 'temp_t'], inplace=True)
                            
                            # 3. Rename the index levels to match the Master Backbone EXACTLY
                            merge_data.index.names = ['Block', 'Time']
                            
                            # 4. Create MultiIndex Headers (File | Column)
                            file_label = f"{uploaded_file.name} | {selected_sec}"
                            merge_data.columns = pd.MultiIndex.from_product([[file_label], selected_cols])
                            
                            # 5. Join
                            st.session_state.master_df = st.session_state.master_df.join(merge_data, how='left')
                            st.success("Successfully added to report!")
                else:
                    st.error("Could not find 'Block' header in this section.")
            except Exception as e:
                st.error(f"Error: {e}")

# --- Preview & Export ---
if not st.session_state.master_df.empty and len(st.session_state.master_df.columns) > 0:
    st.divider()
    st.subheader("📊 Master Report Preview")
    
    # Sort and display
    display_df = st.session_state.master_df.sort_index()
    st.dataframe(display_df, use_container_width=True)
    
    # Excel Download
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        display_df.to_excel(writer, sheet_name='Master_Report')
    
    st.download_button(
        label="📥 Download Master Report (Excel)",
        data=output.getvalue(),
        file_name="AP_Transco_Master_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
