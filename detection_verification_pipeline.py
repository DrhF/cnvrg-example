import argparse
import asyncio
import logging
import os
from typing import List

import pandas as pd
import toloka.client as toloka
from crowdkit.aggregation import MajorityVote
from toloka.client import TolokaClient
from toloka.streaming import AssignmentsObserver, Pipeline
from toloka.streaming.event import AssignmentEvent

# class for handling submissions in the detection pool


class DetectionSubmittedHandler:
    def __init__(self, client, verification_pool_id):
        self.client = client
        self.verification_pool_id = verification_pool_id

    # create new tasks for the verification pool
    def __call__(self, events: List[AssignmentEvent]) -> None:
        verification_tasks = [
            toloka.Task(
                pool_id=self.verification_pool_id,
                input_values={
                    'image': event.assignment.tasks[0].input_values['image'],
                    'selection': event.assignment.solutions[0].output_values['result'],
                    'assignment_id': event.assignment.id,
                }
            )
            for event in events
        ]
        self.client.create_tasks(
            verification_tasks, allow_defaults=True, open_pool=True)


# class for handling accepted tasks in the verification pool
class VerificationDoneHandler:
    def __init__(self, client, verification_skill_id):
        self.microtasks = pd.DataFrame(
            [], columns=['task', 'label', 'worker'])
        self.client = client
        self.verification_skill_id = verification_skill_id

    # filter out tasks that already have enough overlap and aggregate the result
    def __call__(self, events: List[AssignmentEvent]) -> None:
        # Initializing data
        microtasks = pd.concat([self.microtasks, self.as_frame(events)])
        # get user skills for aggregation
        skills = pd.Series({
            skill.user_id: skill.value
            for skill in self.client.get_user_skills(skill_id=self.verification_skill_id)
        })

        # Filtering all microtasks that have overlap of 3
        microtasks['overlap'] = microtasks.groupby(
            'task')['task'].transform('count')
        to_aggregate = microtasks[microtasks['overlap'] >= 3]
        microtasks = microtasks[microtasks['overlap'] < 3]
        aggregated = MajorityVote(
            on_missing_skill='value', default_skill=1).fit_predict(to_aggregate, skills)
        # Accepting or rejecting assignments
        for assignment_id, result in aggregated.items():
            try:
                if result == 'OK':
                    self.client.accept_assignment(assignment_id, 'Well done!')
                else:
                    self.client.reject_assignment(
                        assignment_id, 'The object wasn\'t selected or was selected incorrectly.')
            except toloka.exceptions.IncorrectActionsApiError as e:
                logging.warning(assignment_id, e)

        # Updating mictotasks
        self.microtasks = microtasks[['task', 'label', 'worker']]

    # get the data necessary for aggregation
    @staticmethod
    def as_frame(events: List[AssignmentEvent]) -> pd.DataFrame:
        microtasks = [
            (task.input_values['assignment_id'],
             solution.output_values['result'], event.assignment.user_id)
            for event in events
            for task, solution in zip(event.assignment.tasks, event.assignment.solutions)
        ]
        return pd.DataFrame(microtasks, columns=['task', 'label', 'worker'])


def get_pipeline(toloka_token: str, detection_pool_id: str, verification_pool_id: str, verification_skill_id: str) -> Pipeline:
    toloka_client = TolokaClient(toloka_token, 'PRODUCTION')

    detection_observer = AssignmentsObserver(toloka_client, detection_pool_id)
    detection_observer.on_submitted(
        DetectionSubmittedHandler(toloka_client, verification_pool_id))
    verification_observer = AssignmentsObserver(
        toloka_client, verification_pool_id)
    verification_observer.on_accepted(
        VerificationDoneHandler(toloka_client, verification_skill_id))

    pipeline = Pipeline()
    pipeline.register(detection_observer)
    pipeline.register(verification_observer)

    return pipeline


def get_raw_results(toloka_token: str, pool_id: str) -> pd.DataFrame:
    toloka_client = TolokaClient(toloka_token, 'PRODUCTION')

    return toloka_client.get_assignments_df(pool_id)


if __name__ == '__main__':
    # command line arguments
    parser = argparse.ArgumentParser(
        description='Get of create skill on Toloka.')
    parser.add_argument('--token_env', type=str, required=True,
                        help='Environment variable for Toloka API access token')
    parser.add_argument('--detection_pool_id_path', type=str,
                        required=True, help='Path to file with detection pool id')
    parser.add_argument('--verification_pool_id_path', type=str,
                        required=True, help='Path to file with verification pool id')
    parser.add_argument('--verification_skill_id_path', type=str,
                        required=True, help='Path to file with verification skill id')
    parser.add_argument('--output_pool_results', type=str, required=True,
                        help='Path to store pool results')

    args = parser.parse_args()

    toloka_token = os.environ[args.token_env]

    with open(args.detection_pool_id_path) as detection_pool_id_file:
        detection_pool_id = detection_pool_id_file.readline().strip()
    with open(args.verification_pool_id_path) as verification_pool_id_file:
        verification_pool_id = verification_pool_id_file.readline().strip()
    with open(args.verification_skill_id_path) as verification_skill_id_file:
        verification_skill_id = verification_skill_id_file.readline().strip()

    pipeline = get_pipeline(toloka_token, detection_pool_id,
                            verification_pool_id, verification_skill_id)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(pipeline.run())

    logging.info(f'Pool {detection_pool_id} has finished')

    assignments = get_raw_results(toloka_token, detection_pool_id)
    assignments.to_csv(args.output_pool_results, index=False)
