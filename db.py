from neo4j import GraphDatabase
from py2neo import Graph, Node, Relationship
from utils import Space, Device, Action, Effect
from pandas import DataFrame
import re

# 设置建模好的数据库连接参数
finished_uri = "Bolt://47.101.169.122:7687"
# 设置保存llm结果的数据库连接参数
llm_uri = "Bolt://47.101.169.122:7098"
username = "neo4j"
password = "12345678"

# 创建 Neo4j 驱动程序
def create_driver(uri: str=finished_uri, username: str=username, password: str=password) -> GraphDatabase:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        # 验证连接
        driver.verify_connectivity()
        print("Connection to the database was successful.")
        return driver
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

# 创建py2neo连接
def create_graph(uri: str=llm_uri, username: str=username, password: str=password) -> Graph:
    return Graph(uri, auth=(username, password))


# 读取图数据库中所有节点类型和关系类型
def get_all_labels(driver) -> list:
    with driver.session() as session:
        # 查询所有节点标签
        query = "CALL db.labels()"
        result = session.run(query)
        labels = [record["label"] for record in result]
        return labels

def get_all_relationship_types(driver) -> list:
    with driver.session() as session:
        # 查询所有关系类型
        query = "CALL db.relationshipTypes()"
        result = session.run(query)
        relationship_types = [record["relationshipType"] for record in result]
        return relationship_types

# 查询特定类型节点的属性
def query_node_properties(driver, node_label) -> None:
    query = f"""
    MATCH (n:{node_label})
    RETURN n, keys(n) AS properties
    """
    
    with driver.session() as session:
        result = session.run(query)
        # 打印结果
        print(f"\nProperties for nodes with label '{node_label}':")
        for record in result:
            node = record['n']
            properties = record['properties']
            print(f"Node: {node}, Properties: {properties}")

# 查询 Space, Device, 和 Action 类型节点的属性
# try:
#     query_node_properties("Space")
#     query_node_properties("Device")
#     query_node_properties("Action")
#     query_node_properties("EnvState")
# except Exception as e:
#     print(f"Error: {e}")

# 用得到的属性
# Space: name
# Device: name, state(1为开), type
# Action: name
# EnvState: name


# 获得所有Space-Device-Action关系
def get_all_spaces(driver) -> list[Space]:
    query = """
    MATCH (space:Space)
    OPTIONAL MATCH (space)-[:HAS]->(envstate:EnvState)
    OPTIONAL MATCH (space)<-[:BELONG_TO]-(device:Device)-[:CAN]->(action:Action)
    RETURN space, collect(DISTINCT envstate) AS envstates, 
           collect(DISTINCT {name: device.name, type: device.type, action: action.name, state: device.state}) AS device_actions
    """
    
    with driver.session() as session:
        result = session.run(query)
        spaces = []
        for record in result:
            space_name = record['space']['name']
            envstates = [envstate['name'] for envstate in record['envstates'] if envstate is not None]
            
            devices = {}
            for d in record['device_actions']:
                if d['name'] is not None:
                    if d['name'] not in devices:
                        devices[d['name']] = Device(d['name'], d['type'], d['state'])
                    devices[d['name']].add_action(d['action'])
                    # print(d['action'])
            
            space = Space(space_name, envstates, list(devices.values()))
            spaces.append(space)
        
        return spaces

# 保存定义的类到neo4j数据库
def add_effect_node(graph:Graph, effect: Effect) -> Node:
    assert effect is not None, "Effect is None"
    effect_node = Node("Effect", name=effect.name, reason=effect.reason)
    graph.create(effect_node)
    return effect_node

def add_action_node(graph: Graph, action: Action) -> Node:
    assert action is not None, "Action is None"
    action_node = Node("Action", name=action.name)
    for effect in action.effects:
        effect_node = add_effect_node(graph, effect)
        graph.create(Relationship(action_node, "HAS", effect_node))
    graph.create(action_node)
    return action_node

def add_device_node(graph: Graph, device: Device) -> Node:
    assert device is not None, "Device is None"
    device_node = Node("Device", name=device.name, type=device.type, state=device.state)
    for action in device.actions:
        action_node = add_action_node(graph, action)
        graph.create(Relationship(device_node, "CAN", action_node))
    graph.create(device_node)
    return device_node

def add_space_node(graph: Graph, space: Space) -> None:
    assert space is not None, "Space is None"
    space_node = Node("Space", name=space.name)
    for envstate in space.envstate:
        envstate_node = Node("EnvState", name=envstate)
        graph.create(envstate_node)
        graph.create(Relationship(space_node, "HAS", envstate_node))
    for device in space.devices:
        device_node = add_device_node(graph, device)
        graph.create(Relationship(device_node, "BELONG_TO", space_node))
    graph.create(space_node)


