import asyncio, importlib.util, json, pathlib, sys
import aiohttp
from aiohttp import web

spec = importlib.util.spec_from_file_location(
    "api", str(pathlib.Path(__file__).parent.parent / "custom_components/episode_rsp/api.py"))
api = importlib.util.module_from_spec(spec)
sys.modules["api"] = api
spec.loader.exec_module(api)

STATE = {
    "deviceinfo": {"devicename": "Episode", "devicemodel": "EA-RSP-16D-100",
                   "serialnumber": "TEST", "firmwareversion": "1"},
    "amp_setttings": {
        "input_name": [f"input{i}" for i in range(1, 9)],
        "output_name": ["output1"] + [f"Output{i}" for i in range(2, 8)] + ["Living Room"],
        "output_source1": ["1", "1", "2", "3", "4", "5", "6", "7"],
        "dsp_preset_item": ["FLAT", "CLASSICAL", "POP"],
        "dsp_preset": ["0"] * 8,
        "output_mute": ["off"] * 8,
        "output_volume": ["77", "50", "50", "93", "50", "50", "50", "75"],
        "max_volume": ["100"] * 8,
    },
}
beats = 0


def reply():
    return {"type": "configure", "ovrc": "2", "status": 701, "configures": STATE}


async def ws_handler(request):
    global beats
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logged = False
    async for m in ws:
        msg = json.loads(m.data)
        t = msg["type"]
        if t == "login":
            logged = msg["password"] == "good"
            await ws.send_json({"type": "login", "ovrc": "2", "status": 200 if logged else 400})
        elif t == "heartbeat_request":
            beats += 1
            await ws.send_json({"type": "heartbeat_request", "status": 200})
        elif t == "configure" and logged:
            if msg["direction"] == "put":
                for key, it in msg["items"].items():
                    STATE["amp_setttings"][key][int(it["index"])] = it["value"]
            await ws.send_json(reply())
    return ws


async def main():
    api.HEARTBEAT_INTERVAL = 0.2
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 18081).start()

    async with aiohttp.ClientSession() as s:
        bad = api.EpisodeRspClient(s, "127.0.0.1", 18081, "u", "bad")
        try:
            await bad.async_get_state()
            raise SystemExit("expected auth error")
        except api.RspAuthError:
            print("auth error OK")

        c = api.EpisodeRspClient(s, "127.0.0.1", 18081, "u", "good")
        pushed = []
        c.add_listener(pushed.append)
        st = await c.async_get_state()
        assert len(st["zones"]) == 8, st["zones"]
        assert st["zones"][7]["name"] == "Living Room" and st["zones"][7]["volume"] == 75
        assert st["zones"][0]["source"] == 1 and st["inputs"][0] == "input1"
        assert st["presets"] == ["FLAT", "CLASSICAL", "POP"]
        print("parse OK")

        await c.async_put("output_volume", 2, 51)
        await c.async_put("output_mute", 2, "on")
        await c.async_put("output_source1", 2, 1)
        await c.async_put("dsp_preset", 2, 1)
        z = pushed[-1]["zones"][2]
        assert (z["volume"], z["mute"], z["source"], z["dsp_preset"]) == (51, True, 1, 1), z
        print("put + push OK")

        await asyncio.sleep(0.7)
        assert beats >= 2, beats
        print("heartbeat OK", beats)

        await c._close()
        assert (await c.async_get_state())["zones"][2]["volume"] == 51
        print("reconnect OK")
        await c.async_close()
    await runner.cleanup()

asyncio.run(main())
