from monitor_data.schemas.game_systems import AdvancementSystem
try:
    a = AdvancementSystem(method="test", max_level=0)
    print("Success:", a)
except Exception as e:
    print("Error:", e)
