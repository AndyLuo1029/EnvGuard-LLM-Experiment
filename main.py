import os
import json
import pandas as pd

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from db import create_driver, get_all_spaces, create_graph, add_space_node, add_space_georaphical_relation, add_precondition_node, add_effect_space_relation, delete_preconditions
from utils import construct_effect_node, setup_logger, extract_precondition, save_precondition
from log_analyze import get_counterexamples

if __name__ == "__main__":
    logger = setup_logger("main", "log/main.log")
    os.environ["OPENAI_API_KEY"] = 'YOUR API KEY'
    model = ChatOpenAI(
        model="gpt-4o-mini",
        openai_api_base='https://api.aiproxy.io/v1'
                    )
    parser = StrOutputParser()

    effect_system_template = "You are a helpful assistant for controlling smart home devices."
    effect_user_template = """There is a {device} of type {type} in {space}, the action you can perform on it is {action}. The environment states of {space} that may be affected are as follows: {envstates}. Please infer which of the above environment states this action may affect on {space}, and explain the direction of the impact (up or down). Return in the following format:
    Effect 1: effect_xxx_up/down
    Reason 1: ... (the reason for this effect)

    An example response:
    Effect 1: effect_temperature_up
    Reason 1: Turning on the heater will make the temperature rise
                                                                                    
    IMPORTANT: Don't over-reason, just do the most intuitive and common sense reasoning. Don't take irrelevant states into account, if you are not sure what an environment state means, ignore it.
    """

    effect_prompt_template = ChatPromptTemplate.from_messages([("system", effect_system_template), ("user", effect_user_template)])
    effect_chain = effect_prompt_template | model | parser

    driver = create_driver()
    if driver is None:
        logger.error("Failed to create Neo4j driver")
        exit(1)
    try:
        spaces = get_all_spaces(driver)
        driver.close()
    except Exception as e:
        logger.error(f"Error: {e}")

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
                formatted_prompt = effect_prompt_template.format(**temp_dict)
                logger.info("---------------------------------\nQuery "+str(ind)+"\nFormatted Prompt:\n%s", formatted_prompt)
                result = effect_chain.invoke(temp_dict)
                logger.info("\nLLM Response:\n%s",result)

                effects = construct_effect_node(result)
                for effect in effects:
                    logger.info(effect.name)
                    action.add_effect(effect)

    graph = create_graph()

    for space in spaces:
        add_space_node(graph, space)
        logger.info(f"Space {space.name} added to Neo4j")
    
    # 添加effect和space的关系，因为加上会很乱，所以先注释掉
    # add_effect_space_relation(graph)

    add_space_georaphical_relation(graph)

    initial_states_path = "/Users/andyluo/Documents/实验室/EnvGuard-2024.github.io/DataSet/BuildingEnvironment/initial_environment_state.json"
    with open(initial_states_path, 'r') as f:
        initial_states = json.load(f)
    
    # 2. 从log里找反例（逐条阅读event，根据event实时更新环境信息；对每个action，检查后续是否有对应的effect生效，没有生效的就是反例）
    log_path = "/Users/andyluo/Documents/实验室/EnvGuard-2024.github.io/DataSet/BuildingEnvironment"
    save_path = "/Users/andyluo/Documents/实验室/EnvGuard-LLM-Experiment/counterexamples.jsonl"
    # counter_examples是一个大字典
    counter_examples = get_counterexamples(log_path, save_path, initial_states, graph)

    with open(save_path, 'r') as file:
        data = [json.loads(line) for line in file]
    df = pd.DataFrame(data)
    
    # 对Device, Action, Effect进行分组
    grouped = df.groupby(['Device', 'Action', 'Effect'])
    group_sizes = grouped.size()
    total_groups = len(group_sizes)
    logger.info("每个组的大小："+str(group_sizes))
    logger.info(f"总共有 {total_groups} 个组。")

    # 从每个组中随机选择3条记录
    sampled_data = grouped.apply(lambda x: x.sample(n=min(3, len(x)), random_state=1)).reset_index(drop=True)
    # logger.info(sampled_data.shape)
    
    # 3. 用反例创建precondition
    precondition_system_prompt = """You are a helpful assistant for controlling smart devices. Your task is to analyze the reasons for the absence of the expected device effect."""
    precondition_user_prompt = """The {Device} in {Space} was operated with {Action} but did not achieve the expected effect: {Effect}. The environment states at this time is called EnvStates: {Context}. 
In EnvStates, environment states like temperature, have 3 possible values: -1 (means the lowest), 0 (means medium) and 1 (means the highest). If an environment state is at the lowest level, it can't decrease but can go up. Also, if an environment state is at the highest level, it can't increase but can go down. Devices have 2 possible values: 0 (means off) and 1 (means on). All the environment states and device states given in EnvStates may be the reason why the current expected effect is not produced. The environment states given in EnvStates which are not in the same space of {Device} will also influence the results, since those spaces are connected georaphically. The environment states changes for the next 5 minutes are as follows log: {LogRecords}. 
Based on the provided information, please help me analyze why the {Action} of the {Device} in {Space} and under the given EnvStates did not result in {Effect}. Identify the essential causes from the given current EnvStates and next 5 minutes states logs, exclude irrelevant states. You should consider both environment states and device states given in EnvStates and logs. E.g. if the environment temperature is already -1(means the lowest level), turn on AC will not lead to temperature_down effect. 
Return the analysis in groups of this format:
Thought 1: Your inference steps. Think it step by step.
Reflection 1: Check again if your tought was right. Is it above commonsense? Do you think too much? If there is some problem, correct it in your answer.
Answer 1:((pre_s1, pre_v1)): [[reason]]
... 
where pre_sn represents the nth state name and pre_vn represents the nth state value. Then give out your reason. Only return states that could lead to the expected effect: {Effect} disappears according to your reasoning.

Example 1:
Thought 1: The environment temperature in space where the AC located is already at the lowest level(-1), so it can't decrease, even turn on the AC.
Reflection 1: Trun on the AC will lead to temperature decrease, but the environment temperature is already the lowest, so it can't decrease. These is no logic mistakes.
Answer 1:((Temperature, -1)): [[When the environment temperature is already the lowest(level -1), turning on the AC will not result in temperature_low effect.]]

Example 2:
Thought 1: The environment noise is at the lowest level(-1), meaning it can't decrease but can increase. Turn on the speaker will make noise, leading the noise level increase. But the fact is that turn on speaker didn't result in noise increase. It's contradictory and I don't know why based on present information.
Reflection 1: There is no over reason in my thought, no logic mistake.
Answer 1: ##DON'T KNOW##


IMPORTANT: Please use common sense to reason based on the actual information provided. Do not over-reason. Do not provide contradictory results. If the information currently provided is not enough to infer the reason, please honestly answer that you cannot infer the reason and make sure there is ##DON'T KNOW## in your answer part when you don't know the reason. Do not return a fabricated result."""

    precondition_prompt_template = ChatPromptTemplate.from_messages([("system", precondition_system_prompt), ("user", precondition_user_prompt)])
    precondition_chain = precondition_prompt_template | model | parser

    precondition_result_path = "/Users/andyluo/Documents/实验室/EnvGuard-LLM-Experiment/precondition.csv"
    for index, row in sampled_data.iterrows():
        ce = row.to_dict()
        formatted_prompt = precondition_prompt_template.format(**ce)
        logger.info("---------------------------------\nFormatted Prompt:\n%s", formatted_prompt)
        result = precondition_chain.invoke(ce)
        logger.info("\nLLM Response:\n%s", result)
        try:
            res = extract_precondition(result)
        except Exception as e:
            logger.error(f"Extract Error: {e}")
        if res is not None:
            for r in res:
                # 保存ce里的space，device，action，effect和res里的answer和reason
                data = {
                    "space": ce.get("Space"),
                    "device": ce.get("Device"),
                    "action": ce.get("Action"),
                    "effect": ce.get("Effect"),
                    "precondition": r.get("answer"),
                    "reason": r.get("reason")
                }
                save_precondition(data, precondition_result_path)

    precond_df = pd.read_csv(precondition_result_path)
    precond_df_unique = precond_df.drop_duplicates(subset=['device', 'action', 'effect', 'precondition'])
    precond_df_unique.to_csv('precondition_unique.csv', index=False)
    logger.info("去重后的数据已保存到 'precondition_unique.csv'")

    # 对graph读取所有space，找到里面每个device每个action的effect，从precondition里找到对应的precondition，然后添加到graph里作为节点
    add_precondition_node(graph, precond_df_unique, logger)
    logger.info("FINISHED")