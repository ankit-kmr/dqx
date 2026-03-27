from databricks.connect import DatabricksSession
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.config import InputConfig
from databricks.labs.dqx.profiler.generator import DQGenerator

class dqx_handler:
    def __init__(self):
        self.spark = DatabricksSession.builder.serverless().getOrCreate()
        self.ws = WorkspaceClient()
        self.profiler = DQProfiler(workspace_client=self.ws)

    def profile_check(self, input_table_name, columns_list=[]):
        summary_stats, profiles = self.profiler.profile_table(
            input_config=InputConfig(location=input_table_name),
            columns=columns_list
        )
        return summary_stats, profiles
    
    def generate_profile_checks(self, summary_stats, profiles):
        generator = DQGenerator(self.ws)
        return generator.generate_dq_rules(profiles)
    

if __name__ == "__main__":
    handler = dqx_handler()
    res_summary_stats, res_profiles = handler.profile_check("dqx_sandbox.dqx_bronze.customer", ["customer_state"])
    checks = handler.generate_profile_checks(res_summary_stats, res_profiles)
    print(res_summary_stats)
    print(res_profiles)
    print(checks)
