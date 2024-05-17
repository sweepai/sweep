import copy
import multiprocessing
import os
from time import time
import traceback
from github.Repository import Repository
from github.PullRequest import PullRequest
from loguru import logger
import numpy as np
from sklearn.cluster import DBSCAN

from sweepai.core.review_utils import PRReviewBot, format_pr_changes_by_file, get_pr_changes
from sweepai.core.vector_db import cosine_similarity, embed_text_array
from sweepai.dataclasses.codereview import CodeReview, PRChange
from sweepai.utils.str_utils import object_to_xml
from sweepai.utils.ticket_rendering_utils import create_update_review_pr_comment
from sweepai.utils.ticket_utils import fire_and_forget_wrapper
from sweepai.utils.validate_license import validate_license
from sweepai.utils.chat_logger import ChatLogger
from sweepai.utils.event_logger import posthog

# get the best issue to return based on group vote
def get_group_voted_best_issue_index(file_name: str, label: str, files_to_labels_indexes: dict[str, dict[str, list[int]]], files_to_embeddings: dict[str, any], index_length: int):
    similarity_scores = [0 for _ in range(index_length)]
    for index_i in range(index_length):
        for index_j in range(index_length):
            if index_i != index_j:
                embedding_i = files_to_embeddings[file_name][index_i].reshape(1,512)
                embedding_j = files_to_embeddings[file_name][index_j].reshape(1,512)
                similarity_scores[index_i] += cosine_similarity(embedding_i, embedding_j)[0][0]
    max_index = files_to_labels_indexes[file_name][label][np.argmax(similarity_scores)]
    return max_index

# function that gets the code review for every file in the pr
def get_code_reviews_for_file(pr_changes: list[PRChange], formatted_pr_changes_by_file: dict[str, str], chat_logger: ChatLogger | None = None):
    review_bot = PRReviewBot()
    code_review_by_file = review_bot.review_code_changes_by_file(formatted_pr_changes_by_file, chat_logger=chat_logger)
    code_review_by_file = review_bot.review_code_issues_by_file(pr_changes, formatted_pr_changes_by_file, code_review_by_file, chat_logger=chat_logger)
    return code_review_by_file

# run 5 seperate instances of review_pr and then group the resulting issues and only take the issues that appear the majority of the time (> 3)
def group_vote_review_pr(pr_changes: list[PRChange], formatted_pr_changes_by_file: dict[str, str], multiprocess: bool = True, chat_logger: ChatLogger | None = None):
    majority_code_review_by_file = {}
    code_reviews_by_file = []
    GROUP_SIZE = 5
    if multiprocess:
        chat_logger = None
        pool = multiprocessing.Pool(processes=5)
        results = [
            pool.apply_async(get_code_reviews_for_file, args=(pr_changes, formatted_pr_changes_by_file, chat_logger))
            for _ in range(GROUP_SIZE)
        ]
        pool.close()
        pool.join()
        for result in results:
            try:
                code_review = result.get()
                code_reviews_by_file.append(code_review)
            except Exception as e:
                logger.error(f"Error fetching result: {e}")
    else:
        for _ in range(GROUP_SIZE):
            code_reviews_by_file.append(get_code_reviews_for_file(pr_changes, formatted_pr_changes_by_file))
    
    # embed each issue and then cluster them
    # extract code issues for each file and prepare them for embedding
    code_reviews_ready_for_embedding = [] 
    for code_review_by_file in code_reviews_by_file:
        prepped_code_review = {}
        for file_name, code_review in code_review_by_file.items():
            # using object_to_xml may not be the most optimal as it adds extra xml tags
            prepped_code_review[file_name] = [object_to_xml(code_issue, 'issue') for code_issue in code_review.issues]
        code_reviews_ready_for_embedding.append(prepped_code_review)
    
    # embed all extracted texts
    code_reviews_embeddings = []
    for prepped_code_review in code_reviews_ready_for_embedding:
        embedded_code_review = {}
        for file_name, code_issues in prepped_code_review.items():
            embedded_code_review[file_name] = embed_text_array(code_issues)
        code_reviews_embeddings.append(embedded_code_review)
    # dbscan - density based spatial clustering of app with noise
    # format: {file_name: [label1, label2, ...]}
    files_to_labels = {}
    # corresponding issues for each file
    # format: {file_name: [issue1, issue2, ...]}
    files_to_issues = {}
    # corresponding embeddings for each file
    # format: {file_name: [embedding1, embedding2, ...]}
    files_to_embeddings = {}

    # for each file combine all the embeddings together while determining the max amount of clusters
    for file_name in formatted_pr_changes_by_file:
        all_embeddings = []
        all_issues = []
        for i in range(GROUP_SIZE):
            embeddings = code_reviews_embeddings[i][file_name]
            code_review = code_reviews_by_file[i][file_name]
            if embeddings:
                embeddings = embeddings[0]
                for embedding in embeddings:
                    all_embeddings.append(embedding.flatten())
                    all_issues.extend(code_review.issues)
        files_to_issues[file_name] = all_issues
        all_flattened_embeddings = np.array(all_embeddings)
        files_to_embeddings[file_name] = all_flattened_embeddings
        # note DBSCAN expects a shape with less than or equal to 2 dimensions
        try:
            if all_flattened_embeddings.size:
                db = DBSCAN(eps=0.5, min_samples=3).fit(all_flattened_embeddings)
                files_to_labels[file_name] = db.labels_
            else:
                files_to_labels[file_name] = []
        except ValueError as e:
            logger.error(f"Error with dbscan {e}")
        
    LABEL_THRESHOLD = 4
    # get the labels that have a count greater than the threshold
    # format: {file_name: {label: [index, ...]}}
    files_to_labels_indexes = {}
    for file_name, labels in files_to_labels.items():
        index_dict: dict[str, list[int]] = {}
        for i, v in enumerate(labels):
            key = str(v)
            if key not in index_dict:
                index_dict[key] = []
            index_dict[key].append(i)
        files_to_labels_indexes[file_name] = index_dict

    # create the final code_reviews_by_file
    for file_name, labels_dict in files_to_labels_indexes.items():
        # pick first one as diff summary doesnt really matter
        final_code_review: CodeReview = copy.deepcopy(code_reviews_by_file[0][file_name])
        final_code_review.issues = []
        final_code_review.potential_issues = []
        final_issues = []
        potential_issues = []
        for label, indexes in labels_dict.items():
            index_length = len(indexes)
            # -1 is considered as noise
            if index_length >= LABEL_THRESHOLD and label != "-1":
                max_index = get_group_voted_best_issue_index(file_name, label, files_to_labels_indexes, files_to_embeddings, index_length)
                # add to final issues, first issue - TODO use similarity score of all issues against each other
                final_issues.append(files_to_issues[file_name][max_index])
            # get potential issues which are one below the label_threshold
            if index_length == LABEL_THRESHOLD - 1 and label != "-1":
                max_index = get_group_voted_best_issue_index(file_name, label, files_to_labels_indexes, files_to_embeddings, index_length)
                potential_issues.append(files_to_issues[file_name][max_index])
        final_code_review.issues = final_issues
        final_code_review.potential_issues = potential_issues
        majority_code_review_by_file[file_name] = copy.deepcopy(final_code_review)
    return majority_code_review_by_file

