import streamlit as st
import json
import pandas as pd
from datetime import date, datetime
import yaml


class DqxUIComponents:
    def __init__(self, db_manager, dqx_h):
        self.db = db_manager
        self.dqx = dqx_h


    def render_profile_generator(self, cat, schema, table):
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
        btn_col1, btn_col2, _ = st.columns([2, 2, 4])
        
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
                st.subheader("✅ Profile Checks")
                st.dataframe(pd.DataFrame(profile_checks), use_container_width=True)
                
                profile_checks_json = json.dumps(profile_checks, indent=2, default=self.dqx.json_serial)
                profile_checks_yaml = yaml.dump(profile_checks, default_flow_style=False)
                btn_col3, btn_col4 = st.columns(2)
                with btn_col3:
                    st.download_button(
                        label="📥 Download Profile Checks (JSON)",
                        data=profile_checks_json,
                        file_name="profile_checks.json",
                        mime="application/json"
                    )
                with btn_col4:
                    st.download_button(
                        label="📥 Download Profile Checks (YAML)",
                        data=profile_checks_yaml,
                        file_name="profile_checks.yaml",
                        mime="text/yaml",
                        type="secondary"
                    )

        
    def render_ai_check_generator(self, cat, schema, table):
        st.subheader("AI-Assisted Rule Generation")
        st.info("Describe your data quality requirements in natural language (e.g., 'Ensure emails follow a valid regex' or 'Salary cannot be negative').")

        columns_df = self.db.fetch_columns(cat, schema, table)
        column_list = columns_df['col_name'].tolist()

        # Slider for dynamic column width adjustment
        col_ratio = st.slider(
            "Adjust left/right column width",
            min_value=0.1,
            max_value=0.9,
            value=0.33,
            step=0.01,
            help="Adjust the proportion of left column (Table Columns) vs right column (AI Rule Generation)"
        )
        left_col, right_col = st.columns([col_ratio, 1 - col_ratio])

        with left_col:
            st.subheader("Table Columns")
            st.dataframe(columns_df, use_container_width=True)

        with right_col:
            # AI-detected primary key grid view
            st.subheader("AI Detected Primary Keys")
            try:
                primary_key_checks = self.dqx.ai_detect_primary_key(
                    input_table_name=f"{cat}.{schema}.{table}"
                )
                pk_display = [pk.__dict__ if hasattr(pk, '__dict__') else pk for pk in primary_key_checks]
                st.dataframe(pd.DataFrame(pk_display), use_container_width=True)
            except Exception as e:
                st.error(f"Error detecting primary keys: {str(e)}")

            # User input for natural language requirements
            user_prompt = st.text_area(
                "Requirement Prompt",
                placeholder="Email addresses must be valid.\nPhone numbers should follow standard format.",
                height=150,
                key="ai_prompt_input"
            )

            if st.button("Generate AI Rules", type="primary"):
                if not user_prompt.strip():
                    st.warning("Please enter some requirements first.")
                    return

                with st.spinner("AI is analyzing table context and generating rules..."):
                    try:
                        # Call the AI generation method
                        ai_rules = self.dqx.ai_assisted_rule_generation(
                            user_prompt=user_prompt,
                            input_table_name=f"{cat}.{schema}.{table}"
                        )

                        # Display Results
                        st.success("Rules generated successfully!")
                        st.subheader("Generated AI Rules")
                        
                        # Convert rule objects to dicts for dataframe display
                        rules_display = [r.__dict__ if hasattr(r, '__dict__') else r for r in ai_rules]
                        st.dataframe(pd.DataFrame(rules_display), use_container_width=True)

                        # Download option for the AI rules
                        ai_rules_json = json.dumps(ai_rules, indent=2, default=self.json_serial)
                        st.download_button(
                            label="Download AI Rules (JSON)",
                            data=ai_rules_json,
                            file_name=f"ai_rules_{table}.json",
                            mime="application/json",
                            key="ai_rules_download"
                        )

                    except Exception as e:
                        st.error(f"Error generating AI rules: {str(e)}")
                        if "ENDPOINT_NOT_FOUND" in str(e):
                            st.info("Check if your LLM Model name in dqx_handler is correct (e.g., 'databricks-claude-3-5-sonnet').")
