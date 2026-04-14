from dq_checks_handler import dqx_handler
from dqx_ui_components import DqxUIComponents
from database_manager import DatabaseManager
from workflow_manager import WorkflowManager
import configparser



config_catalog = 'dqx_sandbox'
config_schema = 'dqx_config'
tbl = 'dqx_sandbox.dqx_bronze.order'
inp = """
Phone numbers should follow standard format.
customer_email is valid.
customer_state is a string with less than 5 letter.
"""


env = 'DEV'
config = configparser.ConfigParser()
config.read('/Workspace/Repos/dev.databricks26@gmail.com/dqx/app/dqx-validator-app-01/config.conf')
# Extract variables based on selection
HOST = config.get(env, 'server_hostname')
PATH = config.get(env, 'http_path')
TOKEN = config.get(env, 'token')
job_id = config.get(env, 'job_id')

db_manager = DatabaseManager(HOST, PATH, TOKEN)
wm = WorkflowManager(HOST, TOKEN, job_id)

# res = wm.trigger_workflow(config_catalog, 'dqx_sandbox', config_schema, 'dqx_bronze', 'product')
# print(res.json())

res_status = wm.get_run_status('157119592770214')
print(res_status.json())

# handler = dqx_handler()
# dqx_ui = DqxUIComponents(db_manager, handler, config_catalog , config_schema)

# res_summary_stats, res_profiles = handler.load_profile_data(tbl, ["product_id","product_name"])
# profile_checks = handler.generate_profile_checks(res_profiles,tbl)
# print("profile_checks == ",profile_checks)

# bulk_config = dqx_ui.create_bulk_configs(
#     profile_checks, 
#     db_manager.fetch_rule_definitions(config_catalog, config_schema)
# )
# print("bulk_config == ",bulk_config)


