import streamlit as st
import json
import pandas as pd
import time
import re


class UIComponents:
    def __init__(self, db_manager, workflow_manager, config_catalog, config_schema):
        self.db = db_manager
        self.wm = workflow_manager
        self.config_catalog = config_catalog
        self.config_schema = config_schema

    def reset_configuration_form(self):
        # 1. Clear the structural and visibility states
        st.session_state.column_rule_counts = {}
        st.session_state.hidden_columns = set()
        st.session_state.rules_to_deactivate = []

        # 2. Clear all dynamic widget keys from session_state
        # This identifies keys starting with 'dim_', 'rule_', 'crit_', or 'args_'
        keys_to_delete = [
            key for key in st.session_state.keys() 
            if any(key.startswith(prefix) for prefix in ["dim_t4_", "rule_t4_", "crit_t4_", "args_t4_"])
        ]
        for key in keys_to_delete:
            del st.session_state[key]
        
        # 3. Force a rerun to refresh the UI
        st.rerun()
        
    def render_table_overview(self, cat, schema, table):
        st.subheader("📋 Table Overview")
        overview = self.db.fetch_table_definition(cat, schema, table)
        st.text(overview)

    def render_column_details(self, cat, schema, table):
        st.subheader("🧬 Column Details")
        df = self.db.fetch_columns(cat, schema, table)
        st.dataframe(df, use_container_width=True, hide_index=True)

    def render_manage_dq_mapping(self, cat, schema, table):
        st.subheader("🛡️ Active Rules")
        df_mappings = self.db.fetch_dqx_mappings(self.config_catalog, self.config_schema, cat, schema, table)
        
        # Determine if we have rules to run
        has_rules = not df_mappings.empty

        if has_rules:
            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns([1.5, 2.5, 3, 3, 0.8])
            m_col1.write("**Column**")
            m_col2.write("**Rule Name**")
            m_col3.write("**Description**")
            m_col4.write("**Arguments**")
            m_col5.write("**Action**")
            st.divider()

            for idx, m_row in df_mappings.iterrows():
                rule_key = f"{m_row['column']}_{m_row['rule_id']}"
                if rule_key in st.session_state.rules_to_deactivate:
                    continue
                
                r_col1, r_col2, r_col3, r_col4, r_col5 = st.columns([1.5, 2.5, 3, 3, 0.8])
                r_col1.text(m_row['column'])
                r_col2.info(f"**{m_row['rule_name']}**")
                r_col3.caption(m_row['rule_description'])
                r_col4.caption(str(m_row['arguments']) if m_row['arguments'] else "{}")
                
                if r_col5.button("❌", key=f"del_{idx}"):
                    st.session_state.rules_to_deactivate.append(rule_key)
                    st.rerun()

            # Handling Deactivation
            if st.session_state.rules_to_deactivate:
                st.warning(f"⚠️ {len(st.session_state.rules_to_deactivate)} rules marked for deactivation.")
                c1, c2 = st.columns([2, 8])
                if c1.button("💾 Save Changes", type="primary"):
                    full_path = f"{cat}.{schema}.{table}"
                    for key in st.session_state.rules_to_deactivate:
                        match = df_mappings[(df_mappings['column'] + "_" + df_mappings['rule_id']) == key]
                        if not match.empty:
                            row = match.iloc[0]
                            self.db.deactivate_dq_rule(cat, self.config_schema, full_path, row['column'], row['rule_id'])
                    st.session_state.rules_to_deactivate = []
                    st.cache_data.clear()
                    st.success("Updated!"); st.rerun()
                if c2.button("Undo All"):
                    st.session_state.rules_to_deactivate = []; st.rerun()
        else:
            st.info("No DQX mappings found.")

        st.divider()
        st.subheader("🚀 Execution")
        
        # THE FIX: Toggle 'disabled' based on whether df_mappings had data
        if st.button("Run DQX Checks", 
                     type="primary", 
                     disabled=not has_rules, 
                     help="No rules found to execute" if not has_rules else "Trigger Databricks Workflow"):
            
            with st.spinner("Triggering Workflow..."):
                resp = self.wm.trigger_workflow(self.config_catalog, cat, self.config_schema, schema, table)
                if resp.status_code == 200:
                    st.success(f"✅ Triggered! Run ID: {resp.json().get('run_id')}")
                else:
                    st.error(resp.text)

    def render_add_rules_mapping(self, cat, schema, table):
        st.subheader("✅ Configure New Rules Mapping")
        col_title, col_reset = st.columns([8, 2])
        if col_reset.button("🧹Clear", use_container_width=True, help="Clear all inputs and reset column visibility"):
            self.reset_configuration_form()
        # ---------------------------------------

        # 1. Fetch metadata needed for the form
        dims = self.db.fetch_rule_dimensions(self.config_catalog, self.config_schema)
        df_rules = self.db.fetch_rule_definitions(self.config_catalog, self.config_schema)
        df_cols = self.db.fetch_columns(cat, schema, table)

        bulk_configs = []
        all_args_filled = True
        
        # Table Header
        h_cols = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
        for col_ui, label in zip(h_cols, ["**Column**", "**Dimension**", "**Rule**", "**Criticality**", "**Args (JSON)**", "**+**", "**-**"]):
            col_ui.write(label)
        st.divider()

        # 2. Render Row-by-Row Configuration
        for idx, row in df_cols.iterrows():
            col_name = row['col_name']
            if col_name in st.session_state.get('hidden_columns', set()): 
                continue
            
            if col_name not in st.session_state.column_rule_counts:
                st.session_state.column_rule_counts[col_name] = 1

            for i in range(st.session_state.column_rule_counts[col_name]):
                row_key = f"t4_{col_name}_{i}"
                r_c1, r_c2, r_c3, r_c4, r_c5, r_c6, r_c7 = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
                
                # Column Name & Hide Logic
                if i == 0:
                    sub = r_c1.columns([0.3, 0.7])
                    if sub[0].button("🗑️", key=f"hide_{col_name}"):
                        st.session_state.hidden_columns.add(col_name)
                        st.rerun()
                    sub[1].markdown(f"**{col_name}**")
                else:
                    r_c1.markdown(f"↳ *{col_name}*")

                # Dropdowns and Inputs
                sel_dim = r_c2.selectbox("Dim", options=["All"] + dims, label_visibility="collapsed", key=f"dim_{row_key}")
                mask = [True]*len(df_rules) if sel_dim == "All" else df_rules['rule_dimension'] == sel_dim
                
                sel_rule = r_c3.selectbox("Rule", options=["-- Skip --"] + df_rules[mask]['rule_info'].tolist(), label_visibility="collapsed", key=f"rule_{row_key}")
                crit = r_c4.selectbox("Crit", options=["error", "warn"], label_visibility="collapsed", key=f"crit_{row_key}")
                
                # Dynamic Placeholder logic
                p_val = '{"key": "value"}'
                p_req = True
                if sel_rule != "-- Skip --":
                    rid = sel_rule.split(" - ")[0].strip()
                    m = df_rules[df_rules['rule_id'].astype(str) == rid]
                    if not m.empty: 
                        p_val = m.iloc[0]['argument_placeholder']
                        p_req = m.iloc[0]['is_arg_mendatory']
                
                # Dynamic Placeholder and Example Text Autofill
                example_text = f"e.g: {p_val}"
                # autofill_key = f"autofill_{row_key}"
                args = r_c5.text_input("Args", placeholder=p_val, label_visibility="collapsed", key=f"args_{row_key}")
                r_c5.caption(example_text)

                # Add/Remove Row Buttons
                if r_c6.button("➕", key=f"add_{row_key}"):
                    st.session_state.column_rule_counts[col_name] += 1
                    st.rerun()
                if st.session_state.column_rule_counts[col_name] > 1 and r_c7.button("➖", key=f"rem_{row_key}"):
                    st.session_state.column_rule_counts[col_name] -= 1
                    st.rerun()

                # Collect configuration if rule is selected
                if sel_rule != "-- Skip --":
                    is_valid_json = True
                    try:
                        if args.strip():
                            json.loads(args)
                    except ValueError:
                        is_valid_json = False

                    if not args.strip() and p_req==True:
                        r_c5.error("Required ⚠️")
                        all_args_filled = False
                    elif not is_valid_json:
                        r_c5.error("Invalid JSON ❌")
                        all_args_filled = False
                    else:
                        bulk_configs.append({
                            "col": col_name, 
                            "rid": sel_rule.split(" - ")[0].strip(), 
                            "crit": crit, 
                            "args": args if p_req else p_val
                        })

        st.divider()

        # 3. Registration Logic
        if bulk_configs:
            if not all_args_filled:
                st.warning("⚠️ Some selected rules are missing required Arguments. Please fill them to continue.")

            st.write(f"Ready to register **{len(bulk_configs)}** rules.")
            if st.button("Register Rules", type="primary", disabled=not all_args_filled):
                success_count = 0
                error_logs = []
                progress_bar = st.progress(0)
                # Using the empty string spinner as you requested
                with st.spinner(""):
                    total_rules = len(bulk_configs)
                    for entry in bulk_configs:
                        try:
                            # Validate JSON
                            a_dict = json.loads(entry['args']) if entry['args'].strip() else {}
                            
                            success, msg = self.db.register_dq_rule(
                                cat, self.config_schema, schema, table, 
                                entry['col'], entry['rid'], entry['crit'], a_dict
                            )
                            
                            if success:
                                success_count += 1
                            else:
                                error_logs.append(f"Error in {entry['col']}: {msg}")
                        except json.JSONDecodeError:
                            error_logs.append(f"Invalid JSON format for column: {entry['col']}")
                        except Exception as e:
                            error_logs.append(f"Unexpected error for {entry['col']}: {str(e)}")
                        
                        # Update progress bar (0.0 to 1.0)
                        progress_bar.progress((success_count + len(error_logs)) / total_rules)

                if success_count > 0:
                    self.db.fetch_dqx_mappings.clear() 
                    st.cache_data.clear()
                    st.session_state.show_execution_summary = True
                    st.success(f"Successfully registered {success_count} rules!")
                    time.sleep(1)
                    progress_bar.empty()
                    st.rerun()
                for err in error_logs:
                    st.error(err)

        # 4. Post-Registration: Display Table & Run Button
        if st.session_state.get("show_execution_summary"):
            st.info("💡 Review your changes below and trigger the workflow when ready.")
            st.subheader("🛡️ Active Rule Mappings")
            
            # Re-fetch the newly registered rules
            df_mappings_updated = self.db.fetch_dqx_mappings(self.config_catalog, self.config_schema, cat, schema, table)
            selected_cols = ["column", "rule_dimension", "rule_name", "rule_description", "criticality", "arguments"]
            if not df_mappings_updated.empty:
                st.dataframe(df_mappings_updated[selected_cols], use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("🚀 Execution")
                if st.button("Run DQX Checks", type="primary", key="run_checks_final"):
                    with st.spinner("Connecting to Databricks..."):
                        response = self.wm.trigger_workflow(self.config_catalog, cat, self.config_schema, schema, table)
                        if response.status_code == 200:
                            run_id = response.json().get('run_id')
                            st.success(f"✅ Workflow Triggered Successfully! Run ID: `{run_id}`")
                        else:
                            st.error(f"Workflow Trigger Failed: {response.text}")
            else:
                st.warning("No mappings found. Please ensure the registration was successful.")

