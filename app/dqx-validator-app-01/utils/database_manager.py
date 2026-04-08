import streamlit as st
from databricks import sql
import pandas as pd
import json
import configparser


class DatabaseManager:
    def __init__(self, hostname, http_path, token):
        self.hostname = hostname
        self.http_path = http_path
        self.token = token

    def get_connection(self):
        return sql.connect(
            server_hostname=self.hostname,
            http_path=self.http_path,
            access_token=self.token
        )

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_catalogs(_self):
        with _self.get_connection().cursor() as cursor:
            cursor.execute("SHOW CATALOGS")
            return [row[0] for row in cursor.fetchall()]

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_schemas(_self, catalog_name):
        with _self.get_connection().cursor() as cursor:
            cursor.execute(f"SHOW SCHEMAS IN {catalog_name}")
            return [row[0] for row in cursor.fetchall()]

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_tables(_self, catalog, schema):
        with _self.get_connection().cursor() as cursor:
            cursor.execute(f"SHOW TABLES IN {catalog}.{schema}")
            table_data = cursor.fetchall()
            return [row[1] for row in table_data] if table_data else []

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_table_definition(_self, catalog, schema, table):
        with _self.get_connection().cursor() as cursor:
            cursor.execute(f"DESCRIBE TABLE {catalog}.{schema}.{table}")
            cols = cursor.fetchall()
            cursor.execute(f"SELECT COUNT(*) FROM {catalog}.{schema}.{table}")
            rows = cursor.fetchone()[0]
            return f"catalog_name: {catalog}\ntable_name: {table}\ntotal_columns: {len(cols)}\nrow_count: {rows}"

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_columns(_self, catalog, schema, table):
        with _self.get_connection().cursor() as cursor:
            cursor.execute(f"DESCRIBE TABLE {catalog}.{schema}.{table}")
            data = cursor.fetchall()
            if not data: return pd.DataFrame()
            df = pd.DataFrame(data).iloc[:, [0, 1]]
            df.columns = ['col_name', 'data_type']
            return df

    @st.cache_data(ttl=30, show_spinner=False)
    def fetch_dqx_mappings(_self, catalog, config_schema, src_catalog, src_schema, table):
        query = f"""
        WITH ranked_rules AS (
            SELECT m.column_name AS column, r.rule_dimension, r.rule_name, r.description as rule_description,
                   m.criticality, m.arguments, m.is_active, m.rule_id,
                   ROW_NUMBER() OVER (PARTITION BY m.table_name, m.column_name, r.rule_function ORDER BY m.updated_at DESC) as row_num
            FROM {catalog}.{config_schema}.dqx_rule_mappings m
            JOIN {catalog}.{config_schema}.dqx_rule_definitions r ON m.rule_id = r.rule_id
            WHERE m.table_name = '{src_catalog}.{src_schema}.{table}' AND m.is_active = true
        ) SELECT * FROM ranked_rules WHERE row_num = 1
        """
        with _self.get_connection().cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=[d[0] for d in cursor.description]) if data else pd.DataFrame()

    @st.cache_data(ttl=900, show_spinner=False)
    def fetch_rule_definitions(_self, catalog, config_schema):
        query = f"SELECT rule_id, rule_function, rule_name, rule_dimension, argument_placeholder, is_arg_mendatory, CONCAT(rule_id, ' - ', rule_name) AS rule_info FROM {catalog}.{config_schema}.dqx_rule_definitions"
        with _self.get_connection().cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
            return pd.DataFrame(data, columns=[d[0] for d in cursor.description]) if data else pd.DataFrame()

    @st.cache_data(ttl=1200, show_spinner=False)
    def fetch_rule_dimensions(_self, catalog, config_schema):
        query = f"SELECT DISTINCT rule_dimension FROM {catalog}.{config_schema}.dqx_rule_definitions WHERE rule_dimension IS NOT NULL"
        with _self.get_connection().cursor() as cursor:
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]

    
    def _replace_placeholders(self, data, column_name):
        """Recursively replaces <col_name> with the actual column name."""
        if isinstance(data, str):
            return data.replace("<col_name>", column_name)
        elif isinstance(data, list):
            return [self._replace_placeholders(item, column_name) for item in data]
        elif isinstance(data, dict):
            return {k: self._replace_placeholders(v, column_name) for k, v in data.items()}
        return data
    
    
    def register_dq_rule(self, src_catalog, config_catalog, config_schema, src_schema, table, col, rule_id, criticality, args_dict):
        source_full_path = f"{src_catalog}.{src_schema}.{table}"
        
        # Replace <value> placeholders in the arguments dictionary
        if args_dict:
            args_dict = self._replace_placeholders(args_dict, col)

        if args_dict:
            # Escape single quotes for SQL safety and format the key-value pairs
            kv_pairs = []
            for k, v in args_dict.items():
                val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                val_escaped = val_str.replace("'", "''")
                kv_pairs.append(f"'{k}', '{val_escaped}'")
            
            map_sql = f"map({', '.join(kv_pairs)})"
        else:
            map_sql = "CAST(NULL AS MAP<STRING, STRING>)"
        
        merge_query = f"""
        MERGE INTO {config_catalog}.{config_schema}.dqx_rule_mappings AS target
        USING (SELECT '{source_full_path}' as table_name, '{rule_id}' as rule_id, '{col}' as column_name, '{criticality}' as criticality, true as is_active, {map_sql} as arguments, current_timestamp() as updated_at) AS source
        ON target.table_name = source.table_name AND target.rule_id = source.rule_id AND target.column_name = source.column_name
        WHEN MATCHED THEN UPDATE SET criticality = source.criticality, is_active = source.is_active, arguments = source.arguments, updated_at = source.updated_at
        WHEN NOT MATCHED THEN INSERT (table_name, rule_id, column_name, criticality, is_active, arguments, updated_at) VALUES (source.table_name, source.rule_id, source.column_name, source.criticality, source.is_active, source.arguments, source.updated_at)
        """
        try:
            with self.get_connection().cursor() as cursor: cursor.execute(merge_query)
            return True, "Success"
        except Exception as e: return False, str(e)


    def reg_multiple_dq_rule(self, src_catalog, config_catalog, config_schema, src_schema, table, rules_data):
        """
        rules_data: List of dicts, each dict contains keys:
            col, rid, crit, args
        """
        source_full_path = f"{src_catalog}.{src_schema}.{table}"
        values_sql = []
        for rule in rules_data:
            col = rule.get('col')
            rule_id = rule.get('rid')
            criticality = rule.get('crit')
            args_dict = rule.get('args')
            if args_dict:
                args_dict = self._replace_placeholders(args_dict, col)
                kv_pairs = []
                for k, v in args_dict.items():
                    val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                    val_escaped = val_str.replace("'", "''")
                    kv_pairs.append(f"'{k}', '{val_escaped}'")
                map_sql = f"map({', '.join(kv_pairs)})"
            else:
                map_sql = "CAST(NULL AS MAP<STRING, STRING>)"
            values_sql.append(
                f"SELECT '{source_full_path}' as table_name, '{rule_id}' as rule_id, '{col}' as column_name, '{criticality}' as criticality, true as is_active, {map_sql} as arguments, current_timestamp() as updated_at"
            )
        source_sql = " UNION ALL ".join(values_sql)
        merge_query = f"""
        MERGE INTO {config_catalog}.{config_schema}.dqx_rule_mappings AS target
        USING ({source_sql}) AS source
        ON target.table_name = source.table_name AND target.rule_id = source.rule_id AND target.column_name = source.column_name
        WHEN MATCHED THEN UPDATE SET criticality = source.criticality, is_active = source.is_active, arguments = source.arguments, updated_at = source.updated_at
        WHEN NOT MATCHED THEN INSERT (table_name, rule_id, column_name, criticality, is_active, arguments, updated_at) VALUES (source.table_name, source.rule_id, source.column_name, source.criticality, source.is_active, source.arguments, source.updated_at)
        """
        try:
            with self.get_connection().cursor() as cursor: cursor.execute(merge_query)
            return True, "Success"
        except Exception as e: return False, str(e)

        
    
    def deactivate_dq_rule(self, catalog, config_schema, full_table_path, col, rule_id):
        query = f"UPDATE {catalog}.{config_schema}.dqx_rule_mappings SET is_active = false, updated_at = current_timestamp() WHERE table_name = '{full_table_path}' AND column_name = '{col}' AND rule_id = '{rule_id}'"
        try:
            with self.get_connection().cursor() as cursor: cursor.execute(query)
            return True
        except: return False


if __name__ == "__main__":
    # --- 2. Load Config & Profile ---
    env = 'DEV'
    config = configparser.ConfigParser()
    config.read('/Workspace/Repos/dev.databricks26@gmail.com/dqx/app/dqx-validator-app-01/config.conf')
    # Extract variables based on selection
    HOST = config.get(env, 'server_hostname')
    PATH = config.get(env, 'http_path')
    TOKEN = config.get(env, 'token')
    db_manager = DatabaseManager(HOST, PATH, TOKEN)
    rule_defs_df = db_manager.fetch_rule_definitions('dqx_sandbox', 'dqx_config')
    print(rule_defs_df)
    
