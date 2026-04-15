import streamlit as st
import json
import yaml
import pandas as pd
import time
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class UISubmitComponents:
    def __init__(self, db_manager, dqx_h , workflow_manager, config_catalog, config):
        self.db = db_manager
        self.wm = workflow_manager
        self.dqx = dqx_h
        self.config = config
        self.config_catalog = self.config.get('DEFAULT', 'dqx_catalog_name')
        self.config_schema = self.config.get('DEFAULT', 'dqx_config_schema')
    

    def send_success_email(self, recipient_email, run_id, run_url, table_name):
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = self.config.get('EMAIL', 'address')
        sender_password = self.config.get('EMAIL', 'password')

        subject = f"🚀 DQX Workflow Triggered: {table_name}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h3 style="color: #2e7d32;">DQX Execution Started</h3>
            <p>A Data Quality workflow has been successfully triggered for the table: <b>{table_name}</b>.</p>
            <hr>
            <p><b>Run Details:</b></p>
            <ul>
            <li><b>Run ID:</b> {run_id}</li>
            <li><b>Status:</b> Triggered</li>
            </ul>
            <p><a href="{run_url}" style="display: inline-block; padding: 10px 20px; background-color: #007bff; color: white; text-decoration: none; border-radius: 5px;">View Databricks Run</a></p>
            <p style="font-size: 0.8em; color: #666;">This is an automated notification from the DQX UI.</p>
        </body>
        </html>
        """

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)
            return True
        except Exception as e:
            st.error(f"Failed to send email: {e}")
            return False,str(e)


    def render_submit(self, cat, schema, table):
        st.divider()
        st.subheader("🏁 Final Review & Execution")

        # 1. Initialize variables to ensure they exist even if DB call fails
        rules_list = []
        has_rules = False

        # Fetch current mappings from DB
        dqx_mapped_df = self.db.fetch_dqx_mappings(self.config_catalog, self.config_schema, cat, schema, table)
        st.dataframe(dqx_mapped_df[["column", "rule_name", "rule_function", "criticality", "arguments"]])

        if isinstance(dqx_mapped_df, pd.DataFrame) and not dqx_mapped_df.empty:
            has_rules = True
            for _, row in dqx_mapped_df.iterrows():
                # Parse arguments safely
                raw_args = row.get('arguments', {})
                if isinstance(raw_args, list):
                    args = dict(raw_args)
                else:
                    args = raw_args
                check_dict = {
                    "criticality": row.get('criticality'),
                    "check": {
                        "function": row.get('rule_function'),
                        "arguments": {
                            k: (True if str(v).upper() == 'TRUE' 
                                else False if str(v).upper() == 'FALSE' 
                                else v) for k, v in args.items()
                        }
                    }
                }
                rules_list.append(check_dict)
        else:
            st.warning("No active rules found for this table.")

        # 2. Export Section
        st.markdown("### 📤 Export Configuration")
        exp_col1, exp_col2 = st.columns(2)
        
        with exp_col1:
            st.download_button(
                label="JSON Export",
                data=json.dumps(rules_list, indent=2, default=self.dqx.json_serial),
                file_name=f"dqx_{table}_config.json",
                mime="application/json",
                disabled=not has_rules
            )

        with exp_col2:
            st.download_button(
                label="YAML Export",
                data=yaml.dump(rules_list, sort_keys=False),
                file_name=f"dqx_{table}_config.yaml",
                mime="text/yaml",
                disabled=not has_rules
            )

        # 3. Execution Section
        st.subheader("🚀 Execution")
        if st.button("Run DQX Workflow", type="primary", disabled=not has_rules, use_container_width=True):
            with st.spinner("Triggering Workflow..."):
                try:
                    resp = self.wm.trigger_workflow(self.config_catalog, cat, self.config_schema, schema, table)
                    if resp.status_code == 200:
                        run_id = resp.json().get('run_id')
                        run_resp = self.wm.get_run_status(run_id)
                        run_page_url = run_resp.json().get('run_page_url')
                        
                        st.success(f"✅ Workflow Triggered! Run ID: {run_id}")
                        if run_page_url:
                            st.link_button("Open Databricks Run", run_page_url)

                            # Email Notification
                            if "email" in st.secrets:
                                self.send_success_email('dev.databricks26@gmail.com', run_id, run_page_url, f"{cat}.{schema}.{table}")
                                st.toast(f"Notification sent to {recipient}")
                    else:
                        st.error(f"Trigger failed: {resp.text}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

