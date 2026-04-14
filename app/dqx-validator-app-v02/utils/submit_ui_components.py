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
    def __init__(self, db_manager, dqx_h , workflow_manager, config_catalog, config_schema):
        self.db = db_manager
        self.wm = workflow_manager
        self.dqx = dqx_h
        self.config_catalog = config_catalog
        self.config_schema = config_schema
    

    def send_success_email(self, recipient_email, run_id, run_url, table_name):
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = st.secrets["email"]["address"]
        sender_password = st.secrets["email"]["password"]

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
            return False


    def render_submit(self, cat, schema, table):
        st.divider()
        st.subheader("🏁 Final Review & Execution")

        # 1. Fetch current mappings from DB
        dqx_mapped_df = self.db.fetch_dqx_mappings(self.config_catalog, self.config_schema, cat, schema, table)
        
        # Check if we have rules (assuming Spark/Databricks dataframe based on .collect())
        rows = dqx_mapped_df.collect()
        has_rules = len(rows) > 0
        rules_list = []

        if has_rules:
            for row in rows:
                args = {}
                if row['arguments']:
                    # Handle nested JSON strings within the arguments map
                    for k, v in row['arguments'].items():
                        try:
                            args[k] = json.loads(v)
                        except Exception:
                            args[k] = v
                
                check_dict = {
                    "criticality": row['criticality'],
                    "check": {
                        "function": row['rule_function'], # Ensure this matches your DB col name
                        "arguments": {
                            k: (True if str(v).upper() == 'TRUE' 
                                else False if str(v).upper() == 'FALSE' 
                                else v) for k, v in args.items()
                        }
                    }
                }
                rules_list.append(check_dict)

            # Preview the rules
            with st.expander(f"View Active Rules ({len(rules_list)})", expanded=False):
                st.write(rules_list)
        else:
            st.warning("No rules currently mapped for this table.")

        # 2. Export Section
        st.markdown("### 📤 Export Configuration")
        exp_col1, exp_col2 = st.columns(2)
        
        with exp_col1:
            st.download_button(
                label="JSON Export",
                data=json.dumps(rules_list, indent=2, default=self.dqx.json_serial),
                file_name=f"dqx_config_{table}.json",
                mime="application/json",
                disabled=not has_rules
            )

        with exp_col2:
            st.download_button(
                label="YAML Export",
                data=yaml.dump(rules_list, sort_keys=False),
                file_name=f"dqx_config_{table}.yaml",
                mime="text/yaml",
                disabled=not has_rules
            )

        # 3. Execution Section
        st.subheader("🚀 Execution")
        
        if st.button(
            "Run DQX Workflow", 
            type="primary", 
            disabled=not has_rules, 
            use_container_width=True,
            help="No rules found to execute" if not has_rules else "Trigger Databricks Workflow"
        ):
            with st.spinner("Triggering Workflow..."):
                try:
                    resp = self.wm.trigger_workflow(self.config_catalog, cat, self.config_schema, schema, table)
                    # Inside your Run Workflow button logic:
                    if resp.status_code == 200:
                        run_id = resp.json().get('run_id')
                        run_resp = self.wm.get_run_status(run_id)
                        run_page_url = run_resp.json().get('run_page_url')
                        
                        if run_page_url:
                            st.success(f"✅ Triggered!")
                            st.link_button("Open Databricks Run", run_page_url)

                            # SEND NOTIFICATION
                            user_email = st.session_state.get("user_email", "admin@example.com")
                            if self.send_success_email(user_email, run_id, run_page_url, f'{cat}.{schema}.{table}'):
                                st.toast(f"Notification sent to {user_email}")
                        else:
                            st.info(f"Triggered successfully. Run ID: {run_id}")
                    else:
                        st.error(f"Failed to trigger workflow: {resp.text}")
                except Exception as e:
                    st.error(f"Error calling Workflow Manager: {e}")
