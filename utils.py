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
        

import re
def extract_result_from_llm(result:str) -> list[str]:
    # 提取effect和reason
    pattern = r"Effect \d+:\s*(\S+)\s*Reason \d+:\s*(.*)"
    matches = re.findall(pattern, result)
    assert len(matches) > 0, "Extract effect and reason failed"
    return matches

def extract_precondition(result: str) -> list[dict]:
    res = []
    result = result.replace("*", "")
    # 匹配所有的(())和[[]]内容
    double_parentheses_pattern = r'\(\((.*?)\)\)'
    double_brackets_pattern = r'\[\[(.*?)\]\]'

    # 提取内容
    parentheses_content = re.findall(double_parentheses_pattern, result)
    brackets_content = re.findall(double_brackets_pattern, result)

    if len(parentheses_content) != len(brackets_content):
        raise ValueError("The number of parentheses and brackets should be equal.")
    for pm, bm in zip(parentheses_content, brackets_content):
        answer = pm.strip()
        reason = bm.strip()
        res.append({"answer": answer, "reason": reason})
    return res

def construct_effect_node(result:str) -> list[Effect]:
    # 解析得到的effect是多个
    matches = extract_result_from_llm(result)
    effect_list = []
    for effect, reason in matches:
        effect_list.append(Effect(effect, reason))
    return effect_list

def save_precondition(data:dict, save_path:str) -> None:
    import csv
    import os
    print("in save_precondition")
    file_exists = os.path.exists(save_path) and os.path.getsize(save_path) > 0
    with open(save_path, 'a', newline='') as f:
        writer = csv.writer(f)
        # 如果文件不存在或为空，则写入表头
        if not file_exists:
            writer.writerow(['space', 'device', 'action', 'effect', 'precondition', 'reason'])
        # 写入数据
        writer.writerow([data['space'], data['device'], data['action'], data['effect'], data['precondition'], data['reason']])

import logging

def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

    handler = logging.FileHandler(log_file)        
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


if __name__ == "__main__":
    text = """ Effect 1: effect_brightness_up  
Reason 1: Opening the curtain will allow more natural light into the room, increasing brightness.  

Effect 2: effect_temperature_up  
Reason 2: Allowing sunlight in through the open curtain can raise the temperature in the room.  

Effect 3: effect_ultravioletLevel_up  
Reason 3: Opening the curtain will let in more sunlight, which includes ultraviolet light, thus increasing the ultraviolet level in the room."""

    extract_result_from_llm(text)