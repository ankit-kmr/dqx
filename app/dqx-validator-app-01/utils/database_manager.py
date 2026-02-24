from databricks import sql
import pandas as pd
import json

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

    def fetch_list(self, query):
        with self.get_connection().cursor() as cursor:
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]

    def fetch_dataframe(self, query):
        with self.get_connection().cursor() as cursor:
            cursor.execute(query)
            data = cursor.fetchall()
            if not data:
                return pd.DataFrame()
            return pd.DataFrame(data, columns=[desc[0] for desc in cursor.description])

    def execute_query(self, query):
        try:
            with self.get_connection().cursor() as cursor:
                cursor.execute(query)
            return True, "Success"
        except Exception as e:
            return False, str(e)

    def register_dq_rule(self, catalog, config_schema, src_schema_name, table_name, column_name, rule_id, criticality, arguments_dict):
        source_table_path = f"{catalog}.{src_schema_name}.{table_name}"
        
        if arguments_dict:
            map_items = []
            for k, v in arguments_dict.items():
                val_str = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                clean_val = val_str.replace("'", "''")
                clean_key = str(k).replace("'", "''")
                map_items.append(f"'{clean_key}', '{clean_val}'")
            map_sql = f"map({', '.join(map_items)})"
        else:
            map_sql = "CAST(NULL AS MAP<STRING, STRING>)"

        merge_query = f"""
        MERGE INTO {catalog}.{config_schema}.dqx_rule_mappings AS target
        USING (
            SELECT '{source_table_path}' AS table_name, '{rule_id}' AS rule_id, '{column_name}' AS column_name,
                   '{criticality}' AS criticality, true AS is_active, {map_sql} AS arguments, current_timestamp() AS updated_at
        ) AS source
        ON target.table_name = source.table_name AND target.rule_id = source.rule_id AND target.column_name = source.column_name
        WHEN MATCHED THEN UPDATE SET criticality = source.criticality, is_active = source.is_active, 
                                     arguments = source.arguments, updated_at = source.updated_at
        WHEN NOT MATCHED THEN INSERT (table_name, rule_id, column_name, criticality, is_active, arguments, updated_at)
        VALUES (source.table_name, source.rule_id, source.column_name, source.criticality, source.is_active, source.arguments, source.updated_at)
        """
        return self.execute_query(merge_query)
