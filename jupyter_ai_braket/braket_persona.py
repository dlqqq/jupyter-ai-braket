from jupyter_ai_persona_manager import BasePersona, PersonaDefaults
from jupyterlab_chat.models import Message
from langchain.agents import create_agent
from langchain_aws import ChatBedrockConverse
from botocore.exceptions import ClientError
import os
from .system_prompt import BRAKET_SYS_PROMPT_TEMPLATE

from langchain_mcp_adapters.client import MultiServerMCPClient  

AVATAR_PATH = os.path.join(os.path.dirname(__file__), "static", "braket_icon.svg")

# TODOs:
# - (DONE) handle authn errors
# - (DONE) figure out how to install https://github.com/petertilsen/amazon-braket-mcp-server
# - (DONE) connect agent to MCP server
# - implement chat memory
#
# Observations
# - get_device() does not work
# - visualize_circuit(): jupyter_ai_braket.amazon_braket_mcp_server.exceptions.CircuitCreationError: Error visualizing circuit: "The 'pylatexenc' library is required to use 'MatplotlibDrawer'. You can install it with 'pip install pylatexenc'."
#    2025-12-16 15:44:02.205 | ERROR    | __main__:create_quantum_circuit:117 - Error creating quantum circuit: Error creating circuit visualization: Error visualizing circuit: "The 'pylatexenc' library is required to use 'MatplotlibDrawer'. You can install it with 'pip install pylatexenc'."
class BraketPersona(BasePersona):
    """
    An AI persona designed to assist AWS Braket users with quantum computing tasks.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    @property
    def defaults(self) -> PersonaDefaults:
        """Return default configuration for the Claude Code persona."""
        return PersonaDefaults(
            name="Braket",
            avatar_path=AVATAR_PATH,
            description="AWS Braket AI persona",
            system_prompt="...",
        )
    
    async def process_message(self, message: Message):
        # 1. Initialize chat model and verify authn
        try:
            model = ChatBedrockConverse(
                model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                # Unless `credentials_profile_name` is passed, the
                # `boto3.client()` method is used, which only loads credentials
                # once per process. We pass it here to allow security tokens to
                # be refreshed without needing to restart the server.
                # 
                # See: https://github.com/langchain-ai/langchain-aws/blob/f2dac4838c6cc7acbda10b72aca115ae9838bfd2/libs/aws/langchain_aws/utils.py#L177-L178
                # And the definition of `boto3.client()`.
                credentials_profile_name="default"
            )
        except ValueError as e:
            emsg = str(e)
            if "The config profile (default) could not be found" in emsg:
                self.log.warning(e)
                self.send_message("The `default` profile at `~/.aws/credentials` is missing. Please authenticate using the `aws` CLI and retry.")
                return
            elif "You must specify a region" in emsg:
                self.log.warning(e)
                self.send_message("Please specify the `region` in the `default` profile at `~/.aws/credentials` and retry.")
                return
            else:
                raise e
        except Exception as e:
            self.log.error(e)
            self.send_message(f"Unknown error:\n```{str(e)}\n```\n")

        # 2. Initialize MCP server and get tools
        client = MultiServerMCPClient(  
            {
                "amazon_braket_mcp_server": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "jupyter_ai_braket.amazon_braket_mcp_server.server"],
                },
            }
        )
        tools = await client.get_tools()

        # 3. Initialize agent w/ MCP server tools
        system_prompt = BRAKET_SYS_PROMPT_TEMPLATE
        agent = create_agent(
            model,
            system_prompt=system_prompt,
            tools=tools
            # checkpointer=memory_store,
        )

        context = {
            "thread_id": self.ychat.get_id(),
            "username": message.sender
        }

        async def create_aiter():
            try:
                async for token, metadata in agent.astream(
                    {"messages": [{"role": "user", "content": message.body}]},
                    {"configurable": context},
                    stream_mode="messages",
                ):
                    node = metadata["langgraph_node"]
                    content_blocks = token.content_blocks
                    if node == "model" and content_blocks:
                        if token.text:
                            yield token.text
            except ClientError as e:
                if "ExpiredTokenException" in str(e):
                    self.log.warning(e)
                    self.send_message(f"The configured security token is expired. Please re-authenticate using the `aws` CLI and retry.")
                    return
                else:
                    raise e
            except Exception as e:
                self.log.error(e)
                self.send_message(f"An exception occurred:\n```{str(e)}\n```\n")
                return

        response_aiter = create_aiter()
        await self.stream_message(response_aiter)

    