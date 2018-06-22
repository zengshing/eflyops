# coding: utf-8
from celery import shared_task, subtask
from django.core.cache import cache
from django.utils.translation import ugettext as _

from common.utils import get_logger, get_object_or_none
from .models import Task
from . import const 

logger = get_logger(__file__)


def rerun_task():
    pass


@shared_task
def run_ansible_task(task_id, callback=None, **kwargs):
    """
    :param task_id: is the tasks serialized data
    :param callback: callback function name
    :return:
    """

    task = get_object_or_none(Task, id=task_id)
    if task:
        result = task.run()
        if callback is not None:
            subtask(callback).delay(result, task_name=task.name)
        return result
    else:
        logger.error("No task found")


@shared_task
def hello(name, callback=None):
    print("Hello {}".format(name))
    if callback is not None:
        subtask(callback).delay("Guahongwei")


@shared_task
def hello_callback(result):
    print(result)
    print("Hello callback")

@shared_task
def execute_shell_command_util(assets, tasks, tasktype='command', task_name=None, module=None):
    """
    Using ansible api to execute shell command in remote machines
    :param assets:  asset seq
    :param task_name: task_name running
    :param command: shell command to execute
    :param module: ansible shell module, by default is shell
    :return: result summary ['contacted': {}, 'dark': {}]
    """
    from ops.utils import update_or_create_ansible_task
    if task_name is None:
        # task_name = _("Update some assets hardware info")
        task_name = _("test execute shell command")
    hostname_list = [asset.hostname for asset in assets if asset.is_active and asset.is_unixlike()]
    if not hostname_list:
        logger.info("Not hosts get, may be asset is not active or not unixlike platform")
        return {}
    task, created = update_or_create_ansible_task(
        task_name, hosts=hostname_list, tasks=tasks, tasktype=tasktype, pattern='all',
        options=const.TASK_OPTIONS, run_as_admin=True, created_by='System',
    )
    result = task.run()
    return result

@shared_task
def test_ls_root(asset):
    task_name = _("ls root dictory")
    command = 'ls /root'
    return execute_shell_command_util([asset], [command], task_name=task_name)
