import logging
import threading
import time

logger = logging.getLogger(__name__)

class MacroAction:
    def __init__(self, action_type: str, code: int, value: int, delay: float = 0.0):
        self.action_type = action_type # 'key' or 'wait'
        self.code = code
        self.value = value
        self.delay = delay

class MacroEngine:
    """Motor de execução de macros."""
    def __init__(self, virtual_device):
        self.vdev = virtual_device
        self.running_macros = {}

    def execute_macro(self, actions: list[MacroAction]):
        thread = threading.Thread(target=self._run_macro, args=(actions,), daemon=True)
        thread.start()

    def _run_macro(self, actions: list[MacroAction]):
        for action in actions:
            if action.action_type == 'wait':
                time.sleep(action.delay)
            elif action.action_type == 'key':
                self.vdev.write_event(1, action.code, action.value) # 1 = EV_KEY
                self.vdev.sync()
                if action.delay > 0:
                    time.sleep(action.delay)
