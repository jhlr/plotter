"""Interactive loop: type what to draw, see the tool calls and the agent's replies."""
import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent

APP, USER = "penarm", "user"


async def chat() -> None:
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name=APP, user_id=USER)
    runner = Runner(agent=root_agent, app_name=APP, session_service=sessions)
    try:
        while (text := input("draw> ").strip()) not in ("", "quit", "exit"):
            msg = types.Content(role="user", parts=[types.Part(text=text)])
            async for ev in runner.run_async(user_id=USER, session_id=session.id, new_message=msg):
                for call in ev.get_function_calls():
                    print(f"  [tool] {call.name}({str(call.args)[:100]})")
                if ev.is_final_response() and ev.content and ev.content.parts:
                    print(ev.content.parts[0].text)
    finally:
        await runner.close()


def main() -> None:
    asyncio.run(chat())


if __name__ == "__main__":
    main()
