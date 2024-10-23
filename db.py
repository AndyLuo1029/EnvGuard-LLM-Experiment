from neo4j import GraphDatabase
from utils import Space, Device

# 设置数据库连接参数
uri = "Bolt://47.101.169.122:7687"
username = "neo4j"
password = "12345678"

# 创建 Neo4j 驱动程序
def create_driver(uri: str=uri, username: str=username, password: str=password) -> GraphDatabase:
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        # 验证连接
        driver.verify_connectivity()
        print("Connection to the database was successful.")
        return driver
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

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




