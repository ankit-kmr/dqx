import streamlit as st
import configparser
from utils.state_manager import StateManager
from utils.database_manager import DatabaseManager
from utils.workflow_manager import WorkflowManager
from utils.ui_components import UIComponents
from utils.dq_checks_handler import dqx_handler
from utils.dqx_ui_components import DqxUIComponents

# --- 1. Page Configuration ---
st.set_page_config(layout="wide", page_title="DQX Validator Portal")

# --- 2. Load Config & Profile ---
env = 'DEV'
config = configparser.ConfigParser()
config.read('config.conf')


# Extract variables based on selection
HOST = config.get(env, 'server_hostname')
PATH = config.get(env, 'http_path')
TOKEN = config.get(env, 'token')
JOB_ID = config.get(env, 'job_id')
config_catalog = config.get('DEFAULT', 'dqx_catalog_name')
config_schema = config.get('DEFAULT', 'dqx_config_schema')


# --- 3. Initialize Managers ---
@st.cache_resource(show_spinner='Loading...')
def init_managers():
    db = DatabaseManager(HOST, PATH, TOKEN)
    wm = WorkflowManager(HOST, TOKEN, JOB_ID)
    ui = UIComponents(db, wm, config_catalog, config_schema)
    dqx_h = dqx_handler()
    dqx_ui = DqxUIComponents(db, dqx_h)
    return db, wm, ui, dqx_h, dqx_ui

db, wm, ui, dqx_h, dqx_ui = init_managers()
StateManager.initialize()

# --- 4. Main UI Sidebar Navigation ---
st.title("🛡️ DQX Validator Portal")

with st.sidebar:
    if st.button("🔄 Reset Portal", use_container_width=True):
        StateManager.reset_portal()
    st.divider()

    # Data Selectors
    catalogs = ["-- Select --"] + db.fetch_catalogs()
    cat_select = st.selectbox("Catalog", options=catalogs, key="cat_select")
    
    schemas = ["-- Select --"]
    if cat_select != "-- Select --":
        schemas += db.fetch_schemas(cat_select)
    schema_select = st.selectbox("Schema", options=schemas, key="schema_select")
    
    tables = ["-- Select --"]
    if schema_select != "-- Select --":
        tables += db.fetch_tables(cat_select, schema_select)
    table_select = st.selectbox("Table", options=tables, key="table_select")

# --- 5. Main Content Area ---
if cat_select != "-- Select --" and table_select != "-- Select --":
    tab_labels = [
        "📋 Table Overview", 
        "🧬 Columns Details", 
        "🛡️ Manage DQ Mapping & Run", 
        "🆕 ADD New DQ Mapping",
        "🧪 Profiling & Check Generator",
        "🤖 AI-Assisted Check Generation"
    ]
    active_tab = st.radio("Navigation", options=tab_labels, horizontal=True, key="active_tab_nav")
    st.divider()

    if active_tab == "📋 Table Overview":
        ui.render_table_overview(cat_select, schema_select, table_select)

    elif active_tab == "🧬 Columns Details":
        ui.render_column_details(cat_select, schema_select, table_select)

    elif active_tab == "🛡️ Manage DQ Mapping & Run":
        ui.render_manage_dq_mapping(cat_select, schema_select, table_select)

    elif active_tab == "🆕 ADD New DQ Mapping":
        ui.render_add_rules_mapping(cat_select, schema_select, table_select)
    
    elif active_tab == "🧪 Profiling & Check Generator":
        dqx_ui.render_profile_generator(cat_select, schema_select, table_select)
    
    elif active_tab == "🤖 AI-Assisted Check Generation":
        dqx_ui.render_ai_check_generator(cat_select, schema_select, table_select)

else:
    st.info("👈 Please select a Catalog, Schema, and Table from the sidebar to begin.")
