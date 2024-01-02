import asyncio


async def worker():
    print("Hello world")
    import pdb

    pdb.set_trace()
    print("Goodbye world")


loop = asyncio.get_event_loop()
loop.run_until_complete(worker())
