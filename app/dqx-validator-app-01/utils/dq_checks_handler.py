from databricks.connect import DatabricksSession
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.config import LLMModelConfig,InputConfig
from databricks.labs.dqx.profiler.generator import DQGenerator


class dqx_handler:
    def __init__(self):
        try:
            DatabricksSession.builder.getOrCreate().stop()
        except:
            pass
        self.spark = DatabricksSession.builder.serverless().getOrCreate()
        self.ws = WorkspaceClient()
        self.profiler = DQProfiler(workspace_client=self.ws)
        # 1. Create an LLMConfig object first
        self.llm_cfg = LLMModelConfig("databricks/databricks-meta-llama-3-1-8b-instruct")
        self.generator = DQGenerator(self.ws, llm_model_config=self.llm_cfg)

    def profile_check(self, input_table_name, columns_list=[]):
        summary_stats, profiles = self.profiler.profile_table(
            input_config=InputConfig(location=input_table_name),
            columns=columns_list
        )
        return summary_stats, profiles
    
    def generate_profile_checks(self, summary_stats, profiles):
        return self.generator.generate_dq_rules(profiles)
    
    def ai_assisted_rule_generation(self, user_prompt, input_table_name):
        return self.generator.generate_dq_rules_ai_assisted(
            user_input=user_prompt,
            input_config=InputConfig(location=input_table_name)
        )


if __name__ == "__main__":
    handler = dqx_handler()
    tbl = 'dqx_sandbox.dqx_bronze.customer'
    res_summary_stats, res_profiles = handler.profile_check(tbl, ["customer_state"])
    checks = handler.generate_profile_checks(res_summary_stats, res_profiles)
    inp = """
    Phone numbers should follow standard format.
    customer_email is valid.
    customer_state is a string with less than 5 letter.
    """
    print(res_summary_stats)
    print(handler.ai_assisted_rule_generation(inp,tbl))

