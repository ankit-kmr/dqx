import streamlit as st
import configparser
from databricks.connect import DatabricksSession

from utils.state_manager import StateManager
from utils.database_manager import DatabaseManager
from utils.workflow_manager import WorkflowManager
from utils.ui_components import UIComponents
from utils.dq_checks_handler import dqx_handler
from utils.dqx_ui_components import DqxUIComponents
from utils.submit_ui_components import UISubmitComponents

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
@st.cache_resource(show_spinner='Initializing Core Services...')
def init_base_managers():
    return (
        DatabaseManager(HOST, PATH, TOKEN), 
        WorkflowManager(HOST, TOKEN, JOB_ID)
    )

def get_spark():
    return DatabricksSession.builder.serverless().getOrCreate()

db, wm = init_base_managers()
dqx_h = dqx_handler(get_spark()) 
ui = UIComponents(db, wm, config_catalog, config_schema)
dqx_ui = DqxUIComponents(db, dqx_h, config_catalog, config_schema)
ui_submit = UISubmitComponents(db, wm, dqx_h, config_catalog, config_schema)

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
    
    # 1. Define Step Labels
    wizard_steps = [
        "🔍 Object Overview",
        "🛡️ Active DQ Rules", 
        "🧪 Inferred DQ Rules",
        "🤖 AI-Assisted DQ Rules",
        "🆕 Manage DQ Rules",
        "✅ Final Submit"
    ]

    # Initialize session state for navigation
    if 'step' not in st.session_state:
        st.session_state.step = 0

    # 2. Visual Progress Bar (Non-clickable tabs)
    cols = st.columns(len(wizard_steps))
    for i, step_label in enumerate(wizard_steps):
        if i == st.session_state.step:
            cols[i].markdown(f"**{step_label}**")
            cols[i].markdown("---") # Highlight active
        else:
            cols[i].markdown(f"<span style='color:gray'>{step_label}</span>", unsafe_allow_html=True)

    # 3. Navigation Helper Functions
    def go_next(): st.session_state.step += 1
    def go_back(): st.session_state.step -= 1
    def skip_to_update(): st.session_state.step = 4

    # 4. Step Routing Logic
    current = st.session_state.step

    if current == 0:
        ui.render_object_overview(cat_select, schema_select, table_select)
        if st.button("Next ➡️", use_container_width=True):
            go_next()
            st.rerun()

    elif current == 1:
        ui.render_active_dq_rules(cat_select, schema_select, table_select)
        c1, c2 = st.columns(2)
        if c1.button("⬅️ Back", use_container_width=True): go_back(); st.rerun()
        if c2.button("Next ➡️", use_container_width=True): go_next(); st.rerun()

    elif current == 2:
        dqx_ui.render_profile_rule_generator(cat_select, schema_select, table_select)
        c1, c2, c3 = st.columns(3)
        if c1.button("⬅️ Back"): go_back(); st.rerun()
        if c2.button("Skip to Update ⏭️"): skip_to_update(); st.rerun()
        if c3.button("Next ➡️"): go_next(); st.rerun()

    elif current == 3:
        dqx_ui.render_ai_rule_generator(cat_select, schema_select, table_select)
        c1, c2, c3 = st.columns(3)
        if c1.button("⬅️ Back"): go_back(); st.rerun()
        if c2.button("Skip to Update ⏭️"): skip_to_update(); st.rerun()
        if c3.button("Next ➡️"): go_next(); st.rerun()

    elif current == 4:
        ui.render_add_rules_mapping(cat_select, schema_select, table_select)
        if st.button("⬅️ Back"):
            go_back()
            st.rerun()
    
    elif current == 5:
        ui_submit.render_submit(cat_select, schema_select, table_select)
        if st.button("⬅️ Back"):
            go_back()
            st.rerun

else:
    # Reset step if table selection changes to keep flow consistent
    st.session_state.step = 0
    st.info("👈 Please select a Catalog, Schema, and Table from the sidebar to begin.")
