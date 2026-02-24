import streamlit as st

class AppLogic:
    def __init__(self, db_manager):
        self.db = db_manager

    @st.cache_data(ttl=600)
    def get_catalogs(_self):
        return _self.db.fetch_list("SHOW CATALOGS")

    @st.cache_data(ttl=600)
    def get_schemas(_self, catalog):
        return _self.db.fetch_list(f"SHOW SCHEMAS IN {catalog}")

    @st.cache_data(ttl=300)
    def get_tables(_self, catalog, schema):
        return _self.db.fetch_list(f"SHOW TABLES IN {catalog}.{schema}")

    def get_table_stats(self, catalog, schema, table):
        full_path = f"{catalog}.{schema}.{table}"
        with self.db.get_connection().cursor() as cursor:
            cursor.execute(f"DESCRIBE TABLE {full_path}")
            col_count = len(cursor.fetchall())
            cursor.execute(f"SELECT COUNT(*) FROM {full_path}")
            row_count = cursor.fetchone()[0]
        return f"Catalog: {catalog}\nTable: {table}\nColumns: {col_count}\nRows: {row_count}"