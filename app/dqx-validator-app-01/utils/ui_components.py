import streamlit as st
import json
import pandas as pd

class UIComponents:
    def __init__(self, db_manager, workflow_manager, config_schema):
        self.db = db_manager
        self.wm = workflow_manager
        self.config_schema = config_schema

    def render_table_overview(self, cat, schema, table):
        st.subheader("📋 Table Overview")
        overview = self.db.fetch_table_definition(cat, schema, table)
        st.text(overview)

    def render_column_details(self, cat, schema, table):
        st.subheader("🧬 Column Details")
        df = self.db.fetch_columns(cat, schema, table)
        st.dataframe(df, use_container_width=True, hide_index=True)

    def render_existing_rules(self, cat, schema, table):
        st.subheader("🛡️ Manage Active Rules")
        df_mappings = self.db.fetch_dqx_mappings(cat, self.config_schema, schema, table)
        
        if not df_mappings.empty:
            m_col1, m_col2, m_col3, m_col4 = st.columns([1.5, 2.5, 3, 0.8])
            m_col1.write("**Column**"); m_col2.write("**Rule Name**")
            m_col3.write("**Arguments**"); m_col4.write("**Action**")
            st.divider()

            for idx, m_row in df_mappings.iterrows():
                rule_key = f"{m_row['column']}_{m_row['rule_id']}"
                if rule_key in st.session_state.rules_to_deactivate:
                    continue
                
                r_col1, r_col2, r_col3, r_col4 = st.columns([1.5, 2.5, 3, 0.8])
                r_col1.text(m_row['column'])
                r_col2.info(f"**{m_row['rule_name']}**")
                r_col3.caption(str(m_row['arguments']) if m_row['arguments'] else "{}")
                
                if r_col4.button("❌", key=f"del_{idx}"):
                    st.session_state.rules_to_deactivate.append(rule_key)
                    st.rerun()

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
        if st.button("Run DQX Checks", type="primary", disabled=df_mappings.empty):
            resp = self.wm.trigger_workflow(cat, self.config_schema, schema, table)
            if resp.status_code == 200:
                st.success(f"✅ Triggered! Run ID: {resp.json().get('run_id')}")
            else:
                st.error(resp.text)

    def render_add_rules(self, cat, schema, table):
        st.subheader("✅ Configure New Rules")
        dims = self.db.fetch_rule_dimensions(cat, self.config_schema)
        df_rules = self.db.fetch_rule_definitions(cat, self.config_schema)
        df_cols = self.db.fetch_columns(cat, schema, table)

        bulk_configs = []
        h_cols = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
        for col, label in zip(h_cols, ["**Column**", "**Dimension**", "**Rule**", "**Criticality**", "**Args (JSON)**", "**+**", "**-**"]):
            col.write(label)
        st.divider()

        for idx, row in df_cols.iterrows():
            col_name = row['col_name']
            if col_name in st.session_state.hidden_columns: continue
            if col_name not in st.session_state.column_rule_counts:
                st.session_state.column_rule_counts[col_name] = 1

            for i in range(st.session_state.column_rule_counts[col_name]):
                row_key = f"t4_{col_name}_{i}"
                r_c1, r_c2, r_c3, r_c4, r_c5, r_c6, r_c7 = st.columns([2, 1.5, 2, 1.2, 2, 0.4, 0.4])
                
                if i == 0:
                    sub = r_c1.columns([0.3, 0.7])
                    if sub[0].button("🗑️", key=f"hide_{col_name}"):
                        st.session_state.hidden_columns.add(col_name); st.rerun()
                    sub[1].markdown(f"**{col_name}**")
                else:
                    r_c1.markdown(f"↳ *{col_name}*")

                sel_dim = r_c2.selectbox("Dim", options=["All"] + dims, label_visibility="collapsed", key=f"dim_{row_key}")
                mask = [True]*len(df_rules) if sel_dim == "All" else df_rules['rule_dimension'] == sel_dim
                sel_rule = r_c3.selectbox("Rule", options=["-- Skip --"] + df_rules[mask]['rule_info'].tolist(), label_visibility="collapsed", key=f"rule_{row_key}")
                crit = r_c4.selectbox("Crit", options=["error", "warn"], label_visibility="collapsed", key=f"crit_{row_key}")
                
                p_val = '{"key": "value"}'
                if sel_rule != "-- Skip --":
                    rid = sel_rule.split(" - ")[0].strip()
                    m = df_rules[df_rules['rule_id'].astype(str) == rid]
                    if not m.empty: p_val = m.iloc[0]['argument_placeholder']
                
                args = r_c5.text_input("Args", placeholder=p_val, label_visibility="collapsed", key=f"args_{row_key}")

                if r_c6.button("➕", key=f"add_{row_key}"):
                    st.session_state.column_rule_counts[col_name] += 1; st.rerun()
                if st.session_state.column_rule_counts[col_name] > 1 and r_c7.button("➖", key=f"rem_{row_key}"):
                    st.session_state.column_rule_counts[col_name] -= 1; st.rerun()

                if sel_rule != "-- Skip --":
                    bulk_configs.append({"col": col_name, "rid": sel_rule.split(" - ")[0].strip(), "crit": crit, "args": args})

        st.divider()
        if bulk_configs:
            st.write(f"Ready to register **{len(bulk_configs)}** rules.")
            if st.button("Register Rules", type="primary"):
                for entry in bulk_configs:
                    try:
                        a_dict = json.loads(entry['args']) if entry['args'].strip() else {}
                        self.db.register_dq_rule(cat, self.config_schema, schema, table, entry['col'], entry['rid'], entry['crit'], a_dict)
                    except Exception as e: st.error(f"Error {entry['col']}: {e}")
                st.cache_data.clear(); st.success("Rules Registered!"); st.rerun()