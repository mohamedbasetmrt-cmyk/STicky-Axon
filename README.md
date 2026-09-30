# Sticky Axon — Windows AI Desktop Companion

Background tray agent + transparent floating animated character (PySide6).

## Run

```powershell
& "D:\My Vision\mypackagelib\Scripts\python.exe" "G:\STICKY AXON\main.py"
```

## Structure

- `main.py` — wires everything, single-instance, tray-first (no taskbar)
- `tray/system_tray.py` — QSystemTrayIcon + menu
- `overlay/overlay_window.py` — transparent Tool window, drag, multi-monitor persist
- `overlay/character_view.py` — 30fps painter host
- `overlay/interaction.py` — mini panel + right-click menu
- `character/` — states, controller, animation manager, swappable renderers
- `agent_bridge/` — EventBus + AgentBridge (your agent imports only this)
- `config/settings.py` — `%LOCALAPPDATA%\StickyAxon\settings.json`

## Wire your real agent

```python
from agent_bridge.agent_bridge import AgentBridge
bridge.thinking({"task": "..."})
bridge.executing({...}); bridge.task_completed({...}); bridge.task_failed({...})
bridge.bus.character_event.connect(handler)  # character.clicked etc.
```

Remove `MockAgent` in `main.py` when done.
