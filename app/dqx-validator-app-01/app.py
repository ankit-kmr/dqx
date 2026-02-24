import streamlit as st
import configparser
import os
from utils.database_manager import DatabaseManager
from utils.workflow_manager import WorkflowManager
from utils.app_logic import AppLogic

# --- 1. Load Configuration ---
def load_config(profile):
    config = configparser.ConfigParser()
    config_path = os.path.join(os.getcwd(), 'config.conf')
    
    if not os.path.exists(config_path):
        st.error("❌ config.conf file not found!")
        st.stop()
        
    config.read(config_path)
    if profile not in config:
        st.error(f"❌ Profile '{profile}' not found in config.conf")
        st.stop()
        
    return config[profile]

# --- 2. Setup & Profile Selection ---
env_profile = 'dev'
conf = load_config(env_profile)
print("conf >>", conf)

# --- 3. Initialize Managers with Config Data ---
# We pull values from the 'conf' object mapped to the .conf keys
db_mgr = DatabaseManager(
    hostname=conf['SERVER_HOSTNAME'], 
    http_path=conf['HTTP_PATH'], 
    token=conf['TOKEN']
)

wf_mgr = WorkflowManager(
    hostname=conf['SERVER_HOSTNAME'], 
    token=conf['TOKEN'], 
    job_id=conf['JOB_ID']
)

app_logic = AppLogic(db_mgr)
CONFIG_SCHEMA = conf['CONFIG_SCHEMA']

# --- 4. Sidebar Selection Logic ---
with st.sidebar:
    st.header("⚙️ Data Selection")
    
    try:
        catalogs = ["-- Select --"] + app_logic.get_catalogs()
        cat_input = st.selectbox("Catalog Name", options=catalogs)

        schema_name = "-- Select --"
        if cat_input != "-- Select --":
            schema_name = st.selectbox("Schema Name", options=["-- Select --"] + app_logic.get_schemas(cat_input))

        selected_table = "-- Select --"
        if schema_name != "-- Select --":
            selected_table = st.selectbox("Table Name", options=["-- Select --"] + app_logic.get_tables(cat_input, schema_name))
    except Exception as e:
        st.error(f"Connection Error: Check your {env_profile} credentials.")
        st.stop()

# --- 5. Main App Logic ---
if selected_table != "-- Select --":
    st.title(f"📊 {selected_table}")
    tab_labels = ["📋 Overview", "🛡️ Rules & Run", "✅ Add Rules"]
    active_tab = st.radio("Select View", options=tab_labels, horizontal=True)
    
    if active_tab == "📋 Overview":
        st.text(app_logic.get_table_stats(cat_input, schema_name, selected_table))
        
    elif active_tab == "🛡️ Rules & Run":
        if st.button("🚀 Trigger Job", type="primary"):
            res = wf_mgr.trigger_dqx_job(cat_input, CONFIG_SCHEMA, schema_name, selected_table)
            if res.status_code == 200:
                st.success(f"Success! Run ID: {res.json().get('run_id')}")
            else:
                st.error(res.text)
else:
    st.title("🛡️ DQX Validator Portal")
    st.info(f"Currently in **{env_profile}** mode. Please select a table to proceed.")
    