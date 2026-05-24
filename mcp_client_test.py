"""MCP SSE client: connect to tokindle server and call download_and_convert"""
import asyncio
import json
import httpx
import sys

SSE_URL = "http://127.0.0.1:48000/sse"
MESSAGES_URL = "http://127.0.0.1:48000/messages"
URL = "https://www.zhihu.com/question/1934907181452485781/answer/1935135730310545599"


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(300)) as client:
        # Step 1: Open SSE stream to get session_id
        print("[1] Connecting SSE...")
        session_id = None
        async with client.stream("GET", SSE_URL) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if "session_id=" in data:
                        session_id = data.split("session_id=")[1]
                        break
            # We need to close the SSE stream before POSTing
            # (closing the async context manager does this)

        if not session_id:
            print("ERROR: Failed to get session_id")
            return

        print(f"    Session: {session_id}")

        # Step 2: Initialize
        print("[2] Initializing...")
        msg_url = f"{MESSAGES_URL}/?session_id={session_id}"
        init_resp = await client.post(msg_url, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hermes-mcp-client", "version": "1.0"}
            }
        })
        print(f"    Init response: {init_resp.status_code}")

        # Step 3: Send initialized notification
        await client.post(msg_url, json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        })
        print("    Sent initialized notification")

        # Step 4: Call download_and_convert
        print(f"[3] Calling download_and_convert for: {URL}")
        call_resp = await client.post(msg_url, json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "download_and_convert",
                "arguments": {"url": URL}
            }
        })
        print(f"    POST response: {call_resp.status_code}")

        # Step 5: Read SSE stream for the result
        print("[4] Reading SSE result stream...")
        async with client.stream("GET", SSE_URL) as response:
            buffer = ""
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    try:
                        msg = json.loads(data)
                        if msg.get("id") == 2:
                            print(f"\n=== RESULT ===")
                            print(json.dumps(msg, indent=2, ensure_ascii=False))
                            break
                    except json.JSONDecodeError:
                        pass
                # timeout after some lines
                buffer += line + "\n"
                if len(buffer) > 50000:
                    print("Buffer overflow, stopping")
                    break

        print("\n[DONE]")


if __name__ == "__main__":
    asyncio.run(main())
