import os
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


from db import create_driver, get_all_spaces, create_graph, add_space_node, add_effect_space_relation
from utils import construct_effect_node

if __name__ == "__main__":
    os.environ["OPENAI_API_KEY"] = 'sk-rSXdzHFvQ3Zl1kSnerB6MEBukCly9uPMUXaHqLIyTyoHfC6o'
    model = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_base='https://api.aiproxy.io/v1'
                    )
    parser = StrOutputParser()

    system_template = "You are a helpful assistant for controlling smart home devices."

    prompt_template = ChatPromptTemplate.from_messages([("system", system_template), ("user", """There is a {device} of type {type} in {space}, the action you can perform on it is {action}. The environment states of {space} that may be affected are as follows: {envstates}. Please infer which of the above environment states this action may affect on {space}, and explain the direction of the impact (up or down). Return in the following format:
    Effect 1: effect_xxx_up/down
    Reason 1: ... (the reason for this effect)

    An example response:
    Effect 1: effect_temperature_up
    Reason 1: Turning on the heater will make the temperature rise
                                                                                    
    IMPORTANT: Don't over-reason, just do the most intuitive and common sense reasoning. Don't take irrelevant states into account, if you are not sure what an environment state means, ignore it.
    """)]
    )

    chain = prompt_template | model | parser

    driver = create_driver()
    if driver is None:
        print("Failed to create Neo4j driver")
        exit(1)

    # 运行查询并输出结果
    try:
        spaces = get_all_spaces(driver)
        # 关闭驱动程序
        driver.close()
    except Exception as e:
        print(f"Error: {e}")

    ind = 0
    for space in spaces:
        for device in space.devices:
            temp_dict = {
                    "space": space.name,
                    "device": device.name,
                    "type": device.type,
                    "envstates":space.get_envstate().replace("HumanCount,HumanState,", ''),
                    "devicestate": 'off' if device.state==0 else 'on',
                }
            for action in device.actions:
                temp_dict['action'] = action
                formatted_prompt = prompt_template.format(**temp_dict)
                print("---------------------------------\nQuery "+str(ind)+"\nFormatted Prompt:\n", formatted_prompt)
                result = chain.invoke(temp_dict)
                print("\nLLM Response:\n",result)

                # 提取LLM回答
                effects = construct_effect_node(result)
                for effect in effects:
                    print(effect.name)
                    # 将effect加到action上
                    action.add_effect(effect)

    graph = create_graph()

    # 组成neo4j节点和关系
    for space in spaces:
        add_space_node(graph, space)
        print(f"Space {space.name} added to Neo4j")
    
    # 添加effect和space的关系，因为加上会很乱，所以先注释掉
    # add_effect_space_relation(graph)


    # TODO: 尝试创建precondition
