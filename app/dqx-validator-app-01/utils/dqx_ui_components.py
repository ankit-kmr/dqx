import streamlit as st
import json
import pandas as pd
from datetime import date, datetime

class DqxUIComponents:
    def __init__(self, db_manager, dqx_h):
        self.db = db_manager
        self.dqx = dqx_h

    @staticmethod
    def json_serial(obj):
        """Static method to handle date/datetime serialization in JSON."""
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        # If the object has a __dict__, try to serialize that (for DQX objects)
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        raise TypeError(f"Type {type(obj)} not serializable")

    def render_profile_generator(self, cat, schema, table):
        columns_df = self.db.fetch_columns(cat, schema, table)
        column_list = columns_df['col_name'].tolist()
        res_summary_stats, res_profiles = self.dqx.profile_check(f"{cat}.{schema}.{table}", column_list)

        st.subheader("Summary Stats")
        st.dataframe(pd.DataFrame(res_summary_stats))
        
        # Use the class method via 'default'
        summary_stats_json = json.dumps(res_summary_stats, indent=2, default=self.json_serial)
        
        st.download_button(
            label="Download Summary Stats (JSON)",
            data=summary_stats_json,
            file_name="summary_stats.json",
            mime="application/json",
            key="summary_stats_download",
        )
        st.markdown(
            """
            <style>
            [data-testid="stDownloadButton-summary_stats_download"] button {
                background-color: #87ceeb !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Profiles")
        # Simplified: DataFrame and JSON will both use the serializing logic
        st.dataframe(pd.DataFrame([p.__dict__ for p in res_profiles]))
        
        profiles_json = json.dumps(res_profiles, indent=2, default=self.json_serial)
        
        st.download_button(
            label="Download Profiles (JSON)",
            data=profiles_json,
            file_name="profiles.json",
            mime="application/json"
        )
        
        if st.button("Generate Check"):
            profile_checks = self.dqx.generate_profile_checks(res_summary_stats, res_profiles)
            st.subheader("Generate Checks")
            st.dataframe(pd.DataFrame(profile_checks), use_container_width=True)
            
            profile_checks_json = json.dumps(profile_checks, indent=2, default=self.json_serial)
            
            st.download_button(
                label="Download Profile Checks (JSON)",
                data=profile_checks_json,
                file_name="profile_checks.json",
                mime="application/json"
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
