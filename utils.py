class Effect():
    def __init__(self, name:str):
        self.name = name
    
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
    
    def get_actions(self) -> str:
        return ','.join(self.actions)

class Space():
    def __init__(self, name:str, envstate: list, devices:list[Device]):
        self.name = name
        self.envstate = envstate
        self.devices = devices
    
    def get_envstate(self) -> str:
        return ','.join(self.envstate)
        

def extract_result_from_llm(result:str) -> list[str]:
    pass

def construct_effect_node(result:str) -> list[Effect]:
    # 解析得到的effect是多个
    effects = extract_result_from_llm(result)
    effect_list = []
    for effect in effects:
        effect_list.append(Effect(effect))
    return effect_list
