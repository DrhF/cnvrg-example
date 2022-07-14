import argparse
import json
import logging
import os

from toloka.client import TolokaClient, Skill


def get_or_create_skill(toloka_client: TolokaClient, skill_config_path: str) -> Skill:
    with open(skill_config_path) as skill_config_file:
        json_string = skill_config_file.read()
    skill = Skill.from_json(json_string)
    toloka_skill = next(toloka_client.get_skills(name=skill.name), None)
    if toloka_skill is not None:
        return toloka_skill
    else:
        json_dict = json.loads(json_string)
        return toloka_client.create_skill(**json_dict)


if __name__ == '__main__':
    # command line arguments
    parser = argparse.ArgumentParser(description='Get of create skill on Toloka.')
    parser.add_argument('--token_env', type=str, required=True, help='Environment variable for Toloka API access token')
    parser.add_argument('--skill_config_path', type=str, required=True, help='Path to a skill config file')
    parser.add_argument('--skill_id_path', type=str, required=True, help='Path to store created skill id')
    args = parser.parse_args()

    toloka_token = os.environ[args.token_env]

    toloka_client = TolokaClient(toloka_token, 'PRODUCTION')
    skill = get_or_create_skill(toloka_client, args.skill_config_path)
    
    logging.info(f'Skill {skill.id} is ready for use.')
    with open(args.skill_id_path, 'w') as skill_id_file:
        skill_id_file.write(skill.id)
