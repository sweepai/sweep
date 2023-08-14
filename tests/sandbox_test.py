from sweepai.core.sandbox import Sandbox
import traceback


async def main():
    try:
        s = await Sandbox.from_token("", "")
        print(await s.run_command("pwd"))
    except Exception as e:
        print(traceback.format_exc())
        print(e)


# Run the async function
import asyncio

asyncio.run(main())
