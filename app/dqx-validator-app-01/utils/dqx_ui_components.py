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
