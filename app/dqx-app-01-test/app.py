import streamlit as st
from databricks import sql
import pandas as pd
import requests

import datetime
import json


st.set_page_config(layout="wide", page_title="DQX Validator")

# --- Configuration ---
SERVER_HOSTNAME = "dbc-4b58157d-c7bb.cloud.databricks.com"
HTTP_PATH = "/sql/1.0/warehouses/d1ab6da38ff963c2"
TOKEN = "<token>"
JOB_ID = "<jobid>" 
config_schema_input = 'dqx_config'

# Track the active tab to prevent jumping on rerun
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "📋 Table Overview"
    
# Track how many rule entries each column has
if "column_rule_counts" not in st.session_state:
    st.session_state.column_rule_counts = {}

# --- State Initialization ---
if "reset_trigger" not in st.session_state:
    st.session_state.reset_trigger = False

def reset_callback():
    # Clear specific selection keys
    keys_to_reset = ["cat_select", "schema_select", "table_select"]
    for key in keys_to_reset:
        if key in st.session_state:
            st.session_state[key] = None # Set to None to force default behavior
            del st.session_state[key]
            
    # Clear the data caches
    fetch_catalogs.clear()
    fetch_schemas.clear()
    fetch_tables.clear()
    fetch_dqx_mappings.clear()

# --- 1. Connection & API Management ---
@st.cache_resource
def get_connection():
    return sql.connect(
        server_hostname=SERVER_HOSTNAME,
        http_path=HTTP_PATH,
        access_token=TOKEN
    )

def trigger_workflow(catalog, config, src, table):
    """Triggers the Databricks Job using the modern job_parameters field"""
    api_url = f"https://{SERVER_HOSTNAME}/api/2.1/jobs/run-now"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    
    # Modern payload format using job_parameters
    payload = {
        "job_id": JOB_ID,
        "job_parameters": {
            "catalog_name": catalog,
            "config_schema_name": config,
            "source_schema_name": src,
            "table_name": table
        }
    }
    
    response = requests.post(api_url, headers=headers, json=payload)
    return response

# --- 2. Data Fetching Functions ---
@st.cache_data(ttl=600 ,show_spinner=False)
def fetch_catalogs():
    with get_connection().cursor() as cursor:
        cursor.execute("SHOW CATALOGS")
        return [row[0] for row in cursor.fetchall()]

@st.cache_data(ttl=600 ,show_spinner=False)
def fetch_schemas(catalog_name):
    with get_connection().cursor() as cursor:
        cursor.execute(f"SHOW SCHEMAS IN {catalog_name}")
        return [row[0] for row in cursor.fetchall()]

@st.cache_data(ttl=300 ,show_spinner=False)
def fetch_tables(catalog_name, schema_name):
    with get_connection().cursor() as cursor:
        cursor.execute(f"SHOW TABLES IN {catalog_name}.{schema_name}")
        table_data = cursor.fetchall()
        return [row[1] for row in table_data] if table_data else []

@st.cache_data(ttl=300 ,show_spinner=False)
def fetch_table_definition(catalog_name, schema_name, table_name):
    with get_connection().cursor() as cursor:
        cursor.execute(f"DESCRIBE TABLE {catalog_name}.{schema_name}.{table_name}")
        columns_data = cursor.fetchall()
        total_columns = len(columns_data)
        cursor.execute(f"SELECT COUNT(*) FROM {catalog_name}.{schema_name}.{table_name}")
        row_count = cursor.fetchone()[0]
        definition = (
            f"catalog_name: {catalog_name}\n"
            f"table_name: {table_name}\n"
            f"total_columns: {total_columns}\n"
            f"row_count: {row_count}"
        )
        return definition

@st.cache_data(ttl=300 ,show_spinner=False)
def fetch_columns(catalog_name, schema_name, table_name):
    with get_connection().cursor() as cursor:
        # DESCRIBE returns several columns; we only need the first two
        cursor.execute(f"DESCRIBE TABLE {catalog_name}.{schema_name}.{table_name}")
        columns_data = cursor.fetchall()
        if not columns_data:
            return pd.DataFrame()
        df = pd.DataFrame(columns_data)
        # Select by index to ensure we only get 'col_name' and 'data_type'
        df = df.iloc[:, [0, 1]] 
        df.columns = ['col_name', 'data_type']
        return df
        
