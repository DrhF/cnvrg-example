import argparse
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from toloka.client import TolokaClient, Pool

def replace_config_args(json_config: str, configs: Optional[List[str]]) -> str:
    placeholder = None
    value = None

    for arg in configs:
        if arg.startswith('--'):
            placeholder = '{' + arg.strip('--') + '}'
            value = None
        else:
            if os.path.exists(arg):
                with open(arg) as arg_file:
                        value = arg_file.read().strip()
            else:
                value = arg
        
        if placeholder is not None and value is not None:
            json_config = json_config.replace(placeholder, value)
            placeholder = None
            value = None
    return json_config


def create_pool(toloka_client: TolokaClient, pool_config_path: str, project_id: str, training_id: Optional[str] = None, config_replacements: Optional[List[str]] = None) -> Pool:
    with open(pool_config_path) as pool_config_file:
        json_string = replace_config_args(pool_config_file.read(), config_replacements)

    logging.info('Pool config')
    logging.info(json_string)
    pool = Pool.from_json(json_string)
    pool.project_id = project_id
    if training_id:
        pool.quality_control.training_requirement.training_pool_id = training_id
    pool.will_expire = datetime.now() + timedelta(days=10)
    return toloka_client.create_pool(pool)


if __name__ == '__main__':
    # command line arguments
    parser = argparse.ArgumentParser(description='Create a pool in Toloka project.')
    parser.add_argument('--token_env', type=str, required=True, help='Environment variable for Toloka API access token')
    parser.add_argument('--project_id_path', type=str, required=True, help='Path to file with project id')
    parser.add_argument('--pool_config_path', type=str, required=True, help='Path to a pool config file')
    parser.add_argument('--pool_id_path', type=str, required=True, help='Path to store created pool id')
    parser.add_argument('--training_id_path', type=str, required=False, help='Path to file with training id')
    args, config_replacements = parser.parse_known_args()

    toloka_token = os.environ[args.token_env]

    with open(args.project_id_path) as project_id_file:
        project_id = project_id_file.readline().strip()

    if args.training_id_path is not None:
        with open(args.training_id_path) as training_id_file:
            training_id = training_id_file.readline().strip()
    else:
        training_id = None

    toloka_client = TolokaClient(toloka_token, 'PRODUCTION')
    pool = create_pool(toloka_client, args.pool_config_path, project_id, training_id=training_id, config_replacements=config_replacements)

    logging.info(f'Pool {pool.id} is created.')
    with open(args.pool_id_path, 'w') as pool_id_file:
        pool_id_file.write(pool.id)