def add_effect_space_relation_single(graph: Graph, space_node: Node) -> None:
    # 找到当前Space节点所有Device节点下所有Action节点下所有Effect节点
    query = """
    MATCH (space:Space)<-[:BELONG_TO]-(device:Device)-[:CAN]->(action:Action)-[:HAS]->(effect:Effect)
    WHERE space.name = $space_name
    RETURN effect
    """
    tx = graph.begin()  # 手动开始事务
    try:
        result = tx.run(query, space_name=space_node['name'])
        for record in result:
            effect_node = record['effect']
            graph.create(Relationship(effect_node, "AFFECT", space_node))
        tx.commit()  # 提交事务
    except Exception as e:
        tx.rollback()  # 回滚事务
        raise e

def add_effect_space_relation(graph: Graph) -> None:
    # 找到所有space节点
    query = """
    MATCH (space:Space)
    RETURN space
    """
    tx = graph.begin()  # 手动开始事务
    try:
        result = tx.run(query)
        for record in result:
            space_node = record['space']
            add_effect_space_relation_single(graph, space_node)
        tx.commit()  # 提交事务
    except Exception as e:
        tx.rollback()  # 回滚事务
        raise e

def add_space_georaphical_relation(graph: Graph) -> None:
    # 0. 为space添加物理联系情况（谁和谁相连），会影响到后面的precondition创建
    # Corridor - adjacent to -> Context
    # Corridor <- adjacent to -> Tea Room
    # Tea Room <- adjacent to -> MeetingRoomOne
    # Corridor <- adjacent to -> MeetingRoomTwo
    # Corridor <- adjacent to -> Lab
    query = """
    MATCH (space1:Space), (space2:Space)
    WHERE space1.name = $space1_name AND space2.name = $space2_name
    CREATE (space1)-[:ADJACENT_TO]->(space2)
    """
    tx = graph.begin()  # 手动开始事务
    try:
        tx.run(query, space1_name="Corridor", space2_name="Context")
        tx.run(query, space1_name="Corridor", space2_name="TeaRoom")
        tx.run(query, space1_name="TeaRoom", space2_name="Corridor")
        tx.run(query, space1_name="TeaRoom", space2_name="MeetingRoomOne")
        tx.run(query, space1_name="MeetingRoomOne", space2_name="TeaRoom")
        tx.run(query, space1_name="Corridor", space2_name="MeetingRoomTwo")
        tx.run(query, space1_name="MeetingRoomTwo", space2_name="Corridor")
        tx.run(query, space1_name="Corridor", space2_name="Lab")
        tx.run(query, space1_name="Lab", space2_name="Corridor")        
        tx.commit()  # 提交事务
    except Exception as e:
        tx.rollback()  # 回滚事务
        raise e

def delete_all_space_georaphical_relation(graph: Graph) -> None:
    query = """
    MATCH (n)-[r:ADJACENT_TO]->()
    DELETE r
    """
    graph.run(query)

def delete_all_nodes(graph: Graph) -> None:
    query = """
    MATCH (n)
    DETACH DELETE n
    """
    graph.run(query)

def add_precondition_node(graph: Graph, df: DataFrame, logger) -> None:
    query_spaces = """
    MATCH (space:Space)
    RETURN space
    """

    query_effects = """
    MATCH (space:Space)<-[:BELONG_TO]-(device:Device)-[:CAN]->(action:Action)-[:HAS]->(effect:Effect)
    WHERE space.name = $space_name
    RETURN device, action, effect
    """
    
    result_spaces = graph.run(query_spaces)
    for record_space in result_spaces:
        space_node = record_space['space']
        result_effects = graph.run(query_effects, space_name=space_node['name'])
        for record_effect in result_effects:
            effect_node = record_effect['effect']
            device_name = record_effect['device']['name']
            device_name = re.sub(r'\d+$', '', device_name)
            device, action, effect = device_name, record_effect['action']['name'], record_effect['effect']['name']
            # 获取对应的所有 precondition
            matching_preconditions = df[(df['device'] == device) & 
                                        (df['action'] == action) & 
                                        (df['effect'] == effect)]
            if not matching_preconditions.empty:
                logger.info(f"{device}, {action}, {effect}")
                logger.info(matching_preconditions)
                for _, row in matching_preconditions.iterrows():
                    precondition, reason = row['precondition'], row['reason']
                    precondition_node = Node("Precondition", name=precondition, reason=reason)
                    graph.create(precondition_node)
                    graph.create(Relationship(effect_node, "CONSTRAINED_BY", precondition_node))
                    logger.info(f"Precondition {precondition} added to Neo4j in {space_node['name']}, {device}, {action}, {effect}")

def delete_preconditions(graph: Graph) -> None:
    query1 = """MATCH (effect)-[r:CONSTRAINED_BY]->(precondition) DELETE r"""
    query2 = """MATCH (n:Precondition) DETACH DELETE n"""
    graph.run(query1)
    graph.run(query2)