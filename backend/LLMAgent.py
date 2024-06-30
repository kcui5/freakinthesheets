import os
import json
from TableAgent import *
from gpt_function_tools import *
from claude_function_tools import *

from openai import OpenAI
import boto3

# gpt_model_to_model_IDs = {
#     # Must start with 'gpt'
#     "gpt-4o": "gpt-4o",
#     "gpt-4-turbo": "gpt-4-turbo",
#     "gpt-4": "gpt-4",
#     "gpt-3.5": "gpt-3.5-turbo",
# }

# claude_model_to_model_IDs = {
#     # Must start with 'claude'
#     "claude-3.5": "anthropic.claude-3-5-sonnet-20240620-v1:0",
# }

model_to_model_IDs = {
    "gpt-4o": "gpt-4o",
    "gpt-4-turbo": "gpt-4-turbo",
    "gpt-4": "gpt-4",
    "gpt-3.5": "gpt-3.5-turbo",
    "claude-3.5": "anthropic.claude-3-5-sonnet-20240620-v1:0",
}

tools = {
    "get_instructions",
    "write_table",
    "read_table",
    "create_chart",
    "question",
    "other_instruction"
}

instruction_type_to_tool_name = {
    "WRITE": "write_table",
    "READ": "read_table",
    "CHART": "create_chart",
    "QUESTION": "question",
    "OTHER": "other_instruction",
}

