import logging

from deploy.infra import launch_instances, setup_security_group
from deploy.provisioning import ScriptSetup, provision_instance
from deploy.config import MYSQL_ROOT_PASSWORD
from deploy.utils import get_default_vpc, wait_instance
from jinja2 import Environment, PackageLoader, select_autoescape

logger = logging.getLogger(__name__)

jinja_env = Environment(
    loader=PackageLoader("templates", ""), autoescape=select_autoescape()
)


def setup():
    vpc = get_default_vpc()
    sg = setup_security_group(
        vpc,
        [
            {
                "FromPort": 3306,
                "ToPort": 3306,
                "IpProtocol": "tcp",
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
        ],
    )

    instances = launch_instances([sg], ["t2.micro"])
    inst = instances[0]
    wait_instance(inst)

    # Install mysql server
    script_tpl = jinja_env.get_template("standalone.sh.j2")
    setup = ScriptSetup(script_tpl.render())
    provision_instance(inst, setup)

    #  Update root user
    script_tpl = jinja_env.get_template("mysql_root_setup.sh.j2")
    setup = ScriptSetup(script_tpl.render(mysql_root_password=MYSQL_ROOT_PASSWORD))
    provision_instance(inst, setup)

    # Load sakila database
    script_tpl = jinja_env.get_template("sakila.sh.j2")
    setup = ScriptSetup(script_tpl.render(mysql_root_password=MYSQL_ROOT_PASSWORD))
    provision_instance(inst, setup)

    logger.info(f"Public IP: {inst.public_ip_address}")

    return inst, sg
