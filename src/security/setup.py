import json
import logging
from importlib.resources import files
from typing import TYPE_CHECKING, Sequence

from cluster.setup import make_cluster
from deploy.infra import launch_instances, setup_security_group
from deploy.provisioning import ScriptSetup, provision_instance
from deploy.config import MYSQL_ROOT_PASSWORD
from deploy.utils import get_default_vpc, wait_instance
from jinja2 import Environment, PackageLoader, select_autoescape

import security.app

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Instance, SecurityGroup, Vpc

logger = logging.getLogger(__name__)

jinja_env = Environment(
    loader=PackageLoader("templates", ""), autoescape=select_autoescape()
)
apps_res = files(security.app)


async def setup():
    vpc = get_default_vpc()
    # Start the cluster
    manager, workers, internal_sg = await make_cluster(vpc)
    # Setup the proxy
    proxy, proxy_sg = await make_proxy(vpc, manager, workers, internal_sg)
    # Setup the gatekeeper (and trusted host)
    (gatekeeper, gatekeeper_sg), (trusted_host, _) = await make_gatekeeper(
        vpc, proxy, proxy_sg
    )
    # Allow gatekeeper access from any origin
    gatekeeper_sg.authorize_ingress(
        CidrIp="0.0.0.0/0", FromPort=3000, ToPort=3000, IpProtocol="tcp"
    )

    logger.info("Setup complete")
    logger.info(f"{manager.public_ip_address=}")
    for worker in workers:
        logger.info(f"{worker.public_ip_address=}")
    logger.info(f"{proxy.public_ip_address=}")
    logger.info(f"{trusted_host.public_ip_address=}")
    logger.info(f"{gatekeeper.public_ip_address=}")


async def make_proxy(
    vpc: "Vpc",
    manager: "Instance",
    workers: Sequence["Instance"],
    internal_sg: "SecurityGroup",
):
    logger.info("Setting up proxy")
    sg = setup_security_group(vpc)
    instances = launch_instances([sg], ["t2.large"])
    proxy = instances[0]
    wait_instance(proxy)

    # Allow proxy to access cluster mysqld
    internal_sg.authorize_ingress(
        CidrIp=proxy.private_ip_address + "/32",
        FromPort=3306,
        ToPort=3306,
        IpProtocol="tcp",
    )

    # Setup the Deno app
    script_tpl = jinja_env.get_template("pattern_deploy.sh.j2")
    main_ts = (apps_res / "proxy.ts").read_text()  # app script
    config = dict(
        manager=manager.private_ip_address,
        workers=[w.private_ip_address for w in workers],
        username="root",
        password=MYSQL_ROOT_PASSWORD,
        db="sakila",
    )  # app config
    config_json = json.dumps(config)
    setup = ScriptSetup(script_tpl.render(main_ts=main_ts, config_json=config_json))
    provision_instance(proxy, setup)

    return proxy, sg


async def make_gatekeeper(vpc: "Vpc", proxy: "Instance", proxy_sg: "SecurityGroup"):
    logger.info("Setting up trusted host")
    trusted_host_sg = setup_security_group(vpc)
    instances = launch_instances([trusted_host_sg], ["t2.large"])
    trusted_host = instances[0]
    wait_instance(trusted_host)

    # Allow trusted host to access proxy
    proxy_sg.authorize_ingress(
        CidrIp=trusted_host.private_ip_address + "/32",
        FromPort=9000,
        ToPort=9000,
        IpProtocol="tcp",
    )

    # Setup the Trusted Host Deno app
    script_tpl = jinja_env.get_template("pattern_deploy.sh.j2")
    main_ts = (apps_res / "trusted.ts").read_text()  # app script
    config = dict(
        proxy=f"http://{proxy.private_ip_address}:9000",
    )  # app config
    config_json = json.dumps(config)
    setup = ScriptSetup(script_tpl.render(main_ts=main_ts, config_json=config_json))
    provision_instance(trusted_host, setup)

    logger.info("Setting up gatekeeper")
    gatekeeper_sg = setup_security_group(vpc)
    instances = launch_instances([gatekeeper_sg], ["t2.large"])
    gatekeeper = instances[0]
    wait_instance(gatekeeper)

    # Allow gatekeeper to access trusted host
    trusted_host_sg.authorize_ingress(
        CidrIp=gatekeeper.private_ip_address + "/32",
        FromPort=8000,
        ToPort=8000,
        IpProtocol="tcp",
    )

    # Setup the Gatekeeper Deno app
    script_tpl = jinja_env.get_template("pattern_deploy.sh.j2")
    main_ts = (apps_res / "gatekeeper.ts").read_text()  # app script
    config = dict(
        trusted=f"http://{trusted_host.private_ip_address}:8000",
    )  # app config
    config_json = json.dumps(config)
    setup = ScriptSetup(script_tpl.render(main_ts=main_ts, config_json=config_json))
    provision_instance(gatekeeper, setup)

    return (gatekeeper, gatekeeper_sg), (trusted_host, trusted_host_sg)
