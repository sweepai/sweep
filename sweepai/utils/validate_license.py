import requests
from sweepai.config.server import LICENSE_KEY

def validate_license():
    # Validate the license key
    if LICENSE_KEY is None:
        raise ValueError("No license key provided, please set the LICENSE_KEY environment variable or get a license key from https://deploy.sweep.dev.")
    response = requests.post(
        "https://api.keygen.sh/v1/accounts/sweep-dev/licenses/actions/validate-key",
        headers={
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        },
        json={"meta": {"key": LICENSE_KEY}},
    )
    if response.status_code != 200:
        raise ValueError("License key is invalid or expired. Please contact us at team@sweep.dev to upgrade to an enterprise license.")
    obj = response.json()
    if obj["data"]["attributes"]["status"] not in ("ACTIVE", "EXPIRING"):
        raise ValueError("License key is not active. Please contact us at team@sweep.dev to upgrade to an enterprise license.")
    return True

if __name__ == "__main__":
    assert validate_license()