# TODO: timeit measure latency of class methods
class LLMAgent:
    """LLMAgent is the orchestrated agent responsible for making LLM calls to plan and produce instructions"""

    def __init__(self, default_call="gpt", default_gpt_model="gpt-4o", default_claude_model="claude-3.5"):
        self.tools_to_models = {} # Maps tool's function name to model to use for that tool
        self.max_attempts = 7
        self.default_call = default_call # Either 'gpt' or 'claude'
        self.default_gpt_model = default_gpt_model
        self.default_claude_model = default_claude_model
        # self.openai_client = None
        # self.bedrock_client = None
        self.openai_client = OpenAI(organization=os.environ["OPENAI_ORG"])
        self.bedrock_client = boto3.client(service_name='bedrock-runtime', region_name='us-east-1',
                                aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                                aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
                                )
    
    def set_tools_to_models(self, key, value):
        """Sets the model to use for the given tool"""
        if key not in tools:
            print("Invalid tool!")
            return
        # if value not in gpt_model_to_model_IDs and value not in claude_model_to_model_IDs:
        if value not in model_to_model_IDs:
            print("Invalid model!")
            return
        self.tools_to_models[key] = value
        print("tools_to_models:", self.tools_to_models)

    def get_model_ID(self, tool_name):
        """Returns model ID to use for the given tool_name"""
        if tool_name in self.tools_to_models:
            model_name = self.tools_to_models[tool_name]
            # if model_name.startswith("gpt"):
            #     return gpt_model_to_model_IDs[model_name]
            # elif model_name.startswith("claude"):
            #     return claude_model_to_model_IDs[model_name]
            return model_to_model_IDs[model_name]
        else:
            if self.default_call == "gpt":
                model_name = self.default_gpt_model
                # return gpt_model_to_model_IDs[model_name]
                return model_to_model_IDs[model_name]
            elif self.default_call == "claude":
                model_name = self.default_claude_model
                # return claude_model_to_model_IDs[model_name]
                return model_to_model_IDs[model_name]
            else:
                print("Could not find LLM model to use")
        return ""
    
    def call_gpt(self, model_ID, user_msg_content, tool_name):
        """Call GPT on OpenAI"""
        tool, sys_msg = gpt_tools["gpt_" + tool_name]
        user_msg = {
            "role": "user",
            "content": user_msg_content
        }
        messages = [sys_msg, user_msg]

        response = self.openai_client.chat.completions.create(
            model=model_ID,
            messages=messages,
            tools=[tool],
            tool_choice="required",
        )
        print(response.choices[0].message)
        return response.choices[0].message
    
    def call_claude(self, model_ID, user_msg_content, tool_name):
        """Call Claude on AWS Bedrock"""
        tool, sys_msg = claude_tools["claude_" + tool_name]
        messages = [{"role": "user", "content": user_msg_content}]
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "system": sys_msg,
            "messages": messages,
            "max_tokens": 4000,
            "tools": [tool]
        })

        response = self.bedrock_client.invoke_model(body=body, modelId=model_ID)
        response_body = json.loads(response['body'].read())
        print(response_body['content'])
        return response_body['content']

    def get_instruction_args(self, tool_name, task, sheet_content, args_names, prev_response="", prev_response_error=""):
        """Gets instructions arguments.
        Returns success bool, error message, and args.
        """
        user_msg = "Table:\n" + sheet_content + f"\nEnd Table.\nInstructions:\n{task}"
        if prev_response:
            user_msg += f"\nYour previous response was {prev_response} which resulted in an error."
        if prev_response_error:
            user_msg += f"\nThe error was: {prev_response_error}"
        model_ID = self.get_model_ID(tool_name)
        if model_ID.startswith("gpt"):
            gpt_response = self.call_gpt(model_ID, user_msg, tool_name)
            tool_calls = gpt_response.tool_calls
            args_collection = [None for _ in range(len(args_names))]
            for i in range(len(tool_calls)):
                instruction_args = tool_calls[i].function.arguments
                print(f"{tool_name} function args:", instruction_args)
                args = json.loads(instruction_args)
                for j in range(len(args_names)):
                    if not args_collection[j]:
                        args_collection[j] = args[args_names[j]]
                    else:
                        if type(args_collection[j] == str):
                            args_collection[j] += " " + args[args_names[j]]
                        else:
                            args_collection[j] += args[args_names[j]]
                    if j > 0 and type(args_collection[j]) == list and type(args_collection[j-1]) == list:
                        if len(args_collection[j]) != len(args_collection[j-1]):
                            print("Invalid instructions")
                            return False, "Invalid instructions length", instruction_args
            if type(args_collection[0]) == str:
                return True, "", args_collection
            assert(type(args_collection[0] == list))
            instruction_args = []
            for i in range(len(args_collection[0])):
                curr_instruction = [args_collection[j][i] for j in range(len(args_names))]
                instruction_args.append(curr_instruction)
            return True, "", instruction_args
        elif model_ID.startswith("anthropic"):
            claude_response = self.call_claude(model_ID, user_msg, tool_name)
            # TODO: claude instructions
        else:
            print("Invalid LLM")
            return False, "Invalid LLM", ""

    def get_arg_names(self, instruction_type):
        if instruction_type == "get_instructions":
            return ["types", "instructions"]
        elif instruction_type == "WRITE":
            return ["rows", "columns", "values"]
        elif instruction_type == "READ":
            return ["rows", "columns"]
        elif instruction_type == "CHART":
            return ["arguments"]
        elif instruction_type == "QUESTION":
            return ["answer"]
        elif instruction_type == "OTHER":
            return ["body"]
    
    def act_streamer(self, task_prompt: str, sheet_id: str, sheet_range: str):
        """Attempts to complete given task prompt and streams outputs"""
        table_agent = TableAgent(sheet_id)
        sheet_content = table_agent.get_sheet_content(sheet_range)
        # 1. Get instructions
        prev_response = None
        prev_response_error = None
        instructions = None
        for attempt_num in range(1, self.max_attempts+1):
            try:
                print(f"Attempt {attempt_num} of get_instructions")
                success, error_msg, args = self.get_instruction_args("get_instructions", task_prompt, sheet_content, self.get_arg_names("get_instructions"), prev_response, prev_response_error)
                if not success:
                    assert(type(error_msg) == type(args) == str)
                    prev_response = args
                    prev_response_error = error_msg
                    print("Error in get_instructions", error_msg)
                    continue
                else:
                    instructions = args
                    break
            except:
                print("Error in get_instructions")
                continue
        print("Instructions:", instructions)
        print_instructions = " ".join([f"{instr[1]}" for instr in instructions])
        yield print_instructions

        # 2. Execute instructions
        need_to_push_sheet_content = False
        for instruction in instructions:
            print("Executing", instruction)
            yield f"Executing...\n{instruction[1]}"
            prev_response = None
            prev_response_error = None
            for attempt_num in range(1, self.max_attempts+1):
                try:
                    instruction_type = instruction[0]
                    instruction_command = instruction[1]
                    print(f"Attempt {attempt_num} of {instruction_type}: {instruction_command}")
                    if instruction_type == "INAPPROPRIATE":
                        yield "Sorry I can't help with that..."
                        break
                    if instruction_type not in instruction_type_to_tool_name:
                        print("Unrecognized instruction type")
                        break
                    
                    success, error_msg, args = self.get_instruction_args(instruction_type_to_tool_name[instruction_type], instruction_command, sheet_content, self.get_arg_names(instruction_type), prev_response, prev_response_error)
                    if not success:
                        assert(type(error_msg) == type(args) == str)
                        prev_response = args
                        prev_response_error = error_msg
                        print("Error:", error_msg)
                        continue
                    success, error_msg, result = table_agent.execute_instruction(instruction_type, args)
                    if not success:
                        assert(type(error_msg) == type(result) == str)
                        prev_response_error = error_msg
                        print("Error:", error_msg)
                        continue
                    if instruction_type == "WRITE":
                        need_to_push_sheet_content = True
                    yield result
                    break
                except Exception as e:
                    prev_response = None
                    prev_response_error = None
                    continue
        if need_to_push_sheet_content:
            table_agent.push_sheet_content(sheet_range)
