import streamlit as st
import json
import pandas as pd
from datetime import date, datetime
import yaml


class DqxUIComponents:
    def __init__(self, db_manager, dqx_h , config_catalog , config_schema):
        self.db = db_manager
        self.dqx = dqx_h
        self.config_catalog = config_catalog
        self.config_schema = config_schema
        

    def create_bulk_configs(self, profile_checks):
        bulk_configs = []
        # 2. Clear Streamlit cache before fetching fresh data
        self.db.fetch_rule_definitions.clear()
        rule_definitions_df = self.db.fetch_rule_definitions(self.config_catalog, self.config_schema)
        
        for check in profile_checks:
            if isinstance(check, dict) and "check" in check:
                check_obj = check["check"]
                rule_func = check_obj.get('function')
                crit = check.get("criticality")
                args = check_obj.get("arguments", {})
                rid = None
                col_name = args.get("column") or args.get("columns")

                if rule_definitions_df is not None and rule_func:
                    rule_row = rule_definitions_df.loc[
                        rule_definitions_df['rule_function'].str.lower() == rule_func.lower()
                    ]
                    if not rule_row.empty:
                        rid = rule_row.iloc[0]['rule_id']
                bulk_configs.append({
                    "col": col_name,
                    "rid": rid,
                    "crit": crit,
                    "args": args,
                    "name": check.get("name"),
                    "user_metadata": check.get("user_metadata")
                })
        return bulk_configs


    def render_profile_rule_generator(self, cat, schema, table):
        full_table_name = f"{cat}.{schema}.{table}"
        columns_df = self.db.fetch_columns(cat, schema, table)
        all_columns = columns_df['col_name'].tolist()

        st.subheader(f"Profiling Configuration: {full_table_name}")

        # Top right reset button
        _, reset_col = st.columns([9, 1])
        with reset_col:
            if st.button("🔄 Reset", key=f"reset_{full_table_name}", type="secondary"):
                st.session_state[f"profile_cols_{full_table_name}"] = all_columns.copy()
                st.rerun()

        # 1. Table Structure with Delete Buttons
        st.markdown("### Select Columns to Profile")
        
        # Use session state to track columns
        if f"profile_cols_{full_table_name}" not in st.session_state:
            st.session_state[f"profile_cols_{full_table_name}"] = all_columns.copy()
        profile_columns = st.session_state[f"profile_cols_{full_table_name}"]

        # Header
        h_col1, h_col2 = st.columns([4, 1])
        h_col1.write("**Column Name**")
        h_col2.write("**Action**")

        for col in profile_columns:
            row_col1, row_col2 = st.columns([4, 1])
            row_col1.text(col)
            if row_col2.button("Delete", key=f"delete_{col}"):
                profile_columns.remove(col)
                st.session_state[f"profile_cols_{full_table_name}"] = profile_columns
                st.rerun()

        selected_columns = profile_columns.copy()
        st.divider()

        # 2. Action Buttons
        btn_col1, btn_col2, _, _ = st.columns([2, 2, 2, 4])
        
        gen_pressed = btn_col1.button("Generate Profile Summary", type="primary", use_container_width=True)
        save_pressed = btn_col2.button("Save Profile Summary", use_container_width=True, type="secondary")

        # 3. Save Logic
        if save_pressed:
            with st.spinner("Refreshing profile data..."):
                self.dqx.save_profile_data(full_table_name, columns_list=all_columns)
                st.success(f"Profile data for {full_table_name} updated successfully!")

        
        # 4. Generate/Display Logic
        if gen_pressed:
            if not selected_columns:
                st.error("Please select at least one column.")
                return

            with st.spinner("Generating profiles..."):
                res_summary_stats, res_profiles = self.dqx.load_profile_data(full_table_name, selected_columns)
                profile_checks = self.dqx.generate_profile_checks(res_profiles, full_table_name)

                # 1. Insert new rules
                self.db.insert_rules(self.config_catalog, self.config_schema, profile_checks)
                
                # --- SAVE TO SESSION STATE TO PERSIST AFTER CLICKING OTHER BUTTONS ---
                st.session_state[f"active_profile_checks_{full_table_name}"] = profile_checks
                st.session_state[f"active_summary_stats_{full_table_name}"] = res_summary_stats
                st.session_state[f"bulk_configs_{full_table_name}"] = self.create_bulk_configs(
                    profile_checks
                )

        # 5. Display Logic (Triggered if data exists in Session State)
        if f"active_profile_checks_{full_table_name}" in st.session_state:
            profile_checks = st.session_state[f"active_profile_checks_{full_table_name}"]
            res_summary_stats = st.session_state[f"active_summary_stats_{full_table_name}"]

            # Display Summary Stats
            st.subheader("📊 Summary Stats")
            st.dataframe(pd.DataFrame(res_summary_stats), use_container_width=True)
            
            summary_stats_json = json.dumps(res_summary_stats, indent=2, default=self.dqx.json_serial)
            btn_col1, _ = st.columns(2)
            with btn_col1:
                st.download_button(
                    label="📥 Download Summary Stats (JSON)",
                    data=summary_stats_json,
                    file_name="summary_stats.json",
                    mime="application/json"
                )

            st.divider()

            # Display Profile Checks
            st.subheader("✅ Profile Inferred Rules")
            st.dataframe(pd.DataFrame(profile_checks), use_container_width=True)
            
            btn_col3, btn_col4, _ = st.columns([1, 1, 0.1])
            with btn_col3:
                st.download_button(
                    label="📥 Download Profile Checks (JSON)",
                    data=json.dumps(profile_checks, indent=2, default=self.dqx.json_serial),
                    file_name="profile_checks.json",
                    mime="application/json"
                )
            with btn_col4:
                st.download_button(
                    label="📥 Download Profile Checks (YAML)",
                    data=yaml.dump(profile_checks, default_flow_style=False),
                    file_name="profile_checks.yaml",
                    mime="text/yaml"
                )

            st.divider()

            # 6. Bulk Save Logic (Moved outside the nested IF)
            if st.button("💾 Save Rules ", use_container_width=True, type="primary"):
                bulk_configs = st.session_state.get(f"bulk_configs_{full_table_name}", [])
                
                with st.spinner("⏳ Inserting records into database..."):
                    try:
                        self.db.reg_multiple_dq_rule(
                            src_catalog=cat,
                            config_catalog=self.config_catalog,
                            config_schema=self.config_schema,
                            src_schema=schema,
                            table=table,
                            rules_data=bulk_configs
                        )
                        st.success(f"✅ Success! {len(bulk_configs)} profile checks saved to database.")
                    except Exception as e:
                        st.error(f"❌ Error saving bulk profile checks: {str(e)}")

  
    def render_ai_rule_generator(self, cat, schema, table):
        st.subheader("AI-Assisted Rule Generation")
        st.info("Describe your data quality requirements in natural language (e.g., 'Ensure emails follow a valid regex').")

        columns_df = self.db.fetch_columns(cat, schema, table)
        full_table_name = f"{cat}.{schema}.{table}"
        
        # Session State Keys
        rules_key = f"active_ai_rules_{full_table_name}"
        bulk_key = f"ai_bulk_configs_{full_table_name}"

        # Slider for dynamic column width adjustment
        col_ratio = st.slider(
            "Adjust left/right column width",
            min_value=0.1, max_value=0.9, value=0.33, step=0.01,
            help="Adjust the proportion of Table Columns vs AI Rule Generation"
        )
        left_col, right_col = st.columns([col_ratio, 1 - col_ratio])

        with left_col:
            st.subheader("Table Columns")
            st.dataframe(columns_df, use_container_width=True)

        with right_col:
            st.subheader("AI Detected Primary Keys")
            detect_col, _ = st.columns([1, 3])
            with detect_col:
                detect_pk_pressed = st.button("Detect Primary Key", key=f"detect_pk_{full_table_name}", type="primary")
            
            primary_key_checks = None
            if detect_pk_pressed:
                with st.spinner("Detecting primary key..."):
                    try:
                        primary_key_checks = self.dqx.ai_detect_primary_key(full_table_name)
                        st.session_state[f"pk_attempts_{full_table_name}"] = primary_key_checks
                    except Exception as e:
                        st.error(f"Error detecting primary keys: {str(e)}")
            else:
                primary_key_checks = st.session_state.get(f"pk_attempts_{full_table_name}", None)
            
            if primary_key_checks is not None:
                if isinstance(primary_key_checks, dict) and 'all_attempts' in primary_key_checks:
                    attempts_data = primary_key_checks['all_attempts']
                    st.dataframe(pd.DataFrame(attempts_data), use_container_width=True)
                else:
                    st.error("No result found.")

            # User input
            user_prompt = st.text_area(
                "Requirement Prompt",
                placeholder="Email addresses must be valid.",
                height=150,
                key="ai_prompt_input"
            )
            gen_pressed = st.button("Generate AI Rules", type="primary", key=f"gen_ai_rules_{full_table_name}")

            # --- PHASE 1: GENERATION
            if gen_pressed:
                if not user_prompt.strip():
                    st.warning("Please enter some requirements first.")
                else:
                    with st.spinner("AI is analyzing table context and generating rules..."):
                        try:
                            ai_rules = self.dqx.ai_assisted_rule_generation(
                                user_prompt=user_prompt,
                                input_table_name=full_table_name
                            )

                            # 1. Insert new rules
                            self.db.insert_rules(self.config_catalog, self.config_schema, ai_rules)

                            # Save to session state so they persist across reruns
                            st.session_state[rules_key] = ai_rules
                            st.session_state[bulk_key] = self.create_bulk_configs(
                                ai_rules
                            )
                            st.success("Rules generated successfully!")
                        except Exception as e:
                            st.error(f"Error generating AI rules: {str(e)}")
                            if "ENDPOINT_NOT_FOUND" in str(e):
                                st.info("Check if your LLM Model name in dqx_handler is correct.")

            # --- PHASE 2: PERSISTENT UI (Triggered if rules exist in session state) ---
            if rules_key in st.session_state:
                st.divider()
                st.subheader("Generated AI Rules")
                
                current_rules = st.session_state[rules_key]
                rules_display = [r.__dict__ if hasattr(r, '__dict__') else r for r in current_rules]
                st.dataframe(pd.DataFrame(rules_display), use_container_width=True)

                # Download Option
                st.download_button(
                    label="Download AI Rules (JSON)",
                    data=json.dumps(current_rules, indent=2, default=self.dqx.json_serial),
                    file_name=f"ai_rules_{table}.json",
                    mime="application/json",
                    key=f"dl_{full_table_name}"
                )
                st.download_button(
                    label="Download AI Rules (YAML)",
                    data=yaml.dump(current_rules, default_flow_style=False),
                    file_name=f"ai_rules_{table}.yaml",
                    mime="text/yaml",
                    key=f"dl_yaml_{full_table_name}"
                )

                # --- PHASE 3: SAVE TO DB ---
                if st.button("💾 Save AI Generated Checks", use_container_width=True, type="primary", key=f"save_btn_{full_table_name}"):
                    bulk_configs = st.session_state.get(bulk_key, [])
                    with st.spinner("⏳ Inserting AI-generated rules into database..."):
                        try:
                            self.db.reg_multiple_dq_rule(
                                src_catalog=cat,
                                config_catalog=self.config_catalog,
                                config_schema=self.config_schema,
                                src_schema=schema,
                                table=table,
                                rules_data=bulk_configs
                            )
                            st.success(f"✅ Success! {len(bulk_configs)} AI-generated rules saved to database.")
                            # Optional: Clear the state if you want the UI to reset after saving
                            del st.session_state[rules_key]
                        except Exception as e:
                            st.error(f"❌ Error saving AI-generated rules: {str(e)}")
