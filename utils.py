class Effect():
    def __init__(self, name:str, reason:str):
        self.name = name
        self.reason = reason
    
    def __eq__(self, other) -> bool:
        if isinstance(other, Effect):
            return self.name == other.name
        return False

class Action():
    def __init__(self,name:str):
        self.name = name
        self.effects = []

    def __eq__(self, other) -> bool:
        if isinstance(other, Action):
            return self.name == other.name
        return False
    
    def __str__(self) -> str:
        return self.name

    def add_effect(self, effect:Effect) -> None:
        if effect not in self.effects:
            self.effects.append(effect)

class Device():
    def __init__(self, name:str, type:str, state:int):
        self.name = name
        self.type = type
        self.state = state
        self.actions = []

    def add_action(self, action:Action) -> None:
        if action not in self.actions:
            self.actions.append(action)

    def add_action(self, action:str) -> None:
        temp_action = Action(action)
        if temp_action not in self.actions:
            self.actions.append(temp_action)
    
    def get_actions(self) -> str:
        return ','.join(self.actions)

class Space():
    def __init__(self, name:str, envstate: list[str], devices:list[Device]):
        self.name = name
        self.envstate = envstate
        self.devices = devices
    
    def get_envstate(self) -> str:
        return ','.join(self.envstate)
        

def extract_result_from_llm(result:str) -> list[str]:
    import re
    # 提取effect和reason
    pattern = r"Effect \d+:\s*(\S+)\s*Reason \d+:\s*(.*)"
    matches = re.findall(pattern, result)
    assert len(matches) > 0, "Extract effect and reason failed"
    return matches

def construct_effect_node(result:str) -> list[Effect]:
    # 解析得到的effect是多个
    matches = extract_result_from_llm(result)
    effect_list = []
    for effect, reason in matches:
        effect_list.append(Effect(effect, reason))
    return effect_list


if __name__ == "__main__":
    text = """ Effect 1: effect_brightness_up  
Reason 1: Opening the curtain will allow more natural light into the room, increasing brightness.  

Effect 2: effect_temperature_up  
Reason 2: Allowing sunlight in through the open curtain can raise the temperature in the room.  

Effect 3: effect_ultravioletLevel_up  
Reason 3: Opening the curtain will let in more sunlight, which includes ultraviolet light, thus increasing the ultraviolet level in the room."""

    extract_result_from_llm(text)