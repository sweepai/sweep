from langchain.text_splitter import Language, RecursiveCharacterTextSplitter

python_text = '''
import io
import os
import zipfile

import openai
import requests
from loguru import logger

from sweepai.core.gha_extraction import GHAExtractor
from sweepai.events import CheckRunCompleted
from sweepai.handlers.on_comment import on_comment
from sweepai.utils.config.client import SweepConfig, get_gha_enabled
from sweepai.utils.github_utils import get_github_client, get_token

openai.api_key = os.environ.get("OPENAI_API_KEY")

log_message = """GitHub actions yielded the following error.

{error_logs}

This is likely a linting or type-checking issue with the source code but if you are updating the GitHub Actions or versioning, this could be an issue with the GitHub Action yaml files."""

def download_logs(repo_full_name: str, run_id: int, installation_id: int):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {get_token(installation_id)}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    response = requests.get(f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs",
                            headers=headers)

    logs_str = ""
    if response.status_code == 200:
        zip_file = zipfile.ZipFile(io.BytesIO(response.content))
        for file in zip_file.namelist():
            if "/" not in file:
                with zip_file.open(file) as f:
                    logs_str += f.read().decode("utf-8")
    else:
        logger.warning(f"Failed to download logs for run id: {run_id}")
    return logs_str


def clean_logs(logs_str: str):
    log_list = logs_str.split("\n")
    truncated_logs = [log[log.find(" ") + 1:] for log in log_list]
    patterns = [
        # for docker
        "Already exists",
        "Pulling fs layer",
        "Waiting",
        "Download complete",
        "Verifying Checksum",
        "Pull complete",
        # For github
        "remote: Counting objects",
        "remote: Compressing objects:",
        "Receiving objects:",
        "Resolving deltas:"
    ]
    return "\n".join([log.strip() for log in truncated_logs if not any(pattern in log for pattern in patterns)])


def on_check_suite(request: CheckRunCompleted):
    logger.info(f"Received check run completed event for {request.repository.full_name}")
    g = get_github_client(request.installation.id)
    repo = g.get_repo(request.repository.full_name)
    if not get_gha_enabled(repo):
        logger.info(f"Skipping github action for {request.repository.full_name} because it is not enabled")
        return None
    pr = repo.get_pull(request.check_run.pull_requests[0].number)
    num_pr_commits = len(list(pr.get_commits()))
    if num_pr_commits > 20:
        logger.info(f"Skipping github action for PR with {num_pr_commits} commits")
        return None
    logger.info(f"Running github action for PR with {num_pr_commits} commits")
    logs = download_logs(
        request.repository.full_name,
        request.check_run.run_id,
        request.installation.id
    )
    if not logs:
        return None
    logs = clean_logs(logs)
    extractor = GHAExtractor()
    logger.info(f"Extracting logs from {request.repository.full_name}, logs: {logs}")
    problematic_logs = extractor.gha_extract(logs)
    if problematic_logs.count("\n") > 15:
        problematic_logs += "\n\nThere are a lot of errors. This is likely a larger issue with the PR and not a small linting/type-checking issue."
    comments = list(pr.get_issue_comments())
    if len(comments) >= 2 and problematic_logs == comments[-1].body and comments[-2].body == comments[-1].body:
        comment = pr.as_issue().create_comment(log_message.format(error_logs=problematic_logs) + "\n\nI'm getting the same errors 3 times in a row, so I will stop working on fixing this PR.")
        logger.warning("Skipping logs because it is duplicated")
        raise Exception("Duplicate error logs")
    print(problematic_logs)
    comment = pr.as_issue().create_comment(log_message.format(error_logs=problematic_logs))
    on_comment(
        repo_full_name=request.repository.full_name,
        repo_description=request.repository.description,
        comment=problematic_logs,
        pr_path=None,
        pr_line_position=None,
        username=request.sender.login,
        installation_id=request.installation.id,
        pr_number=request.check_run.pull_requests[0].number,
        comment_id=comment.id,
        repo=repo,
    )
    return {"success": True}
'''

python_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON, chunk_size=1500, chunk_overlap=0
)
python_docs = python_splitter.create_documents([python_text])
# [print(document.page_content + "\n\n===========\n\n") for document in python_docs]

# quit()

