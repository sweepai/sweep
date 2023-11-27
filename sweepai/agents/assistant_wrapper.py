from loguru import logger

from sweepai.config.server import OPENAI_API_KEY
from sweepai.utils.openai_proxy import OpenAI

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY environment variable not set.")
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

import json
import os


from sweepai.services.escrow_handler import bulk_payout, create_job, handle_results


def setup_module(module):
    os.environ["PAYLOAD_SAMPLE"] = "test_manifest.json"
    os.environ["RESULT_SAMPLE"] = "test_results.json"

    # Populate 'test_manifest.json' with mock data required for testing.
    with open("test_manifest.json", "w") as f:
        mock_data = {
            "Annotations": {
                "images": [
                    {"id": 1, "file_name": "sample1.jpg"},
                    {"id": 2, "file_name": "sample2.jpg"},
                ],
                "annotations": [
                    {
                        "id": 125686,
                        "image_id": 1,
                        "annotator_email": "sergey@hmt.ai",
                        "label": "Car",
                        "segmentation_url": "https://s3.hmt.aws.com/0xerdsdasd/annotation/125686/2254",
                        "bbox": [19.23, 383.18, 314.5, 244.46],
                        "acceptance_rate": 0.0,
                    },
                    {
                        "id": 125686,
                        "image_id": 2,
                        "annotator_email": "sergey@hmt.ai",
                        "label": "Car",
                        "segmentation_url": "https://s3.hmt.aws.com/0xerdsdasd/annotation/125686/2254",
                        "bbox": [19.23, 383.18, 314.5, 244.46],
                        "acceptance_rate": 1.0,
                    },
                ],
            }
        }
        json.dump(mock_data, f)

    # Populate 'test_results.json' with mock data required for testing.
    with open("test_results.json", "w") as f:
        mock_data = {"Annotations": {"images": [{}, {}]}}
        json.dump(mock_data, f)


def teardown_module(module):
    # Cleanup after tests
    os.remove("test_manifest.json")
    os.remove("test_results.json")


def test_escrow_handler():
    if not OPENAI_API_KEY:
        logger.warning(
            "Skipping test_escrow_handler because OPENAI_API_KEY is not set."
        )
        return

    escrow_address = ""
    escrow_address = create_job()

    assert escrow_address != ""

    result_files = ""
    result_files = handle_results(escrow_address)

    assert "url" in result_files and "hash" in result_files
    assert result_files["url"] != "" and result_files["hash"] != ""

    url = result_files["url"]
    url_hash = result_files["hash"]

    payouts = [
        {
            # not needed for this test
            "mission_id": "1234567",
            # this is the address of the wallet that solved the job and is getting rewarded
            "public_address": "0x1e35c4D77771A118f7a96378cFb082Fe65da8e3c",
            # sample amount to be distributed, it matches the amount put in the escrow to close it
            "amount": 1,
        }
    ]

    receipients = []
    receipients.append(payouts[0]["public_address"])

    amounts = []
    amounts.append(payouts[0]["amount"])

    txId = 1

    result = ""
    result = bulk_payout(escrow_address, receipients, amounts, url, url_hash, txId)

    assert result == True
