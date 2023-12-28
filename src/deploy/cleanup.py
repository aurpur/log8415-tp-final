#!/usr/bin/env python3
import logging

import backoff
from botocore.exceptions import ClientError
from deploy.config import AWS_RES_NAME, LOG_LEVEL
from deploy.utils import ec2_res, get_error_code

logger = logging.getLogger(__name__)


def giveup(e: Exception):
    return not (
        isinstance(e, ClientError)
        and (get_error_code(e) in ("DependencyViolation", "ResourceInUse"))
    )


def terminate_ec2():
    instances = ec2_res.instances.filter(
        Filters=[
            {"Name": "tag:Name", "Values": [AWS_RES_NAME]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopped"],
            },
        ]
    )
    for inst in instances:
        logger.info(f"Terminating instance: {inst}")
        inst.terminate()


@backoff.on_exception(backoff.constant, ClientError, giveup=giveup)
def delete_security_groups():
    try:
        security_groups = ec2_res.security_groups.filter(
            Filters=[{"Name": "tag:Name", "Values": [AWS_RES_NAME]}]
        )
        for sg in security_groups:
            logger.info(f"Deleting security group: {sg}")
            sg.delete()
    except ClientError as e:
        error_code = get_error_code(e)
        if error_code != "InvalidGroup.NotFound":
            raise


def main():
    terminate_ec2()
    delete_security_groups()


if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    main()
