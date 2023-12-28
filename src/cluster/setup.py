import asyncio
import logging
from typing import TYPE_CHECKING

from deploy.infra import launch_instances, setup_security_group
from deploy.provisioning import ScriptSetup, provision_instance
from deploy.config import MYSQL_ROOT_PASSWORD
from deploy.utils import get_default_vpc, wait_instance
from jinja2 import Environment, PackageLoader, select_autoescape

if TYPE_CHECKING:
    from mypy_boto3_ec2.service_resource import Instance, Vpc

logger = logging.getLogger(__name__)

jinja_env = Environment(
    loader=PackageLoader("templates", ""), autoescape=select_autoescape()
)


async def setup():
    vpc = get_default_vpc()
    # Start the cluster
    _, _, sg = await make_cluster(vpc)
    # Allow mysqld access from anywhere
    sg.authorize_ingress(
        CidrIp="0.0.0.0/0", FromPort=3306, ToPort=3306, IpProtocol="tcp"
    )


async def make_cluster(vpc: "Vpc"):
    sg = setup_security_group(vpc)

    # Launch 4 instances
    instances = launch_instances([sg], ["t2.micro", "t2.micro", "t2.micro", "t2.micro"])
    async with asyncio.TaskGroup() as tg:
        for inst in instances:
            tg.create_task(asyncio.to_thread(wait_instance, inst))

    logger.info("Update security group")
    for inst in instances:
        # Allow everything between cluster instances
        sg.authorize_ingress(
            CidrIp=inst.private_ip_address + "/32",
            FromPort=-1,
            ToPort=-1,
            IpProtocol="-1",
        )

    manager = instances[0]
    workers = instances[1:]

    logger.info("Setup mysql-apt-config on all instances")
    script_tpl = jinja_env.get_template("mysql_apt_config.sh.j2")
    setup = ScriptSetup(script_tpl.render(server="mysql-cluster-8.0"))
    async with asyncio.TaskGroup() as tg:
        for inst in instances:
            tg.create_task(asyncio.to_thread(provision_instance, inst, setup))

    logger.info("Setup mgmd on manager")
    script_tpl = jinja_env.get_template("cluster_mgmd.sh.j2")
    setup = ScriptSetup(script_tpl.render(manager=manager, workers=workers))
    provision_instance(manager, setup)

    logger.info("Setup ndbd on worker instances")
    script_tpl = jinja_env.get_template("cluster_ndbd.sh.j2")
    setup = ScriptSetup(script_tpl.render(manager=manager))
    async with asyncio.TaskGroup() as tg:
        for worker in workers:
            tg.create_task(asyncio.to_thread(provision_instance, worker, setup))

    logger.info("Setup mysql on all instances")
    async with asyncio.TaskGroup() as tg:
        for inst in instances:
            tg.create_task(asyncio.to_thread(_setup_mysqld, inst, manager))

    logger.info(f"Manager: {manager.public_ip_address}")
    logger.info(f"Workers: {[w.public_ip_address for w in workers]}")

    return manager, workers, sg


def _setup_mysqld(instance: "Instance", manager: "Instance"):
    # Install cluster-compatible mysql-server
    script_tpl = jinja_env.get_template("cluster_mysql.sh.j2")
    setup = ScriptSetup(script_tpl.render(manager=manager))
    provision_instance(instance, setup)

    # Update root user
    script_tpl = jinja_env.get_template("mysql_root_setup.sh.j2")
    setup = ScriptSetup(script_tpl.render(mysql_root_password=MYSQL_ROOT_PASSWORD))
    provision_instance(instance, setup)

    # Load sakila database
    # Sakila hardcodes InnoDB engine (!= NDBENGINE) hence it is not replicated
    # across the cluster. We load it on all instances.
    script_tpl = jinja_env.get_template("sakila.sh.j2")
    setup = ScriptSetup(script_tpl.render(mysql_root_password=MYSQL_ROOT_PASSWORD))
    provision_instance(instance, setup)