def review_pr(username: str, pr: PullRequest, repository: Repository, installation_id: int, tracking_id: str | None = None):
    if not os.environ.get("CLI"):
        assert validate_license(), "License key is invalid or expired. Please contact us at team@sweep.dev to upgrade to an enterprise license."
    with logger.contextualize(
        tracking_id=tracking_id,
    ):
        review_pr_start_time = time()
        chat_logger: ChatLogger = ChatLogger({"username": username,"title": f"Review PR: {pr.number}"})
        posthog_metadata = {
            "pr_url": pr.html_url,
            "repo_full_name": repository.full_name,
            "repo_description": repository.description,
            "username": username,
            "installation_id": installation_id,
            "function": "review_pr",
            "tracking_id": tracking_id,
        }
        fire_and_forget_wrapper(posthog.capture)(
            username, "review_pr_started", properties=posthog_metadata
        )

        try:
            # check if the pr has been merged or not
            if pr.state == "closed":
                fire_and_forget_wrapper(posthog.capture)(
                    username,
                    "issue_closed",
                    properties={
                        **posthog_metadata,
                        "duration": round(time() - review_pr_start_time),
                    },
                )
                return {"success": False, "reason": "PR is closed"}
            # handle creating comments on the pr to tell the user we are going to begin reviewing the pr
            _comment_id = create_update_review_pr_comment(pr)
            pr_changes, dropped_files = get_pr_changes(repository, pr)
            formatted_pr_changes_by_file = format_pr_changes_by_file(pr_changes)
            code_review_by_file = group_vote_review_pr(pr_changes, formatted_pr_changes_by_file, multiprocess=True, chat_logger=chat_logger)
            _comment_id = create_update_review_pr_comment(pr, code_review_by_file=code_review_by_file, dropped_files=dropped_files)
        except Exception as e:
            posthog.capture(
                username,
                "review_pr failed",
                properties={
                    **posthog_metadata,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                    "duration": round(time() - review_pr_start_time),
                },
            )
            raise e
        posthog.capture(
            username,
            "review_pr success",
            properties={**posthog_metadata, "duration": round(time() - review_pr_start_time)},
        )
        logger.info("review_pr success in " + str(round(time() - review_pr_start_time)))
        return {"success": True}