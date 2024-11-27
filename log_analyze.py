import os
import json
import copy
import pandas as pd
from datetime import datetime, timedelta

context_mapping = {
    "Context": ["Context", "Corridor"],
    "Corridor": ["Corridor", "Context", "TeaRoom", "MeetingRoomTwo", "Lab"],
    "TeaRoom": ["TeaRoom", "Corridor", "MeetingRoomOne"],
    "MeetingRoomOne": ["MeetingRoomOne", "TeaRoom"],
    "MeetingRoomTwo": ["MeetingRoomTwo", "Corridor"],
    "Lab": ["Lab", "Corridor"]
}

def get_counterexamples(log_path, save_path, initial_states, graph):
    excel_files = sorted(
    [f for f in os.listdir(log_path) if f.endswith('.xlsx') and any(f.startswith(f'day_{i:02}') for i in range(1, 29))],
    key=lambda x: int(x.split('_')[1].split('.')[0])
)
    
    counterexamples = []
    with open(save_path, 'w') as f:  # 打开jsonl文件
        for file in excel_files:
            file_path = os.path.join(log_path, file)
            df = pd.read_excel(file_path, engine='openpyxl')
            for index, row in df.iterrows():
                if row['Type'] == 'Event':
                    # 根据event实时更新环境信息
                    event_space = row['Location']
                    attr = row['Object']
                    value = row['Payload Data'].split(':')[1].strip()
                    initial_states[event_space]['state'][attr] = value
                elif row['Type'] == 'Action':
                    if 'on' in row['Name']:
                        initial_states[row['Location']]['device'][row['Object']] = '1'
                    elif 'off' in row['Name']:
                        initial_states[row['Location']]['device'][row['Object']] = '0'
                    if row['Object'] != 'Door':
                        effects = []
                        # 对每个action，检查后续是否有对应的effect生效，没有生效的就是反例
                        action_space = row['Location']
                        device = row['Object']
                        action = 'action_on' if 'on' in row['Name'] else 'action_off'
                        # 用graph查询找到对应space的对应device的对应action的effect
                        query = f"""
                        MATCH (space:Space {{name: "{action_space}"}})<-[:BELONG_TO]-(device:Device)-[:CAN]->(action:Action {{name: "{action}"}})-[:HAS]->(effect:Effect)
                        WHERE device.name =~ "{device}.*"
                        RETURN effect
                        """

                        tx = graph.begin()  # 手动开始事务
                        try:
                            result = tx.run(query, action_space=action_space, device=device, action=action)
                            for record in result:
                                effect_node = record['effect']['name']
                                effects.append(effect_node)
                            tx.commit()  # 提交事务
                        except Exception as e:
                            tx.rollback()  # 回滚事务
                            raise e
                        
                        # 检查接下来5分钟的event log，判断是否有对应的effect生效
                        logs = []
                        action_time = datetime.strptime(row['Timestamp'], "%Y-%m-%d %H:%M:%S")
                        effect_active = False
                        for i in range(index+1, len(df)):
                            log_time = datetime.strptime(df.loc[i, 'Timestamp'], "%Y-%m-%d %H:%M:%S")
                            time_delta = log_time - action_time
                            if df.loc[i, 'Type'] == 'Event' and df.loc[i, 'Location'] == action_space and time_delta <= timedelta(minutes=5):
                                if any(df.loc[i, 'Name'].strip().lower() in element.lower() for element in effects):
                                    effect_active = True
                                    break
                                else:
                                    logs.append(str(df.loc[i, 'Object'])+", "+str(df.loc[i, 'Name'])+", "+str(df.loc[i, 'Payload Data']))
                            if time_delta > timedelta(minutes=5):
                                break
                        if not effect_active:
                            for effect in effects:
                                if 'energy' in effect:
                                    # 跳过energy consumption相关的effect
                                    continue
                                # 根据action_space，只保留联通部分的context的state，构建大字典方便直接被ChatPromptTemplate调用
                                temp_keys = context_mapping[action_space]
                                specific_context = {key: copy.deepcopy(initial_states[key]) for key in temp_keys}
                                counterexample = {
                                    "Space": action_space,
                                    "Context": specific_context,
                                    "Device": device,
                                    "Action": action,
                                    "Effect": effect,
                                    "LogRecords": logs
                                }
                                counterexamples.append(counterexample)
                                f.write(json.dumps(counterexample) + '\n')  # 每找到一个反例就写入一次文件
    
    return counterexamples

if __name__ == "__main__":
    import json

    from db import create_graph
    from log_analyze import get_counterexamples

    graph = create_graph()

    initial_states_path = "/Users/andyluo/Documents/实验室/EnvGuard-2024.github.io/DataSet/BuildingEnvironment/initial_environment_state.json"
    with open(initial_states_path, 'r') as f:
        initial_states = json.load(f)

    # 2. 从log里找反例（逐条阅读event，根据event实时更新环境信息；对每个action，检查后续是否有对应的effect生效，没有生效的就是反例）
    log_path = "/Users/andyluo/Documents/实验室/EnvGuard-2024.github.io/DataSet/BuildingEnvironment"
    # counter_examples是一个大字典
    counter_examples = get_counterexamples(log_path, initial_states, graph)