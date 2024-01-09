import asyncio
import json
import time

import aiohttp
from tqdm import tqdm


async def post_request(session, url, data, headers, progress_bar):
    async with session.post(url, json=data, headers=headers) as response:
        print(await response.text())
        progress_bar.update(1)


num_runs = 10


async def main():
    start_time = time.time()
    progress_bar = tqdm(total=num_runs)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_runs):
            data = json.load(open("tests/jsons/branch_push.json", "r"))
            task = asyncio.create_task(
                post_request(
                    session,
                    "http://127.0.0.1:8080",
                    data,
                    {"X-GitHub-Event": "push"},
                    progress_bar,
                )
            )
            tasks.append(task)
        await asyncio.gather(*tasks)
    progress_bar.close()
    print(f"Finished in {time.time() - start_time}")


if __name__ == "__main__":
    asyncio.run(main())
