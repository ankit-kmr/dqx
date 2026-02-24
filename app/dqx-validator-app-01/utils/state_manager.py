import streamlit as st

class StateManager:
    @staticmethod
    def initialize():
        if "active_tab" not in st.session_state:
            st.session_state.active_tab = "📋 Table Overview"
        if "column_rule_counts" not in st.session_state:
            st.session_state.column_rule_counts = {}
        if "rules_to_deactivate" not in st.session_state:
            st.session_state.rules_to_deactivate = []
        if "hidden_columns" not in st.session_state:
            st.session_state.hidden_columns = set()

    @staticmethod
    def reset_portal():
        # Clear specific selection keys
        keys_to_reset = ["cat_select", "schema_select", "table_select"]
        for key in keys_to_reset:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear data logic states
        st.session_state.column_rule_counts = {}
        st.session_state.hidden_columns = set()
        st.session_state.rules_to_deactivate = []
        
        # Clear specific input widgets
        keys_to_clear = [k for k in st.session_state.keys() if any(prefix in k for prefix in ["dim_t4_", "rule_t4_", "crit_t4_", "args_t4_"])]
        for key in keys_to_clear:
            del st.session_state[key]
            
        st.cache_data.clear()
        st.rerun()