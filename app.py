import streamlit as st
import pandas as pd
import io
import re

# --- Page Config ---
st.set_page_config(page_title="Power System Data Merger", layout="wide")
st.title("⚡ Power System Master Report Builder")

# --- Session State Initialization ---
if 'master_df' not in st.session_state:
    # Initialize Backbone: 96 blocks, 15-min intervals
    blocks = list(range(1, 97))
    times = pd.date_range("00:00", "23:45", freq="15min").strftime('%H:%M:%S').tolist()
    
    backbone = pd.DataFrame({'Block': blocks, 'Time': times})
    # Set the index for the backbone (The Anchor)
    backbone.set_index(['Block', 'Time'], inplace=True)
    
    # Initialize columns as a MultiIndex to match the incoming data structure
    backbone.columns = pd.MultiIndex.from_tuples([], names=['File', 'Column'])
    st.session_state.master_df = backbone

def reset_app():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- Robust Fuzzy Logic Helpers ---
def get_all_sections(df):
    if df.empty or 0 not in df.columns:
        return []
    candidates = df[0].dropna().astype(str).str.strip()
    sections = [s for s in candidates.unique() if s.lower() not in ['block', 'time', 'date', 'total'] and not s.isdigit() and len(s) > 3]
    return sections

def find_table_by_title(df, section_title):
    df_str = df.astype(str)
    escaped_title = re.escape(section_title)
    mask = df_str.apply(lambda x: x.str.contains(escaped_title, case=False, na=False))
    if not mask.any().any():
        return None
    
    section_row_idx = mask.any(axis=1).idxmax()
    search_limit = min(section_row_idx + 100, len(df))
    search_area = df.iloc[section_row_idx : search_limit]
    
    for i, row in search_area.iterrows():
        row_values_as_strings = [str(val) if pd.notna(val) else "" for val in row.values]
        combined_row_text = "".join(row_values_as_strings).replace(" ", "").upper()
        if "BLOCK" in combined_row_text:
            return i
    return None

# --- UI Controls ---
with st.sidebar:
    st.header("Global Controls")
    if st.button("🗑️ Reset Everything", type="primary"):
        reset_app()

# --- File Upload Section ---
uploaded_files = st.file_uploader("Upload Power System Files", type=['csv', 'xlsx'], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        with st.expander(f"📄 File: {uploaded_file.name}", expanded=True):
            try:
                if uploaded_file.name.endswith('.csv'):
                    raw_df = pd.read_csv(uploaded_file, header=None)
                else:
                    raw_df = pd.read_excel(uploaded_file, header=None)
                
                sections = get_all_sections(raw_df)
                selected_sec = st.selectbox("Select Section:", sections, key=f"sel_{uploaded_file.name}")
                
                header_row_idx = find_table_by_title(raw_df, selected_sec)
                
                if header_row_idx is not None:
                    df_clean = raw_df.iloc[header_row_idx:].copy()
                    df_clean.columns = df_clean.iloc[0].astype(str).str.strip()
                    df_clean = df_clean[1:97] 
                    
                    # Normalize Block and Time
                    df_clean['Block'] = pd.to_numeric(df_clean['Block'], errors='coerce').fillna(0).astype(int)
                    df_clean['Time'] = df_clean['Time'].astype(str).str.strip()
                    
                    # UPDATED: Filter out only empty or system columns, KEEPING Block and Time
                    data_cols = [c for c in df_clean.columns if c not in ['nan', 'none', ''] and not str(c).startswith('Unnamed')]
                    
                    selected_cols = st.multiselect(
                        "Select columns to add (Including Block/Time):", 
                        data_cols, 
                        key=f"cols_{uploaded_file.name}"
                    )
                    
                    if st.button(f"Append to Master", key=f"btn_{uploaded_file.name}"):
                        if not selected_cols:
                            st.error("Please select at least one column.")
                        else:
                            # Use Block/Time as join keys, but allow them to be selected as data columns too
                            temp_df = df_clean[['Block', 'Time'] + [c for c in selected_cols if c not in ['Block', 'Time']]].copy()
                            
                            # If user explicitly selected Block or Time to be merged as data columns:
                            for col in ['Block', 'Time']:
                                if col in selected_cols:
                                    temp_df[f"{col}_data"] = df_clean[col]
                            
                            temp_df.set_index(['Block', 'Time'], inplace=True)
                            
                            # Multi-Index: Prepend Filename + Section
                            header_label = f"{uploaded_file.name} | {selected_sec}"
                            temp_df.columns = pd.MultiIndex.from_product([[header_label], selected_cols])
                            
                            # Perform Join
                            st.session_state.master_df = st.session_state.master_df.join(temp_df, how='outer')
                            st.success(f"Added to report!")
                else:
                    st.error(f"Could not find a table with a 'Block' header under that section.")
            except Exception as e:
                st.error(f"Error parsing file: {e}")

# --- Preview & Export ---
if not st.session_state.master_df.empty and len(st.session_state.master_df.columns) > 0:
    st.divider()
    st.subheader("📊 Master Report Preview")
    st.dataframe(st.session_state.master_df, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        st.session_state.master_df.to_excel(writer, sheet_name='Master_Report')
    
    st.download_button(
        label="📥 Download Master Report (Excel)",
        data=output.getvalue(),
        file_name="Master_Power_Report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