js_text = """
import { Document, BaseNode } from "../Node";
import { v4 as uuidv4 } from "uuid";
import { BaseRetriever } from "../Retriever";
import { ServiceContext } from "../ServiceContext";
import { StorageContext } from "../storage/StorageContext";
import { BaseDocumentStore } from "../storage/docStore/types";
import { VectorStore } from "../storage/vectorStore/types";
import { BaseIndexStore } from "../storage/indexStore/types";
import { BaseQueryEngine } from "../QueryEngine";
import { ResponseSynthesizer } from "../ResponseSynthesizer";

/**
 * The underlying structure of each index.
 */
export abstract class IndexStruct {
  indexId: string;
  summary?: string;

  constructor(indexId = uuidv4(), summary = undefined) {
    this.indexId = indexId;
    this.summary = summary;
  }

  toJson(): Record<string, unknown> {
    return {
      indexId: this.indexId,
      summary: this.summary,
    };
  }

  getSummary(): string {
    if (this.summary === undefined) {
      throw new Error("summary field of the index dict is not set");
    }
    return this.summary;
  }
}

export enum IndexStructType {
  SIMPLE_DICT = "simple_dict",
  LIST = "list",
}

export class IndexDict extends IndexStruct {
  nodesDict: Record<string, BaseNode> = {};
  docStore: Record<string, Document> = {}; // FIXME: this should be implemented in storageContext
  type: IndexStructType = IndexStructType.SIMPLE_DICT;

  getSummary(): string {
    if (this.summary === undefined) {
      throw new Error("summary field of the index dict is not set");
    }
    return this.summary;
  }

  addNode(node: BaseNode, textId?: string) {
    const vectorId = textId ?? node.id_;
    this.nodesDict[vectorId] = node;
  }

  toJson(): Record<string, unknown> {
    return {
      ...super.toJson(),
      nodesDict: this.nodesDict,
      type: this.type,
    };
  }
}

export function jsonToIndexStruct(json: any): IndexStruct {
  if (json.type === IndexStructType.LIST) {
    const indexList = new IndexList(json.indexId, json.summary);
    indexList.nodes = json.nodes;
    return indexList;
  } else if (json.type === IndexStructType.SIMPLE_DICT) {
    const indexDict = new IndexDict(json.indexId, json.summary);
    indexDict.nodesDict = json.nodesDict;
    return indexDict;
  } else {
    throw new Error(`Unknown index struct type: ${json.type}`);
  }
}

export class IndexList extends IndexStruct {
  nodes: string[] = [];
  type: IndexStructType = IndexStructType.LIST;

  addNode(node: BaseNode) {
    this.nodes.push(node.id_);
  }

  toJson(): Record<string, unknown> {
    return {
      ...super.toJson(),
      nodes: this.nodes,
      type: this.type,
    };
  }
}

export interface BaseIndexInit<T> {
  serviceContext: ServiceContext;
  storageContext: StorageContext;
  docStore: BaseDocumentStore;
  vectorStore?: VectorStore;
  indexStore?: BaseIndexStore;
  indexStruct: T;
}

/**
 * Indexes are the data structure that we store our nodes and embeddings in so
 * they can be retrieved for our queries.
 */
export abstract class BaseIndex<T> {
  serviceContext: ServiceContext;
  storageContext: StorageContext;
  docStore: BaseDocumentStore;
  vectorStore?: VectorStore;
  indexStore?: BaseIndexStore;
  indexStruct: T;

  constructor(init: BaseIndexInit<T>) {
    this.serviceContext = init.serviceContext;
    this.storageContext = init.storageContext;
    this.docStore = init.docStore;
    this.vectorStore = init.vectorStore;
    this.indexStore = init.indexStore;
    this.indexStruct = init.indexStruct;
  }

  /**
   * Create a new retriever from the index.
   * @param retrieverOptions
   */
  abstract asRetriever(options?: any): BaseRetriever;

  /**
   * Create a new query engine from the index. It will also create a retriever
   * and response synthezier if they are not provided.
   * @param options you can supply your own custom Retriever and ResponseSynthesizer
   */
  abstract asQueryEngine(options?: {
    retriever?: BaseRetriever;
    responseSynthesizer?: ResponseSynthesizer;
  }): BaseQueryEngine;
}

export interface VectorIndexOptions {
  nodes?: BaseNode[];
  indexStruct?: IndexDict;
  indexId?: string;
  serviceContext?: ServiceContext;
  storageContext?: StorageContext;
}

export interface VectorIndexConstructorProps extends BaseIndexInit<IndexDict> {
  vectorStore: VectorStore;
}
"""

js_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.JS, chunk_size=1500, chunk_overlap=0
)
js_docs = js_splitter.create_documents([js_text])
[print(document.page_content + "\n\n========\n") for document in js_docs]