@st.cache_data(ttl=300 ,show_spinner=False)
def fetch_dqx_mappings(catalog, config_schema, src_schema_name, table):
    query = f"""
    WITH ranked_rules AS (
        SELECT
            m.table_name,
            m.rule_id,
            r.rule_name,
            m.column_name AS column,
            r.rule_function AS function,
            m.criticality,
            m.arguments,
            r.rule_type,
            r.rule_dimension,
            r.description as rule_description,
            m.is_active,
            ROW_NUMBER() OVER (
                PARTITION BY m.table_name, m.column_name, r.rule_function 
                ORDER BY m.updated_at DESC
            ) as row_num
        FROM {catalog}.{config_schema}.dqx_rule_mappings m
        JOIN {catalog}.{config_schema}.dqx_rule_definitions r 
            ON m.rule_id = r.rule_id
        WHERE m.table_name = '{catalog}.{src_schema_name}.{table}'
          AND m.is_active = true
    )
    SELECT column, rule_dimension, rule_name, rule_description, criticality, arguments, is_active,rule_id
    FROM ranked_rules
    WHERE row_num = 1
    """
    with get_connection().cursor() as cursor:
        cursor.execute(query)
        data = cursor.fetchall()
        return pd.DataFrame(data, columns=[desc[0] for desc in cursor.description]) if data else pd.DataFrame()


@st.cache_data(ttl=600 ,show_spinner=False)
def fetch_rule_definitions(catalog, config_schema):
    # Added argument_placeholder to the SELECT
    query = f"""
        SELECT rule_id, rule_name, rule_dimension, argument_placeholder,CONCAT(rule_id, ' - ', rule_name) AS rule_info 
        FROM {catalog}.{config_schema}.dqx_rule_definitions
    """
    with get_connection().cursor() as cursor:
        cursor.execute(query)
        data = cursor.fetchall()
        return pd.DataFrame(data, columns=[desc[0] for desc in cursor.description]) if data else pd.DataFrame()


@st.cache_data(ttl=600 ,show_spinner=False)
def fetch_rule_dimensions(catalog, config_schema):
    query = f"SELECT DISTINCT rule_dimension FROM {catalog}.{config_schema}.dqx_rule_definitions WHERE rule_dimension IS NOT NULL"
    with get_connection().cursor() as cursor:
        cursor.execute(query)
        data = cursor.fetchall()
        return [row[0] for row in data] if data else []
 
    
def register_dq_rule(catalog, config_schema, src_schema_name, table_name, column_name, rule_id, criticality, arguments_dict):
    """Upserts a rule mapping into the Databricks table using MERGE."""

    # 1. Define source_table_name as "catalog.config_schema.table_name"
    source_table_name = f"{catalog}.{src_schema_name}.{table_name}"


    # 2. Format the arguments dict into a Spark SQL MAP string
    if arguments_dict:
        map_items = []
        for k, v in arguments_dict.items():
            # If v is a list/dict, convert to JSON string; if string, keep as is
            val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
            # Escape single quotes for SQL safety
            val_str = val_str.replace("'", "''")
            map_items.append(f"'{k}', '{val_str}'")
        
        map_sql = f"map({', '.join(map_items)})"
    else:
        map_sql = "CAST(NULL AS MAP<STRING, STRING>)"

    # 3. Prepare the MERGE Query
    merge_query = f"""
    MERGE INTO {catalog}.{config_schema}.dqx_rule_mappings AS target
    USING (
        SELECT
            '{source_table_name}' AS table_name,
            '{rule_id}' AS rule_id,
            '{column_name}' AS column_name,
            '{criticality}' AS criticality,
            true AS is_active,
            {map_sql} AS arguments,
            current_timestamp() AS updated_at
    ) AS source
    ON target.table_name = source.table_name AND target.rule_id = source.rule_id AND target.column_name = source.column_name
    WHEN MATCHED THEN
        UPDATE SET
            criticality = source.criticality,
            is_active = source.is_active,
            arguments = source.arguments,
            updated_at = source.updated_at
    WHEN NOT MATCHED THEN
        INSERT (table_name, rule_id, column_name, criticality, is_active, arguments, updated_at)
        VALUES (source.table_name, source.rule_id, source.column_name, source.criticality, source.is_active, source.arguments, source.updated_at)
    """
    try:
        with get_connection().cursor() as cursor:
            cursor.execute(merge_query)
        return True, "Success"
    except Exception as e:
        return False, str(e)


def deactivate_dq_rule(catalog, config_schema, src_table_full_path, column_name, rule_id):
    """Sets is_active to false for a specific mapping."""
    query = f"""
    UPDATE {catalog}.{config_schema}.dqx_rule_mappings
    SET is_active = false, updated_at = current_timestamp()
    WHERE table_name = '{src_table_full_path}' 
      AND column_name = '{column_name}' 
      AND rule_id = '{rule_id}'
    """
    try:
        with get_connection().cursor() as cursor:
            cursor.execute(query)
        return True
    except Exception as e:
        return False
    
    
