import bpy
def _start():
    try:
        r = bpy.ops.blendermcp.start_server()
        print("MCP_AUTOSTART:", r)
    except Exception as e:
        print("MCP_AUTOSTART_ERR:", e)
    return None  # 只跑一次
bpy.app.timers.register(_start, first_interval=2.0)
