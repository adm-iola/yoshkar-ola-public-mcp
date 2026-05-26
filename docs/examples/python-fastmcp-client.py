import asyncio

from fastmcp import Client


async def main() -> None:
    async with Client("https://apiiola.yasg.ru/mcp") as client:
        info = await client.call_tool("get_server_info", {})
        print(info.structured_content)

        layers = await client.call_tool("list_data_layers", {})
        print(layers.structured_content)

        search = await client.call_tool(
            "search_all",
            {"query": "29", "limit_per_layer": 5},
        )
        print(search.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