# --- 3. UI Logic ---
st.title("🛡️ DQX Validator Portal")

try:
    with st.sidebar:
        st.header("⚙️ Configuration")
        if st.button("🔄 Reset Portal", use_container_width=True, on_click=reset_callback):
            st.rerun()
        st.divider()

        # 1. Catalog Selection
        catalogs = ["-- Select --"] + fetch_catalogs()
        cat_input = st.selectbox("Catalog Name", options=catalogs, key="cat_select")
    
        # 2. Schema Selection (Dependent on Catalog)
        if cat_input and cat_input != "-- Select --":
            schemas = ["-- Select --"] + fetch_schemas(cat_input)
        else:
            schemas = ["-- Select --"]
        schema_name = st.selectbox("Schema Name", options=schemas, key="schema_select")
        
        # 3. Table Selection (Dependent on Schema)
        if schema_name and schema_name != "-- Select --":
            table_list = ["-- Select --"] + fetch_tables(cat_input, schema_name)
        else:
            table_list = ["-- Select --"]
        selected_table = st.selectbox("Table Name", options=table_list, key="table_select")

        st.divider()
        st.caption(f"🚀 Workspace: {SERVER_HOSTNAME}")

    # Main workflow
    if cat_input and config_schema_input:
        # Standard Data Explorer Logic
        if selected_table != "-- Select --":
            # 1. Define Tab Labels
            tab_labels = [
                "📋 Table Overview", 
                "🧬 Columns Details", 
                "🛡️ Existing DQ Rules & Run",
                "✅ ADD NEW DQ Rules"
            ]

            # 2. Use a Radio button as a 'Tab Switcher' to guarantee state persistence
            # This replaces st.tabs(tab_labels)
            active_tab = st.radio(
                "Select View", 
                options=tab_labels, 
                horizontal=True, 
                key="active_tab_nav" # This key is the magic that stops the jumping
            )
            st.divider()

            # --- VIEW 1: Table Overview ---
            if active_tab == "📋 Table Overview":
                table_overview = fetch_table_definition(cat_input, schema_name, selected_table)
                st.text(table_overview)

            # --- VIEW 2: Columns Details ---
            elif active_tab == "🧬 Columns Details":
                df_columns = fetch_columns(cat_input, schema_name, selected_table)
                st.dataframe(df_columns, use_container_width=True, hide_index=True)

            # --- VIEW 3: Existing DQ Rules & Run ---
            elif active_tab == "🛡️ Existing DQ Rules & Run":
                df_mappings = fetch_dqx_mappings(cat_input, config_schema_input, schema_name, selected_table)
                
                if not df_mappings.empty:
                    st.subheader("Manage Active Rules")
                    
                    if "rules_to_deactivate" not in st.session_state:
                        st.session_state.rules_to_deactivate = []

                    # Table Header - Adjusted for better alignment
                    # Added "Rule Description" column after "Rule Name"
                    m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([1.5, 2.5, 2.5, 3, 0.8])
                    m_col1.write("**Column**")
                    m_col2.write("**Rule Name**")
                    m_col3.write("**Rule Description**")
                    m_col4.write("**Arguments**")
                    m_col5.write("**Action**")
                    st.divider()

                    for idx, m_row in df_mappings.iterrows():
                        # Create a unique key using column and rule_id (internal)
                        rule_key = f"{m_row['column']}_{m_row['rule_id']}"
                        
                        if rule_key in st.session_state.rules_to_deactivate:
                            continue
                            
                        r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([1.5, 2.5, 2.5, 3, 0.8])
                        
                        # 1. Column
                        r_col1.text(m_row['column'])
                        # 2. Rule Name
                        r_col2.info(f"**{m_row['rule_name']}**")
                        # 3. Rule Description
                        r_col3.caption(m_row['rule_description'])
                        # 4. Arguments
                        args_display = str(m_row['arguments']) if m_row['arguments'] else "{}"
                        r_col4.caption(args_display)
                        # 5. Action Button
                        if r_col5.button("❌", key=f"del_{idx}", help="Deactivate this rule"):
                            st.session_state.rules_to_deactivate.append(rule_key)
                            st.rerun()

                    # Commit Section
                    if st.session_state.rules_to_deactivate:
                        st.warning(f"⚠️ {len(st.session_state.rules_to_deactivate)} rules marked for deactivation.")
                        c_col1, c_col2 = st.columns([2, 8])
                        if c_col1.button("💾 Save Changes", type="primary"):
                            full_table_path = f"{cat_input}.{schema_name}.{selected_table}"
                            
                            for key in st.session_state.rules_to_deactivate:
                                # Find the original row to get the actual rule_id for the SQL query
                                match = df_mappings[
                                    (df_mappings['column'] + "_" + df_mappings['rule_id']) == key
                                ]
                                
                                if not match.empty:
                                    row_to_kill = match.iloc[0]
                                    # Pass the hidden rule_id to the database function
                                    deactivate_dq_rule(
                                        cat_input, 
                                        config_schema_input, 
                                        full_table_path, 
                                        row_to_kill['column'], 
                                        row_to_kill['rule_id']
                                    )
                            
                            st.session_state.rules_to_deactivate = []
                            fetch_dqx_mappings.clear()
                            st.success("Rules updated successfully!")
                            st.rerun()
                        
                        if c_col2.button("Undo All"):
                            st.session_state.rules_to_deactivate = []
                            st.rerun()

                else:
                    st.info("No DQX mappings found for this table.")

                st.divider()
                st.subheader("🚀 Execution")
                
                run_disabled = df_mappings.empty
                if st.button("Run DQX Checks", type="primary", disabled=run_disabled, key="run_checks_btn"):
                    with st.spinner("Triggering Workflow..."):
                        response = trigger_workflow(cat_input, config_schema_input, schema_name, selected_table)
                        if response.status_code == 200:
                            st.success(f"✅ Triggered! Run ID: {response.json().get('run_id')}")
                        else:
                            st.error(f"Failed to trigger: {response.text}")

            # --- VIEW 4: ADD NEW DQ Rules ---
            elif active_tab == "✅ ADD NEW DQ Rules":
                # --- NEW: Reset/Refresh Section ---
                r_col_a, r_col_b = st.columns([8, 2])
                r_col_a.info("Configure rules. Use **+** to add multiple rules per column and **-** to remove rows. Use 🗑️ to hide a column.")
                
                # Logic to clear all input-related keys and hidden columns
                if r_col_b.button("🧹Reset", use_container_width=True):
                    st.session_state.column_rule_counts = {}
                    if "hidden_columns" in st.session_state:
                        st.session_state.hidden_columns = set()
                    
                    keys_to_clear = [k for k in st.session_state.keys() if any(prefix in k for prefix in ["dim_t4_", "rule_t4_", "crit_t4_", "args_t4_"])]
                    for key in keys_to_clear:
                        del st.session_state[key]
                    
                    fetch_rule_dimensions.clear()
                    fetch_rule_definitions.clear()
                    fetch_columns.clear()
                    st.rerun()

                # Initialize hidden columns set
                if "hidden_columns" not in st.session_state:
                    st.session_state.hidden_columns = set()

                dimensions = fetch_rule_dimensions(cat_input, config_schema_input)
                df_rules = fetch_rule_definitions(cat_input, config_schema_input)
                df_columns = fetch_columns(cat_input, schema_name, selected_table)
                
                if df_rules.empty or df_columns.empty:
                    st.warning("Metadata missing. Please check if rules are defined in the config schema.")
                else:
                    # Header
                    h_col1, h_col2, h_col3, h_col4, h_col5, h_col6, h_col7 = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
                    h_col1.write("**Column**")
                    h_col2.write("**Dimension**")
                    h_col3.write("**Rule**")
                    h_col4.write("**Criticality**")
                    h_col5.write("**Args (JSON)**")
                    h_col6.write("**+**")
                    h_col7.write("**-**")
                    st.divider()

                    bulk_configs = []

                    for idx, row in df_columns.iterrows():
                        col_name = row['col_name']
                        
                        # Skip if user "removed" the column
                        if col_name in st.session_state.hidden_columns:
                            continue

                        if col_name not in st.session_state.column_rule_counts:
                            st.session_state.column_rule_counts[col_name] = 1
                        
                        for i in range(st.session_state.column_rule_counts[col_name]):
                            row_key = f"t4_{col_name}_{i}"
                            r_col1, r_col2, r_col3, r_col4, r_col5, r_col6, r_col7 = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
                            
                            # 1. Column Display
                            if i == 0:
                                col_display = r_col1.columns([0.3, 0.7])
                                if col_display[0].button("🗑️", key=f"hide_{col_name}", help=f"Hide {col_name}"):
                                    st.session_state.hidden_columns.add(col_name)
                                    st.rerun()
                                col_display[1].markdown(f"**{col_name}**")
                            else:
                                r_col1.markdown(f"↳ *{col_name}*")
                            
                            # 2. Dimension & Rule Selection
                            selected_dim = r_col2.selectbox("Dim", options=["All"] + dimensions, label_visibility="collapsed", key=f"dim_{row_key}")
                            rule_mask = [True]*len(df_rules) if selected_dim == "All" else df_rules['rule_dimension'] == selected_dim
                            current_rule_list = ["-- Skip --"] + df_rules[rule_mask]['rule_info'].tolist()
                            selected_rule = r_col3.selectbox("Rule", options=current_rule_list, label_visibility="collapsed", key=f"rule_{row_key}")

                            # 3. CRITICALITY DROP DOWN
                            crit = r_col4.selectbox(
                                "Crit", 
                                options=["error", "warn"], 
                                index=0, 
                                label_visibility="collapsed", 
                                key=f"crit_{row_key}"
                            )
                            
                            # 4. Dynamic Placeholder & Arguments
                            placeholder_val = '{"key": "value"}'
                            if selected_rule != "-- Skip --":
                                rid = selected_rule.split(" - ")[0].strip()
                                match = df_rules[df_rules['rule_id'].astype(str) == rid]
                                if not match.empty:
                                    placeholder_val = match.iloc[0]['argument_placeholder']

                            args = r_col5.text_input("Args", placeholder=placeholder_val, label_visibility="collapsed", key=f"args_{row_key}")

                            # Row Add/Remove Logic
                            if r_col6.button("➕", key=f"add_{row_key}"):
                                st.session_state.column_rule_counts[col_name] += 1
                                st.rerun()

                            if st.session_state.column_rule_counts[col_name] > 1:
                                if r_col7.button("➖", key=f"rem_{row_key}"):
                                    st.session_state.column_rule_counts[col_name] -= 1
                                    st.rerun()

                            if selected_rule != "-- Skip --":
                                bulk_configs.append({
                                    "col_name": col_name,
                                    "rule_id": selected_rule.split(" - ")[0].strip(),
                                    "criticality": crit,
                                    "arg_str": args
                                })
                    
                    st.divider()
                    
                    # --- Save Logic (Updated for List) ---
                    st.subheader("💾 Save Configuration")
                    if not bulk_configs:
                        st.warning("No rules selected.")
                    else:
                        st.write(f"✅ Ready to register **{len(bulk_configs)}** total rules.")
                        
                        if st.button("Register Rules", type="primary", key="bulk_reg_btn"):
                            success_count = 0
                            error_logs = []

                            with st.spinner("Registering rules..."):
                                for entry in bulk_configs:
                                    # JSON Parsing
                                    arg_dict = {}
                                    if entry['arg_str'].strip():
                                        try:
                                            arg_dict = json.loads(entry['arg_str'])
                                        except Exception as ex :
                                            error_logs.append(f"❌ {entry['col_name']}: Invalid JSON.: {ex}")
                                            continue
                                    
                                    # Registration
                                    success, message = register_dq_rule(
                                        catalog=cat_input,
                                        config_schema=config_schema_input,
                                        src_schema_name=schema_name,
                                        table_name=selected_table,
                                        column_name=entry['col_name'],
                                        rule_id=entry['rule_id'],
                                        criticality=entry['criticality'],
                                        arguments_dict=arg_dict
                                    )

                                    if success: success_count += 1
                                    else: error_logs.append(f"❌ {entry['col_name']}: {message}")

                            if success_count > 0:
                                st.success(f"Registered {success_count} rules!")
                                fetch_dqx_mappings.clear()

                                # --- Display updated DQX mappings and allow execution of DQX checks ---
                                df_mappings_updated = fetch_dqx_mappings(cat_input, config_schema_input, schema_name, selected_table)
                                selected_cols = ["column", "rule_dimension", "rule_name", "rule_description", "criticality", "arguments"]
                                if not df_mappings_updated.empty:
                                    st.dataframe(df_mappings_updated[selected_cols], use_container_width=True, hide_index=True)
                                else:
                                    st.info("No DQX mappings found for this table.")
                                
                                st.divider()
                                st.subheader("🚀 Execution")
                                if st.button("Run DQX Checks", type="primary"):
                                    with st.spinner("Triggering..."):
                                        response = trigger_workflow(cat_input, config_schema_input, schema_name, selected_table)
                                        if response.status_code == 200:
                                            st.success(f"✅ Triggered! Run ID: {response.json().get('run_id')}")
                                        else:
                                            st.error(response.text)

                            for err in error_logs:
                                st.error(err)
                            
                
                            
except Exception as e:
    st.error(f"Error: {e}")
